from __future__ import annotations

from dataclasses import dataclass

from agent_harness.advanced_model import AdvancedModelClient
from agent_harness.config import Settings
from agent_harness.ollama_client import OllamaClient
from agent_harness.router import ModelChoice, TaskRouter
from agent_harness.task_types import TaskType


@dataclass
class PlanResult:
    plan_markdown: str
    confidence: str  # "low" | "medium" | "high"
    missing_info: list[str]
    task_type: TaskType
    model_choice: ModelChoice
    model_name: str
    is_mock: bool


@dataclass
class LLMResponse:
    content: str
    task_type: TaskType
    model_choice: ModelChoice
    model_name: str
    is_mock: bool


class RoutedLLM:
    def __init__(self, settings: Settings):
        self.router = TaskRouter()
        self.advanced_model = AdvancedModelClient.from_settings(settings)
        self.local_model = OllamaClient.from_settings(settings)

    def invoke(
        self,
        task_type: TaskType,
        prompt: str,
        system_prompt: str | None = None,
        fallback_text: str = "",
    ) -> LLMResponse:
        route = self.router.route(task_type)

        if route.model_choice == ModelChoice.ADVANCED and self.advanced_model.is_configured():
            result = self.advanced_model.complete(prompt=prompt, system_prompt=system_prompt)
            return LLMResponse(
                content=result["content"],
                task_type=task_type,
                model_choice=route.model_choice,
                model_name=result["model_name"],
                is_mock=bool(result["is_mock"]),
            )

        if route.model_choice == ModelChoice.LOCAL and self.local_model.is_configured():
            result = self.local_model.complete(prompt=prompt, system_prompt=system_prompt)
            return LLMResponse(
                content=result["content"],
                task_type=task_type,
                model_choice=route.model_choice,
                model_name=result["model_name"],
                is_mock=bool(result["is_mock"]),
            )

        fallback_model_name = f"mock-{route.model_choice.value}"
        return LLMResponse(
            content=fallback_text,
            task_type=task_type,
            model_choice=route.model_choice,
            model_name=fallback_model_name,
            is_mock=True,
        )


class PlannerLLM:
    """Produce plans through the explicit task router.

    Planning is routed to the advanced model. If no advanced provider is
    configured, the harness falls back to a deterministic mock plan.
    """

    def __init__(self, settings: Settings):
        self._llm = RoutedLLM(settings)

    def make_plan(self, issue_key: str, issue_summary: str, issue_description: str) -> PlanResult:
        missing = []
        if not issue_description or len(issue_description.strip()) < 20:
            missing.append("Description trop courte (ajouter contexte, logs, étapes de repro)")

        fallback_plan = f"""# Plan pour {issue_key}: {issue_summary}

## Compréhension
- Résumé: {issue_summary}
- Hypothèses: ticket incomplet → vérifier contexte et impacts.

## Étapes
1. Identifier le(s) module(s) concernés (repos, packages, endpoints).
2. Reproduire le problème (si bug) ou valider les AC (si feature).
3. Implémenter le changement de façon minimale.
4. Ajouter/adapter les tests (unitaires + intégration si pertinent).
5. Lancer la suite de tests + lint.
6. Ouvrir une PR avec un résumé + preuves (tests OK).

## Risques / points d'attention
- Régression sur chemins voisins.
- Contrats API (backward compatibility).
- Gestion des erreurs + logs.

## Infos manquantes
{('- ' + '\n- '.join(missing)) if missing else '- (rien)'}
"""

        prompt = f"""Contexte: on va travailler à partir d'un ticket Jira.

Ticket: {issue_key}
Titre: {issue_summary}
Description:
{issue_description}
"""

        response = self._llm.invoke(
            task_type=TaskType.PLANNING,
            prompt=prompt,
            system_prompt="""Tu es un ingénieur logiciel senior. Produis un plan court, actionnable et vérifiable.
Réponds en français.
Utilise du markdown.
Donne une checklist et les tests à lancer.
Liste les informations manquantes si nécessaire.""",
            fallback_text=fallback_plan,
        )

        if response.is_mock:
            confidence = "medium" if not missing else "low"
        else:
            confidence = "high" if not missing else "medium"

        return PlanResult(
            plan_markdown=response.content,
            confidence=confidence,
            missing_info=missing,
            task_type=response.task_type,
            model_choice=response.model_choice,
            model_name=response.model_name,
            is_mock=response.is_mock,
        )
