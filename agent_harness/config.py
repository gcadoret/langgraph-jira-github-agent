from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Jira
    jira_base_url: str | None = os.getenv("JIRA_BASE_URL")
    jira_email: str | None = os.getenv("JIRA_EMAIL")
    jira_api_token: str | None = os.getenv("JIRA_API_TOKEN")
    jira_project_key: str | None = os.getenv("JIRA_PROJECT_KEY")

    # GitHub
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_repo: str | None = os.getenv("GITHUB_REPO")

    # LLM (optionnel)
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    # Behaviour
    dry_run_default: bool = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes", "y")


def get_settings() -> Settings:
    return Settings()
