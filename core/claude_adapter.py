import asyncio
import json
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

from core.schemas import ExecutionPlan
from core.safe_executor import SafeExecutor, ExecutionResult, ExecutionStep


@dataclass
class ClaudeExecutionResult:
    task_id: str
    success: bool
    raw_output: str = ""
    parsed_output: Optional[dict] = None
    files_created: list = field(default_factory=list)
    files_modified: list = field(default_factory=list)
    duration_sec: float = 0.0
    error: Optional[str] = None
    blocked: bool = False
    blocked_reason: str = ""


class ClaudeAdapter:
    def __init__(
        self,
        workspace_dir: str = "./outputs",
        timeout: int = 300,
        max_retries: int = 1,
        safe_executor: Optional[SafeExecutor] = None,
    ):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries
        self.safe_executor = safe_executor or SafeExecutor(workspace_dir=workspace_dir)
        self._claude_path: Optional[str] = None
        self._detect_claude()

    def _detect_claude(self):
        self._claude_path = shutil.which("claude")
        if self._claude_path:
            print(f"[ClaudeAdapter] claude CLI found: {self._claude_path}")
        else:
            print("[ClaudeAdapter] WARNING: claude CLI not found in PATH")

    def is_available(self) -> bool:
        return self._claude_path is not None

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        task_id: str = "",
        dry_run: bool = False,
    ) -> ClaudeExecutionResult:
        if not task_id:
            task_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_plan"

        validation_issues = self.safe_executor.validate_plan(plan)
        if validation_issues:
            return ClaudeExecutionResult(
                task_id=task_id,
                success=False,
                error=f"Plan validation failed: {'; '.join(validation_issues[:3])}",
                blocked=True,
                blocked_reason="Plan validation failed",
            )

        safe_result = await self.safe_executor.execute_plan(plan)

        if dry_run or not self.is_available():
            return ClaudeExecutionResult(
                task_id=task_id,
                success=safe_result.success,
                raw_output="\n".join(
                    s.output for s in safe_result.results if s.output
                ),
                duration_sec=0.0,
                error=safe_result.error,
                blocked=len(safe_result.blocked_commands) > 0 or len(safe_result.blocked_files) > 0,
                blocked_reason="; ".join(
                    safe_result.blocked_commands + safe_result.blocked_files
                )[:500] if safe_result.blocked_commands or safe_result.blocked_files else "",
            )

        prompt = self._build_prompt(plan)
        return await self._run_claude(prompt, task_id)

    async def execute_task(
        self,
        task: str,
        task_id: str = "",
        timeout: Optional[int] = None,
    ) -> ClaudeExecutionResult:
        if not task_id:
            task_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_task"

        commands = self.safe_executor._extract_commands(task)
        for cmd in commands:
            ok, reason = self.safe_executor.validate_command(cmd)
            if not ok:
                return ClaudeExecutionResult(
                    task_id=task_id,
                    success=False,
                    error=reason,
                    blocked=True,
                    blocked_reason=reason,
                )

        if not self.is_available():
            return ClaudeExecutionResult(
                task_id=task_id,
                success=False,
                error="Claude CLI not available",
            )

        prompt = self._build_task_prompt(task)
        return await self._run_claude(prompt, task_id, timeout=timeout)

    def _build_prompt(self, plan: ExecutionPlan) -> str:
        steps_text = "\n".join(
            f"  {i+1}. {step}" for i, step in enumerate(plan.steps)
        )
        constraints_text = "\n".join(
            f"  - {c}" for c in plan.constraints
        )
        allowed_files_text = ", ".join(plan.allowed_files) if plan.allowed_files else "N/A"
        forbidden_files_text = ", ".join(plan.forbidden_files) if plan.forbidden_files else "N/A"
        allowed_cmds_text = ", ".join(plan.allowed_commands) if plan.allowed_commands else "N/A"
        forbidden_cmds_text = ", ".join(plan.forbidden_commands) if plan.forbidden_commands else "N/A"

        return f"""【执行计划】

目标: {plan.goal}
标题: {plan.title}

步骤:
{steps_text}

约束:
{constraints_text}

安全边界:
- 允许修改的目录: {allowed_files_text}
- 禁止修改的文件: {forbidden_files_text}
- 允许执行的命令: {allowed_cmds_text}
- 禁止执行的命令: {forbidden_cmds_text}

请在工作目录内执行以上步骤。完成后输出JSON格式结果:
{{
  "success": true/false,
  "files_created": ["文件路径列表"],
  "files_modified": ["文件路径列表"],
  "summary": "执行摘要（200字内）",
  "error": "错误信息（如有）"
}}"""

    def _build_task_prompt(self, task: str) -> str:
        return f"""【任务执行】

任务: {task}

安全约束:
- 只能在当前工作目录下创建/修改文件
- 禁止读取或修改 .env、密钥文件、系统目录
- 完成后输出JSON格式结果

输出格式:
{{
  "success": true/false,
  "files_created": ["文件路径列表"],
  "files_modified": ["文件路径列表"],
  "summary": "执行摘要（200字内）",
  "error": "错误信息（如有）"
}}

请开始执行。"""

    async def _run_claude(
        self,
        prompt: str,
        task_id: str,
        timeout: Optional[int] = None,
    ) -> ClaudeExecutionResult:
        if not self._claude_path:
            return ClaudeExecutionResult(
                task_id=task_id,
                success=False,
                error="Claude CLI not found",
            )

        effective_timeout = timeout or self.timeout
        cmd = [self._claude_path, "-p", prompt, "--no-input"]

        task_dir = self.workspace_dir / f"task_{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)

        start = datetime.now()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(task_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=effective_timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                duration = (datetime.now() - start).total_seconds()
                return ClaudeExecutionResult(
                    task_id=task_id,
                    success=False,
                    error=f"Timeout (>{effective_timeout}s)",
                    duration_sec=duration,
                )

            duration = (datetime.now() - start).total_seconds()
            result_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            parsed = None
            try:
                parsed = json.loads(result_text)
            except json.JSONDecodeError:
                json_match = re.search(r'\{[\s\S]*\}', result_text)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass

            files_created = []
            files_modified = []
            if parsed:
                files_created = parsed.get("files_created", [])
                files_modified = parsed.get("files_modified", [])

            for f in files_created + files_modified:
                ok, reason = self.safe_executor.validate_file_path(f)
                if not ok:
                    return ClaudeExecutionResult(
                        task_id=task_id,
                        success=False,
                        raw_output=result_text[:5000],
                        parsed_output=parsed,
                        files_created=files_created,
                        files_modified=files_modified,
                        duration_sec=duration,
                        error=f"Blocked file in output: {f} - {reason}",
                        blocked=True,
                        blocked_reason=reason,
                    )

            success = (parsed.get("success", False) if parsed else proc.returncode == 0)

            return ClaudeExecutionResult(
                task_id=task_id,
                success=success,
                raw_output=result_text[:5000],
                parsed_output=parsed,
                files_created=files_created,
                files_modified=files_modified,
                duration_sec=duration,
                error=parsed.get("error") if parsed and parsed.get("error") else (stderr_text[:500] if stderr_text and not success else None),
            )

        except FileNotFoundError:
            return ClaudeExecutionResult(
                task_id=task_id,
                success=False,
                error="Claude CLI not found",
            )
        except Exception as e:
            duration = (datetime.now() - start).total_seconds()
            return ClaudeExecutionResult(
                task_id=task_id,
                success=False,
                error=str(e)[:500],
                duration_sec=duration,
            )
