from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Sandbox:
    root: Path

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)


def create_sandbox(prefix: str = "agent-sbx-") -> Sandbox:
    root = Path(tempfile.mkdtemp(prefix=prefix))
    return Sandbox(root=root)


def cleanup_sandbox(sandbox: Sandbox) -> None:
    try:
        shutil.rmtree(sandbox.root, ignore_errors=True)
    except Exception:
        pass
