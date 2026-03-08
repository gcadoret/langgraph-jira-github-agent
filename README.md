# LangGraph Jira→PR Minimal Agent Harness (Python)

This repository is a **minimal starter** (not a heavy-duty framework) for a single agent based on **LangGraph** that can:
- Read a Jira ticket
- Produce a plan (routed to an advanced LLM, or deterministic mock mode if no key is provided)
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
- `DEFAULT_REPO_PATH` optional local repo path used when `--repo-path` is omitted
- `ADVANCED_PROVIDER` ex: `openai` or `gemini`
- `ADVANCED_API_KEY` for the advanced model (optional, planning falls back to a deterministic mock if absent)
- `ADVANCED_MODEL_NAME` ex: `gpt-4.1-mini`
- `ADVANCED_BASE_URL` optional override for provider-specific endpoints
- `OLLAMA_BASE_URL` ex: `http://localhost:11434`
- `OLLAMA_MODEL` ex: `llama3.1:8b`
- `MAX_REVIEW_ITERATIONS` max revision loops for executor/reviewer in action mode
- `PROMPTS_DIR` optional directory override for markdown-based validation/review profiles

For backward compatibility, `OPENAI_API_KEY` is still accepted as a fallback, but `ADVANCED_API_KEY` is the preferred name.

## 4) Hybrid LLM Routing

The project now uses an explicit `TaskType` enum and a small router instead of ad-hoc model selection.

### Task routing
- `PLANNING` -> `ADVANCED`
- `REASONING` -> `ADVANCED`
- `CRITIQUE` -> `ADVANCED`
- `JIRA_DRAFTING` -> `LOCAL`
- `SUMMARIZATION` -> `LOCAL`
- `FIELD_EXTRACTION` -> `LOCAL`
- `FORMAT_TRANSFORMATION` -> `LOCAL`
- `TOOL_SUPPORT` -> `LOCAL`

### Components
- `agent_harness/router.py`: explicit task-to-model mapping
- `agent_harness/advanced_model.py`: advanced provider wrapper (`openai` or `gemini`)
- `agent_harness/code_executor.py`: targeted code-edit executor for action mode
- `agent_harness/ollama_client.py`: lightweight Ollama HTTP wrapper using `requests`
- `agent_harness/repo_context.py`: cached repository context builder for planning
- `agent_harness/reviewer.py`: review/critique agent for implementation feedback
- `agent_harness/validators.py`: markdown-driven validation abstraction
- `agent_harness/prompts/validation/*.md`: validation profiles (repo detection, commands, blocking severities)
- `agent_harness/prompts/review/default.md`: reviewer prompt and excerpt policy
- `agent_harness/llm.py`: routed LLM entrypoint used by the graph

Today, the LangGraph planning node uses `TaskType.PLANNING`, so planning always goes through the advanced route. When `--repo-path` is provided, the graph also loads a cached repository context and injects a targeted summary/snippets into the planning prompt. Operational local tasks are ready to use for future nodes such as Jira drafting or extraction.
In `--action` mode, the graph now chains three intelligent agents: planner, executor, reviewer. The reviewer combines markdown-driven validation policies with an LLM critique, and the graph retries bounded revisions before commit/PR.

## 4.1) Prompt-Driven Validation Profiles

Validation and review rules are no longer meant to live primarily in Python classes. The project loads markdown profiles from `agent_harness/prompts/` by default:

- `validation/*.md` selects a validator profile based on repo markers such as `pubspec.yaml`
- each validation profile defines command candidates and blocking severities
- `review/default.md` defines the reviewer system prompt, excerpt strategy, and review rules

Example `flutter.md` policy:
- detect a Flutter repo with `pubspec.yaml`
- try `flutter analyze`, then `dart analyze`
- block only on `error`
- keep `warning` and `info` as advisory findings

If you want to customize this without editing the package defaults, point `PROMPTS_DIR` to your own directory containing:

```text
<prompts-dir>/
  review/
    default.md
  validation/
    default.md
    flutter.md
    your_other_stack.md
```

### Advanced provider examples
- OpenAI: `ADVANCED_PROVIDER=openai`, `ADVANCED_API_KEY=...`, `ADVANCED_MODEL_NAME=gpt-4.1-mini`
- Gemini: `ADVANCED_PROVIDER=gemini`, `ADVANCED_API_KEY=...`, `ADVANCED_MODEL_NAME=gemini-2.5-pro`

For Gemini, the client applies bounded retries with exponential backoff on transient `429` and `5xx` responses.
If the advanced provider still fails after retries, planning falls back to the deterministic mock plan so the graph can keep running.

## 5) Running the Agent

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

If you always work on the same repository, you can set `DEFAULT_REPO_PATH` in `.env` and shorten the command to:

```bash
python3 -m agent_harness.run --issue <JIRA_KEY> --action
```

The CLI flag still has priority over the `.env` default.

## 6) What This Starter Actually Does
- It doesn't claim to be Devin.
- It gives you a clean skeleton:
  - **LangGraph** for orchestration
  - Isolated Jira/GitHub **tools**
  - Explicit LLM routing by task type
  - A deterministic fallback when no advanced model is configured

You can then:
- Connect it to your CI (GitHub Actions / Jenkins / GitLab CI)
- Add "guardrails" (action allowlists, limits, approvals)
- Replace the "simple patch" with a real code→tests→fix loop

## Structure

```
agent_harness/
  advanced_model.py   # Advanced model wrapper
  graph.py            # LangGraph graph definition
  run.py              # CLI entrypoint
  config.py           # .env loader
  llm.py              # Routed LLM entrypoint + planner wrapper
  ollama_client.py    # Ollama HTTP wrapper
  prompt_store.py     # Markdown prompt/profile loader
  prompts/            # Built-in review and validation profiles
  router.py           # TaskType -> model routing
  task_types.py       # Explicit task categories
  tools/
    jira.py           # Jira API (read/comment/create/update)
    github.py         # GitHub API (create PR) + git helpers
  sandbox.py          # Ephemeral workspace
tests/
  test_code_executor.py # Lightweight implementation executor coverage
  test_repo_context.py # Lightweight cached repo-context coverage
  test_router.py      # Lightweight router coverage
```

## 7) Testing

Run the lightweight router tests with:

```bash
python3 -m unittest discover -s tests
```

## Security Notes (to keep in mind)
- Give the Jira/GitHub token **minimum required permissions**.
- Keep **dry-run** mode as the default.
- Log all actions (tool calls) and keep a run_id.
