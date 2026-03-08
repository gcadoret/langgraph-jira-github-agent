from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from agent_harness.task_types import TaskType


class ModelChoice(str, Enum):
    LOCAL = "local"
    ADVANCED = "advanced"


DEFAULT_TASK_MODEL_MAP: dict[TaskType, ModelChoice] = {
    TaskType.PLANNING: ModelChoice.ADVANCED,
    TaskType.IMPLEMENTATION: ModelChoice.ADVANCED,
    TaskType.REASONING: ModelChoice.ADVANCED,
    TaskType.CRITIQUE: ModelChoice.ADVANCED,
    TaskType.JIRA_DRAFTING: ModelChoice.LOCAL,
    TaskType.SUMMARIZATION: ModelChoice.LOCAL,
    TaskType.FIELD_EXTRACTION: ModelChoice.LOCAL,
    TaskType.FORMAT_TRANSFORMATION: ModelChoice.LOCAL,
    TaskType.TOOL_SUPPORT: ModelChoice.LOCAL,
}


@dataclass(frozen=True)
class TaskRoute:
    task_type: TaskType
    model_choice: ModelChoice


class TaskRouter:
    def __init__(self, mapping: Mapping[TaskType, ModelChoice] | None = None):
        self._mapping = dict(mapping or DEFAULT_TASK_MODEL_MAP)

    def route(self, task_type: TaskType) -> TaskRoute:
        try:
            model_choice = self._mapping[task_type]
        except KeyError as exc:  # pragma: no cover
            raise ValueError(f"No model route configured for task_type={task_type}") from exc
        return TaskRoute(task_type=task_type, model_choice=model_choice)
