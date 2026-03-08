from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import json
from pathlib import Path
import time


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".dart_tool",
    ".idea",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}
IGNORED_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".jar",
    ".class",
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".mp4",
    ".mov",
}
HIGH_SIGNAL_FILES = (
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "Pipfile",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
)
STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "dans",
    "pour",
    "avec",
    "ticket",
    "issue",
    "plan",
    "jira",
    "sur",
    "des",
    "les",
    "une",
    "est",
}
CACHE_TTL_SECONDS = 300
CACHE_SCHEMA_VERSION = 2
MAX_INDEXED_FILES = 500
MAX_STRUCTURE_LINES = 40
MAX_CANDIDATE_FILES = 6
MAX_EDITABLE_FILES = 4
MAX_SNIPPET_LINES = 60
MAX_SNIPPET_CHARS = 1600
MAX_EDITABLE_FILE_CHARS = 30000
MAX_CONTENT_SCORE_CHARS = 4000
CODE_FILE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".dart",
    ".java",
    ".kt",
    ".go",
    ".rb",
}
PREFERRED_CODE_ROOTS = (
    "lib/",
    "src/",
    "app/",
    "packages/",
    "test/",
)
LOW_SIGNAL_EDIT_PATTERNS = (
    "lib/firebase_options.dart",
    "lib/l10n/app_localizations",
    ".g.dart",
    ".freezed.dart",
    "generated_plugin_registrant",
)
HIGH_SIGNAL_EDIT_PATTERNS = (
    "main.dart",
    "/screens/",
    "/services/",
    "/widgets/",
    "/models/",
    "/controllers/",
    "test/",
)
TOKEN_SYNONYMS = {
    "son": {"audio", "sound", "music"},
    "sons": {"audio", "sound", "music"},
    "audio": {"sound", "music"},
    "sound": {"audio", "music"},
    "musique": {"audio", "music", "sound"},
    "selection": {"select", "picker", "choose"},
    "selectionner": {"select", "picker", "choose"},
    "choisir": {"select", "picker", "choose"},
    "galerie": {"gallery"},
    "miniature": {"thumbnail", "thumb"},
    "boucle": {"loop"},
    "video": {"player", "media"},
}


@dataclass(frozen=True)
class RepoContextResult:
    summary_markdown: str
    source: str
    cache_path: str


@dataclass(frozen=True)
class EditableFile:
    path: str
    content: str


@dataclass(frozen=True)
class RepoEditContextResult:
    editable_files: list[EditableFile]
    source: str
    cache_path: str


