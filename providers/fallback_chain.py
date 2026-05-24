import asyncio
from typing import List, Optional

from providers.base import BaseProvider, ModelMessage, ModelResponse, ProviderHealth
from providers.errors import ProviderError


class FallbackChain(BaseProvider):
    name = "fallback_chain"
    provider_type = "fallback_chain"

    def __init__(
        self,
        chain_name: str = "fallback_chain",
        providers: Optional[List[BaseProvider]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._name = chain_name
        self._chain: List[BaseProvider] = providers or []

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    def add_provider(self, provider: BaseProvider, position: int = -1):
        if position == -1:
            self._chain.append(provider)
        else:
            self._chain.insert(position, provider)

    def remove_provider(self, name: str) -> bool:
        for i, p in enumerate(self._chain):
            if p.name == name:
                self._chain.pop(i)
                return True
        return False

    def get_chain(self) -> List[BaseProvider]:
        return list(self._chain)

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        if not self._chain:
            self._record_failure(error="no providers in fallback chain")
            return ModelResponse(
                content="",
                model="fallback_chain",
                provider_name=self.name,
                latency_ms=0,
                error="[FallbackChain] No providers available",
            )

        last_error = None
        for provider in self._chain:
            if not provider.enabled:
                continue

            try:
                result = await provider.generate(messages, **kwargs)
                if result.ok:
                    self._record_success(latency_ms=result.latency_ms)
                    result.provider_name = self.name
                    result.metadata = result.metadata or {}
                    result.metadata["fallback_used"] = provider.name
                    return result
                else:
                    last_error = result.error
            except Exception as e:
                last_error = str(e)[:200]
                continue

        self._record_failure(error=last_error or "all providers failed")
        return ModelResponse(
            content="",
            model="fallback_chain",
            provider_name=self.name,
            latency_ms=0,
            error=f"[FallbackChain] All providers failed. Last error: {last_error}",
        )

    async def health_check(self) -> ProviderHealth:
        health = ProviderHealth(
            name=self.name,
            provider_type=self.provider_type,
            enabled=self.enabled,
            total_calls=self.total_calls,
            failed_calls=self.failed_calls,
            latency_ms=self.last_latency_ms,
            last_error=self.last_error,
        )
        health.last_check = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0

        available = False
        for provider in self._chain:
            if provider.enabled:
                try:
                    ph = await provider.health_check()
                    if ph.available:
                        available = True
                        break
                except Exception:
                    continue

        health.available = available
        return health
