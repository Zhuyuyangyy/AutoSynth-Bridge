"""
Humanize - SCI论文人味化降重模块

通过LLM驱动的多层改写策略，降低AI检测率的同时保持学术质量。
核心思路：不是简单同义词替换，而是从句式、逻辑、风格三个维度重构文本。
"""
import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from providers.registry import ProviderRegistry
from providers.base import ModelMessage


class RewriteStrategy(str, Enum):
    """改写策略"""
    SENTENCE_RESTRUCTURE = "sentence_restructure"  # 句式重组
    LOGIC_REORDER = "logic_reorder"                # 逻辑重排
    STYLE_INJECTION = "style_injection"            # 风格注入
    ACADEMIC_POLISH = "academic_polish"            # 学术润色
    DEEP_REWRITE = "deep_rewrite"                  # 深度改写（综合）


@dataclass
class HumanizeConfig:
    """人味化配置"""
    strategies: list[RewriteStrategy] = field(default_factory=lambda: [
        RewriteStrategy.SENTENCE_RESTRUCTURE,
        RewriteStrategy.STYLE_INJECTION,
        RewriteStrategy.ACADEMIC_POLISH,
    ])
    temperature: float = 0.7          # 改写温度（越高越随机）
    preserve_structure: bool = True    # 保留段落结构
    preserve_terms: bool = True        # 保留专业术语
    max_chunk_chars: int = 2000        # 单次改写最大字符数
    overlap_chars: int = 100           # 分块重叠字符数
    model: Optional[str] = None        # 使用的模型（None则用默认）


# ============ 改写Prompt模板 ============

SENTENCE_RESTRUCTURE_PROMPT = """你是一位学术写作专家。请对以下学术文本进行句式重组改写。

【改写规则】
1. 保持原文的学术含义完全不变
2. 主动句↔被动句交替使用
3. 长句拆短、短句合并，增加句式变化
4. 调整从句位置（前置↔后置）
5. 使用不同的连接词和过渡语
6. 保留所有专业术语、数据、引用不变
7. 不要添加或删除任何实质性内容

【禁止】
- 不要使用"首先...其次...最后"等模板化结构
- 不要使用"值得注意的是""需要指出的是"等AI常用开头
- 不要使用排比句式
- 每段的首句不要用相同句式

【原文】
{text}

【改写后】"""

LOGIC_REORDER_PROMPT = """你是一位学术写作专家。请对以下学术文本进行逻辑重排改写。

【改写规则】
1. 保持原文的核心论点和证据完全不变
2. 调整段落内论点的呈现顺序（如因果→果因，总分→分总）
3. 将并列论述改为递进论述，或反之
4. 合并或拆分段落，改变信息密度分布
5. 保留所有专业术语、数据、引用不变

【禁止】
- 不要改变论证的逻辑方向（不要把支持改成反对）
- 不要删除任何论据
- 不要使用AI常见的模板化过渡

【原文】
{text}

【改写后】"""

STYLE_INJECTION_PROMPT = """你是一位资深学术作者，有十年以上SCI论文发表经验。请对以下文本进行风格化改写，使其更像人类学者撰写。

【改写规则】
1. 偶尔使用略带个人判断的措辞（如"我们认为""这一发现颇具启发性"）
2. 适当使用学术口语化表达（如"不难发现""显而易见"）
3. 在关键论断处补充限定语（如"在特定条件下""就目前的实验结果而言"）
4. 使用多样化的引用方式（如"正如[1]所指出的""与Smith等人的发现一致"）
5. 保留所有专业术语和数据

【禁止】
- 不要使用"综上所述""总而言之"等AI高频结尾
- 不要使用"具有重要意义""提供了新的视角"等空泛表述
- 不要每段都用相同结构开头
- 不要过度使用被动语态

【原文】
{text}

【改写后】"""

ACADEMIC_POLISH_PROMPT = """你是一位SCI期刊编辑。请对以下学术文本进行润色改写，提升学术表达质量。

【改写规则】
1. 替换过于口语化或重复的表述
2. 增强论证的精确性和严谨性
3. 适当增加学术限定（hedging），避免过度claim
4. 优化段落间的逻辑衔接
5. 保留所有专业术语、数据、引用不变

【特别注意】
- 使用hedging表达：may, suggest, indicate, tend to, appear to
- 避免绝对化表述：always, never, prove, definitely
- 使用精确量化表述替代模糊表述

【原文】
{text}

【改写后】"""

