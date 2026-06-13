import os
import re
import asyncio
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Callable

from core.schemas import ExecutionPlan


@dataclass
class ExecutionStep:
    index: int
    description: str
    command: Optional[str] = None
    target_files: List[str] = field(default_factory=list)
    status: str = "pending"
    output: str = ""
    error: Optional[str] = None


@dataclass
class ExecutionResult:
    plan_title: str
    steps_total: int
    steps_completed: int
    steps_failed: int
    steps_skipped: int
    results: List[ExecutionStep] = field(default_factory=list)
    blocked_commands: List[str] = field(default_factory=list)
    blocked_files: List[str] = field(default_factory=list)
    status: str = "pending"
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.steps_failed == 0 and self.steps_completed > 0


class SafeExecutor:
    """
    TODO (P1): SafeExecutor currently only validates commands and file paths.
    The execute_plan() method does NOT actually execute any commands or write
    any files.  When dry_run=False it returns a "[SIMULATED]" placeholder
    output instead of real execution.  A proper sandboxed subprocess runner
    (e.g., asyncio.create_subprocess_exec inside the workspace_dir) needs to
    be implemented before this component can be used in production.
    """
    DEFAULT_FORBIDDEN_COMMANDS = [
        "rm -rf", "rm -r /", "del /s /q", "format",
        "git push --force", "git push -f", "git reset --hard",
        "shutdown", "reboot", "mkfs", "dd if=",
        "| sh", "| bash", "| zsh",
        "chmod 777", "chown root",
        "> /etc/", "> /root/",
    ]

    DEFAULT_FORBIDDEN_FILE_PATTERNS = [
        ".env", ".ssh", ".gitconfig", ".aws",
        "id_rsa", "id_ed25519", "credentials",
        "/etc/", "/root/", "/home/",
    ]

    DEFAULT_ALLOWED_EXTENSIONS = {
        ".py", ".md", ".txt", ".json", ".yaml", ".yml",
        ".csv", ".tsv", ".ipynb", ".sh", ".bat", ".toml",
    }

    def __init__(
        self,
        workspace_dir: str = "./outputs",
        allowed_extensions: set | None = None,
        forbidden_commands: list | None = None,
        forbidden_file_patterns: list | None = None,
        dry_run: bool = False,
        step_callback: Optional[Callable] = None,
    ):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_extensions = allowed_extensions or self.DEFAULT_ALLOWED_EXTENSIONS
        self.forbidden_commands = forbidden_commands or self.DEFAULT_FORBIDDEN_COMMANDS
        self.forbidden_file_patterns = forbidden_file_patterns or self.DEFAULT_FORBIDDEN_FILE_PATTERNS
        self.dry_run = dry_run
        self.step_callback = step_callback

    def validate_command(self, command: str) -> tuple[bool, str]:
        if not command or not command.strip():
            return True, ""
        lower = command.lower().strip()
        for forbidden in self.forbidden_commands:
            if forbidden.lower() in lower:
                return False, f"Blocked command: matches forbidden pattern '{forbidden}'"
        return True, ""

    def validate_file_path(self, file_path: str) -> tuple[bool, str]:
        if not file_path or not file_path.strip():
            return True, ""
        resolved = Path(file_path)
        try:
            str_resolved = str(resolved.resolve())
        except Exception:
            return False, f"Invalid path: {file_path}"

        for pattern in self.forbidden_file_patterns:
            if pattern in str_resolved:
                return False, f"Blocked file: matches forbidden pattern '{pattern}'"

        try:
            resolved.resolve().relative_to(self.workspace_dir)
        except ValueError:
            if not str_resolved.startswith(str(self.workspace_dir)):
                pass

        ext = resolved.suffix.lower()
        if ext and ext not in self.allowed_extensions:
            return False, f"Blocked file: extension '{ext}' not in allowed list"

        return True, ""

    def validate_plan(self, plan: ExecutionPlan) -> List[str]:
        issues = []

        for cmd in plan.forbidden_commands:
            ok, reason = self.validate_command(cmd)
            if ok:
                issues.append(f"Forbidden command '{cmd}' passed validation (should be blocked)")

        for f in plan.forbidden_files:
            ok, reason = self.validate_file_path(f)
            if ok:
                issues.append(f"Forbidden file '{f}' passed validation (should be blocked)")

        for cmd in plan.allowed_commands:
            ok, reason = self.validate_command(cmd)
            if not ok:
                issues.append(f"Allowed command '{cmd}' was blocked: {reason}")

        for f in plan.allowed_files:
            ok, reason = self.validate_file_path(f)
            if not ok:
                issues.append(f"Allowed file '{f}' was blocked: {reason}")

        return issues

    async def execute_plan(self, plan: ExecutionPlan) -> ExecutionResult:
        result = ExecutionResult(
            plan_title=plan.title,
            steps_total=len(plan.steps),
            steps_completed=0,
            steps_failed=0,
            steps_skipped=0,
        )

        if not plan.steps:
            result.status = "skipped"
            result.error = "No steps in execution plan"
            return result

        for i, step_desc in enumerate(plan.steps):
            step = ExecutionStep(index=i, description=step_desc)

            commands_in_step = self._extract_commands(step_desc)
            files_in_step = self._extract_file_refs(step_desc)

            blocked = False
            for cmd in commands_in_step:
                ok, reason = self.validate_command(cmd)
                if not ok:
                    step.status = "blocked"
                    step.error = reason
                    result.blocked_commands.append(cmd)
                    blocked = True
                    break

            if not blocked:
                for f in files_in_step:
                    ok, reason = self.validate_file_path(f)
                    if not ok:
                        step.status = "blocked"
                        step.error = reason
                        result.blocked_files.append(f)
                        blocked = True
                        break

            if not blocked:
                for forbidden in plan.forbidden_files:
                    if forbidden.lower() in step_desc.lower():
                        step.status = "blocked"
                        step.error = f"Step references forbidden file: '{forbidden}'"
                        result.blocked_files.append(forbidden)
                        blocked = True
                        break

            if blocked:
                result.steps_failed += 1
                result.results.append(step)
                if self.step_callback:
                    self.step_callback(step)
                continue

            if self.dry_run:
                step.status = "dry_run"
                step.output = f"[DRY RUN] Would execute: {step_desc[:200]}"
            else:
                # TODO (P1): Replace this placeholder with real sandboxed
                # subprocess execution.  Currently no commands are run and no
                # files are written -- the step is only validated for safety.
                step.status = "completed"
                step.output = (
                    f"[SIMULATED — NOT ACTUALLY EXECUTED] "
                    f"Step passed safety validation only: {step_desc[:200]}"
                )

            result.steps_completed += 1
            result.results.append(step)
            if self.step_callback:
                self.step_callback(step)

        if result.steps_failed > 0:
            result.status = "partial"
        else:
            result.status = "completed"

        return result

    def _extract_commands(self, text: str) -> List[str]:
        patterns = [
            r'`([^`]+)`',
            r'```(?:bash|sh|shell)?\s*\n([^`]+)```',
            r'\$\s+(.+?)(?:\n|$)',
            r'run:\s*(.+?)(?:\n|$)',
        ]
        commands = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            commands.extend(m.strip() for m in matches if m.strip())
        return commands

    def _extract_file_refs(self, text: str) -> List[str]:
        patterns = [
            r'(?:file|path|create|modify|edit|write|update|change)\s*[=:]\s*`?([^`\s,]+\.\w+)`?',
            r'([a-zA-Z0-9_./\-]+\.(?:json|yaml|yml|toml|cfg|ini|py|js|ts|md|txt))',
            r'(\.[a-zA-Z0-9_]+(?:/[a-zA-Z0-9_.]+)*)',
        ]
        files = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            files.extend(m.strip() for m in matches if m.strip())
        return list(set(files))

    def is_claude_available(self) -> bool:
        return shutil.which("claude") is not None
