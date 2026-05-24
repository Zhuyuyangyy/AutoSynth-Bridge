"""Claude Code Executor - 工程落地执行者角色（安全壳版）"""
import subprocess
import json
import os
import asyncio
import shutil
import git
from pathlib import Path
from datetime import datetime
from typing import Optional
from config import settings
from database import db

# 允许的输出扩展名
ALLOWED_EXTENSIONS = {".py", ".md", ".txt", ".json", ".yaml", ".yml",
                      ".csv", ".tsv", ".ipynb", ".sh", ".bat"}
# 禁止的路径关键词
FORBIDDEN_PATTERNS = ["..", "/etc/", "/root/", "/home/", ".env", ".ssh/",
                      "/usr/bin/", "/usr/local/bin/", "password", "secret"]


class ClaudeExecutor:
    """Claude Code执行器 - 带安全壳和重试限制"""
    
    def __init__(self, workspace_dir: str = "./outputs"):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._check_claude_cli()
    
    def _check_claude_cli(self):
        """检查Claude CLI是否存在"""
        result = shutil.which("claude")
        if not result:
            print("[ClaudeExecutor] WARNING: claude CLI not found in PATH")
        else:
            print(f"[ClaudeExecutor] claude CLI: {result}")
    
    def _validate_path(self, path: str) -> bool:
        """验证路径安全"""
        resolved = Path(path).resolve()
        try:
            resolved.resolve().relative_to(self.workspace_dir)
        except ValueError:
            return False  # 路径在workspace之外
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in str(resolved):
                return False
        return True
    
    async def execute_task(self, task: str, task_id: str,
                          timeout: int = None,
                          retry_count: int = 0) -> dict:
        """执行Claude Code任务 - 带安全壳和重试限制"""
        timeout = timeout or settings.claude_code_timeout
        max_retries = settings.claude_code_max_retries
        
        # 超过重试限制
        if retry_count > max_retries:
            return {
                "success": False,
                "error": f"Max retries ({max_retries}) exceeded",
                "task_id": task_id,
                "retry_count": retry_count
            }
        
        # 创建任务目录
        task_dir = self.workspace_dir / f"task_{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 安全检查：确保任务目录在workspace内
        if not _is_subpath(task_dir, self.workspace_dir):
            return {"success": False, "error": "Task directory outside workspace", "task_id": task_id}
        
        # 执行前 git diff 记录（如果目录是git仓库）
        pre_diff = _git_diff(task_dir)
        
        start_time = datetime.now()
        
        # 构造prompt - 强制JSON输出 + 安全约束
        full_prompt = f"""【任务执行】
        
任务：{task}

【安全约束】
- 只能在 {task_dir} 目录下创建/修改文件
- 只允许创建以下类型文件：{', '.join(ALLOWED_EXTENSIONS)}
- 禁止读取或修改 .env、密钥文件、系统目录
- 完成后输出JSON格式结果

【输出格式】
{{
  "success": true/false,
  "files_created": ["相对路径列表"],
  "files_modified": ["相对路径列表"],
  "code": "主要代码（限制5000字符）",
  "data": "实验数据摘要",
  "charts": ["图表路径列表"],
  "summary": "执行摘要（200字内）",
  "error": "错误信息（如有）"
}}

请开始执行。"""
        
        cmd = ["claude", "-p", full_prompt, "--no-input"]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(task_dir)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                duration = (datetime.now() - start_time).total_seconds()
                error_msg = f"Task timeout (>{timeout}s)"
                db.log_claude_execution(
                    run_id=None, task_id=task_id, task=task[:200],
                    task_dir=str(task_dir), success=False, returncode=-1,
                    files_created=[], error=error_msg, duration_sec=duration
                )
                # 超时不重试，直接返回
                return {
                    "success": False,
                    "error": error_msg,
                    "task_id": task_id,
                    "task_dir": str(task_dir),
                    "duration_sec": duration
                }
            
            duration = (datetime.now() - start_time).total_seconds()
            result_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            
            # 执行后 git diff
            post_diff = _git_diff(task_dir)
            
            # 解析JSON
            result_data = None
            parse_error = None
            try:
                result_data = json.loads(result_text)
            except json.JSONDecodeError as e:
                parse_error = str(e)
            
            if result_data is None:
                # JSON解析失败，保存raw_output
                result = {
                    "success": proc.returncode == 0,
                    "raw_output": result_text[:8000],
                    "stderr": stderr_text[:2000],
                    "parse_error": parse_error,
                    "task_id": task_id,
                    "task_dir": str(task_dir),
                    "duration_sec": duration,
                    "files_created": [],
                    "post_diff": post_diff[:500] if post_diff else ""
                }
            else:
                result = result_data
                result["task_id"] = task_id
                result["task_dir"] = str(task_dir)
                result["duration_sec"] = duration
                result["returncode"] = proc.returncode
                result["stderr"] = stderr_text[:1000]
            
            # 验证创建的文件路径
            if "files_created" in result:
                safe_files = [f for f in result["files_created"] if self._validate_path(f)]
                result["files_created"] = safe_files
            
            success = result.get("success", proc.returncode == 0)
            
            db.log_claude_execution(
                run_id=None, task_id=task_id, task=task[:200],
                task_dir=str(task_dir), success=success, returncode=proc.returncode,
                files_created=result.get("files_created", []),
                error=result.get("error", stderr_text[:300] if stderr_text else ""),
                duration_sec=duration
            )
            
            # 自动重试：仅针对资源错误/超时
            if not success and retry_count < max_retries:
                if "resource" in stderr_text.lower() or "rate_limit" in stderr_text.lower():
                    await asyncio.sleep(2 ** retry_count)  # 指数退避
                    return await self.execute_task(task, task_id, timeout, retry_count + 1)
            
            return result
            
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Claude CLI not found. Install from https://docs.anthropic.com/claude-code",
                "task_id": task_id
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            db.log_claude_execution(
                run_id=None, task_id=task_id, task=task[:200],
                task_dir=str(task_dir), success=False, returncode=-1,
                files_created=[], error=str(e), duration_sec=duration
            )
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id,
                "duration_sec": duration
            }
    
    async def execute_batch(self, tasks: list[dict]) -> list[dict]:
        """批量执行任务（串行）"""
        results = []
        for task in tasks:
            result = await self.execute_task(
                task=task.get("task", ""),
                task_id=task.get("id", "unknown")
            )
            results.append(result)
        return results


def _is_subpath(child: Path, parent: Path) -> bool:
    """检查child是否为parent的子目录"""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False

def _git_diff(repo_path: Path) -> str:
    """获取git diff摘要"""
    try:
        repo = git.Repo(repo_path)
        diffs = repo.index.diff(None)
        return ", ".join([d.a_path for d in diffs if d.a_path])
    except Exception:
        return ""
