"""Agent基类 - 统一接口封装"""
import json
from abc import ABC, abstractmethod
from typing import Optional
import httpx

class BaseAgent(ABC):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=60.0)
    
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        pass
    
    async def close(self):
        await self.client.aclose()
    
    def _build_messages(self, system: str, user: str) -> list[dict]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
