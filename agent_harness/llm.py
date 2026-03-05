from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agent_harness.config import Settings

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore


@dataclass
class PlanResult:
    plan_markdown: str
    confidence: str  # "low" | "medium" | "high"
    missing_info: list[str]


class PlannerLLM:
    """Petit wrapper pour produire un plan.
    - Si OPENAI_API_KEY est présent: utilise ChatOpenAI
    - Sinon: génère un plan "mock" déterministe (utile pour valider le harness sans LLM)
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._llm = None
        if settings.openai_api_key and ChatOpenAI is not None:
            self._llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.2)

    def make_plan(self, issue_key: str, issue_summary: str, issue_description: str) -> PlanResult:
        if not self._llm:
            # Mock simple : structure + checklists
            missing = []
            if not issue_description or len(issue_description.strip()) < 20:
                missing.append("Description trop courte (ajouter contexte, logs, étapes de repro)")
            plan = f"""# Plan pour {issue_key}: {issue_summary}

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
            return PlanResult(plan_markdown=plan, confidence="medium" if not missing else "low", missing_info=missing)

        prompt = f"""Tu es un ingénieur logiciel senior. Produis un plan court, actionnable et vérifiable.
Contexte: on va travailler à partir d'un ticket Jira.

Ticket: {issue_key}
Titre: {issue_summary}
Description:
{issue_description}

Contraintes:
- Réponds en français
- Utilise du markdown
- Donne une checklist et les tests à lancer
- Liste les informations manquantes si nécessaire
"""

        msg = self._llm.invoke(prompt)
        content = getattr(msg, "content", str(msg))
        return PlanResult(plan_markdown=str(content), confidence="high", missing_info=[])
