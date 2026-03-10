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
    validation_summary: str
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

    def log_step(message: str) -> None:
        if settings.verbose_logs:
            print(f"[agent] {message}", flush=True)

    def load_issue(state: AgentState) -> dict:
        issue_key = state["issue_key"]
        log_step(f"load_issue: fetching Jira issue {issue_key}")
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
        log_step(f"load_issue: summary loaded ({len(summary)} chars), description extracted ({len(desc_text)} chars)")
        return {"issue_summary": summary, "issue_description": desc_text}

    def make_plan(state: AgentState) -> dict:
        log_step("make_plan: generating technical plan")
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
        log_step(
            "make_plan: completed "
            f"(route={res.model_choice.value}, model={res.model_name}, mock={str(res.is_mock).lower()})"
        )
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
            log_step("load_repo_context: disabled (no repo path)")
            return {"repo_context": "", "repo_context_source": "disabled"}

        log_step(f"load_repo_context: building targeted repo context from {repo_path}")
        issue_text = " ".join(
            part for part in (
                state.get("issue_key", ""),
                state.get("issue_summary", ""),
                state.get("issue_description", ""),
            )
            if part
        )
        context = repo_context_builder.build(repo_path=repo_path, issue_text=issue_text)
        log_step(f"load_repo_context: completed (source={context.source})")
        return {
            "repo_context": context.summary_markdown,
            "repo_context_source": context.source,
        }

    def comment_plan(state: AgentState) -> dict:
        log_step(f"comment_plan: posting plan comment to Jira for {state['issue_key']}")
        body = f"""Plan proposé par l'agent (dry-run={state.get('dry_run', True)})

{state.get('plan_markdown','')}

_(notes: {state.get('notes','')})_
"""
        jira.add_comment(state["issue_key"], body)
        log_step("comment_plan: comment posted")
        return {}

    def implement_and_pr(state: AgentState) -> dict:
        if not state.get("repo_path"):
            raise RuntimeError("--repo-path requis en mode action")

        repo_path = state["repo_path"]
        issue_key = state["issue_key"]
        branch = f"fix/{issue_key.lower()}"
        from pathlib import Path
        repo_root = Path(repo_path)
        log_step(f"implement_and_pr: checkout branch {branch}")
        git_checkout_branch(repo_root, branch=branch)
        validator = ProjectValidatorFactory.for_repo(repo_path, settings=settings)
        log_step(f"implement_and_pr: validator selected ({validator.name})")
        review_feedback = ""
        preferred_files: list[str] = []
        execution_summary = ""
        validation_summary = ""
        review_summary = ""

        for attempt in range(1, settings.max_review_iterations + 1):
            log_step(f"implement_and_pr: iteration {attempt}/{settings.max_review_iterations}")
            implementation = code_executor.propose_changes(
                issue_key=issue_key,
                issue_summary=state.get("issue_summary", ""),
                issue_description=state.get("issue_description", ""),
                plan_markdown=state.get("plan_markdown", ""),
                repo_path=repo_path,
                review_feedback=review_feedback,
                preferred_files=preferred_files,
            )
            selected_files = ", ".join(implementation.selected_files) or "(none)"
            log_step(f"implement_and_pr: proposed target files -> {selected_files}")
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
                    log_step("implement_and_pr: no code changes proposed, retrying with accumulated feedback")
                    continue
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
            log_step(
                "implement_and_pr: applied changes to "
                f"{', '.join(changed_files or modified_files)}"
            )

            validation = validator.validate(repo_path)
            log_step(
                "implement_and_pr: validation completed "
                f"(status={validation.status}, summary={validation.summary})"
            )
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
            validation_summary = review.validation_summary
            review_summary = review.summary
            log_step(
                "implement_and_pr: review completed "
                f"(approved={str(review.approved).lower()}, summary={review.summary})"
            )
            if review.approved and validation.passed:
                final_files = changed_files or modified_files
                if not final_files:
                    raise RuntimeError("No changed files available after approved review")
                commit_msg = f"AI: implement {issue_key}"
                log_step(f"implement_and_pr: committing changes ({commit_msg})")
                git_add_and_commit(repo_root, final_files, commit_msg)
                log_step(f"implement_and_pr: pushing branch {branch}")
                git_push(repo_root, branch=branch)

                gh = GitHubClient.from_settings(settings)
                changed_files_markdown = "\n".join(f"- {path}" for path in final_files)
                log_step("implement_and_pr: creating GitHub pull request")
                pr = gh.create_pull_request(
                    head=branch,
                    base="main",
                    title=f"{issue_key}: automated implementation",
                    body=f"""{state.get("plan_markdown","")[:5000]}

## Implémentation
{implementation.summary}

## Validation
{validation_summary}

## Review
{review.summary}

## Fichiers modifiés
{changed_files_markdown}
""",
                )
                log_step(f"implement_and_pr: pull request created ({pr.get('html_url')})")
                return {
                    "pr_url": pr.get("html_url"),
                    "execution_summary": execution_summary,
                    "validation_summary": validation_summary,
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
            log_step("implement_and_pr: change rejected, preparing next iteration")

        raise RuntimeError(
            "Reviewer rejected the implementation after max iterations. "
            f"last_execution_summary={execution_summary}; "
            f"last_review_summary={review_summary}; "
            f"last_feedback={review_feedback[:800]}"
        )

    def comment_pr(state: AgentState) -> dict:
        pr_url = state.get("pr_url")
        log_step(f"comment_pr: posting final Jira comment with PR {pr_url}")
        modified_files = "\n".join(f"- {path}" for path in state.get("modified_files", []))
        body = f"""J'ai ouvert une PR: {pr_url}

Plan:
{state.get('plan_markdown','')}

Implémentation:
{state.get('execution_summary','')}

Validation:
{state.get('validation_summary','')}

Review:
{state.get('review_summary','')}

Fichiers modifiés:
{modified_files or '- (non renseigné)'}
"""
        jira.add_comment(state["issue_key"], body)
        log_step("comment_pr: comment posted")
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
