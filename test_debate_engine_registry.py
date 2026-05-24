import pytest
import asyncio

from providers.base import BaseProvider, ModelMessage, ModelResponse
from providers.registry import ProviderRegistry
from core.debate_engine import DebateEngine
from core.schemas import DebateRequest, DebateRole


class MockProvider(BaseProvider):
    name = "mock"
    provider_type = "mock"

    def __init__(self, name_override: str = "mock", ok: bool = True, **kwargs):
        super().__init__(**kwargs)
        self._name_override = name_override
        self._ok = ok

    async def generate(self, messages, **kwargs):
        if self._ok:
            self._record_success(latency_ms=10)
            return ModelResponse(
                content=f"{self._name_override} response about 方案 and 优化",
                model=self.model,
                provider_name=self._name_override,
                latency_ms=10,
            )
        self._record_failure(error="mock error", latency_ms=10)
        return ModelResponse(
            content="",
            model=self.model,
            provider_name=self._name_override,
            latency_ms=10,
            error="mock error",
        )


@pytest.mark.asyncio
async def test_debate_engine_with_registry():
    reg = ProviderRegistry()
    reg.register("gemini", MockProvider(name_override="gemini"))
    reg.register("gpt", MockProvider(name_override="gpt"))
    engine = DebateEngine(registry_or_providers=reg)

    request = DebateRequest(
        query="test registry",
        topic="registry",
        participants=["gemini", "gpt"],
        rounds=1,
    )
    result = await engine.run(request)
    assert result.status == "completed"
    assert len(result.rounds) >= 2


@pytest.mark.asyncio
async def test_debate_engine_registry_missing_provider():
    reg = ProviderRegistry()
    reg.register("gemini", MockProvider(name_override="gemini"))
    engine = DebateEngine(registry_or_providers=reg)

    request = DebateRequest(
        query="test missing",
        topic="missing",
        participants=["gemini", "nonexistent"],
        rounds=1,
    )
    result = await engine.run(request, enable_concurrent=True)
    assert result.status == "completed"
    assert any("nonexistent" in r.participant for r in result.rounds)
    assert any("ERROR" in r.content for r in result.rounds)


@pytest.mark.asyncio
async def test_debate_engine_registry_partial_failure():
    reg = ProviderRegistry()
    reg.register("gemini", MockProvider(name_override="gemini", ok=True))
    reg.register("gpt", MockProvider(name_override="gpt", ok=False))
    engine = DebateEngine(registry_or_providers=reg)

    request = DebateRequest(
        query="test partial failure",
        topic="failure",
        participants=["gemini", "gpt"],
        rounds=1,
    )
    result = await engine.run(request, enable_concurrent=True)
    assert result.status == "completed"
    assert any("ERROR" in r.content for r in result.rounds)


@pytest.mark.asyncio
async def test_debate_engine_dict_backward_compat():
    providers = {
        "gemini": MockProvider(name_override="gemini"),
        "gpt": MockProvider(name_override="gpt"),
    }
    engine = DebateEngine(providers=providers)

    request = DebateRequest(
        query="test dict compat",
        topic="compat",
        participants=["gemini", "gpt"],
        rounds=1,
    )
    result = await engine.run(request)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_debate_engine_participant_with_role():
    reg = ProviderRegistry()
    reg.register("gpt_api", MockProvider(name_override="gpt_api"))
    reg.register("gemini_api", MockProvider(name_override="gemini_api"))
    engine = DebateEngine(registry_or_providers=reg)

    request = DebateRequest(
        query="test role binding",
        topic="roles",
        participants=[
            {"provider": "gpt_api", "role": "critic"},
            {"provider": "gemini_api", "role": "architect"},
        ],
        rounds=1,
    )
    result = await engine.run(request)
    assert result.status == "completed"
    critic_rounds = [r for r in result.rounds if r.role == "critic"]
    architect_rounds = [r for r in result.rounds if r.role == "architect"]
    assert len(critic_rounds) >= 1
    assert len(architect_rounds) >= 1
