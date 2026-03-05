# LangGraph Jira→PR Minimal Agent Harness (Python)

This repository is a **minimal starter** (not a heavy-duty framework) for a single agent based on **LangGraph** that can:
- Read a Jira ticket
- Produce a plan (using an LLM or in "mock" mode if no key is provided)
- (Optional) Create a branch + a simple patch in a sandbox
- Open a GitHub PR
- Comment on the Jira ticket with the plan / PR link

⚠️ By default, the project runs in **dry-run** mode: it does not modify anything until you explicitly enable it.

## 1) Prerequisites
- Python 3.10+
- (Optional) Git installed if you want to use the patch/PR mode
- Jira (Cloud) and GitHub (token) access

## 2) Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 3) Configuration

Copy `.env.example` to `.env` and fill in the necessary values:

```bash
cp .env.example .env
```

### Main variables
- `JIRA_BASE_URL` ex: `https://your-org.atlassian.net`
- `JIRA_EMAIL` + `JIRA_API_TOKEN` (Jira Cloud)
- `JIRA_PROJECT_KEY` (optional, useful for creating tickets)
- `GITHUB_TOKEN`
- `GITHUB_REPO` ex: `org/repo`
- `OPENAI_API_KEY` (optional)

## 4) Running the Agent

### Dry-run (recommended for starters)
```bash
python3 -m agent_harness.run --issue KAN-1 --dry-run
```
This command analyzes the specified Jira ticket (`--issue`) and posts an action plan as a comment, without making any code changes (no branch, commit, or Pull Request). This is the ideal mode for testing and validating the agent's plan.

### "Action" mode (writes a simple patch + PR)
```bash
python3 -m agent_harness.run --issue <JIRA_KEY> --repo-path /path/to/your/repo --action
```
This command enables the "action" mode. Unlike dry-run, the agent will actually perform Git operations:
1. It creates a new branch from the default branch of the specified repository (`--repo-path`).
2. It applies a simple code patch (in this starter, it's a basic modification for demonstration purposes).
3. It creates a commit and pushes the new branch to GitHub.
4. Finally, it opens a Pull Request and updates the Jira ticket with a link to it.

**Warning:** This mode actually modifies the Git repository. The path provided in `--repo-path` is mandatory.

## 5) What This Starter Actually Does
- It doesn't claim to be Devin.
- It gives you a clean skeleton:
  - **LangGraph** for orchestration
  - Isolated Jira/GitHub **tools**
  - A basic "sandbox" (working directory) to prepare a patch

You can then:
- Connect it to your CI (GitHub Actions / Jenkins / GitLab CI)
- Add "guardrails" (action allowlists, limits, approvals)
- Replace the "simple patch" with a real code→tests→fix loop

## Structure

```
agent_harness/
  graph.py            # LangGraph graph definition
  run.py              # CLI entrypoint
  config.py           # .env loader
  llm.py              # LLM wrapper (optional OpenAI) + mock mode
  tools/
    jira.py           # Jira API (read/comment/create/update)
    github.py         # GitHub API (create PR) + git helpers
  sandbox.py          # Ephemeral workspace
```

## Security Notes (to keep in mind)
- Give the Jira/GitHub token **minimum required permissions**.
- Keep **dry-run** mode as the default.
- Log all actions (tool calls) and keep a run_id.
