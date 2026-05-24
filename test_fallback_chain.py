import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from providers.base import BaseProvider, ModelMessage, ModelResponse
from providers.fallback_chain import FallbackChain


class OkProvider(BaseProvider):
    name = "ok_provider"
    provider_type = "mock"

    def __init__(self, content: str = "ok response", **kwargs):
        super().__init__(**kwargs)
        self._content = content

    async def generate(self, messages, **kwargs):
        self._record_success(latency_ms=10)
        return ModelResponse(
            content=self._content,
            model="mock",
            provider_name=self.name,
            latency_ms=10,
        )


class FailProvider(BaseProvider):
    name = "fail_provider"
    provider_type = "mock"

    async def generate(self, messages, **kwargs):
        self._record_failure(error="mock failure", latency_ms=10)
        return ModelResponse(
            content="",
            model="mock",
            provider_name=self.name,
            latency_ms=10,
            error="mock failure",
        )


class ExceptionProvider(BaseProvider):
    name = "exception_provider"
    provider_type = "mock"

    async def generate(self, messages, **kwargs):
        raise RuntimeError("provider crashed")


class TestFallbackChainBasic:

    def test_create_empty_chain(self):
        chain = FallbackChain()
        assert chain.name == "fallback_chain"
        assert len(chain.get_chain()) == 0

    def test_create_named_chain(self):
        chain = FallbackChain(chain_name="gpt_fallback")
        assert chain.name == "gpt_fallback"

    def test_add_provider(self):
        chain = FallbackChain()
        chain.add_provider(OkProvider())
        assert len(chain.get_chain()) == 1

    def test_add_provider_at_position(self):
        chain = FallbackChain()
        chain.add_provider(OkProvider(content="first"))
        chain.add_provider(OkProvider(content="second"), position=0)
        assert len(chain.get_chain()) == 2
        assert chain.get_chain()[0]._content == "second"

    def test_remove_provider(self):
        chain = FallbackChain()
        chain.add_provider(OkProvider())
        assert chain.remove_provider("ok_provider") is True
        assert len(chain.get_chain()) == 0

    def test_remove_nonexistent_provider(self):
        chain = FallbackChain()
        assert chain.remove_provider("nonexistent") is False


class TestFallbackChainGenerate:

    @pytest.mark.asyncio
    async def test_first_provider_succeeds(self):
        chain = FallbackChain()
        chain.add_provider(OkProvider())
        result = await chain.generate([ModelMessage(role="user", content="hi")])
        assert result.ok
        assert result.content == "ok response"

    @pytest.mark.asyncio
    async def test_fallback_to_second_provider(self):
        chain = FallbackChain()
        chain.add_provider(FailProvider())
        chain.add_provider(OkProvider(content="fallback response"))
        result = await chain.generate([ModelMessage(role="user", content="hi")])
        assert result.ok
        assert result.content == "fallback response"
        assert result.metadata.get("fallback_used") == "ok_provider"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        chain = FallbackChain()
        chain.add_provider(FailProvider())
        chain.add_provider(FailProvider())
        result = await chain.generate([ModelMessage(role="user", content="hi")])
        assert not result.ok
        assert "All providers failed" in result.error

    @pytest.mark.asyncio
    async def test_empty_chain(self):
        chain = FallbackChain()
        result = await chain.generate([ModelMessage(role="user", content="hi")])
        assert not result.ok
        assert "No providers" in result.error

    @pytest.mark.asyncio
    async def test_skip_disabled_provider(self):
        chain = FallbackChain()
        chain.add_provider(OkProvider(enabled=False))
        chain.add_provider(OkProvider(content="enabled response"))
        result = await chain.generate([ModelMessage(role="user", content="hi")])
        assert result.ok
        assert result.content == "enabled response"

    @pytest.mark.asyncio
    async def test_exception_provider_falls_through(self):
        chain = FallbackChain()
        chain.add_provider(ExceptionProvider())
        chain.add_provider(OkProvider(content="recovered"))
        result = await chain.generate([ModelMessage(role="user", content="hi")])
        assert result.ok
        assert result.content == "recovered"

    @pytest.mark.asyncio
    async def test_three_level_fallback(self):
        chain = FallbackChain()
        chain.add_provider(FailProvider())
        chain.add_provider(ExceptionProvider())
        chain.add_provider(OkProvider(content="third level"))
        result = await chain.generate([ModelMessage(role="user", content="hi")])
        assert result.ok
        assert result.content == "third level"


class TestFallbackChainInRegistry:

    def test_register_fallback_chain(self):
        from providers.registry import ProviderRegistry
        reg = ProviderRegistry()
        chain = FallbackChain(chain_name="gpt_chain")
        chain.add_provider(OkProvider())
        reg.register("gpt_chain", chain)
        assert reg.has("gpt_chain")

    @pytest.mark.asyncio
    async def test_debate_engine_with_fallback_chain(self):
        from providers.registry import ProviderRegistry
        from core.debate_engine import DebateEngine
        from core.schemas import DebateRequest

        reg = ProviderRegistry()

        chain1 = FallbackChain(chain_name="gpt_chain")
        chain1.add_provider(OkProvider(content="gpt response about 方案 and 优化"))
        reg.register("gpt_chain", chain1)

        chain2 = FallbackChain(chain_name="gemini_chain")
        chain2.add_provider(OkProvider(content="gemini response about 方案 and 优化"))
        reg.register("gemini_chain", chain2)

        engine = DebateEngine(registry_or_providers=reg)
        request = DebateRequest(
            query="test fallback",
            topic="fallback",
            participants=["gpt_chain", "gemini_chain"],
            rounds=1,
        )
        result = await engine.run(request)
        assert result.status == "completed"
