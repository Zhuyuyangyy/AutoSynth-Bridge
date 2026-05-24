from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ModelMessage:
    role: str
    content: str


@dataclass
class ModelResponse:
    content: str
    model: str
    provider_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class ProviderHealth:
    name: str
    provider_type: str = ""
    available: bool = False
    enabled: bool = True
    last_error: Optional[str] = None
    last_check: Optional[str] = None
    latency_ms: int = 0
    total_calls: int = 0
    failed_calls: int = 0
    success_count: int = 0
    fail_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.total_calls
        if total == 0:
            total = self.success_count + self.fail_count
        return (total - self.failed_calls) / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "provider_type": self.provider_type,
            "available": self.available,
            "enabled": self.enabled,
            "last_error": self.last_error,
            "last_check": self.last_check,
            "latency_ms": self.latency_ms,
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 3),
        }


class BaseProvider(ABC):
    name: str = "base"
    provider_type: str = "base"

    def __init__(self, model: str = "", enabled: bool = True, **kwargs):
        self.model = model
        self.enabled = enabled
        self.last_error: Optional[str] = None
        self.last_latency_ms: int = 0
        self.total_calls: int = 0
        self.failed_calls: int = 0
        self._health: Optional[ProviderHealth] = None

    def _ensure_health(self) -> ProviderHealth:
        if self._health is None:
            provider_name = self.__class__.name if isinstance(self.__class__.name, str) else self.name
            self._health = ProviderHealth(
                name=str(provider_name),
                provider_type=self.provider_type,
                enabled=self.enabled,
            )
        return self._health

    @abstractmethod
    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        pass

    async def health_check(self) -> ProviderHealth:
        health = self._ensure_health()
        health.last_check = datetime.now().isoformat()
        health.total_calls = self.total_calls
        health.failed_calls = self.failed_calls
        health.latency_ms = self.last_latency_ms
        health.last_error = self.last_error
        return health

    def get_health_status(self) -> ProviderHealth:
        return self._ensure_health()

    def _record_success(self, latency_ms: int = 0):
        self._ensure_health()
        self.total_calls += 1
        self.last_latency_ms = latency_ms
        self._health.success_count += 1
        self._health.available = True
        self._health.total_calls = self.total_calls
        self._health.failed_calls = self.failed_calls
        self._health.latency_ms = latency_ms
        self.last_error = None

    def _record_failure(self, error: str = "", latency_ms: int = 0):
        self._ensure_health()
        self.total_calls += 1
        self.failed_calls += 1
        self.last_latency_ms = latency_ms
        self.last_error = error or "unknown error"
        self._health.fail_count += 1
        self._health.available = False
        self._health.total_calls = self.total_calls
        self._health.failed_calls = self.failed_calls
        self._health.last_error = self.last_error
        self._health.latency_ms = latency_ms

    @property
    def health(self) -> ProviderHealth:
        return self._ensure_health()