DEEP_REWRITE_PROMPT = """你是一位学术写作大师，擅长将AI生成的文本改写为自然的人类学术写作风格。

请对以下文本进行深度改写，目标是：
1. 降低AI检测率（改写后的文本应通过GPTZero、Turnitin AI Detection等工具检测）
2. 保持学术质量和专业性
3. 保持原文的核心含义和论证逻辑

【改写策略 - 综合运用】
- 句式重组：打破AI常见的"主语+谓语+宾语"模板
- 逻辑重排：调整论述顺序，增加非线性表达
- 风格注入：加入人类学者的写作习惯和判断
- 学术润色：提升表达精确性

【人类写作特征 - 必须体现】
- 句子长度不均匀（短句和长句交替）
- 偶尔使用倒装句或强调句
- 过渡自然但不模板化
- 有适度的学术hedging
- 段落长短不一

【AI写作特征 - 必须消除】
- "首先...其次...最后..."结构
- "值得注意的是""需要指出的是"开头
- "综上所述""总而言之"结尾
- 过度使用被动语态
- 每段首句结构雷同
- 排比和并列句式过多

【原文】
{text}

【改写后】"""


STRATEGY_PROMPTS = {
    RewriteStrategy.SENTENCE_RESTRUCTURE: SENTENCE_RESTRUCTURE_PROMPT,
    RewriteStrategy.LOGIC_REORDER: LOGIC_REORDER_PROMPT,
    RewriteStrategy.STYLE_INJECTION: STYLE_INJECTION_PROMPT,
    RewriteStrategy.ACADEMIC_POLISH: ACADEMIC_POLISH_PROMPT,
    RewriteStrategy.DEEP_REWRITE: DEEP_REWRITE_PROMPT,
}


