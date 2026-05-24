import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from providers.errors import (
    ProviderError,
    ProviderNotFoundError,
    ProviderTimeoutError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ProviderErrorInfo,
)


def test_provider_error_base():
    err = ProviderError("test error", provider_name="test", error_type="unknown", retryable=True)
    assert str(err) == "test error"
    assert err.provider_name == "test"
    assert err.error_type == "unknown"
    assert err.retryable is True


def test_provider_not_found_error():
    err = ProviderNotFoundError("missing", available=["a", "b"])
    assert "missing" in str(err)
    assert err.available == ["a", "b"]
    assert err.retryable is False
    assert err.error_type == "not_found"


def test_provider_timeout_error():
    err = ProviderTimeoutError("gpt", timeout=30.0, detail="slow")
    assert "timed out" in str(err)
    assert err.timeout == 30.0
    assert err.retryable is True
    assert err.error_type == "timeout"


def test_provider_authentication_error():
    err = ProviderAuthenticationError("gpt", status_code=401)
    assert "authentication" in str(err).lower()
    assert err.status_code == 401
    assert err.retryable is False
    assert err.error_type == "authentication"


def test_provider_rate_limit_error():
    err = ProviderRateLimitError("gpt", status_code=429)
    assert "rate limit" in str(err).lower()
    assert err.retryable is True
    assert err.error_type == "rate_limit"


def test_provider_unavailable_error():
    err = ProviderUnavailableError("gpt", status_code=503)
    assert "unavailable" in str(err).lower()
    assert err.retryable is True
    assert err.error_type == "unavailable"


def test_provider_error_to_info():
    err = ProviderTimeoutError("gpt", timeout=10.0)
    info = err.to_info()
    assert isinstance(info, ProviderErrorInfo)
    assert info.provider_name == "gpt"
    assert info.error_type == "timeout"
    assert info.retryable is True


def test_provider_not_found_backward_compat():
    err = ProviderNotFoundError("x", ["a"])
    assert "x" in str(err)
    assert err.name == "x"
