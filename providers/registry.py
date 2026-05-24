import asyncio
from typing import Optional

from providers.base import BaseProvider, ProviderHealth
from providers.errors import ProviderNotFoundError


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider, overwrite: bool = False) -> None:
        if name in self._providers and not overwrite:
            raise ValueError(
                f"Provider '{name}' already registered. Use overwrite=True to replace."
            )
        self._providers[name] = provider

    def unregister(self, name: str) -> bool:
        if name in self._providers:
            del self._providers[name]
            return True
        return False

    def get(self, name: str) -> BaseProvider:
        if name not in self._providers:
            raise ProviderNotFoundError(name, list(self._providers.keys()))
        return self._providers[name]

    def has(self, name: str) -> bool:
        return name in self._providers

    def is_registered(self, name: str) -> bool:
        return name in self._providers

    def list_names(self) -> list[str]:
        return list(self._providers.keys())

    def get_all(self) -> dict[str, BaseProvider]:
        return dict(self._providers)

    def clear(self) -> None:
        self._providers.clear()

    async def health_check_all(self) -> dict[str, ProviderHealth]:
        results: dict[str, ProviderHealth] = {}
        tasks = {}
        for name, provider in self._providers.items():
            tasks[name] = asyncio.create_task(provider.health_check())
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                results[name] = ProviderHealth(
                    name=name,
                    provider_type=getattr(self._providers[name], "provider_type", "unknown"),
                    available=False,
                    last_error=str(e)[:200],
                )
        return results

    def get_available_providers(self) -> dict[str, BaseProvider]:
        return {
            name: provider
            for name, provider in self._providers.items()
            if provider.enabled
        }


_default_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ProviderRegistry()
    return _default_registry


def register_provider(name: str, provider: BaseProvider, overwrite: bool = False) -> None:
    get_registry().register(name, provider, overwrite=overwrite)


def get_provider(name: str) -> BaseProvider:
    return get_registry().get(name)
