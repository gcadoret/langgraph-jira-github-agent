from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv() -> None:
        return None


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

    # Advanced LLM
    advanced_provider: str = os.getenv("ADVANCED_PROVIDER", "openai")
    advanced_api_key: str | None = os.getenv("ADVANCED_API_KEY", os.getenv("OPENAI_API_KEY"))
    advanced_model_name: str = os.getenv("ADVANCED_MODEL_NAME", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    advanced_base_url: str | None = os.getenv("ADVANCED_BASE_URL")

    # Local LLM
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str | None = os.getenv("OLLAMA_MODEL")

    # Behaviour
    dry_run_default: bool = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes", "y")


def get_settings() -> Settings:
    return Settings()