class RepoContextBuilder:
    def __init__(self, cache_ttl_seconds: int = CACHE_TTL_SECONDS):
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_dir = Path(__file__).resolve().parent.parent / ".agent_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def build(self, repo_path: str, issue_text: str) -> RepoContextResult:
        repo_root = Path(repo_path).expanduser().resolve()
        payload, source, cache_path = self._load_or_scan(repo_root)
        summary = self._render_summary(repo_root=repo_root, payload=payload, issue_text=issue_text, source=source)
        return RepoContextResult(summary_markdown=summary, source=source, cache_path=str(cache_path))

    def build_edit_context(
        self,
        repo_path: str,
        issue_text: str,
        preferred_files: list[str] | None = None,
    ) -> RepoEditContextResult:
        repo_root = Path(repo_path).expanduser().resolve()
        payload, source, cache_path = self._load_or_scan(repo_root)
        files = payload.get("files", [])
        selected_files = self._select_candidate_files(
            repo_root=repo_root,
            files=files,
            issue_text=issue_text,
            max_files=MAX_EDITABLE_FILES,
            prefer_code=True,
        )
        for preferred_file in preferred_files or []:
            if preferred_file in files and preferred_file not in selected_files:
                selected_files.insert(0, preferred_file)
        selected_files = selected_files[:MAX_EDITABLE_FILES]
        editable_files = self._load_editable_files(repo_root=repo_root, relative_paths=selected_files)
        return RepoEditContextResult(
            editable_files=editable_files,
            source=source,
            cache_path=str(cache_path),
        )

    def _cache_path_for(self, repo_root: Path) -> Path:
        cache_key = sha1(str(repo_root).encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"repo_context_{cache_key}.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        if not cache_path.exists():
            return False
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        age_seconds = time.time() - cache_path.stat().st_mtime
        if age_seconds > self.cache_ttl_seconds:
            return False
        return payload.get("schema_version") == CACHE_SCHEMA_VERSION

    def _load_or_scan(self, repo_root: Path) -> tuple[dict, str, Path]:
        cache_path = self._cache_path_for(repo_root)
        source = "fresh"

        if self._is_cache_valid(cache_path):
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            source = "cache"
        else:
            payload = self._scan_repo(repo_root)
            cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        return payload, source, cache_path

    def _scan_repo(self, repo_root: Path) -> dict:
        files: list[str] = []
        top_level_entries: list[str] = []

        for child in sorted(repo_root.iterdir(), key=lambda item: item.name.lower()):
            if child.name in IGNORED_DIRS:
                continue
            top_level_entries.append(f"{child.name}/" if child.is_dir() else child.name)

        for path in sorted(repo_root.rglob("*")):
            if len(files) >= MAX_INDEXED_FILES:
                break
            if path.is_dir():
                continue
            if self._is_ignored(path, repo_root):
                continue
            files.append(str(path.relative_to(repo_root)))

        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "generated_at": time.time(),
            "top_level_entries": top_level_entries[:MAX_STRUCTURE_LINES],
            "files": files,
        }

    def _is_ignored(self, path: Path, repo_root: Path) -> bool:
        parts = set(path.relative_to(repo_root).parts)
        if parts & IGNORED_DIRS:
            return True
        if path.suffix.lower() in IGNORED_SUFFIXES:
            return True
        return False

    def _render_summary(self, repo_root: Path, payload: dict, issue_text: str, source: str) -> str:
        files = payload.get("files", [])
        selected_files = self._select_candidate_files(
            repo_root=repo_root,
            files=files,
            issue_text=issue_text,
            max_files=MAX_CANDIDATE_FILES,
        )
        snippets = self._load_snippets(repo_root=repo_root, relative_paths=selected_files)

        structure_lines = "\n".join(f"- {entry}" for entry in payload.get("top_level_entries", [])[:MAX_STRUCTURE_LINES])
        candidate_lines = "\n".join(f"- {path}" for path in selected_files) or "- (aucun fichier ciblé)"

        sections = [
            "## Contexte repo",
            f"- Source du contexte: {source}",
            f"- Racine: {repo_root}",
            "",
            "### Structure racine",
            structure_lines or "- (structure indisponible)",
            "",
            "### Fichiers ciblés pour ce ticket",
            candidate_lines,
        ]

        if snippets:
            sections.extend(["", "### Extraits ciblés"])
            for relative_path, snippet in snippets:
                sections.extend(
                    [
                        f"#### {relative_path}",
                        "```text",
                        snippet,
                        "```",
                    ]
                )

        return "\n".join(sections).strip()

    def _select_candidate_files(
        self,
        repo_root: Path,
        files: list[str],
        issue_text: str,
        max_files: int,
        prefer_code: bool = False,
    ) -> list[str]:
        selected: list[str] = []

        if not prefer_code:
            for high_signal in HIGH_SIGNAL_FILES:
                if high_signal in files:
                    selected.append(high_signal)

        issue_tokens = self._tokenize(issue_text)
        scored_files: list[tuple[int, str]] = []
        for relative_path in files:
            path_tokens = self._tokenize(relative_path.replace("/", " ").replace(".", " "))
            overlap = len(issue_tokens & path_tokens)
            score = overlap
            if not prefer_code and Path(relative_path).name in HIGH_SIGNAL_FILES:
                score += 2
            if prefer_code and Path(relative_path).suffix.lower() in CODE_FILE_SUFFIXES:
                score += 1
            if prefer_code and self._is_preferred_code_path(relative_path):
                score += 2
            if prefer_code and self._is_high_signal_edit_path(relative_path):
                score += 3
            if prefer_code and self._is_low_signal_edit_path(relative_path):
                score -= 3
            if prefer_code:
                score += self._content_overlap_score(
                    repo_root=repo_root,
                    relative_path=relative_path,
                    issue_tokens=issue_tokens,
                )
            if score > 0:
                scored_files.append((score, relative_path))

        scored_files.sort(key=lambda item: (-item[0], item[1]))
        for _, relative_path in scored_files:
            if relative_path not in selected:
                selected.append(relative_path)
            if len(selected) >= max_files:
                break

        if prefer_code and len(selected) < max_files:
            preferred_paths = [path for path in files if self._is_preferred_code_path(path)]
            fallback_paths = preferred_paths + files
            for relative_path in fallback_paths:
                if relative_path in selected:
                    continue
                suffix = Path(relative_path).suffix.lower()
                if suffix in CODE_FILE_SUFFIXES:
                    selected.append(relative_path)
                if len(selected) >= max_files:
                    break

        return selected[:max_files]

    def _load_snippets(self, repo_root: Path, relative_paths: list[str]) -> list[tuple[str, str]]:
        snippets: list[tuple[str, str]] = []
        for relative_path in relative_paths:
            path = repo_root / relative_path
            if not path.exists() or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            lines = content.splitlines()
            snippet = "\n".join(lines[:MAX_SNIPPET_LINES]).strip()
            if not snippet:
                continue
            if len(snippet) > MAX_SNIPPET_CHARS:
                snippet = snippet[:MAX_SNIPPET_CHARS].rstrip() + "\n..."
            snippets.append((relative_path, snippet))
        return snippets

    def _load_editable_files(self, repo_root: Path, relative_paths: list[str]) -> list[EditableFile]:
        editable_files: list[EditableFile] = []
        for relative_path in relative_paths:
            path = repo_root / relative_path
            if not path.exists() or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not content.strip():
                continue
            if len(content) > MAX_EDITABLE_FILE_CHARS:
                continue
            editable_files.append(EditableFile(path=relative_path, content=content))
        return editable_files

    def _tokenize(self, text: str) -> set[str]:
        normalized = []
        for char in text.lower():
            normalized.append(char if char.isalnum() else " ")
        base_tokens = {token for token in "".join(normalized).split() if len(token) >= 3 and token not in STOP_WORDS}
        expanded_tokens = set(base_tokens)
        for token in base_tokens:
            expanded_tokens.update(TOKEN_SYNONYMS.get(token, set()))
        tokens = {token for token in expanded_tokens if len(token) >= 3 and token not in STOP_WORDS}
        return tokens

    def _is_preferred_code_path(self, relative_path: str) -> bool:
        return relative_path.startswith(PREFERRED_CODE_ROOTS)

    def _is_low_signal_edit_path(self, relative_path: str) -> bool:
        return any(pattern in relative_path for pattern in LOW_SIGNAL_EDIT_PATTERNS)

    def _is_high_signal_edit_path(self, relative_path: str) -> bool:
        normalized = f"/{relative_path}"
        return any(pattern in relative_path or pattern in normalized for pattern in HIGH_SIGNAL_EDIT_PATTERNS)

    def _content_overlap_score(self, repo_root: Path, relative_path: str, issue_tokens: set[str]) -> int:
        path = repo_root / relative_path
        suffix = path.suffix.lower()
        if suffix not in CODE_FILE_SUFFIXES:
            return 0
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return 0
        content_tokens = self._tokenize(content[:MAX_CONTENT_SCORE_CHARS])
        overlap = len(issue_tokens & content_tokens)
        if overlap >= 3:
            return 4
        if overlap == 2:
            return 2
        if overlap == 1:
            return 1
        return 0
