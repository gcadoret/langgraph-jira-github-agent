from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from agent_harness.config import Settings
from agent_harness.llm import RoutedLLM
from agent_harness.repo_context import EditableFile, RepoContextBuilder
from agent_harness.task_types import TaskType


@dataclass(frozen=True)
class ImplementationPlan:
    summary: str
    updated_files: dict[str, str]
    selected_files: list[str]
    context_source: str
    raw_response: str


class CodeExecutor:
    def __init__(self, settings: Settings, repo_context_builder: RepoContextBuilder | None = None):
        self._llm = RoutedLLM(settings)
        self._repo_context_builder = repo_context_builder or RepoContextBuilder()

    def propose_changes(
        self,
        issue_key: str,
        issue_summary: str,
        issue_description: str,
        plan_markdown: str,
        repo_path: str,
        review_feedback: str = "",
        preferred_files: list[str] | None = None,
    ) -> ImplementationPlan:
        issue_text = " ".join(
            part for part in (issue_key, issue_summary, issue_description, plan_markdown, review_feedback) if part
        )
        context = self._repo_context_builder.build_edit_context(
            repo_path=repo_path,
            issue_text=issue_text,
            preferred_files=preferred_files or [],
        )
        if not context.editable_files:
            raise RuntimeError("No editable source files were selected for implementation")

        prompt = self._build_prompt(
            issue_key=issue_key,
            issue_summary=issue_summary,
            issue_description=issue_description,
            plan_markdown=plan_markdown,
            editable_files=context.editable_files,
            review_feedback=review_feedback,
        )
        response = self._llm.invoke(
            task_type=TaskType.IMPLEMENTATION,
            prompt=prompt,
            system_prompt="""Tu es un ingénieur logiciel senior. Tu modifies un petit nombre de fichiers existants.
Réponds uniquement avec un JSON valide, sans markdown.
Ne crée pas de nouveaux fichiers.
Retourne le contenu complet de chaque fichier modifié.
Fais un changement minimal, lisible et cohérent avec le plan.""",
            fallback_text="",
        )

        summary, updated_files = self._parse_response(
            content=response.content,
            editable_files=context.editable_files,
        )
        return ImplementationPlan(
            summary=summary,
            updated_files=updated_files,
            selected_files=[item.path for item in context.editable_files],
            context_source=context.source,
            raw_response=response.content,
        )

    def apply_changes(self, repo_path: str, updated_files: dict[str, str]) -> list[str]:
        repo_root = Path(repo_path).expanduser().resolve()
        modified_files: list[str] = []

        for relative_path, new_content in updated_files.items():
            target = repo_root / relative_path
            old_content = target.read_text(encoding="utf-8")
            if old_content == new_content:
                continue
            target.write_text(new_content, encoding="utf-8")
            modified_files.append(relative_path)

        return modified_files

    def _build_prompt(
        self,
        issue_key: str,
        issue_summary: str,
        issue_description: str,
        plan_markdown: str,
        editable_files: list[EditableFile],
        review_feedback: str,
    ) -> str:
        file_blocks = []
        for editable_file in editable_files:
            file_blocks.append(
                "\n".join(
                    [
                        f"FILE: {editable_file.path}",
                        "```text",
                        editable_file.content,
                        "```",
                    ]
                )
            )

        return "\n\n".join(
            [
                f"Ticket: {issue_key}",
                f"Titre: {issue_summary}",
                f"Description:\n{issue_description}",
                f"Plan:\n{plan_markdown}",
                f"Feedback reviewer:\n{review_feedback or '(aucun)'}",
                "Tu peux uniquement modifier les fichiers suivants.",
                *file_blocks,
                """Schéma de réponse JSON attendu:
{"summary":"résumé court","files":[{"path":"relative/path.ext","content":"contenu complet mis à jour"}]}

Contraintes:
- modifie au maximum 3 fichiers
- utilise seulement les chemins fournis
- si aucun changement sûr n'est possible, retourne {"summary":"aucun changement sûr proposé","files":[]}""",
            ]
        )

    def _parse_response(self, content: str, editable_files: list[EditableFile]) -> tuple[str, dict[str, str]]:
        data = self._extract_json(content)
        if not isinstance(data, dict):
            raise RuntimeError("Implementation response must be a JSON object")

        summary = str(data.get("summary", "")).strip() or "Implementation generated."
        files_payload = data.get("files", [])
        if not isinstance(files_payload, list):
            raise RuntimeError("Implementation response field 'files' must be a list")

        allowed_files = {editable_file.path: editable_file.content for editable_file in editable_files}
        updated_files: dict[str, str] = {}

        for item in files_payload:
            if not isinstance(item, dict):
                raise RuntimeError("Each implementation file entry must be an object")
            path = item.get("path")
            new_content = item.get("content")
            if not isinstance(path, str) or not isinstance(new_content, str):
                raise RuntimeError("Implementation file entries require string 'path' and 'content'")
            if path not in allowed_files:
                raise RuntimeError(f"Implementation attempted to edit unauthorized file: {path}")
            if allowed_files[path] == new_content:
                continue
            updated_files[path] = new_content

        return summary, updated_files

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
            raise RuntimeError("Implementation response did not contain JSON")
        return json.loads(content[start : end + 1])
