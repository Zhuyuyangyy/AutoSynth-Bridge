"""GPT Agent - 学术逻辑裁判角色（ProviderRouter版）"""
from pathlib import Path
from config import settings
from providers import ProviderRouter

def _load_system_prompt() -> str:
    """从prompts/system_gpt.md加载系统提示词"""
    prompt_file = Path(__file__).parent.parent / "prompts" / "system_gpt.md"
    if prompt_file.exists():
        text = prompt_file.read_text(encoding="utf-8")
        # 去掉markdown标题行，保留核心内容
        lines = [l for l in text.split("\n") if not l.startswith("# ")]
        return "\n".join(lines).strip()
    # fallback
    return """你是一位资深的SCI期刊审稿专家（IF>5），负责学术逻辑把关。
核心职责：审查逻辑漏洞、指出学术不合规、反驳创新点可行性、要求证据支撑、输出学术合规方案。
用【学术审查】开头回复。"""

SYSTEM_PROMPT = _load_system_prompt()


class GPTAgent:
    """GPT学术裁判 - 使用ProviderRouter"""

    def __init__(self, router: ProviderRouter):
        self.router = router
        self.model = settings.gpt_model
    
    async def generate(self, prompt: str, **kwargs) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        resp = await self.router.chat(
            messages=messages,
            model=self.model,
            temperature=0.3,
            **kwargs
        )
        if resp.error:
            raise RuntimeError(f"GPT API error: {resp.error}")
        return resp.content
    
    async def review(self, content: str, round_num: int) -> str:
        prompt = f"【第{round_num}轮学术审查】请对以下内容进行审稿式审查：\n\n{content}"
        return await self.generate(prompt)
    
    async def debate(self, gemini_content: str, round_num: int) -> str:
        prompt = f"【第{round_num}轮互搏】Gemini提出了以下观点，请进行学术反驳或认可，并说明理由：\n\n{gemini_content}"
        return await self.generate(prompt)
    
    async def converge(self, gemini_final: str) -> str:
        prompt = f"【收敛提交】请给出符合SCI二区标准的最终学术方案，基于Gemini的创新内容：\n\n{gemini_final}"
        return await self.generate(prompt)
