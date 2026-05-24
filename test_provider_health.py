import pytest
import asyncio

from providers.base import BaseProvider, ModelMessage, ModelResponse, ProviderHealth
from providers.registry import ProviderRegistry


class MockProvider(BaseProvider):
    name = "mock"
    provider_type = "mock"

    def __init__(self, model: str = "mock-model", ok: bool = True, **kwargs):
        super().__init__(model=model, **kwargs)
        self._ok = ok

    async def generate(self, messages, **kwargs):
        if self._ok:
            self._record_success(latency_ms=10)
            return ModelResponse(
                content="mock response",
                model=self.model,
                provider_name=self.name,
                latency_ms=10,
            )
        self._record_failure(error="mock error", latency_ms=10)
        return ModelResponse(
            content="",
            model=self.model,
            provider_name=self.name,
            latency_ms=10,
            error="mock error",
        )


def test_provider_health_initial():
    p = MockProvider()
    h = p.get_health_status()
    assert h.name == "mock"
    assert h.provider_type == "mock"
    assert h.total_calls == 0
    assert h.failed_calls == 0


def test_provider_health_after_success():
    p = MockProvider(ok=True)
    result = asyncio.get_event_loop().run_until_complete(
        p.generate([ModelMessage(role="user", content="hi")])
    )
    assert result.ok
    h = p.get_health_status()
    assert h.total_calls == 1
    assert h.failed_calls == 0
    assert h.available is True


def test_provider_health_after_failure():
    p = MockProvider(ok=False)
    result = asyncio.get_event_loop().run_until_complete(
        p.generate([ModelMessage(role="user", content="hi")])
    )
    assert not result.ok
    h = p.get_health_status()
    assert h.total_calls == 1
    assert h.failed_calls == 1
    assert h.available is False
    assert h.last_error == "mock error"


def test_provider_health_success_rate():
    p = MockProvider(ok=True)
    for _ in range(8):
        asyncio.get_event_loop().run_until_complete(
            p.generate([ModelMessage(role="user", content="hi")])
        )
    h = p.get_health_status()
    assert h.success_rate == 1.0


def test_provider_health_to_dict():
    p = MockProvider()
    h = p.get_health_status()
    d = h.to_dict()
    assert "name" in d
    assert "provider_type" in d
    assert "available" in d
    assert "enabled" in d
    assert "total_calls" in d
    assert "failed_calls" in d
    assert "success_rate" in d


def test_provider_enabled_disabled():
    p = MockProvider(enabled=False)
    assert not p.enabled
    h = p.get_health_status()
    assert not h.enabled


@pytest.mark.asyncio
async def test_provider_health_check():
    p = MockProvider()
    h = await p.health_check()
    assert h.name == "mock"
    assert h.last_check is not None


@pytest.mark.asyncio
async def test_registry_health_check_all_stats():
    reg = ProviderRegistry()
    p1 = MockProvider(ok=True)
    p2 = MockProvider(ok=False)
    reg.register("ok_provider", p1)
    reg.register("fail_provider", p2)

    await p1.generate([ModelMessage(role="user", content="hi")])
    await p2.generate([ModelMessage(role="user", content="hi")])

    results = await reg.health_check_all()
    assert results["ok_provider"].total_calls == 1
    assert results["ok_provider"].failed_calls == 0
    assert results["fail_provider"].total_calls == 1
    assert results["fail_provider"].failed_calls == 1