class PaperHumanizer:
    """SCI论文人味化处理器"""

    def __init__(self, registry: ProviderRegistry, config: HumanizeConfig = None):
        self.registry = registry
        self.config = config or HumanizeConfig()

    def _split_into_chunks(self, text: str) -> list[str]:
        """将文本按段落分块，每块不超过max_chunk_chars"""
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 > self.config.max_chunk_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # 如果单段超长，按句子拆分
                if len(para) > self.config.max_chunk_chars:
                    sentences = re.split(r'(?<=[。！？.!?])\s*', para)
                    sub_chunk = ""
                    for sent in sentences:
                        if len(sub_chunk) + len(sent) > self.config.max_chunk_chars:
                            if sub_chunk:
                                chunks.append(sub_chunk.strip())
                            sub_chunk = sent
                        else:
                            sub_chunk += sent
                    current_chunk = sub_chunk
                else:
                    current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text]

    def _extract_preserved_terms(self, text: str) -> list[str]:
        """提取需要保留的专业术语（英文术语、缩写、公式等）"""
        # 英文术语和缩写
        terms = re.findall(r'\b[A-Z][A-Za-z]*(?:[- ][A-Z][A-Za-z]*)*\b', text)
        # 缩写如 CNN, RAG, LLM
        abbrevs = re.findall(r'\b[A-Z]{2,}\b', text)
        # 数学公式片段
        formulas = re.findall(r'\$[^$]+\$', text)
        # 引用 [1], [2-4]
        refs = re.findall(r'\[\d+(?:[-–]\d+)?\]', text)

        all_terms = list(set(terms + abbrevs + formulas + refs))
        return all_terms[:30]  # 限制数量避免prompt过长

    async def _rewrite_chunk(self, text: str, strategy: RewriteStrategy) -> str:
        """用指定策略改写一个文本块"""
        prompt_template = STRATEGY_PROMPTS.get(strategy, DEEP_REWRITE_PROMPT)
        prompt = prompt_template.format(text=text)

        # 如果需要保留术语，在prompt中追加
        if self.config.preserve_terms:
            terms = self._extract_preserved_terms(text)
            if terms:
                prompt += f"\n\n【必须保留的术语】{', '.join(terms)}"

        messages = [
            ModelMessage(role="system", content="你是一位学术写作专家，擅长将文本改写为自然的人类学术风格。只输出改写后的文本，不要加任何解释。"),
            ModelMessage(role="user", content=prompt),
        ]

        provider_name = self.config.model or "gpt"
        try:
            provider = self.registry.get(provider_name)
        except Exception:
            available = self.registry.list_names()
            if not available:
                print(f"[Humanize] No providers registered in ProviderRegistry")
                return text
            provider = self.registry.get(available[0])

        resp = await provider.generate(
            messages,
            model=self.config.model or "gpt-4.5-mini",
            temperature=self.config.temperature,
        )

        if resp.error:
            print(f"[Humanize] Rewrite failed ({strategy}): {resp.error}")
            return text  # 失败时返回原文

        result = resp.content.strip()
        # 去掉可能的markdown包裹
        if result.startswith("```"):
            result = re.sub(r'^```\w*\n?', '', result)
            result = re.sub(r'\n?```$', '', result)

        return result

    async def humanize(self, text: str, strategies: list[RewriteStrategy] = None) -> dict:
        """
        主入口：对论文文本进行人味化改写

        Args:
            text: 原始论文文本
            strategies: 改写策略列表（None则使用配置默认）

        Returns:
            {
                "original": 原文,
                "humanized": 改写后文本,
                "strategies_used": 使用的策略列表,
                "chunks_processed": 处理的文本块数,
                "char_ratio": 改写前后字符比
            }
        """
        strategies = strategies or self.config.strategies
        if not strategies:
            strategies = [RewriteStrategy.DEEP_REWRITE]

        chunks = self._split_into_chunks(text)
        print(f"[Humanize] Split into {len(chunks)} chunks, strategies: {[s.value for s in strategies]}")

        result_chunks = []
        for i, chunk in enumerate(chunks):
            current_text = chunk

            # 按顺序应用每个策略
            for strategy in strategies:
                current_text = await self._rewrite_chunk(current_text, strategy)
                # 策略间短暂间隔，避免rate limit
                await asyncio.sleep(0.5)

            result_chunks.append(current_text)
            print(f"[Humanize] Chunk {i + 1}/{len(chunks)} done")

        humanized = "\n\n".join(result_chunks)

        return {
            "original": text,
            "humanized": humanized,
            "strategies_used": [s.value for s in strategies],
            "chunks_processed": len(chunks),
            "char_ratio": len(humanized) / max(1, len(text)),
        }

    async def humanize_sections(self, sections: dict[str, str]) -> dict[str, dict]:
        """
        按论文章节分别改写，不同章节可用不同策略

        Args:
            sections: {"abstract": "...", "introduction": "...", "method": "...", ...}

        Returns:
            {"abstract": {"original": ..., "humanized": ...}, ...}
        """
        section_strategies = {
            "abstract": [RewriteStrategy.SENTENCE_RESTRUCTURE, RewriteStrategy.STYLE_INJECTION],
            "introduction": [RewriteStrategy.LOGIC_REORDER, RewriteStrategy.STYLE_INJECTION],
            "method": [RewriteStrategy.SENTENCE_RESTRUCTURE],  # 方法部分改动最小
            "results": [RewriteStrategy.SENTENCE_RESTRUCTURE, RewriteStrategy.ACADEMIC_POLISH],
            "discussion": [RewriteStrategy.DEEP_REWRITE],
            "conclusion": [RewriteStrategy.SENTENCE_RESTRUCTURE, RewriteStrategy.STYLE_INJECTION],
        }

        results = {}
        for section_name, content in sections.items():
            if not content or not content.strip():
                continue
            strategies = section_strategies.get(
                section_name.lower(),
                [RewriteStrategy.SENTENCE_RESTRUCTURE]
            )
            print(f"[Humanize] Processing section: {section_name}")
            results[section_name] = await self.humanize(content, strategies)

        return results


def split_paper_sections(text: str) -> dict[str, str]:
    """
    将论文文本按章节拆分

    支持中英文常见章节标题：
    Abstract/摘要, Introduction/引言, Method/方法, Results/结果,
    Discussion/讨论, Conclusion/结论, References/参考文献
    """
    section_patterns = [
        r'^(?:#{1,3}\s*)?(?:Abstract|摘要)',
        r'^(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:Introduction|引言|绪论)',
        r'^(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:Related\s+Work|相关工作)',
        r'^(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:Method(?:ology)?|方法|模型)',
        r'^(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:Experiment(?:s)?|实验)',
        r'^(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:Results?|结果)',
        r'^(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:Discussion|讨论)',
        r'^(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:Conclusion|结论|总结)',
        r'^(?:#{1,3}\s*)?(?:References?|参考文献|Bibliography)',
    ]

    sections = {}
    current_section = "preamble"
    current_content = []

    for line in text.split("\n"):
        matched = False
        for pattern in section_patterns:
            if re.match(pattern, line.strip(), re.IGNORECASE):
                # 保存上一个section
                if current_content:
                    sections[current_section] = "\n".join(current_content).strip()
                # 开始新section
                current_section = re.sub(r'^[#\d.\s]+', '', line.strip()).strip()
                current_content = []
                matched = True
                break

        if not matched:
            current_content.append(line)

    # 保存最后一个section
    if current_content:
        sections[current_section] = "\n".join(current_content).strip()

    return sections
