from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from agent_harness.config import Settings
from agent_harness.prompt_store import PromptStore


SEVERITY_ORDER = {
    "info": 1,
    "warning": 2,
    "error": 3,
}

ISSUE_PATTERN = re.compile(r"^\s*(error|warning|info)\b", flags=re.IGNORECASE)


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    line: str


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    status: str
    validator_name: str
    summary: str
    output: str
    command: str = ""
    review_guidance: str = ""


@dataclass(frozen=True)
class ValidationProfile:
    name: str
    match_files: tuple[str, ...]
    command_candidates: tuple[str, ...]
    blocking_severities: tuple[str, ...]
    allow_nonzero_without_blockers: bool
    review_guidance: str

    @classmethod
    def from_prompt(cls, prompt) -> "ValidationProfile":
        return cls(
            name=prompt.get("name", prompt.path.stem),
            match_files=prompt.get_list("match_files"),
            command_candidates=prompt.get_list("command_candidates", separator="|"),
            blocking_severities=prompt.get_list("blocking_severities"),
            allow_nonzero_without_blockers=prompt.get_bool("allow_nonzero_without_blockers", False),
            review_guidance=prompt.body,
        )


class ProjectValidator:
    name = "noop"

    def validate(self, repo_path: str) -> ValidationResult:
        return ValidationResult(
            passed=True,
            status="skipped",
            validator_name=self.name,
            summary="No project-specific validator configured.",
            output="",
        )


class ConfiguredCommandValidator(ProjectValidator):
    def __init__(self, profile: ValidationProfile, command: list[str] | None):
        self.profile = profile
        self.command = command
        self.name = profile.name

    def validate(self, repo_path: str) -> ValidationResult:
        if not self.command:
            return ValidationResult(
                passed=True,
                status="skipped",
                validator_name=self.profile.name,
                summary=f"No available command for validation profile '{self.profile.name}'.",
                output="",
                review_guidance=self.profile.review_guidance,
            )

        repo_root = Path(repo_path).expanduser().resolve()
        process = subprocess.run(
            self.command,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        output = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part).strip()
        issues = self._extract_issues(output)
        blocking_issues = [issue for issue in issues if issue.severity in self.profile.blocking_severities]

        if process.returncode == 0:
            passed = True
        elif blocking_issues:
            passed = False
        elif self.profile.allow_nonzero_without_blockers and issues:
            passed = True
        else:
            passed = False

        status = self._build_status(passed=passed, issues=issues)
        summary = self._build_summary(issues=issues, passed=passed, returncode=process.returncode)
        return ValidationResult(
            passed=passed,
            status=status,
            validator_name=self.profile.name,
            summary=summary,
            output=output,
            command=" ".join(self.command),
            review_guidance=self.profile.review_guidance,
        )

    def _extract_issues(self, output: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for raw_line in output.splitlines():
            match = ISSUE_PATTERN.match(raw_line)
            if not match:
                continue
            severity = match.group(1).lower()
            issues.append(ValidationIssue(severity=severity, line=raw_line.strip()))
        return issues

    def _build_status(self, passed: bool, issues: list[ValidationIssue]) -> str:
        if not passed:
            return "failed"
        if issues:
            return "passed_with_findings"
        return "passed"

    def _build_summary(self, issues: list[ValidationIssue], passed: bool, returncode: int) -> str:
        command_text = " ".join(self.command or [])
        counts = {
            "error": sum(1 for issue in issues if issue.severity == "error"),
            "warning": sum(1 for issue in issues if issue.severity == "warning"),
            "info": sum(1 for issue in issues if issue.severity == "info"),
        }
        counts_text = ", ".join(f"{severity}={counts[severity]}" for severity in ("error", "warning", "info"))
        if passed and issues:
            return f"{command_text} completed with non-blocking findings ({counts_text}; exit={returncode})."
        if passed:
            return f"{command_text} passed."
        return f"{command_text} failed with blocking findings ({counts_text}; exit={returncode})."


class ValidationProfileRegistry:
    def __init__(self, prompt_store: PromptStore):
        prompts = prompt_store.load_many("validation")
        self._profiles = [ValidationProfile.from_prompt(prompt) for prompt in prompts]

    def select(self, repo_path: str) -> ValidationProfile:
        repo_root = Path(repo_path).expanduser().resolve()
        matching_profiles = [profile for profile in self._profiles if self._matches(repo_root, profile)]
        if not matching_profiles:
            return ValidationProfile(
                name="default",
                match_files=(),
                command_candidates=(),
                blocking_severities=("error",),
                allow_nonzero_without_blockers=False,
                review_guidance="No validation guidance configured.",
            )
        matching_profiles.sort(key=lambda profile: len(profile.match_files), reverse=True)
        return matching_profiles[0]

    def _matches(self, repo_root: Path, profile: ValidationProfile) -> bool:
        if not profile.match_files:
            return True
        for pattern in profile.match_files:
            if any(repo_root.glob(pattern)):
                return True
        return False


class ProjectValidatorFactory:
    @staticmethod
    def for_repo(repo_path: str, settings: Settings | None = None) -> ProjectValidator:
        prompt_store = PromptStore(settings.prompts_dir if settings else None)
        registry = ValidationProfileRegistry(prompt_store)
        profile = registry.select(repo_path)
        command = ProjectValidatorFactory._resolve_command(profile.command_candidates)
        if not command:
            return ProjectValidator() if profile.name == "default" else ConfiguredCommandValidator(profile, None)
        return ConfiguredCommandValidator(profile, command)

    @staticmethod
    def _resolve_command(command_candidates: tuple[str, ...]) -> list[str] | None:
        for candidate in command_candidates:
            parts = shlex.split(candidate)
            if not parts:
                continue
            executable = parts[0]
            if Path(executable).exists() or shutil.which(executable):
                return parts
        return None
