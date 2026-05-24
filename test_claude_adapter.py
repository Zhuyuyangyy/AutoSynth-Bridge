import pytest
import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from core.claude_adapter import ClaudeAdapter, ClaudeExecutionResult
from core.safe_executor import SafeExecutor
from core.schemas import ExecutionPlan

WORKSPACE = os.path.join(os.path.dirname(__file__), "test_workspace_p6_claude")


@pytest.fixture(autouse=True)
def setup_workspace():
    os.makedirs(WORKSPACE, exist_ok=True)
    yield
    import shutil
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE, ignore_errors=True)


@pytest.fixture
def adapter():
    return ClaudeAdapter(workspace_dir=WORKSPACE)


@pytest.fixture
def dry_adapter():
    return ClaudeAdapter(
        workspace_dir=WORKSPACE,
        safe_executor=SafeExecutor(workspace_dir=WORKSPACE),
    )


class TestClaudeAdapterBasic:

    def test_adapter_creation(self, adapter):
        assert adapter.workspace_dir.exists()

    def test_is_available_check(self, adapter):
        result = adapter.is_available()
        assert isinstance(result, bool)


class TestPlanExecutionDryRun:

    @pytest.mark.asyncio
    async def test_execute_plan_dry_run(self, dry_adapter):
        plan = ExecutionPlan(
            title="Test Plan",
            goal="test",
            steps=["Create file test.py", "Run pytest"],
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        result = await dry_adapter.execute_plan(plan, dry_run=True)
        assert isinstance(result, ClaudeExecutionResult)
        assert result.task_id != ""

    @pytest.mark.asyncio
    async def test_execute_plan_blocked(self, dry_adapter):
        plan = ExecutionPlan(
            title="Blocked Plan",
            goal="test",
            steps=["Run `rm -rf /` to clean"],
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        result = await dry_adapter.execute_plan(plan, dry_run=True)
        assert result.blocked is True or result.success is False


class TestTaskExecution:

    @pytest.mark.asyncio
    async def test_execute_task_blocked_command(self, dry_adapter):
        result = await dry_adapter.execute_task(
            task="Run `rm -rf /` to clean everything",
            task_id="test_blocked",
        )
        assert result.blocked is True

    @pytest.mark.asyncio
    async def test_execute_task_safe_command(self, dry_adapter):
        with patch.object(dry_adapter, '_run_claude') as mock_run:
            mock_run.return_value = ClaudeExecutionResult(
                task_id="test_safe",
                success=True,
                raw_output='{"success": true}',
                duration_sec=1.0,
            )
            result = await dry_adapter.execute_task(
                task="Create a test file",
                task_id="test_safe",
            )
            assert result.task_id == "test_safe"


class TestPromptBuilding:

    def test_build_prompt(self, dry_adapter):
        plan = ExecutionPlan(
            title="Test",
            goal="test goal",
            steps=["Step 1", "Step 2"],
            constraints=["Do not delete files"],
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        prompt = dry_adapter._build_prompt(plan)
        assert "test goal" in prompt
        assert "Step 1" in prompt
        assert "rm -rf" in prompt
        assert ".env" in prompt

    def test_build_task_prompt(self, dry_adapter):
        prompt = dry_adapter._build_task_prompt("Write a Python function")
        assert "Write a Python function" in prompt
        assert "JSON" in prompt


class TestClaudeNotAvailable:

    @pytest.mark.asyncio
    async def test_execute_plan_no_claude(self):
        adapter = ClaudeAdapter(workspace_dir=WORKSPACE)
        adapter._claude_path = None
        plan = ExecutionPlan(
            title="No Claude",
            goal="test",
            steps=["Step 1"],
        )
        result = await adapter.execute_plan(plan, dry_run=True)
        assert isinstance(result, ClaudeExecutionResult)
