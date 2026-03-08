from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random
import time
from typing import Any

from agent_harness.config import Settings

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore


class AdvancedProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"


DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MAX_RETRIES = 4
DEFAULT_INITIAL_BACKOFF_SECONDS = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 16.0


@dataclass
class AdvancedModelClient:
    provider: AdvancedProvider
    model_name: str
    api_key: str | None
    base_url: str | None = None
    temperature: float = 0.2
    timeout_seconds: int = 120
    max_retries: int = DEFAULT_MAX_RETRIES

    def __post_init__(self) -> None:
        self._llm = None
        if self.provider == AdvancedProvider.OPENAI and self.api_key and ChatOpenAI is not None:
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "api_key": self.api_key,
                "temperature": self.temperature,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._llm = ChatOpenAI(**kwargs)

    @staticmethod
    def from_settings(settings: Settings) -> "AdvancedModelClient":
        return AdvancedModelClient(
            provider=AdvancedProvider(settings.advanced_provider.lower()),
            model_name=settings.advanced_model_name,
            api_key=settings.advanced_api_key,
            base_url=settings.advanced_base_url,
        )

    def is_configured(self) -> bool:
        if not self.api_key:
            return False
        if self.provider == AdvancedProvider.OPENAI:
            return self._llm is not None
        if self.provider == AdvancedProvider.GEMINI:
            return True
        return False

    def complete(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError(
                "Advanced model is not configured: set ADVANCED_PROVIDER, ADVANCED_API_KEY, and ADVANCED_MODEL_NAME"
            )

        if self.provider == AdvancedProvider.OPENAI:
            return self._complete_openai(prompt=prompt, system_prompt=system_prompt)
        if self.provider == AdvancedProvider.GEMINI:
            return self._complete_gemini(prompt=prompt, system_prompt=system_prompt)
        raise RuntimeError(f"Unsupported advanced provider: {self.provider}")

    def _complete_openai(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        if self._llm is None:
            raise RuntimeError("OpenAI provider is unavailable: install langchain-openai and set ADVANCED_API_KEY")

        if system_prompt:
            prompt = f"{system_prompt}\n\n{prompt}"

        message = self._llm.invoke(prompt)
        return {
            "content": str(getattr(message, "content", message)),
            "model_name": self.model_name,
            "provider": self.provider.value,
            "is_mock": False,
        }

    def _complete_gemini(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        if requests is None:
            raise RuntimeError("requests is required for Gemini calls")

        base_url = (self.base_url or DEFAULT_GEMINI_BASE_URL).rstrip("/")
        url = f"{base_url}/models/{self.model_name}:generateContent"
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {"temperature": self.temperature},
        }
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}

        response = self._post_with_retry(
            url=url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key or "",
            },
            payload=payload,
        )
        data = response.json()

        return {
            "content": self._extract_gemini_text(data),
            "model_name": self.model_name,
            "provider": self.provider.value,
            "is_mock": False,
        }

    @staticmethod
    def _extract_gemini_text(data: dict[str, Any]) -> str:
        text_parts: list[str] = []
        for candidate in data.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)

        if text_parts:
            return "\n".join(text_parts).strip()
        raise RuntimeError("Gemini response did not contain any text parts")

    def _post_with_retry(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> Any:
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(  # type: ignore[union-attr]
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as exc:  # type: ignore[union-attr]
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise
                time.sleep(self._retry_delay_seconds(attempt=attempt, response=exc.response))

        if last_error is not None:  # pragma: no cover
            raise last_error
        raise RuntimeError("Gemini request failed without producing a response")  # pragma: no cover

    def _retry_delay_seconds(self, attempt: int, response: Any | None) -> float:
        retry_after_seconds = self._parse_retry_after_seconds(response)
        backoff_seconds = min(
            DEFAULT_INITIAL_BACKOFF_SECONDS * (2 ** attempt),
            DEFAULT_MAX_BACKOFF_SECONDS,
        )
        jitter_seconds = random.random()

        if retry_after_seconds is not None:
            return max(retry_after_seconds, backoff_seconds + jitter_seconds)
        return backoff_seconds + jitter_seconds

    @staticmethod
    def _parse_retry_after_seconds(response: Any | None) -> float | None:
        if response is None:
            return None

        retry_after = response.headers.get("Retry-After")
        if retry_after is None:
            return None

        try:
            return max(0.0, float(retry_after))
        except (TypeError, ValueError):
            return None
