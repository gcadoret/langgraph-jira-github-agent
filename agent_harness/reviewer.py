from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from agent_harness.config import Settings
from agent_harness.llm import RoutedLLM
from agent_harness.prompt_store import PromptStore
from agent_harness.task_types import TaskType
from agent_harness.validators import ValidationResult


@dataclass(frozen=True)
class ReviewProfile:
    system_prompt: str
    instructions: str
    file_excerpt_chars: int
    validation_output_chars: int
    file_excerpt_strategy: str


@dataclass(frozen=True)
class ReviewResult:
    approved: bool
    summary: str
    feedback: str
    validation_summary: str
    raw_response: str


class CodeReviewer:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._llm = RoutedLLM(settings)
        prompt_store = PromptStore(settings.prompts_dir)
        prompt = prompt_store.load("review/default.md")
        self._profile = ReviewProfile(
            system_prompt=prompt.get("system_prompt", "Tu es un reviewer technique strict et factuel."),
            instructions=prompt.body,
            file_excerpt_chars=prompt.get_int("file_excerpt_chars", 12000),
            validation_output_chars=prompt.get_int("validation_output_chars", 4000),
            file_excerpt_strategy=prompt.get("file_excerpt_strategy", "head_tail"),
        )

    def review(
        self,
        issue_key: str,
        issue_summary: str,
        plan_markdown: str,
        implementation_summary: str,
        repo_path: str,
        modified_files: list[str],
        validation: ValidationResult,
    ) -> ReviewResult:
        file_context = self._load_file_context(repo_path=repo_path, modified_files=modified_files)
        validation_summary = self._build_validation_summary(validation)
        prompt_sections = [
            f"Ticket: {issue_key}",
            f"Titre: {issue_summary}",
            f"Plan:\n{plan_markdown}",
            f"Résumé d'implémentation:\n{implementation_summary}",
            f"Politique de validation ({validation.validator_name}):\n{validation.review_guidance or '(aucune)'}",
        ]
        if validation_summary:
            prompt_sections.append(f"Synthèse de validation:\n{validation_summary}")
        prompt_sections.extend(
            [
                (
                    "Validation:\n"
                    f"- status={validation.status}\n"
                    f"- validator={validation.validator_name}\n"
                    f"- command={validation.command or '(none)'}\n"
                    f"- summary={validation.summary}\n"
                    f"- output=\n{validation.output[: self._profile.validation_output_chars]}"
                ),
                f"Fichiers modifiés:\n{file_context}",
                self._profile.instructions,
            ]
        )
        prompt = "\n\n".join(prompt_sections)
        fallback_payload = {
            "approved": validation.passed,
            "summary": validation.summary,
            "feedback": "" if validation.passed else validation.output[:1200] or validation.summary,
        }
        response = self._llm.invoke(
            task_type=TaskType.CRITIQUE,
            prompt=prompt,
            system_prompt=self._profile.system_prompt,
            fallback_text=json.dumps(fallback_payload, ensure_ascii=False),
        )
        approved, summary, feedback = self._parse_response(response.content)
        if not validation.passed:
            approved = False
            if not feedback:
                feedback = validation.output[:1200] or validation.summary
        return ReviewResult(
            approved=approved,
            summary=summary,
            feedback=feedback,
            validation_summary=validation_summary,
            raw_response=response.content,
        )

    def _build_validation_summary(self, validation: ValidationResult) -> str:
        if not self._settings.enable_validation_summary:
            return ""

        counts = (
            f"errors={validation.error_count}, "
            f"warnings={validation.warning_count}, "
            f"infos={validation.info_count}"
        )
        lines = [
            f"validator={validation.validator_name}",
            f"status={validation.status}",
        ]
        if validation.command:
            lines.append(f"command={validation.command}")
        lines.append(f"counts={counts}")
        lines.append(f"summary={validation.summary}")

        finding_lines = [
            raw_line.strip()
            for raw_line in validation.output.splitlines()
            if raw_line.strip() and re.match(r"^(error|warning|info)\b", raw_line.strip(), flags=re.IGNORECASE)
        ][:3]
        if finding_lines:
            lines.append("top_findings=" + " | ".join(finding_lines))
        return "\n".join(lines)

    def _load_file_context(self, repo_path: str, modified_files: list[str]) -> str:
        repo_root = Path(repo_path).expanduser().resolve()
        sections: list[str] = []
        for relative_path in modified_files:
            target = repo_root / relative_path
            if not target.exists():
                continue
            try:
                content = target.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            excerpt = self._build_excerpt(content)
            sections.extend(
                [
                    f"FILE: {relative_path} (chars={len(content)}, excerpt_strategy={self._profile.file_excerpt_strategy})",
                    "```text",
                    excerpt,
                    "```",
                ]
            )
        return "\n".join(sections) if sections else "(aucun contenu lisible)"

    def _build_excerpt(self, content: str) -> str:
        max_chars = self._profile.file_excerpt_chars
        if len(content) <= max_chars:
            return content
        if self._profile.file_excerpt_strategy != "head_tail":
            return content[:max_chars]
        separator = "\n\n... [TRUNCATED] ...\n\n"
        head_size = max((max_chars - len(separator)) // 2, 0)
        tail_size = max(max_chars - len(separator) - head_size, 0)
        return content[:head_size] + separator + content[-tail_size:]

    def _parse_response(self, content: str) -> tuple[bool, str, str]:
        data = self._extract_json(content)
        if not isinstance(data, dict):
            raise RuntimeError("Review response must be a JSON object")
        approved = bool(data.get("approved", False))
        summary = str(data.get("summary", "")).strip() or "Review completed."
        feedback = str(data.get("feedback", "")).strip()
        return approved, summary, feedback

    def _extract_json(self, content: str) -> object:
        stripped = content.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        fenced_match = re.search(r"```json\s*(\{.*\})\s*```", content, flags=re.DOTALL)
        if fenced_match:
            return json.loads(fenced_match.group(1))

        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Review response did not contain JSON")
        return json.loads(content[start : end + 1])
