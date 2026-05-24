import os
import asyncio
import time
import httpx
import uuid
from typing import Optional

from providers.base import BaseProvider, ModelMessage, ModelResponse, ProviderHealth
from providers.errors import (
    ProviderError,
    ProviderTimeoutError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


class OpenAICompatibleProvider(BaseProvider):
    name = "openai_compatible"
    provider_type = "openai_compatible"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        env_prefix: str = "",
        **kwargs,
    ):
        self.api_key = api_key or os.getenv(f"{env_prefix}API_KEY", "")
        self.base_url = (base_url or os.getenv(f"{env_prefix}BASE_URL", "")).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        resolved_model = model or os.getenv(f"{env_prefix}MODEL", "gpt-4.5-mini")
        super().__init__(model=resolved_model, **kwargs)

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        request_id = uuid.uuid4().hex[:8]
        last_error = None

        for attempt in range(self.max_retries + 1):
            resp = await self._do_request(messages, model, temperature, request_id, attempt, **kwargs)
            if resp is not None and resp.error is None:
                return resp
            if resp is not None:
                last_error = resp.error
                if attempt < self.max_retries and resp.error and any(
                    keyword in resp.error.lower()
                    for keyword in ["timeout", "connection", "429", "500", "502", "503", "rate limit"]
                ):
                    wait = (attempt + 1) * 1.5
                    await asyncio.sleep(wait)
                    continue
                return resp

        return ModelResponse(
            content="",
            model=model,
            provider_name=self.name,
            latency_ms=0,
            error=last_error or "All retries exhausted",
        )

    async def _do_request(
        self,
        messages: list[ModelMessage],
        model: str,
        temperature: float,
        request_id: str,
        attempt: int,
        **kwargs,
    ) -> Optional[ModelResponse]:
        start = time.time()
        try:
            payload = {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": temperature,
            }
            payload.update(kwargs)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "X-Request-ID": request_id,
                    },
                    json=payload,
                )

            latency_ms = int((time.time() - start) * 1000)

            if resp.status_code == 401 or resp.status_code == 403:
                self._record_failure(
                    error=f"[HTTP {resp.status_code} Auth] request_id={request_id}",
                    latency_ms=latency_ms,
                )
                return ModelResponse(
                    content="",
                    model=model,
                    provider_name=self.name,
                    latency_ms=latency_ms,
                    error=f"[HTTP {resp.status_code} Auth] request_id={request_id} attempt={attempt}",
                )

            if resp.status_code == 429:
                self._record_failure(
                    error=f"[429 Rate Limit] request_id={request_id}",
                    latency_ms=latency_ms,
                )
                return ModelResponse(
                    content="",
                    model=model,
                    provider_name=self.name,
                    latency_ms=latency_ms,
                    error=f"[429 Rate Limit] request_id={request_id} attempt={attempt}",
                )

            if resp.status_code in (500, 502, 503):
                self._record_failure(
                    error=f"[HTTP {resp.status_code}] request_id={request_id}",
                    latency_ms=latency_ms,
                )
                return ModelResponse(
                    content="",
                    model=model,
                    provider_name=self.name,
                    latency_ms=latency_ms,
                    error=f"[HTTP {resp.status_code}] request_id={request_id} attempt={attempt}: {resp.text[:200]}",
                )

            if resp.status_code != 200:
                self._record_failure(
                    error=f"[HTTP {resp.status_code}] request_id={request_id}",
                    latency_ms=latency_ms,
                )
                return ModelResponse(
                    content="",
                    model=model,
                    provider_name=self.name,
                    latency_ms=latency_ms,
                    error=f"[HTTP {resp.status_code}] request_id={request_id}: {resp.text[:200]}",
                )

            raw = resp.json()
            content = raw["choices"][0]["message"]["content"]
            usage = raw.get("usage", {})

            self._record_success(latency_ms=latency_ms)
            return ModelResponse(
                content=content,
                model=model,
                provider_name=self.name,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                latency_ms=latency_ms,
                metadata={
                    "request_id": request_id,
                    "raw_usage": usage,
                    "attempt": attempt,
                },
            )

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start) * 1000)
            self._record_failure(
                error=f"[Timeout {self.timeout}s] request_id={request_id}",
                latency_ms=latency_ms,
            )
            return ModelResponse(
                content="",
                model=model,
                provider_name=self.name,
                latency_ms=latency_ms,
                error=f"[Timeout {self.timeout}s] request_id={request_id} attempt={attempt}",
            )

        except httpx.ConnectError as e:
            latency_ms = int((time.time() - start) * 1000)
            self._record_failure(
                error=f"[Connection Error] request_id={request_id}: {str(e)[:200]}",
                latency_ms=latency_ms,
            )
            return ModelResponse(
                content="",
                model=model,
                provider_name=self.name,
                latency_ms=latency_ms,
                error=f"[Connection Error] request_id={request_id}: {str(e)[:200]}",
            )

        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            self._record_failure(
                error=f"[Unexpected Error] request_id={request_id}: {str(e)[:200]}",
                latency_ms=latency_ms,
            )
            return ModelResponse(
                content="",
                model=model,
                provider_name=self.name,
                latency_ms=latency_ms,
                error=f"[Unexpected Error] request_id={request_id}: {str(e)[:200]}",
            )

    def classify_error(self, error_str: str) -> ProviderError:
        lower = error_str.lower()
        if "timeout" in lower:
            return ProviderTimeoutError(self.name, self.timeout, detail=error_str)
        if "401" in lower or "403" in lower or "auth" in lower:
            return ProviderAuthenticationError(self.name, detail=error_str)
        if "429" in lower or "rate limit" in lower:
            return ProviderRateLimitError(self.name, detail=error_str)
        if "500" in lower or "502" in lower or "503" in lower or "connection" in lower:
            return ProviderUnavailableError(self.name, detail=error_str)
        return ProviderError(error_str, provider_name=self.name, error_type="unknown")

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
        if not self.api_key or not self.base_url:
            health.available = False
            health.last_error = "Missing API key or base URL"
            health.last_check = time.strftime("%Y-%m-%dT%H:%M:%S")
            return health
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            health.available = resp.status_code == 200
            if not health.available:
                health.last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            health.available = False
            health.last_error = str(e)[:100]
        health.last_check = time.strftime("%Y-%m-%dT%H:%M:%S")
        return health
