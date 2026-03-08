from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarkdownPrompt:
    path: Path
    metadata: dict[str, str]
    body: str

    def get(self, key: str, default: str = "") -> str:
        return self.metadata.get(key, default).strip()

    def get_int(self, key: str, default: int) -> int:
        raw_value = self.get(key)
        if not raw_value:
            return default
        return int(raw_value)

    def get_bool(self, key: str, default: bool) -> bool:
        raw_value = self.get(key)
        if not raw_value:
            return default
        return raw_value.lower() in {"1", "true", "yes", "y", "on"}

    def get_list(self, key: str, separator: str = ",") -> tuple[str, ...]:
        raw_value = self.get(key)
        if not raw_value:
            return ()
        return tuple(part.strip() for part in raw_value.split(separator) if part.strip())


class PromptStore:
    def __init__(self, base_dir: str | Path | None = None):
        default_dir = Path(__file__).resolve().parent / "prompts"
        self.base_dir = Path(base_dir).expanduser().resolve() if base_dir else default_dir

    def load(self, relative_path: str) -> MarkdownPrompt:
        target = self.base_dir / relative_path
        text = target.read_text(encoding="utf-8")
        metadata, body = self._split_front_matter(text)
        return MarkdownPrompt(path=target, metadata=metadata, body=body.strip())

    def load_many(self, relative_dir: str) -> list[MarkdownPrompt]:
        directory = self.base_dir / relative_dir
        if not directory.exists():
            return []
        prompts: list[MarkdownPrompt] = []
        for path in sorted(directory.glob("*.md")):
            prompts.append(self.load(str(path.relative_to(self.base_dir))))
        return prompts

    def _split_front_matter(self, text: str) -> tuple[dict[str, str], str]:
        if not text.startswith("---\n"):
            return {}, text

        end_marker = "\n---\n"
        end_index = text.find(end_marker, 4)
        if end_index == -1:
            return {}, text

        front_matter = text[4:end_index]
        body = text[end_index + len(end_marker) :]
        metadata: dict[str, str] = {}
        for raw_line in front_matter.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition(":")
            if not separator:
                continue
            metadata[key.strip()] = value.strip()
        return metadata, body
