from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Optional

import requests

from agent_harness.config import Settings


@dataclass
class JiraClient:
    base_url: str
    email: str
    api_token: str
    project_key: Optional[str] = None

    @staticmethod
    def from_settings(s: Settings) -> "JiraClient":
        if not (s.jira_base_url and s.jira_email and s.jira_api_token):
            raise RuntimeError("Config Jira manquante: JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN")
        return JiraClient(
            base_url=s.jira_base_url.rstrip("/"),
            email=s.jira_email,
            api_token=s.jira_api_token,
            project_key=s.jira_project_key,
        )

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.email}:{self.api_token}".encode("utf-8")).decode("utf-8")
        return {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        r = requests.get(url, headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    def add_comment(self, issue_key: str, body_markdown: str) -> dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": body_markdown[:3000]}]}
                ],
            }
        }
        r = requests.post(url, headers=self._headers(), data=json.dumps(payload), timeout=30)
        r.raise_for_status()
        return r.json()

    def create_issue(self, summary: str, description: str, issue_type: str = "Task") -> dict[str, Any]:
        if not self.project_key:
            raise RuntimeError("JIRA_PROJECT_KEY requis pour create_issue")
        url = f"{self.base_url}/rest/api/3/issue"
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
            }
        }
        r = requests.post(url, headers=self._headers(), data=json.dumps(payload), timeout=30)
        r.raise_for_status()
        return r.json()
