from __future__ import annotations

from enum import Enum


class TaskType(str, Enum):
    PLANNING = "planning"
    REASONING = "reasoning"
    CRITIQUE = "critique"
    JIRA_DRAFTING = "jira_drafting"
    SUMMARIZATION = "summarization"
    FIELD_EXTRACTION = "field_extraction"
    FORMAT_TRANSFORMATION = "format_transformation"
    TOOL_SUPPORT = "tool_support"
