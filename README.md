# LangGraph Jira→PR Minimal Agent Harness (Python)

Ce repo est un **starter minimal** (pas une usine à gaz) pour un agent unique basé sur **LangGraph** qui peut :
- lire un ticket Jira
- produire un plan (LLM ou mode "mock" si pas de clé)
- (optionnel) créer une branche + patch simple dans une sandbox
- ouvrir une PR GitHub
- commenter le ticket Jira avec le plan / lien PR

⚠️ Par défaut le projet tourne en **dry-run** : il ne modifie rien tant que tu ne l'actives pas explicitement.

## 1) Pré-requis
- Python 3.10+
- (optionnel) Git installé si tu veux le mode patch/PR
- Accès Jira (Cloud) et GitHub (token)

## 2) Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 3) Configuration

Copie `.env.example` vers `.env` et remplis ce qui est utile :

```bash
cp .env.example .env
```

### Variables principales
- `JIRA_BASE_URL` ex: `https://ton-org.atlassian.net`
- `JIRA_EMAIL` + `JIRA_API_TOKEN` (Jira Cloud)
- `JIRA_PROJECT_KEY` (optionnel, utile pour créer des tickets)
- `GITHUB_TOKEN`
- `GITHUB_REPO` ex: `org/repo`
- `OPENAI_API_KEY` (optionnel)

## 4) Lancer l'agent

### Dry-run (recommandé au début)
```bash
python3 -m agent_harness.run --issue CARDS-123 --dry-run
```

### Mode "action" (écrit un patch simple + PR)
```bash
python -m agent_harness.run --issue CARDS-123 --repo-path /chemin/vers/ton/repo --action
```

## 5) Ce que fait réellement ce starter
- Il ne prétend pas être Devin.
- Il te donne un squelette propre :
  - **LangGraph** pour l'orchestration
  - des **tools** Jira/GitHub isolés
  - une "sandbox" basique (répertoire de travail) pour préparer un patch

Tu pourras ensuite :
- brancher ton CI (GitHub Actions / Jenkins / GitLab CI)
- ajouter des "guardrails" (allowlist d'actions, limites, approvals)
- remplacer le "patch simple" par un vrai boucle code→tests→fix

## Structure

```
agent_harness/
  graph.py            # définition du graph LangGraph
  run.py              # CLI
  config.py           # chargement .env
  llm.py              # wrapper LLM (OpenAI optionnel) + mode mock
  tools/
    jira.py           # API Jira (read/comment/create/update)
    github.py         # API GitHub (create PR) + helpers git
  sandbox.py          # workspace éphémère
```

## Notes sécurité (à garder)
- Donne au token Jira/GitHub **les droits minimum**.
- Garde le mode **dry-run** par défaut.
- Logue toutes les actions (tool calls) et garde un run_id.
