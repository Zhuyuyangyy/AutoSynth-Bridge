import pytest
import asyncio

from providers.base import BaseProvider, ModelMessage, ModelResponse, ProviderHealth
from providers.registry import ProviderRegistry
from providers.errors import ProviderNotFoundError


class StubProvider(BaseProvider):
    name = "stub"
    provider_type = "stub"

    def __init__(self, model: str = "stub-model", ok: bool = True, **kwargs):
        super().__init__(model=model, **kwargs)
        self._ok = ok

    async def generate(self, messages, **kwargs):
        if self._ok:
            self._record_success(latency_ms=50)
            return ModelResponse(
                content="stub response",
                model=self.model,
                provider_name=self.name,
                latency_ms=50,
            )
        self._record_failure(error="stub error", latency_ms=50)
        return ModelResponse(
            content="",
            model=self.model,
            provider_name=self.name,
            latency_ms=50,
            error="stub error",
        )


class FailingHealthProvider(StubProvider):
    async def health_check(self):
        health = await super().health_check()
        health.available = False
        health.last_error = "forced failure"
        return health


def test_registry_register_and_get():
    reg = ProviderRegistry()
    p = StubProvider()
    reg.register("stub", p)
    assert reg.get("stub") is p


def test_registry_has():
    reg = ProviderRegistry()
    assert not reg.has("stub")
    reg.register("stub", StubProvider())
    assert reg.has("stub")


def test_registry_get_not_found():
    reg = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError):
        reg.get("nonexistent")


def test_registry_list_names():
    reg = ProviderRegistry()
    reg.register("a", StubProvider())
    reg.register("b", StubProvider())
    assert set(reg.list_names()) == {"a", "b"}


def test_registry_unregister():
    reg = ProviderRegistry()
    reg.register("stub", StubProvider())
    assert reg.unregister("stub") is True
    assert not reg.has("stub")
    assert reg.unregister("stub") is False


def test_registry_clear():
    reg = ProviderRegistry()
    reg.register("a", StubProvider())
    reg.register("b", StubProvider())
    reg.clear()
    assert reg.list_names() == []


def test_registry_duplicate_register_raises():
    reg = ProviderRegistry()
    reg.register("stub", StubProvider())
    with pytest.raises(ValueError, match="already registered"):
        reg.register("stub", StubProvider())


def test_registry_duplicate_register_overwrite():
    reg = ProviderRegistry()
    p1 = StubProvider(model="v1")
    p2 = StubProvider(model="v2")
    reg.register("stub", p1)
    reg.register("stub", p2, overwrite=True)
    assert reg.get("stub").model == "v2"


def test_registry_get_available_providers():
    reg = ProviderRegistry()
    reg.register("ok", StubProvider(enabled=True))
    reg.register("disabled", StubProvider(enabled=False))
    available = reg.get_available_providers()
    assert "ok" in available
    assert "disabled" not in available


@pytest.mark.asyncio
async def test_registry_health_check_all():
    reg = ProviderRegistry()
    reg.register("ok", StubProvider(ok=True))
    reg.register("fail", FailingHealthProvider(ok=True))
    results = await reg.health_check_all()
    assert "ok" in results
    assert "fail" in results
    assert results["fail"].available is False


@pytest.mark.asyncio
async def test_registry_health_check_all_exception():
    class ExplodingProvider(StubProvider):
        async def health_check(self):
            raise RuntimeError("boom")

    reg = ProviderRegistry()
    reg.register("boom", ExplodingProvider())
    results = await reg.health_check_all()
    assert "boom" in results
    assert results["boom"].available is False
    assert "boom" in results["boom"].last_error


def test_registry_get_all():
    reg = ProviderRegistry()
    reg.register("a", StubProvider())
    all_providers = reg.get_all()
    assert "a" in all_providers
    all_providers.clear()
    assert reg.has("a")
