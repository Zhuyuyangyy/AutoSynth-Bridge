import pytest
import asyncio
from providers.base import BaseProvider, ModelMessage, ModelResponse, ProviderHealth


class StubProvider(BaseProvider):
    name = "stub"

    def __init__(self, model: str = "stub-v1", response_text: str = "hello"):
        super().__init__(model=model)
        self.response_text = response_text

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        return ModelResponse(
            content=self.response_text,
            model=self.model,
            provider_name=self.name,
        )


class FailingProvider(BaseProvider):
    name = "failing"

    def __init__(self, model: str = "fail-v1"):
        super().__init__(model=model)

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        self._record_failure()
        return ModelResponse(
            content="",
            model=self.model,
            provider_name=self.name,
            error="intentional failure",
        )


@pytest.mark.asyncio
async def test_stub_provider_returns_ok():
    p = StubProvider(response_text="world")
    msgs = [ModelMessage(role="user", content="hi")]
    resp = await p.generate(msgs)
    assert resp.ok
    assert resp.content == "world"
    assert resp.provider_name == "stub"


@pytest.mark.asyncio
async def test_failing_provider_returns_error():
    p = FailingProvider()
    msgs = [ModelMessage(role="user", content="hi")]
    resp = await p.generate(msgs)
    assert not resp.ok
    assert resp.error == "intentional failure"


@pytest.mark.asyncio
async def test_provider_health_tracking():
    p = StubProvider()
    p._record_success()
    p._record_success()
    p._record_failure()
    h = p.health
    assert h.success_count == 2
    assert h.fail_count == 1
    assert abs(h.success_rate - 2 / 3) < 0.01


@pytest.mark.asyncio
async def test_model_message_dataclass():
    m = ModelMessage(role="system", content="test")
    assert m.role == "system"
    assert m.content == "test"


@pytest.mark.asyncio
async def test_model_response_ok_property():
    ok_resp = ModelResponse(content="hi", model="m", provider_name="p")
    assert ok_resp.ok
    err_resp = ModelResponse(content="", model="m", provider_name="p", error="fail")
    assert not err_resp.ok


@pytest.mark.asyncio
async def test_provider_health_check():
    p = StubProvider()
    health = await p.health_check()
    assert isinstance(health, ProviderHealth)
    assert health.name == "stub"
    assert health.last_check is not None
