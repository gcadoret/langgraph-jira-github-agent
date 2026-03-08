from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from agent_harness.repo_context import RepoContextBuilder


class RepoContextBuilderTests(unittest.TestCase):
    def test_builds_targeted_context_and_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (repo_root / "requirements.txt").write_text("langgraph\nrequests\n", encoding="utf-8")
            (repo_root / "src").mkdir()
            (repo_root / "src" / "worker.py").write_text(
                "def process_clip():\n    return 'ok'\n",
                encoding="utf-8",
            )
            (repo_root / "tests").mkdir()
            (repo_root / "tests" / "test_worker.py").write_text(
                "from src.worker import process_clip\n",
                encoding="utf-8",
            )

            builder = RepoContextBuilder(cache_ttl_seconds=3600)
            issue_text = "clip worker failing processing test"

            fresh = builder.build(repo_path=str(repo_root), issue_text=issue_text)
            cached = builder.build(repo_path=str(repo_root), issue_text=issue_text)

            self.assertEqual(fresh.source, "fresh")
            self.assertEqual(cached.source, "cache")
            self.assertIn("README.md", fresh.summary_markdown)
            self.assertIn("src/worker.py", fresh.summary_markdown)
            self.assertTrue(Path(fresh.cache_path).exists())

    def test_edit_context_prefers_real_source_files_over_generated_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".dart_tool").mkdir()
            (repo_root / ".dart_tool" / "generated.dart").write_text("void generated() {}\n", encoding="utf-8")
            (repo_root / "lib").mkdir()
            (repo_root / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
            (repo_root / "test").mkdir()
            (repo_root / "test" / "main_test.dart").write_text("void testMain() {}\n", encoding="utf-8")

            builder = RepoContextBuilder(cache_ttl_seconds=3600)
            edit_context = builder.build_edit_context(
                repo_path=str(repo_root),
                issue_text="dart main implementation",
            )

            editable_paths = [item.path for item in edit_context.editable_files]
            self.assertIn("lib/main.dart", editable_paths)
            self.assertIn("test/main_test.dart", editable_paths)
            self.assertNotIn(".dart_tool/generated.dart", editable_paths)

    def test_edit_context_can_match_content_with_synonyms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "lib" / "screens").mkdir(parents=True)
            (repo_root / "lib" / "services").mkdir(parents=True)
            (repo_root / "lib" / "screens" / "video_player_screen.dart").write_text(
                "class AddAudioSheet { final String label = 'audio picker'; }\n",
                encoding="utf-8",
            )
            (repo_root / "lib" / "services" / "gallery_meta_service.dart").write_text(
                "class GalleryMetaService {}\n",
                encoding="utf-8",
            )

            builder = RepoContextBuilder(cache_ttl_seconds=3600)
            edit_context = builder.build_edit_context(
                repo_path=str(repo_root),
                issue_text="ajouter une selection de son",
            )

            editable_paths = [item.path for item in edit_context.editable_files]
            self.assertIn("lib/screens/video_player_screen.dart", editable_paths)
