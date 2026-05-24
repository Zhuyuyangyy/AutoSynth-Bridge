import pytest
from providers.registry import ProviderRegistry
from providers.errors import ProviderNotFoundError


class DummyProvider:
    name = "dummy"
    model = "d-v1"

    def __init__(self):
        pass

    @property
    def _custom_name(self):
        return "dummy"

    @property
    def name(self):
        return self._custom_name

    async def generate(self, messages, **kwargs):
        from providers.base import ModelResponse
        return ModelResponse(content="ok", model=self.model, provider_name="dummy")


def test_register_and_get():
    reg = ProviderRegistry()
    p = DummyProvider()
    reg.register("foo", p)
    assert reg.get("foo") is p
    assert reg.is_registered("foo")
    assert not reg.is_registered("bar")


def test_get_nonexistent_raises():
    reg = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError) as exc_info:
        reg.get("missing")
    assert "missing" in str(exc_info.value)
    assert "Available" in str(exc_info.value)


def test_list_names():
    reg = ProviderRegistry()
    reg.register("a", DummyProvider())
    reg.register("b", DummyProvider())
    assert set(reg.list_names()) == {"a", "b"}


def test_get_all():
    reg = ProviderRegistry()
    p1 = DummyProvider()
    p2 = DummyProvider()
    reg.register("x", p1)
    reg.register("y", p2)
    all_providers = reg.get_all()
    assert len(all_providers) == 2
    assert all_providers["x"] is p1
    assert all_providers["y"] is p2


def test_unregister():
    reg = ProviderRegistry()
    p = DummyProvider()
    reg.register("z", p)
    assert reg.is_registered("z")
    reg.unregister("z")
    assert not reg.is_registered("z")


def test_unregister_missing():
    reg = ProviderRegistry()
    assert reg.unregister("nonexistent") is False


def test_global_registry_singleton():
    reg = ProviderRegistry()
    import providers.registry as r
    r._default_registry = None
    assert r.get_registry() is r.get_registry()


def test_global_register_and_get():
    import providers.registry as r
    r._default_registry = None
    reg = r.get_registry()
    reg.unregister("gp_test1")
    reg.unregister("gp_test2")
    p1 = DummyProvider()
    p2 = DummyProvider()
    r.register_provider("gp_test1", p1)
    r.register_provider("gp_test2", p2)
    assert r.get_provider("gp_test1") is p1
    assert r.get_provider("gp_test2") is p2
    reg.unregister("gp_test1")
    reg.unregister("gp_test2")
