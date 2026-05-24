import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from providers.openai_compatible import OpenAICompatibleProvider
from providers.base import ModelMessage
from providers.errors import (
    ProviderTimeoutError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


def _make_messages():
    return [ModelMessage(role="user", content="test")]


def test_classify_timeout():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m")
    err = p.classify_error("[Timeout 60s] request_id=abc")
    assert isinstance(err, ProviderTimeoutError)


def test_classify_auth():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m")
    err = p.classify_error("[HTTP 401 Auth] request_id=abc")
    assert isinstance(err, ProviderAuthenticationError)


def test_classify_rate_limit():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m")
    err = p.classify_error("[429 Rate Limit] request_id=abc")
    assert isinstance(err, ProviderRateLimitError)


def test_classify_unavailable():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m")
    err = p.classify_error("[HTTP 503] request_id=abc")
    assert isinstance(err, ProviderUnavailableError)


def test_classify_connection_error():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m")
    err = p.classify_error("[Connection Error] request_id=abc")
    assert isinstance(err, ProviderUnavailableError)


def test_classify_unknown():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m")
    err = p.classify_error("some random error")
    assert err.error_type == "unknown"


@pytest.mark.asyncio
async def test_http_401_returns_error():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m", max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    with patch("httpx.AsyncClient") as mock_client:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = instance
        result = await p.generate(_make_messages())
        assert not result.ok
        assert "401" in result.error or "Auth" in result.error
        assert p.failed_calls == 1


@pytest.mark.asyncio
async def test_http_429_returns_error():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m", max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate Limited"
    with patch("httpx.AsyncClient") as mock_client:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = instance
        result = await p.generate(_make_messages())
        assert not result.ok
        assert "429" in result.error or "Rate Limit" in result.error


@pytest.mark.asyncio
async def test_http_500_returns_error():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m", max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    with patch("httpx.AsyncClient") as mock_client:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = instance
        result = await p.generate(_make_messages())
        assert not result.ok
        assert "500" in result.error


@pytest.mark.asyncio
async def test_timeout_returns_error():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m", max_retries=0)
    with patch("httpx.AsyncClient") as mock_client:
        instance = AsyncMock()
        instance.post.side_effect = httpx.TimeoutException("timeout")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = instance
        result = await p.generate(_make_messages())
        assert not result.ok
        assert "Timeout" in result.error or "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_connection_error_returns_error():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m", max_retries=0)
    with patch("httpx.AsyncClient") as mock_client:
        instance = AsyncMock()
        instance.post.side_effect = httpx.ConnectError("connection refused")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = instance
        result = await p.generate(_make_messages())
        assert not result.ok
        assert "Connection" in result.error


@pytest.mark.asyncio
async def test_success_records_stats():
    p = OpenAICompatibleProvider(api_key="k", base_url="http://x", model="m", max_retries=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    with patch("httpx.AsyncClient") as mock_client:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = instance
        result = await p.generate(_make_messages())
        assert result.ok
        assert p.total_calls == 1
        assert p.failed_calls == 0
        assert p.last_latency_ms >= 0
