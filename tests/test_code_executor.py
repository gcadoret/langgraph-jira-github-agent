from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from agent_harness.code_executor import CodeExecutor
from agent_harness.config import Settings


class CodeExecutorTests(unittest.TestCase):
    def test_propose_and_apply_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "lib").mkdir()
            target = repo_root / "lib" / "main.dart"
            target.write_text("void main() {\n  print('old');\n}\n", encoding="utf-8")

            executor = CodeExecutor(
                Settings(
                    advanced_provider="openai",
                    advanced_api_key=None,
                    advanced_model_name="gpt-4.1-mini",
                    ollama_base_url="http://localhost:11434",
                    ollama_model="llama3.1:8b",
                )
            )
            response_content = json.dumps(
                {
                    "summary": "Update the startup log.",
                    "files": [
                        {
                            "path": "lib/main.dart",
                            "content": "void main() {\n  print('new');\n}\n",
                        }
                    ],
                }
            )

            with mock.patch.object(executor._llm, "invoke") as invoke_mock:
                invoke_mock.return_value = mock.Mock(content=response_content)
                plan = executor.propose_changes(
                    issue_key="KAN-1",
                    issue_summary="Update startup log",
                    issue_description="Change the startup log in the Flutter app.",
                    plan_markdown="Modify the startup print statement.",
                    repo_path=str(repo_root),
                )

            modified = executor.apply_changes(str(repo_root), plan.updated_files)

            self.assertEqual(plan.summary, "Update the startup log.")
            self.assertEqual(modified, ["lib/main.dart"])
            self.assertEqual(target.read_text(encoding="utf-8"), "void main() {\n  print('new');\n}\n")


if __name__ == "__main__":
    unittest.main()
