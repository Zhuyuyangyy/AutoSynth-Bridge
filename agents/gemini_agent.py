"""Gemini Agent - 跨界创新发散者角色（ProviderRouter版）"""
from pathlib import Path
from config import settings
from providers import ProviderRouter

def _load_system_prompt() -> str:
    """从prompts/system_gemini.md加载系统提示词"""
    prompt_file = Path(__file__).parent.parent / "prompts" / "system_gemini.md"
    if prompt_file.exists():
        text = prompt_file.read_text(encoding="utf-8")
        lines = [l for l in text.split("\n") if not l.startswith("# ")]
        return "\n".join(lines).strip()
    return """你是一位跨界创新专家，负责打破常规、提出新颖科研思路。
核心职责：跨学科创新、拆解技术细节、坚持有价值的创新点、补充证据、输出创新性版本。
用【创新发散】开头回复。"""

SYSTEM_PROMPT = _load_system_prompt()


class GeminiAgent:
    """Gemini创新发散 - 使用ProviderRouter"""

    def __init__(self, router: ProviderRouter):
        self.router = router
        self.model = settings.gemini_model
    
    async def generate(self, prompt: str, **kwargs) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        resp = await self.router.chat(
            messages=messages,
            model=self.model,
            temperature=0.9,  # 高温度保证创意
            **kwargs
        )
        if resp.error:
            raise RuntimeError(f"Gemini API error: {resp.error}")
        return resp.content
    
    async def brainstorm(self, query: str, round_num: int) -> str:
        prompt = f"【第{round_num}轮创新发散】针对以下研究主题，进行跨界创新思考：\n\n{query}"
        return await self.generate(prompt)
    
    async def respond(self, gpt_criticism: str, round_num: int) -> str:
        prompt = f"【第{round_num}轮回应】GPT提出了以下质疑，请进行创新性回应：\n\n{gpt_criticism}"
        return await self.generate(prompt)
    
    async def converge(self, gpt_standard: str) -> str:
        prompt = f"【收敛提交】请在以下学术标准框架下，给出创新性最强的最终版本：\n\n{gpt_standard}"
        return await self.generate(prompt)
