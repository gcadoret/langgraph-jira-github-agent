from __future__ import annotations

import argparse
import json
from agent_harness.config import get_settings
from agent_harness.graph import build_graph


def main():
    p = argparse.ArgumentParser(description="LangGraph minimal agent: Jira -> plan -> (optional) PR -> comment")
    p.add_argument("--issue", required=True, help="Clé Jira (ex: CARDS-123)")
    p.add_argument("--dry-run", action="store_true", help="Ne fait que commenter le plan sur Jira")
    p.add_argument("--action", action="store_true", help="Autorise création branche/commit/push/PR")
    p.add_argument("--repo-path", default=None, help="Chemin local du repo git (requis si --action)")
    args = p.parse_args()

    settings = get_settings()
    repo_path = args.repo_path or settings.default_repo_path

    # Priorité: flags CLI
    dry_run = True
    if args.action:
        dry_run = False
    if args.dry_run:
        dry_run = True
    if not dry_run and not repo_path:
        raise SystemExit("--repo-path requis en mode --action")

    mode = "dry-run" if dry_run else "action"
    if settings.verbose_logs:
        print(
            f"[agent] start: issue={args.issue}, mode={mode}, repo_path={repo_path or '(none)'}",
            flush=True,
        )

    graph = build_graph(settings)
    initial_state = {
        "issue_key": args.issue,
        "dry_run": dry_run,
        "repo_path": repo_path,
    }
    result = graph.invoke(initial_state)
    if settings.verbose_logs:
        print("[agent] done: graph execution completed", flush=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
