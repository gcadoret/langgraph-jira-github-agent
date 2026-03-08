from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from agent_harness.config import Settings


@dataclass
class GitHubClient:
    token: str
    repo: str  # "org/repo"

    @staticmethod
    def from_settings(s: Settings) -> "GitHubClient":
        if not (s.github_token and s.github_repo):
            raise RuntimeError("Config GitHub manquante: GITHUB_TOKEN/GITHUB_REPO")
        return GitHubClient(token=s.github_token, repo=s.github_repo)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    def create_pull_request(self, head: str, base: str, title: str, body: str) -> dict:
        url = f"https://api.github.com/repos/{self.repo}/pulls"
        payload = {"title": title, "head": head, "base": base, "body": body}
        r = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()


def run(cmd: list[str], cwd: Optional[Path] = None) -> None:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, capture_output=True, text=True)
    # garde les logs si besoin
    _ = p.stdout


def run_capture(cmd: list[str], cwd: Optional[Path] = None) -> str:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, capture_output=True, text=True)
    return p.stdout


def git_checkout_branch(repo_path: Path, branch: str) -> None:
    run(["git", "checkout", "-B", branch], cwd=repo_path)


def git_add_and_commit(repo_path: Path, paths: list[str], message: str) -> None:
    if not paths:
        raise ValueError("paths requis pour commit")
    run(["git", "add", *paths], cwd=repo_path)
    run(["git", "commit", "-m", message], cwd=repo_path)


def git_prepare_patch(repo_path: Path, branch: str, message: str, file_relpath: str, content: str) -> None:
    # create branch
    git_checkout_branch(repo_path, branch)

    target = repo_path / file_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    git_add_and_commit(repo_path, [file_relpath], message)


def git_push(repo_path: Path, remote: str = "origin", branch: str = "") -> None:
    if not branch:
        raise ValueError("branch requis")
    run(["git", "push", "--set-upstream", remote, branch], cwd=repo_path)


def git_changed_files(repo_path: Path) -> list[str]:
    output = run_capture(["git", "diff", "--name-only"], cwd=repo_path)
    return [line.strip() for line in output.splitlines() if line.strip()]
