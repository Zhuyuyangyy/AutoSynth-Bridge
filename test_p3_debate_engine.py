import pytest
import asyncio
from core.schemas import (
    DebateRequest,
    ConsensusResult,
    ExecutionPlan,
    DebateRole
)
from core.debate_engine import DebateEngine
from core.debate_roles import get_default_role_map
from core.debate_prompts import get_system_prompt_for_role


class MockProvider:
    def __init__(self, name: str, ok: bool = True):
        self.name = name
        self.ok = ok

    async def health_check(self):
        return {
            "name": self.name,
            "available": self.ok,
            "latency_ms": 10
        }

    async def generate(self, messages, **kwargs):
        class Response:
            def __init__(self, ok, content, provider_name):
                self.ok = ok
                self.content = content
                self.model = f"{provider_name}_model"
                self.provider_name = provider_name
                self.latency_ms = 100
                self.error = None if ok else "Mock error"
        content = f"这是 {self.name} 的回应，提到了方案、创新、优化"
        if self.name == "gpt":
            content += "，但是有一些问题和风险需要注意"
        return Response(self.ok, content, self.name)


@pytest.mark.asyncio
async def test_debate_engine_with_roles():
    providers = {
        "gemini": MockProvider("gemini"),
        "gpt": MockProvider("gpt")
    }
    engine = DebateEngine(providers=providers)

    request = DebateRequest(
        query="如何设计一个更好的Agent系统？",
        topic="Agent架构",
        participants=["gemini", "gpt"],
        rounds=2
    )

    result = await engine.run(request, enable_concurrent=False)

    assert result.status == "completed"
    assert result.task_id is not None
    assert len(result.rounds) >= 2
    assert result.consensus is not None
    assert hasattr(result.consensus, "agreement_points")
    assert hasattr(result.consensus, "disagreement_points")
    assert hasattr(result.consensus, "risks")
    assert result.execution_plan is not None


@pytest.mark.asyncio
async def test_debate_engine_concurrent_mode():
    providers = {
        "gemini": MockProvider("gemini"),
        "gpt": MockProvider("gpt"),
        "claude": MockProvider("claude")
    }
    engine = DebateEngine(providers=providers)

    request = DebateRequest(
        query="并发辩论测试",
        topic="并发",
        participants=["gemini", "gpt", "claude"],
        rounds=2
    )

    result = await engine.run(request, enable_concurrent=True)

    assert result.status == "completed"
    assert len(result.rounds) > 5


@pytest.mark.asyncio
async def test_debate_engine_partial_failure():
    providers = {
        "gemini": MockProvider("gemini", ok=True),
        "gpt": MockProvider("gpt", ok=False)
    }
    engine = DebateEngine(providers=providers)

    request = DebateRequest(
        query="测试失败恢复",
        topic="失败恢复",
        participants=["gemini", "gpt"],
        rounds=2
    )

    result = await engine.run(request, enable_concurrent=True)

    assert result.status == "completed"
    assert any("ERROR" in r.content for r in result.rounds)


def test_debate_role_enum():
    assert DebateRole.ARCHITECT == "architect"
    assert DebateRole.CRITIC == "critic"
    assert DebateRole.EXECUTOR == "executor"
    assert DebateRole.RESEARCHER == "researcher"
    assert DebateRole.JUDGE == "judge"


def test_default_role_map():
    role_map = get_default_role_map()
    assert role_map["gemini"] == DebateRole.ARCHITECT
    assert role_map["gpt"] == DebateRole.CRITIC


def test_role_prompts():
    assert "架构" in get_system_prompt_for_role(DebateRole.ARCHITECT)
    assert "风险" in get_system_prompt_for_role(DebateRole.CRITIC)
    assert "步骤" in get_system_prompt_for_role(DebateRole.EXECUTOR)
    assert "资料" in get_system_prompt_for_role(DebateRole.RESEARCHER)
    assert "裁判" in get_system_prompt_for_role(DebateRole.JUDGE)


@pytest.mark.asyncio
async def test_consensus_extraction():
    providers = {
        "gemini": MockProvider("gemini"),
        "gpt": MockProvider("gpt")
    }
    engine = DebateEngine(providers=providers)

    request = DebateRequest(
        query="测试共识提取",
        topic="共识",
        participants=["gemini", "gpt"],
        rounds=2
    )
    result = await engine.run(request)

    assert result.consensus.agreement_points != []
    assert result.consensus.risks != []


@pytest.mark.asyncio
async def test_execution_plan_generation():
    providers = {
        "gemini": MockProvider("gemini"),
        "gpt": MockProvider("gpt")
    }
    engine = DebateEngine(providers=providers)

    request = DebateRequest(
        query="测试执行计划",
        topic="执行计划",
        participants=["gemini", "gpt"],
        rounds=2
    )
    result = await engine.run(request)

    assert result.execution_plan is not None
    assert result.execution_plan.allowed_files is not None
    assert result.execution_plan.forbidden_files is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
