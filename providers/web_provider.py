import asyncio
import json
import time
from typing import Optional, List
from dataclasses import dataclass

from providers.base import BaseProvider, ModelMessage, ModelResponse, ProviderHealth
from providers.errors import ProviderError, ProviderUnavailableError


HAS_WEBSOCKETS = False
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    pass


WEBSITE_SELECTORS = {
    "chatgpt": {
        "input": "textarea",
        "submit": 'button[data-testid="send-button"]',
        "response": '[data-testid="turn"] .markdown',
        "loading": '.result-streaming',
        "url": "https://chatgpt.com/",
    },
    "gemini": {
        "input": "div[contenteditable='true']",
        "submit": "button.send-button",
        "response": ".message-content",
        "loading": ".loading-indicator",
        "url": "https://gemini.google.com/",
    },
    "claude": {
        "input": '[data-testid="composer-input"]',
        "submit": 'button[aria-label="Send message"]',
        "response": ".claude-message",
        "loading": ".typing-indicator",
        "url": "https://claude.ai/",
    },
}


class WebProvider(BaseProvider):
    provider_type = "web"

    def __init__(
        self,
        name: str,
        website_key: str,
        cdp_url: str = "ws://localhost:9222",
        timeout: int = 120,
        enabled: bool = True,
        **kwargs,
    ):
        super().__init__(enabled=enabled, **kwargs)
        self._name = name
        self.website_key = website_key
        self.cdp_url = cdp_url
        self.timeout = timeout
        self._cdp_connected = False

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        start = time.time()

        if not HAS_WEBSOCKETS:
            self._record_failure(error="websockets not installed")
            return ModelResponse(
                content="",
                model=self.model,
                provider_name=self.name,
                latency_ms=0,
                error="[WebProvider] websockets library not installed. Run: pip install websockets",
            )

        if not self.enabled:
            self._record_failure(error="provider disabled")
            return ModelResponse(
                content="",
                model=self.model,
                provider_name=self.name,
                latency_ms=0,
                error=f"[WebProvider] {self.name} is disabled",
            )

        selectors = WEBSITE_SELECTORS.get(self.website_key)
        if not selectors:
            self._record_failure(error=f"unknown website key: {self.website_key}")
            return ModelResponse(
                content="",
                model=self.model,
                provider_name=self.name,
                latency_ms=0,
                error=f"[WebProvider] Unknown website: {self.website_key}",
            )

        prompt = messages[-1].content if messages else ""

        try:
            result = await self._cdp_generate(prompt, selectors)
            latency_ms = int((time.time() - start) * 1000)
            if result:
                self._record_success(latency_ms=latency_ms)
                return ModelResponse(
                    content=result,
                    model=f"web_{self.website_key}",
                    provider_name=self.name,
                    latency_ms=latency_ms,
                )
            else:
                self._record_failure(error="empty response from web", latency_ms=latency_ms)
                return ModelResponse(
                    content="",
                    model=f"web_{self.website_key}",
                    provider_name=self.name,
                    latency_ms=latency_ms,
                    error="[WebProvider] Empty response from web interface",
                )
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            self._record_failure(error=str(e)[:200], latency_ms=latency_ms)
            return ModelResponse(
                content="",
                model=f"web_{self.website_key}",
                provider_name=self.name,
                latency_ms=latency_ms,
                error=f"[WebProvider] {str(e)[:200]}",
            )

    async def _cdp_generate(self, prompt: str, selectors: dict) -> Optional[str]:
        try:
            async with websockets.connect(self.cdp_url, max_size=10 * 1024 * 1024) as ws:
                targets = await self._cdp_list_targets(ws)
                target_id = None
                for t in targets:
                    if selectors["url"].rstrip("/") in t.get("url", ""):
                        target_id = t["id"]
                        break

                if not target_id and targets:
                    target_id = targets[0]["id"]

                if not target_id:
                    return None

                ws_url = None
                for t in targets:
                    if t["id"] == target_id:
                        ws_url = t.get("webSocketDebuggerUrl")
                        break

                if not ws_url:
                    return None

                async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as page_ws:
                    msg_id = 1

                    await page_ws.send(json.dumps({
                        "id": msg_id,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": f"""
                                (function() {{
                                    const input = document.querySelector('{selectors["input"]}');
                                    if (!input) return 'INPUT_NOT_FOUND';
                                    input.focus();
                                    input.value = {json.dumps(prompt)};
                                    input.dispatchEvent(new Event('input', {{bubbles: true}}));
                                    return 'OK';
                                }})()
                            """,
                            "returnByValue": True,
                        },
                    }))
                    msg_id += 1

                    await asyncio.sleep(1)

                    submit_js = f"""
                        (function() {{
                            const btn = document.querySelector('{selectors["submit"]}');
                            if (btn) {{ btn.click(); return 'CLICKED'; }}
                            const input = document.querySelector('{selectors["input"]}');
                            if (input) {{ input.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}})); return 'ENTER_SENT'; }}
                            return 'NO_SUBMIT';
                        }})()
                    """
                    await page_ws.send(json.dumps({
                        "id": msg_id,
                        "method": "Runtime.evaluate",
                        "params": {"expression": submit_js, "returnByValue": True},
                    }))
                    msg_id += 1

                    for _ in range(self.timeout // 3):
                        await asyncio.sleep(3)
                        check_js = f"""
                            (function() {{
                                const loading = document.querySelector('{selectors["loading"]}');
                                if (loading) return 'LOADING';
                                const responses = document.querySelectorAll('{selectors["response"]}');
                                if (responses.length > 0) return responses[responses.length - 1].innerText;
                                return 'NO_RESPONSE';
                            }})()
                        """
                        await page_ws.send(json.dumps({
                            "id": msg_id,
                            "method": "Runtime.evaluate",
                            "params": {"expression": check_js, "returnByValue": True},
                        }))
                        msg_id += 1

                        try:
                            resp = await asyncio.wait_for(page_ws.recv(), timeout=5)
                            data = json.loads(resp)
                            result = data.get("result", {}).get("result", {}).get("value", "")
                            if result and result not in ("LOADING", "NO_RESPONSE", "INPUT_NOT_FOUND"):
                                return str(result)[:10000]
                        except (asyncio.TimeoutError, json.JSONDecodeError):
                            pass

                    return None

        except Exception as e:
            raise ProviderUnavailableError(self.name, detail=str(e)[:200])

    async def _cdp_list_targets(self, ws) -> list:
        await ws.send(json.dumps({"id": 1, "method": "Target.getTargets"}))
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(resp)
            return data.get("result", {}).get("targetInfos", [])
        except Exception:
            return []

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
        health.last_check = time.strftime("%Y-%m-%dT%H:%M:%S")

        if not HAS_WEBSOCKETS:
            health.available = False
            health.last_error = "websockets not installed"
            return health

        try:
            async with websockets.connect(self.cdp_url, max_size=1024 * 1024) as ws:
                targets = await self._cdp_list_targets(ws)
                health.available = len(targets) > 0
                if not health.available:
                    health.last_error = "No browser targets found"
        except Exception as e:
            health.available = False
            health.last_error = str(e)[:100]

        return health


class WebChatGPTProvider(WebProvider):
    def __init__(self, cdp_url: str = "ws://localhost:9222", timeout: int = 120, **kwargs):
        super().__init__(
            name="web_chatgpt",
            website_key="chatgpt",
            cdp_url=cdp_url,
            timeout=timeout,
            **kwargs,
        )


class WebGeminiProvider(WebProvider):
    def __init__(self, cdp_url: str = "ws://localhost:9222", timeout: int = 120, **kwargs):
        super().__init__(
            name="web_gemini",
            website_key="gemini",
            cdp_url=cdp_url,
            timeout=timeout,
            **kwargs,
        )


class WebClaudeProvider(WebProvider):
    def __init__(self, cdp_url: str = "ws://localhost:9222", timeout: int = 120, **kwargs):
        super().__init__(
            name="web_claude",
            website_key="claude",
            cdp_url=cdp_url,
            timeout=timeout,
            **kwargs,
        )
