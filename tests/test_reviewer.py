from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from agent_harness.config import Settings
from agent_harness.reviewer import CodeReviewer
from agent_harness.validators import ValidationResult


class ReviewerTests(unittest.TestCase):
    def test_review_rejects_when_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "lib").mkdir()
            (repo_root / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")

            reviewer = CodeReviewer(
                Settings(
                    advanced_provider="openai",
                    advanced_api_key=None,
                    advanced_model_name="gpt-4.1-mini",
                    ollama_base_url="http://localhost:11434",
                    ollama_model="llama3.1:8b",
                )
            )
            payload = json.dumps({"approved": True, "summary": "Looks good.", "feedback": ""})
            validation = ValidationResult(
                passed=False,
                status="failed",
                validator_name="flutter",
                summary="flutter analyze failed.",
                output="error: does not compile",
            )

            with mock.patch.object(reviewer._llm, "invoke") as invoke_mock:
                invoke_mock.return_value = mock.Mock(content=payload)
                result = reviewer.review(
                    issue_key="KAN-1",
                    issue_summary="Fix compile issue",
                    plan_markdown="Fix the compile issue.",
                    implementation_summary="Changed main.dart",
                    repo_path=str(repo_root),
                    modified_files=["lib/main.dart"],
                    validation=validation,
                )

            self.assertFalse(result.approved)
            self.assertEqual(result.summary, "Looks good.")
            self.assertIn("does not compile", result.feedback)

    def test_file_context_uses_head_tail_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "lib").mkdir()
            content = "A" * 9000 + "MIDDLE_MARKER" + "B" * 9000 + "TAIL_MARKER"
            (repo_root / "lib" / "main.dart").write_text(content, encoding="utf-8")

            reviewer = CodeReviewer(
                Settings(
                    advanced_provider="openai",
                    advanced_api_key=None,
                    advanced_model_name="gpt-4.1-mini",
                    ollama_base_url="http://localhost:11434",
                    ollama_model="llama3.1:8b",
                )
            )
            file_context = reviewer._load_file_context(str(repo_root), ["lib/main.dart"])

            self.assertIn("... [TRUNCATED] ...", file_context)
            self.assertIn("TAIL_MARKER", file_context)
