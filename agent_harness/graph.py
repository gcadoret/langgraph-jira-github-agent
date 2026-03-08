from __future__ import annotations

from typing import Optional, TypedDict, Any

from langgraph.graph import StateGraph, START, END

from agent_harness.code_executor import CodeExecutor
from agent_harness.config import Settings
from agent_harness.llm import PlannerLLM
from agent_harness.repo_context import RepoContextBuilder
from agent_harness.reviewer import CodeReviewer
from agent_harness.tools.jira import JiraClient
from agent_harness.tools.github import GitHubClient, git_add_and_commit, git_changed_files, git_checkout_branch, git_push
from agent_harness.validators import ProjectValidatorFactory


class AgentState(TypedDict, total=False):
    issue_key: str
    dry_run: bool
    repo_path: Optional[str]
    # fetched from Jira
    issue_summary: str
    issue_description: str
    repo_context: str
    repo_context_source: str
    # outputs
    plan_markdown: str
    plan_task_type: str
    plan_model_choice: str
    plan_model_name: str
    execution_summary: str
    modified_files: list[str]
    review_summary: str
    pr_url: Optional[str]
    notes: str


def build_graph(settings: Settings):
    jira = JiraClient.from_settings(settings)
    repo_context_builder = RepoContextBuilder()
    planner = PlannerLLM(settings)
    code_executor = CodeExecutor(settings, repo_context_builder=repo_context_builder)
    reviewer = CodeReviewer(settings)

    def load_issue(state: AgentState) -> dict:
        issue_key = state["issue_key"]
        issue = jira.get_issue(issue_key)
        fields = issue.get("fields", {})
        summary = fields.get("summary") or ""
        # description Jira est souvent "ADF" (Atlassian Document Format) → on simplifie :
        desc = fields.get("description")
        if isinstance(desc, dict):
            # extraction ultra basique
            desc_text = _adf_to_text(desc)
        else:
            desc_text = str(desc or "")
        return {"issue_summary": summary, "issue_description": desc_text}

    def make_plan(state: AgentState) -> dict:
        res = planner.make_plan(
            state["issue_key"],
            state.get("issue_summary",""),
            state.get("issue_description",""),
            repo_context=state.get("repo_context", ""),
        )
        notes = (
            f"confidence={res.confidence}; "
            f"task_type={res.task_type.value}; "
            f"route={res.model_choice.value}; "
            f"model={res.model_name}; "
            f"mock={str(res.is_mock).lower()}"
        )
        if state.get("repo_context_source"):
            notes += f"; repo_context_source={state['repo_context_source']}"
        if res.fallback_reason:
            notes += f"; fallback_reason={res.fallback_reason}"
        return {
            "plan_markdown": res.plan_markdown,
            "plan_task_type": res.task_type.value,
            "plan_model_choice": res.model_choice.value,
            "plan_model_name": res.model_name,
            "notes": notes,
        }

    def load_repo_context(state: AgentState) -> dict:
        repo_path = state.get("repo_path")
        if not repo_path:
            return {"repo_context": "", "repo_context_source": "disabled"}

        issue_text = " ".join(
            part for part in (
                state.get("issue_key", ""),
                state.get("issue_summary", ""),
                state.get("issue_description", ""),
            )
            if part
        )
        context = repo_context_builder.build(repo_path=repo_path, issue_text=issue_text)
        return {
            "repo_context": context.summary_markdown,
            "repo_context_source": context.source,
        }

    def comment_plan(state: AgentState) -> dict:
        body = f"""Plan proposé par l'agent (dry-run={state.get('dry_run', True)})

{state.get('plan_markdown','')}

_(notes: {state.get('notes','')})_
"""
        jira.add_comment(state["issue_key"], body)
        return {}

    def implement_and_pr(state: AgentState) -> dict:
        if not state.get("repo_path"):
            raise RuntimeError("--repo-path requis en mode action")

        repo_path = state["repo_path"]
        issue_key = state["issue_key"]
        branch = f"fix/{issue_key.lower()}"
        from pathlib import Path
        repo_root = Path(repo_path)
        git_checkout_branch(repo_root, branch=branch)
        validator = ProjectValidatorFactory.for_repo(repo_path, settings=settings)
        review_feedback = ""
        preferred_files: list[str] = []
        execution_summary = ""
        review_summary = ""

        for attempt in range(1, settings.max_review_iterations + 1):
            implementation = code_executor.propose_changes(
                issue_key=issue_key,
                issue_summary=state.get("issue_summary", ""),
                issue_description=state.get("issue_description", ""),
                plan_markdown=state.get("plan_markdown", ""),
                repo_path=repo_path,
                review_feedback=review_feedback,
                preferred_files=preferred_files,
            )
            if not implementation.updated_files:
                review_feedback = "\n".join(
                    part for part in (
                        review_feedback,
                        implementation.summary,
                        implementation.raw_response[:1000],
                    )
                    if part
                )
                if attempt < settings.max_review_iterations:
                    continue
                selected_files = ", ".join(implementation.selected_files) or "(none)"
                raise RuntimeError(
                    "No code changes were proposed for action mode. "
                    f"selected_files={selected_files}; "
                    f"implementation_summary={implementation.summary}; "
                    f"raw_response={implementation.raw_response[:500]}"
                )

            modified_files = code_executor.apply_changes(repo_path, implementation.updated_files)
            changed_files = git_changed_files(repo_root)
            if not modified_files and not changed_files:
                raise RuntimeError("Code executor produced no effective file changes")

            validation = validator.validate(repo_path)
            review = reviewer.review(
                issue_key=issue_key,
                issue_summary=state.get("issue_summary", ""),
                plan_markdown=state.get("plan_markdown", ""),
                implementation_summary=implementation.summary,
                repo_path=repo_path,
                modified_files=changed_files or modified_files,
                validation=validation,
            )
            execution_summary = implementation.summary
            review_summary = review.summary
            if review.approved and validation.passed:
                final_files = changed_files or modified_files
                if not final_files:
                    raise RuntimeError("No changed files available after approved review")
                commit_msg = f"AI: implement {issue_key}"
                git_add_and_commit(repo_root, final_files, commit_msg)
                git_push(repo_root, branch=branch)

                gh = GitHubClient.from_settings(settings)
                changed_files_markdown = "\n".join(f"- {path}" for path in final_files)
                pr = gh.create_pull_request(
                    head=branch,
                    base="main",
                    title=f"{issue_key}: automated implementation",
                    body=f"""{state.get("plan_markdown","")[:5000]}

## Implémentation
{implementation.summary}

## Review
{review.summary}

## Fichiers modifiés
{changed_files_markdown}
""",
                )
                return {
                    "pr_url": pr.get("html_url"),
                    "execution_summary": execution_summary,
                    "review_summary": review_summary,
                    "modified_files": final_files,
                }

            preferred_files = list(dict.fromkeys((changed_files or modified_files) + implementation.selected_files))
            review_feedback = "\n".join(
                part for part in (
                    review.summary,
                    review.feedback,
                    validation.summary,
                    validation.output[:2000],
                )
                if part
            )

        raise RuntimeError(
            "Reviewer rejected the implementation after max iterations. "
            f"last_execution_summary={execution_summary}; "
            f"last_review_summary={review_summary}; "
            f"last_feedback={review_feedback[:800]}"
        )

    def comment_pr(state: AgentState) -> dict:
        pr_url = state.get("pr_url")
        modified_files = "\n".join(f"- {path}" for path in state.get("modified_files", []))
        body = f"""J'ai ouvert une PR: {pr_url}

Plan:
{state.get('plan_markdown','')}

Implémentation:
{state.get('execution_summary','')}

Review:
{state.get('review_summary','')}

Fichiers modifiés:
{modified_files or '- (non renseigné)'}
"""
        jira.add_comment(state["issue_key"], body)
        return {}

    def route_after_plan(state: AgentState) -> str:
        return "comment_plan" if state.get("dry_run", True) else "implement_and_pr"

    g = StateGraph(AgentState)
    g.add_node("load_issue", load_issue)
    g.add_node("load_repo_context", load_repo_context)
    g.add_node("make_plan", make_plan)
    g.add_node("comment_plan", comment_plan)
    g.add_node("implement_and_pr", implement_and_pr)
    g.add_node("comment_pr", comment_pr)

    g.add_edge(START, "load_issue")
    g.add_edge("load_issue", "load_repo_context")
    g.add_edge("load_repo_context", "make_plan")
    g.add_conditional_edges("make_plan", route_after_plan, {
        "comment_plan": "comment_plan",
        "implement_and_pr": "implement_and_pr",
    })
    g.add_edge("comment_plan", END)
    g.add_edge("implement_and_pr", "comment_pr")
    g.add_edge("comment_pr", END)

    return g.compile()


def _adf_to_text(adf: dict) -> str:
    # extraction minimale ADF → texte (suffisant pour starter)
    out: list[str] = []

    def walk(node: Any):
        if isinstance(node, dict):
            t = node.get("type")
            if t == "text" and isinstance(node.get("text"), str):
                out.append(node["text"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(adf)
    return "".join(out).strip()
