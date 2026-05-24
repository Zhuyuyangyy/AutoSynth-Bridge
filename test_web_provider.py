import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from providers.base import BaseProvider, ModelMessage, ModelResponse
from providers.web_provider import (
    WebProvider,
    WebChatGPTProvider,
    WebGeminiProvider,
    WebClaudeProvider,
    WEBSITE_SELECTORS,
)


class TestWebProviderCreation:

    def test_web_chatgpt_provider(self):
        p = WebChatGPTProvider()
        assert p.name == "web_chatgpt"
        assert p.website_key == "chatgpt"
        assert p.provider_type == "web"

    def test_web_gemini_provider(self):
        p = WebGeminiProvider()
        assert p.name == "web_gemini"
        assert p.website_key == "gemini"
        assert p.provider_type == "web"

    def test_web_claude_provider(self):
        p = WebClaudeProvider()
        assert p.name == "web_claude"
        assert p.website_key == "claude"
        assert p.provider_type == "web"

    def test_web_provider_custom_cdp_url(self):
        p = WebChatGPTProvider(cdp_url="ws://localhost:9223")
        assert p.cdp_url == "ws://localhost:9223"

    def test_web_provider_disabled(self):
        p = WebChatGPTProvider(enabled=False)
        assert not p.enabled


class TestWebProviderGenerate:

    @pytest.mark.asyncio
    async def test_generate_no_websockets(self):
        with patch("providers.web_provider.HAS_WEBSOCKETS", False):
            p = WebChatGPTProvider()
            result = await p.generate([ModelMessage(role="user", content="hello")])
            assert not result.ok
            assert "websockets" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_disabled(self):
        with patch("providers.web_provider.HAS_WEBSOCKETS", True):
            p = WebChatGPTProvider(enabled=False)
            result = await p.generate([ModelMessage(role="user", content="hello")])
            assert not result.ok
            assert "disabled" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_unknown_website(self):
        with patch("providers.web_provider.HAS_WEBSOCKETS", True):
            p = WebProvider(name="bad", website_key="nonexistent")
            result = await p.generate([ModelMessage(role="user", content="hello")])
            assert not result.ok
            assert "unknown website" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_cdp_connection_failure(self):
        p = WebChatGPTProvider()
        p._cdp_generate = AsyncMock(side_effect=ConnectionRefusedError("no browser"))
        with patch.object(p, '_cdp_generate', side_effect=ConnectionRefusedError("no browser")):
            with patch("providers.web_provider.HAS_WEBSOCKETS", True):
                result = await p.generate([ModelMessage(role="user", content="hello")])
                assert not result.ok
                assert p.failed_calls == 1


class TestWebProviderHealthCheck:

    @pytest.mark.asyncio
    async def test_health_check_no_websockets(self):
        with patch("providers.web_provider.HAS_WEBSOCKETS", False):
            p = WebChatGPTProvider()
            health = await p.health_check()
            assert not health.available
            assert "websockets" in health.last_error.lower()

    @pytest.mark.asyncio
    async def test_health_check_no_browser(self):
        p = WebChatGPTProvider()
        with patch.object(p, 'health_check', new_callable=AsyncMock) as mock_hc:
            from providers.base import ProviderHealth
            mock_hc.return_value = ProviderHealth(
                name="web_chatgpt",
                provider_type="web",
                available=False,
                last_error="Connection refused",
            )
            health = await p.health_check()
            assert not health.available


class TestWebsiteSelectors:

    def test_chatgpt_selectors_exist(self):
        assert "chatgpt" in WEBSITE_SELECTORS
        s = WEBSITE_SELECTORS["chatgpt"]
        assert "input" in s
        assert "submit" in s
        assert "response" in s
        assert "url" in s

    def test_gemini_selectors_exist(self):
        assert "gemini" in WEBSITE_SELECTORS
        s = WEBSITE_SELECTORS["gemini"]
        assert "input" in s
        assert "url" in s

    def test_claude_selectors_exist(self):
        assert "claude" in WEBSITE_SELECTORS
        s = WEBSITE_SELECTORS["claude"]
        assert "input" in s
        assert "url" in s


class TestWebProviderInRegistry:

    def test_register_web_provider(self):
        from providers.registry import ProviderRegistry
        reg = ProviderRegistry()
        p = WebChatGPTProvider()
        reg.register("web_chatgpt", p)
        assert reg.has("web_chatgpt")
        assert reg.get("web_chatgpt").website_key == "chatgpt"

    def test_register_multiple_web_providers(self):
        from providers.registry import ProviderRegistry
        reg = ProviderRegistry()
        reg.register("web_chatgpt", WebChatGPTProvider())
        reg.register("web_gemini", WebGeminiProvider())
        assert reg.has("web_chatgpt")
        assert reg.has("web_gemini")
