# LangGraph Jira -> Repo Agent

Agent Python minimal basé sur **LangGraph** pour :

- lire un ticket Jira
- produire un plan technique
- charger un contexte repo ciblé
- proposer et appliquer des modifications de code
- valider puis reviewer les changements
- créer une branche, un commit, une PR GitHub
- commenter le ticket Jira

Le projet reste volontairement simple :

- orchestration via LangGraph
- routing explicite par `TaskType`
- profils de validation configurés en Markdown
- **dry-run par défaut**
- peu de dépendances

## Prérequis

- Python 3.10+
- Git
- accès Jira Cloud
- accès GitHub
- un provider `ADVANCED` configuré pour planning / implementation / critique
- optionnel : Ollama pour les tâches locales futures

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Configuration

Créer le fichier `.env` :

```bash
cp .env.example .env
```

Variables principales :

- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`
- `JIRA_PROJECT_KEY` optionnel
- `GITHUB_TOKEN`
- `GITHUB_REPO`
- `DEFAULT_REPO_PATH` chemin local par défaut si `--repo-path` est omis
- `ADVANCED_PROVIDER` ex: `openai` ou `gemini`
- `ADVANCED_API_KEY`
- `ADVANCED_MODEL_NAME`
- `ADVANCED_BASE_URL` optionnel
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `DRY_RUN`
- `MAX_REVIEW_ITERATIONS`
- `ENABLE_VALIDATION_SUMMARY`
- `PROMPTS_DIR` pour surcharger les profils Markdown intégrés

Compatibilité :

- `OPENAI_API_KEY` est encore accepté comme fallback de `ADVANCED_API_KEY`

## Routing LLM

Le routing est défini dans [router.py](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/router.py).

### Tâches `ADVANCED`

- `PLANNING`
- `IMPLEMENTATION`
- `REASONING`
- `CRITIQUE`

### Tâches `LOCAL`

- `JIRA_DRAFTING`
- `SUMMARIZATION`
- `FIELD_EXTRACTION`
- `FORMAT_TRANSFORMATION`
- `TOOL_SUPPORT`

Important :

- dans le flow principal actuel `--action`, le modèle local n’est pas requis
- la synthèse de validation est maintenant **déterministe en Python**, pas générée par un LLM

## Flux d’exécution

Le graphe principal est défini dans [graph.py](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/graph.py).

### Dry-run

1. lecture du ticket Jira
2. chargement optionnel du contexte repo
3. génération du plan
4. commentaire Jira avec le plan

### Action

1. lecture du ticket Jira
2. chargement du contexte repo
3. planning
4. création / checkout de branche
5. proposition de changements de code
6. application des changements
7. validation projet
8. review critique
9. boucle de révision bornée
10. commit, push, PR GitHub
11. commentaire Jira final

## Validation configurable par profils Markdown

Les règles de validation ne sont pas codées via des classes techno spécifiques.

Le moteur générique charge des profils depuis :

- [agent_harness/prompts/validation/default.md](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/prompts/validation/default.md)
- [agent_harness/prompts/validation/flutter.md](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/prompts/validation/flutter.md)

Chaque profil peut définir :

- `priority`
- `match_files`
- `command_candidates`
- `severity_patterns`
- `blocking_severities`
- `allow_nonzero_without_blockers`

Exemple Flutter :

- détection via `pubspec.yaml`
- tentative `flutter analyze`, puis `dart analyze`
- `error` bloquant
- `warning` et `info` non bloquants

Le moteur est dans [validators.py](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/validators.py).

## Reviewer

Le reviewer est dans [reviewer.py](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/reviewer.py).

Il combine :

- le résultat du validateur
- une synthèse déterministe optionnelle de validation
- le contenu des fichiers modifiés
- une critique `ADVANCED`

La synthèse déterministe est contrôlée par :

- `ENABLE_VALIDATION_SUMMARY=true|false`

Quand elle est activée, elle est persistée :

- dans l’état LangGraph
- dans le corps de la PR
- dans le commentaire Jira final

## Prompts Markdown

Les prompts et profils intégrés vivent dans :

- [agent_harness/prompts/review/default.md](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/prompts/review/default.md)
- [agent_harness/prompts/validation/](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/prompts/validation)

Si `PROMPTS_DIR` est défini, le projet charge les fichiers depuis ce dossier à la place.

Structure attendue :

```text
<PROMPTS_DIR>/
  review/
    default.md
  validation/
    default.md
    flutter.md
    ...
```

## Commandes

### Dry-run

```bash
python3 -m agent_harness.run --issue KAN-1 --dry-run
```

### Action avec repo explicite

```bash
python3 -m agent_harness.run --issue KAN-1 --repo-path /path/to/repo --action
```

### Action avec `DEFAULT_REPO_PATH`

```bash
python3 -m agent_harness.run --issue KAN-1 --action
```

Priorité :

- le flag CLI `--repo-path` écrase `DEFAULT_REPO_PATH`

## Structure

```text
agent_harness/
  advanced_model.py
  code_executor.py
  config.py
  graph.py
  llm.py
  ollama_client.py
  prompt_store.py
  repo_context.py
  reviewer.py
  router.py
  run.py
  task_types.py
  validators.py
  prompts/
    review/
    validation/
  tools/
    github.py
    jira.py
tests/
```

## Tests

```bash
python3 -m unittest discover -s tests
```

Vérification syntaxe :

```bash
python3 -m compileall agent_harness tests
```

## Notes de conception

- le projet n’essaie pas d’être un framework généraliste
- le comportement par défaut reste prudent
- la partie la plus configurable est la validation projet via Markdown
- les décisions de planning / implementation / critique restent routées vers le modèle `ADVANCED`

## Limites actuelles

- la qualité d’implémentation dépend encore fortement du modèle `ADVANCED`
- la boucle reviewer reste mono-agent côté critique finale
- les profils de validation sont simples mais explicites
- la stack LangChain / LangGraph peut être sensible aux versions Python les plus récentes
