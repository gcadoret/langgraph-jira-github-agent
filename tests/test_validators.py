from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest import mock

from agent_harness.config import Settings
from agent_harness.validators import ConfiguredCommandValidator, ProjectValidatorFactory


class ValidatorTests(unittest.TestCase):
    def test_detects_flutter_repo_from_markdown_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "pubspec.yaml").write_text("name: demo\n", encoding="utf-8")
            settings = Settings(prompts_dir=None)
            with mock.patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "flutter" else None):
                validator = ProjectValidatorFactory.for_repo(str(repo_root), settings=settings)
            self.assertIsInstance(validator, ConfiguredCommandValidator)
            self.assertEqual(validator.profile.name, "flutter")
            self.assertEqual(validator.command, ["flutter", "analyze"])

    def test_non_blocking_warnings_pass_flutter_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "pubspec.yaml").write_text("name: demo\n", encoding="utf-8")
            settings = Settings(prompts_dir=None)
            with mock.patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "flutter" else None):
                validator = ProjectValidatorFactory.for_repo(str(repo_root), settings=settings)

            process = mock.Mock(
                returncode=1,
                stdout="warning • Deprecated API • lib/main.dart:1:1 • deprecated_member_use\n"
                "info • Style note • lib/main.dart:2:1 • style\n",
                stderr="",
            )
            with mock.patch("subprocess.run", return_value=process):
                result = validator.validate(str(repo_root))

            self.assertTrue(result.passed)
            self.assertEqual(result.status, "passed_with_findings")
            self.assertIn("warning=1", result.summary)
            self.assertIn("info=1", result.summary)

    def test_blocking_errors_fail_flutter_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "pubspec.yaml").write_text("name: demo\n", encoding="utf-8")
            settings = Settings(prompts_dir=None)
            with mock.patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "flutter" else None):
                validator = ProjectValidatorFactory.for_repo(str(repo_root), settings=settings)

            process = mock.Mock(
                returncode=1,
                stdout="error • Undefined name • lib/main.dart:1:1 • undefined_identifier\n",
                stderr="",
            )
            with mock.patch("subprocess.run", return_value=process):
                result = validator.validate(str(repo_root))

            self.assertFalse(result.passed)
            self.assertEqual(result.status, "failed")
            self.assertIn("error=1", result.summary)
