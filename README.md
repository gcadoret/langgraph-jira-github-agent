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
- `VERBOSE_LOGS`
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

#### Détail de chaque étape

1. `lecture du ticket Jira`

Le graphe appelle le client Jira pour récupérer le ticket demandé par `--issue`. Il lit principalement le `summary` et la `description`, puis convertit la description Jira en texte simple si elle est stockée au format ADF. Cette étape ne touche pas au repo local ; elle sert à construire le contexte minimal de travail partagé par la suite.

2. `chargement du contexte repo`

Si `repo_path` est disponible, l’agent construit un contexte repo ciblé via [repo_context.py](/Users/guillaumecadoret/devperso/LanggraphJiraGithubAgent/agent_harness/repo_context.py). Concrètement, il scanne la structure du dépôt, met en cache un index léger, puis sélectionne quelques fichiers et extraits pertinents par rapport au ticket. L’objectif n’est pas de donner tout le repo au modèle, mais un sous-ensemble utile pour le planning et l’implémentation.

3. `planning`

Le planner prend le ticket Jira et le contexte repo ciblé, puis génère un plan en Markdown. Ce plan sert de contrat de travail pour la suite : il donne l’intention, les zones de code probables, les tests à lancer et les risques à surveiller. Si le provider `ADVANCED` n’est pas disponible, le planner retombe sur un plan mock déterministe afin de ne pas bloquer tout le flow.

4. `création / checkout de branche`

En mode `--action`, le graphe prépare la branche de travail locale avant d’entrer dans la boucle d’implémentation. Cette étape se contente de faire le `checkout` d’une branche dédiée au ticket, pour isoler les changements générés et éviter de polluer la branche courante. Elle ne crée pas encore de commit.

5. `proposition de changements de code`

Le `CodeExecutor` choisit un ensemble limité de fichiers cibles à partir du ticket, du plan, du contexte repo, et éventuellement du feedback de la tentative précédente. Il envoie ensuite au modèle `ADVANCED` le ticket, le plan et le contenu de ces fichiers pour lui demander une proposition de modifications structurée. À cette étape, on est encore dans la phase “proposer”, pas “valider”.

6. `application des changements`

Si la proposition contient bien des fichiers mis à jour, l’executor écrit ces contenus dans le repo cible. L’agent compare ensuite l’état Git pour confirmer qu’il y a de vrais changements effectifs. Si la proposition ne produit aucun diff réel, l’itération est considérée comme un échec et le flow tente une nouvelle passe ou s’arrête selon le nombre d’essais restants.

7. `validation projet`

Une fois les fichiers écrits, l’agent lance un validateur projet choisi via les profils Markdown de validation. Le moteur détecte le type de repo à partir de marqueurs comme `pubspec.yaml`, sélectionne une commande candidate, exécute cette commande, puis parse les findings selon les patterns de sévérité du profil. Le résultat produit un `status`, un résumé, des compteurs `error/warning/info` et la sortie brute du validateur.

8. `review critique`

Le reviewer prend le plan, le résumé d’implémentation, le résultat de validation, une synthèse déterministe optionnelle de validation, et un extrait des fichiers modifiés. Il demande ensuite au modèle `ADVANCED` une critique structurée : changement approuvé ou non, résumé, et feedback actionnable pour l’itération suivante. Le reviewer est volontairement plus strict que l’executor : son rôle est de refuser un patch risqué, incomplet ou incohérent.

9. `boucle de révision bornée`

Si la validation ou le reviewer rejettent la proposition, le graphe ne commit pas immédiatement. Il repart dans une nouvelle itération avec le feedback accumulé, les fichiers déjà modifiés et le contexte précédent pour tenter une correction. Cette boucle est bornée par `MAX_REVIEW_ITERATIONS`, ce qui évite de tourner indéfiniment en cas de patch médiocre ou de ticket trop ambigu.

10. `commit, push, PR GitHub`

Une fois qu’une proposition est à la fois validée et approuvée, l’agent prépare le commit Git sur la branche dédiée, pousse la branche vers le remote, puis ouvre une Pull Request GitHub. Le corps de la PR inclut le plan, un résumé de l’implémentation, la synthèse de validation si activée, le résumé de review et la liste des fichiers modifiés. Tant que cette étape n’est pas atteinte, rien n’est poussé vers GitHub.

11. `commentaire Jira final`

Après création de la PR, l’agent poste un commentaire final sur le ticket Jira avec l’URL de la PR et un résumé compact de ce qui a été fait. Le commentaire reprend le plan, le résumé d’implémentation, le résumé de review, la synthèse de validation si elle est activée, et les fichiers modifiés. Cette étape sert surtout de trace opérationnelle pour que le ticket reflète l’état réel du travail effectué par l’agent.

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
