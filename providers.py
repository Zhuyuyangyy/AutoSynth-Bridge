"""LLM Provider抽象层 - 支持多网关OpenAI-compatible接入

.. deprecated::
    This module is **DEPRECATED**.  It contains the legacy ``ProviderRouter``,
    ``LLMProvider``, and ``OpenAICompatibleProvider`` classes that are being
    replaced by the new ``providers/`` package (``ProviderRegistry`` +
    ``BaseProvider`` + ``FallbackChain``).

    All new code MUST use the ``providers/`` package.  This file is kept only
    for backward compatibility with older call-sites that have not yet been
    migrated.  It will be removed in a future release.

    **Migration guide:**
    - ``ProviderRouter`` → ``ProviderRegistry`` (``providers/registry.py``)
    - ``LLMProvider``     → ``BaseProvider``    (``providers/base.py``)
    - ``LLMProvider.chat()`` → ``BaseProvider.generate()``
    - ``LLMResponse``     → ``ModelResponse``   (``providers/base.py``)
"""
import os
import json
import time
import httpx
from abc import ABC, abstractmethod
from typing import Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime
from database import db

@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    raw: dict = field(default_factory=dict)
    error: Optional[str] = None

class LLMProvider(ABC):
    """Provider基类"""
    name: str = "base"
    supports_structured: bool = False
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.extra = kwargs
    
    @abstractmethod
    async def chat(self, messages: list[dict], model: str,
                   temperature: float = 0.7, **kwargs) -> LLMResponse:
        pass
    
    def _log_call(self, model: str, prompt_tokens: int, completion_tokens: int,
                  latency_ms: int, cost_usd: float, error: Optional[str] = None):
        """记录到SQLite"""
        db.log_model_call(
            provider=self.name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            error=error
        )


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible聚合网关（4SAPI/Poe/OpenRouter等）"""
    name = "openai_compatible"
    
    async def chat(self, messages: list[dict], model: str,
                   temperature: float = 0.7, **kwargs) -> LLMResponse:
        start = time.time()
        error = None
        raw = {}
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        **kwargs
                    }
                )
                resp.raise_for_status()
                raw = resp.json()
                
                content = raw["choices"][0]["message"]["content"]
                usage = raw.get("usage", {})
                
                latency_ms = int((time.time() - start) * 1000)
                prompt_tok = usage.get("prompt_tokens", 0)
                completion_tok = usage.get("completion_tokens", 0)
                cost = self._estimate_cost(model, prompt_tok, completion_tok)
                
                self._log_call(model, prompt_tok, completion_tok, latency_ms, cost)
                
                return LLMResponse(
                    content=content,
                    model=model,
                    provider=self.name,
                    prompt_tokens=prompt_tok,
                    completion_tokens=completion_tok,
                    latency_ms=latency_ms,
                    raw=raw
                )
                
        except httpx.HTTPStatusError as e:
            error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        except Exception as e:
            error = str(e)
        
        latency_ms = int((time.time() - start) * 1000)
        self._log_call(model, 0, 0, latency_ms, 0.0, error=error)
        
        return LLMResponse(
            content="",
            model=model,
            provider=self.name,
            error=error,
            raw=raw
        )
    
    def _estimate_cost(self, model: str, prompt_tok: int, completion_tok: int) -> float:
        """按模型估算成本（$/1M tokens）"""
        prices = {
            "gpt-4": (2.5, 10),
            "gpt-4.5-mini": (0.15, 0.6),
            "gpt-3.5-turbo": (0.5, 1.5),
            "claude-sonnet-4": (3.0, 15.0),
            "claude-haiku-4": (0.25, 1.25),
            "gemini-3.1-flash": (0.035, 0.14),
            "gemini-3.1-pro": (1.25, 5.0),
        }
        for key, (in_price, out_price) in prices.items():
            if key in model.lower():
                return prompt_tok / 1_000_000 * in_price + completion_tok / 1_000_000 * out_price
        return 0.0


class ProviderRouter:
    """多Provider路由 + 故障自动转移"""
    
    def __init__(self, providers: dict[str, LLMProvider]):
        # 按优先级排序
        self.providers = providers  # dict of name -> provider
        self.call_stats = {name: {"success": 0, "fail": 0} for name in providers}
    
    async def chat(self, messages: list[dict], model: str,
                   temperature: float = 0.7,
                   preferred_provider: Optional[str] = None,
                   **kwargs) -> LLMResponse:
        """优先用指定provider，失败则自动切换"""
        tried = []
        
        # 优先顺序：指定provider -> 按stats成功率排序
        order = []
        if preferred_provider and preferred_provider in self.providers:
            order.append(preferred_provider)
        order.extend(sorted(
            self.providers.keys(),
            key=lambda n: self.call_stats[n]["success"] / max(1, sum(self.call_stats[n].values())),
            reverse=True
        ))
        
        for name in order:
            if name in tried:
                continue
            tried.append(name)
            
            resp = await self.providers[name].chat(messages, model, temperature, **kwargs)
            
            if resp.error is None:
                self.call_stats[name]["success"] += 1
                return resp
            
            self.call_stats[name]["fail"] += 1
            print(f"[ProviderRouter] {name} failed: {resp.error}, trying next...")
        
        # 全部失败
        return LLMResponse(
            content="", model=model, provider="none",
            error=f"All providers failed. Tried: {tried}"
        )
    
    def get_stats(self) -> dict:
        return {
            name: {"success": s["success"], "fail": s["fail"],
                   "rate": s["success"] / max(1, s["success"] + s["fail"])}
            for name, s in self.call_stats.items()
        }


# ============ 2. SQLite数据库 + 成本日志 ============
