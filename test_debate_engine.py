import pytest
import asyncio
from providers.base import BaseProvider, ModelMessage, ModelResponse
from providers.registry import ProviderRegistry
from providers.errors import ProviderNotFoundError
from core.debate_engine import DebateEngine
from core.schemas import DebateRequest


class MockProvider(BaseProvider):
    def __init__(self, name: str = "mock", responses: list[str] = None):
        super().__init__(model="mock-v1")
        self._name = name
        self._responses = responses or ["mock response"]
        self._call_count = 0

    @property
    def name(self):
        return self._name

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        idx = min(self._call_count, len(self._responses) - 1)
        content = self._responses[idx]
        self._call_count += 1
        self._record_success()
        return ModelResponse(
            content=content,
            model=self.model,
            provider_name=self._name,
            latency_ms=10,
        )


@pytest.mark.asyncio
async def test_debate_engine_two_providers_two_rounds():
    gpt = MockProvider("gpt", responses=["GPT initial view", "GPT round 1", "GPT round 2"])
    gemini = MockProvider("gemini", responses=["Gemini initial", "Gemini round 1", "Gemini round 2"])

    engine = DebateEngine(registry_or_providers={"gpt": gpt, "gemini": gemini})
    req = DebateRequest(
        query="分析中医RAG创新方向",
        topic="中医RAG",
        participants=["gpt", "gemini"],
        rounds=2,
    )

    result = await engine.run(req)

    assert result.status == "completed"
    assert result.error is None
    assert len(result.rounds) > 0
    assert result.consensus is not None
    assert result.task_id


@pytest.mark.asyncio
async def test_debate_engine_result_has_consensus():
    gpt = MockProvider("gpt", responses=["innovation novel approach experiment data"])
    gemini = MockProvider("gemini", responses=["innovation novel approach experiment data"])

    engine = DebateEngine(registry_or_providers={"gpt": gpt, "gemini": gemini})
    req = DebateRequest(query="test", topic="test", participants=["gpt", "gemini"], rounds=1)

    result = await engine.run(req)
    assert result.consensus is not None
    assert isinstance(result.consensus.consistency_score, float)
    assert 0.0 <= result.consensus.consistency_score <= 1.0


@pytest.mark.asyncio
async def test_debate_engine_missing_provider_graceful():
    engine = DebateEngine(registry_or_providers={"gpt": MockProvider("gpt")})
    req = DebateRequest(query="test", topic="test", participants=["gpt", "gemini"], rounds=1)
    result = await engine.run(req)
    assert result.status == "completed"
    assert any("ERROR" in r.content for r in result.rounds)


@pytest.mark.asyncio
async def test_debate_engine_single_provider():
    engine = DebateEngine(registry_or_providers={"gpt": MockProvider("gpt")})
    req = DebateRequest(query="test", topic="test", participants=["gpt"], rounds=1)
    result = await engine.run(req)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_debate_engine_rounds_have_correct_participants():
    gpt = MockProvider("gpt", responses=["gpt resp"] * 5)
    gemini = MockProvider("gemini", responses=["gemini resp"] * 5)

    engine = DebateEngine(registry_or_providers={"gpt": gpt, "gemini": gemini})
    req = DebateRequest(query="test", topic="test", participants=["gpt", "gemini"], rounds=2)

    result = await engine.run(req)

    participants_in_rounds = {r.participant for r in result.rounds}
    assert "gpt" in participants_in_rounds
    assert "gemini" in participants_in_rounds


@pytest.mark.asyncio
async def test_debate_engine_execution_plan_generated():
    gpt = MockProvider("gpt", responses=["innovation novel experiment data approach method"])
    gemini = MockProvider("gemini", responses=["innovation novel experiment data approach method"])

    engine = DebateEngine(registry_or_providers={"gpt": gpt, "gemini": gemini})
    req = DebateRequest(query="test", topic="test", participants=["gpt", "gemini"], rounds=1)

    result = await engine.run(req)
    if result.consensus and (result.consensus.converged or not result.consensus.need_human_review):
        assert result.execution_plan is not None
        assert result.execution_plan.title
        assert len(result.execution_plan.steps) > 0
