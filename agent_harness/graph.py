from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TypedDict, Any

from langgraph.graph import StateGraph, START, END

from agent_harness.config import Settings
from agent_harness.llm import PlannerLLM
from agent_harness.sandbox import create_sandbox, cleanup_sandbox
from agent_harness.tools.jira import JiraClient
from agent_harness.tools.github import GitHubClient, git_prepare_patch, git_push


class AgentState(TypedDict, total=False):
    issue_key: str
    dry_run: bool
    repo_path: Optional[str]
    # fetched from Jira
    issue_summary: str
    issue_description: str
    # outputs
    plan_markdown: str
    pr_url: Optional[str]
    notes: str


def build_graph(settings: Settings):
    jira = JiraClient.from_settings(settings)
    planner = PlannerLLM(settings)

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
        res = planner.make_plan(state["issue_key"], state.get("issue_summary",""), state.get("issue_description",""))
        return {"plan_markdown": res.plan_markdown, "notes": f"confidence={res.confidence}"}

    def comment_plan(state: AgentState) -> dict:
        body = f"""Plan proposé par l'agent (dry-run={state.get('dry_run', True)})

{state.get('plan_markdown','')}

_(notes: {state.get('notes','')})_
"""
        jira.add_comment(state["issue_key"], body)
        return {}

    def implement_and_pr(state: AgentState) -> dict:
        # implémentation volontairement simple (starter):
        # - écrit un fichier de notes sous /ai/ISSUE.md
        # - commit + push
        # - ouvre une PR
        if not state.get("repo_path"):
            raise RuntimeError("--repo-path requis en mode action")

        repo_path = state["repo_path"]
        issue_key = state["issue_key"]
        branch = f"ai/{issue_key.lower()}"
        commit_msg = f"AI: scaffold for {issue_key}"
        file_rel = f"ai/{issue_key}.md"
        content = f"""# {issue_key}

## Plan
{state.get('plan_markdown','')}

## Notes
Généré automatiquement par un starter LangGraph. À remplacer par du vrai code/tests.
"""
        from pathlib import Path
        git_prepare_patch(Path(repo_path), branch=branch, message=commit_msg, file_relpath=file_rel, content=content)
        git_push(Path(repo_path), branch=branch)

        gh = GitHubClient.from_settings(settings)
        pr = gh.create_pull_request(
            head=branch,
            base="main",
            title=f"{issue_key}: plan + scaffold (AI)",
            body=state.get("plan_markdown","")[:6000],
        )
        return {"pr_url": pr.get("html_url")}

    def comment_pr(state: AgentState) -> dict:
        pr_url = state.get("pr_url")
        body = f"""J'ai ouvert une PR: {pr_url}

Plan:
{state.get('plan_markdown','')}
"""
        jira.add_comment(state["issue_key"], body)
        return {}

    def route_after_plan(state: AgentState) -> str:
        return "comment_plan" if state.get("dry_run", True) else "implement_and_pr"

    g = StateGraph(AgentState)
    g.add_node("load_issue", load_issue)
    g.add_node("make_plan", make_plan)
    g.add_node("comment_plan", comment_plan)
    g.add_node("implement_and_pr", implement_and_pr)
    g.add_node("comment_pr", comment_pr)

    g.add_edge(START, "load_issue")
    g.add_edge("load_issue", "make_plan")
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
