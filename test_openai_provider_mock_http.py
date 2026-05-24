import pytest
from unittest.mock import patch, AsyncMock
import httpx

from providers.openai_compatible import OpenAICompatibleProvider
from providers.base import ModelMessage


@pytest.fixture
def provider():
    return OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        timeout=5.0,
        max_retries=2,
    )


@pytest.mark.asyncio
async def test_successful_response(provider):
    mock_response = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Hello world"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        resp = await provider.generate([ModelMessage(role="user", content="hi")])

    assert resp.ok
    assert resp.content == "Hello world"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert "request_id" in resp.metadata


@pytest.mark.asyncio
async def test_http_429_returns_error():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        max_retries=0,
    )
    mock_response = httpx.Response(429, text="rate limited")
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        resp = await provider.generate([ModelMessage(role="user", content="hi")])

    assert not resp.ok
    assert "429" in resp.error


@pytest.mark.asyncio
async def test_http_500_returns_error():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        max_retries=0,
    )
    mock_response = httpx.Response(500, text="server error")
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        resp = await provider.generate([ModelMessage(role="user", content="hi")])

    assert not resp.ok
    assert "500" in resp.error


@pytest.mark.asyncio
async def test_timeout_returns_error():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        timeout=0.001,
        max_retries=0,
    )
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("timed out")
        resp = await provider.generate([ModelMessage(role="user", content="hi")])

    assert not resp.ok
    assert "Timeout" in resp.error


@pytest.mark.asyncio
async def test_connection_error_returns_error():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        max_retries=0,
    )
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("connection refused")
        resp = await provider.generate([ModelMessage(role="user", content="hi")])

    assert not resp.ok
    assert "Connection Error" in resp.error


@pytest.mark.asyncio
async def test_retry_on_429():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        max_retries=2,
    )

    mock_429 = httpx.Response(429, text="rate limited")
    mock_200 = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "success after retry"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        },
    )
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [mock_429, mock_200]
        with patch("providers.openai_compatible.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            resp = await provider.generate([ModelMessage(role="user", content="hi")])

    assert resp.ok
    assert resp.content == "success after retry"
    assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        max_retries=1,
    )

    mock_500 = httpx.Response(500, text="error")
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [mock_500, mock_500]
        resp = await provider.generate([ModelMessage(role="user", content="hi")])

    assert not resp.ok
    assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_health_check_success():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
    )
    mock_response = httpx.Response(200, json={"data": []})
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        health = await provider.health_check()

    assert health.available is True
    assert health.name == "openai_compatible"


@pytest.mark.asyncio
async def test_health_check_failure():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
    )
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("network error")
        health = await provider.health_check()

    assert health.available is False
    assert "network error" in health.last_error
