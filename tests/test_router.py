from __future__ import annotations

import unittest

from agent_harness.advanced_model import AdvancedModelClient, AdvancedProvider
from agent_harness.config import Settings
from agent_harness.llm import PlannerLLM
from agent_harness.router import ModelChoice, TaskRouter
from agent_harness.task_types import TaskType


class TaskRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = TaskRouter()

    def test_advanced_tasks_route_to_advanced_model(self) -> None:
        for task_type in (TaskType.PLANNING, TaskType.REASONING, TaskType.CRITIQUE):
            with self.subTest(task_type=task_type):
                route = self.router.route(task_type)
                self.assertEqual(route.model_choice, ModelChoice.ADVANCED)

    def test_operational_tasks_route_to_local_model(self) -> None:
        for task_type in (
            TaskType.JIRA_DRAFTING,
            TaskType.SUMMARIZATION,
            TaskType.FIELD_EXTRACTION,
            TaskType.FORMAT_TRANSFORMATION,
            TaskType.TOOL_SUPPORT,
        ):
            with self.subTest(task_type=task_type):
                route = self.router.route(task_type)
                self.assertEqual(route.model_choice, ModelChoice.LOCAL)

    def test_planner_keeps_advanced_route_with_mock_fallback(self) -> None:
        settings = Settings(
            advanced_provider="openai",
            advanced_api_key=None,
            advanced_model_name="gpt-4.1-mini",
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1:8b",
        )
        planner = PlannerLLM(settings)

        result = planner.make_plan(
            issue_key="KAN-1",
            issue_summary="Fix flaky test",
            issue_description="Short description for deterministic fallback coverage.",
        )

        self.assertEqual(result.task_type, TaskType.PLANNING)
        self.assertEqual(result.model_choice, ModelChoice.ADVANCED)
        self.assertTrue(result.is_mock)
        self.assertEqual(result.model_name, "mock-advanced")

    def test_gemini_provider_is_considered_configured_with_api_key(self) -> None:
        client = AdvancedModelClient(
            provider=AdvancedProvider.GEMINI,
            model_name="gemini-2.5-pro",
            api_key="test-key",
        )

        self.assertTrue(client.is_configured())

    def test_extract_gemini_text_from_response(self) -> None:
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "First line."},
                            {"text": "Second line."},
                        ]
                    }
                }
            ]
        }

        self.assertEqual(
            AdvancedModelClient._extract_gemini_text(response),
            "First line.\nSecond line.",
        )


if __name__ == "__main__":
    unittest.main()
