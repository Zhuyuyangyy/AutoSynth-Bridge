import pytest
from core.schemas import ExecutionPlan


class TestExecutionPlanSafety:

    def test_has_safety_constraints_true(self):
        plan = ExecutionPlan(
            title="Test",
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        assert plan.has_safety_constraints() is True

    def test_has_safety_constraints_false(self):
        plan = ExecutionPlan(title="Test")
        assert plan.has_safety_constraints() is False

    def test_has_safety_constraints_only_commands(self):
        plan = ExecutionPlan(title="Test", forbidden_commands=["rm -rf"])
        assert plan.has_safety_constraints() is True

    def test_is_step_safe_pass(self):
        plan = ExecutionPlan(
            title="Test",
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        ok, reason = plan.is_step_safe("Create file test.py")
        assert ok is True

    def test_is_step_safe_blocked_command(self):
        plan = ExecutionPlan(
            title="Test",
            forbidden_commands=["rm -rf"],
        )
        ok, reason = plan.is_step_safe("Run rm -rf to clean up")
        assert ok is False
        assert "rm -rf" in reason

    def test_is_step_safe_blocked_file(self):
        plan = ExecutionPlan(
            title="Test",
            forbidden_files=[".env"],
        )
        ok, reason = plan.is_step_safe("Modify .env configuration")
        assert ok is False
        assert ".env" in reason

    def test_is_step_safe_empty_step(self):
        plan = ExecutionPlan(
            title="Test",
            forbidden_commands=["rm -rf"],
            forbidden_files=[".env"],
        )
        ok, reason = plan.is_step_safe("")
        assert ok is True

    def test_execution_plan_backward_compat(self):
        plan = ExecutionPlan(
            title="Compat",
            summary="test summary",
            steps=["step1"],
            constraints=["c1"],
        )
        assert plan.title == "Compat"
        assert plan.summary == "test summary"
        assert len(plan.steps) == 1
        assert plan.allowed_files == []
        assert plan.forbidden_files == []
