from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from agent_harness.config import Settings


@dataclass
class OllamaClient:
    base_url: str | None
    model: str | None
    timeout_seconds: int = 120

    @staticmethod
    def from_settings(settings: Settings) -> "OllamaClient":
        return OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )

    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)

    def complete(self, prompt: str, system_prompt: str | None = None, temperature: float = 0.1) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Ollama is not configured: set OLLAMA_BASE_URL and OLLAMA_MODEL")
        if requests is None:
            raise RuntimeError("requests is required for Ollama calls")

        url = f"{self.base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system_prompt:
            payload["system"] = system_prompt

        response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        return {
            "content": str(data.get("response", "")),
            "model_name": str(data.get("model", self.model)),
            "is_mock": False,
        }
