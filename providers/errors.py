from dataclasses import dataclass
from typing import Optional


@dataclass
class ProviderErrorInfo:
    provider_name: str
    error_type: str
    message: str
    retryable: bool = True


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        provider_name: str = "",
        error_type: str = "unknown",
        retryable: bool = True,
    ):
        super().__init__(message)
        self.provider_name = provider_name
        self.error_type = error_type
        self.retryable = retryable

    def to_info(self) -> ProviderErrorInfo:
        return ProviderErrorInfo(
            provider_name=self.provider_name,
            error_type=self.error_type,
            message=str(self),
            retryable=self.retryable,
        )


class ProviderNotFoundError(ProviderError):
    def __init__(self, name: str, available: list[str] | None = None):
        self.name = name
        self.available = available or []
        msg = f"Provider '{name}' not found. Available: {self.available}"
        super().__init__(
            message=msg,
            provider_name=name,
            error_type="not_found",
            retryable=False,
        )


class ProviderTimeoutError(ProviderError):
    def __init__(self, provider_name: str, timeout: float = 0.0, detail: str = ""):
        msg = f"Provider '{provider_name}' timed out after {timeout}s"
        if detail:
            msg += f": {detail}"
        super().__init__(
            message=msg,
            provider_name=provider_name,
            error_type="timeout",
            retryable=True,
        )
        self.timeout = timeout


class ProviderAuthenticationError(ProviderError):
    def __init__(self, provider_name: str, status_code: int = 0, detail: str = ""):
        msg = f"Provider '{provider_name}' authentication failed (HTTP {status_code})"
        if detail:
            msg += f": {detail}"
        super().__init__(
            message=msg,
            provider_name=provider_name,
            error_type="authentication",
            retryable=False,
        )
        self.status_code = status_code


class ProviderRateLimitError(ProviderError):
    def __init__(self, provider_name: str, status_code: int = 429, detail: str = ""):
        msg = f"Provider '{provider_name}' rate limited (HTTP {status_code})"
        if detail:
            msg += f": {detail}"
        super().__init__(
            message=msg,
            provider_name=provider_name,
            error_type="rate_limit",
            retryable=True,
        )
        self.status_code = status_code


class ProviderUnavailableError(ProviderError):
    def __init__(self, provider_name: str, status_code: int = 0, detail: str = ""):
        msg = f"Provider '{provider_name}' unavailable (HTTP {status_code})"
        if detail:
            msg += f": {detail}"
        super().__init__(
            message=msg,
            provider_name=provider_name,
            error_type="unavailable",
            retryable=True,
        )
        self.status_code = status_code


class DebateEngineError(Exception):
    pass


class TrajectorySaveError(Exception):
    pass
