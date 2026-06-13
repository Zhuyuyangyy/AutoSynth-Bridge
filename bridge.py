"""Bridge入口 - API模式与Web模式统一调度"""
from typing import Literal, Optional
from memory_palace import MemoryPalace, palace, DebateMemory
from web_debate import WebDebateExecutor, DebateConfig


class Bridge:
    """
    AutoSynth-Bridge 统一调度器
    支持两种模式：
    - api模式：使用4SAPI/Poe/官方API（参考 providers.py）
    - web模式：使用Playwright网页模拟（参考 web_debate.py）
    支持辩论后人味化降重处理。
    """

    def __init__(self, mode: Literal["api", "web"] = "api"):
        self.mode = mode
        self.palace = palace
        self._web_executor: Optional[WebDebateExecutor] = None
        self._humanizer = None  # 延迟初始化

    def _get_humanizer(self):
        """延迟初始化人味化处理器"""
        if self._humanizer is None:
            from providers.registry import get_registry
            from humanize import PaperHumanizer, HumanizeConfig
            try:
                registry = get_registry()
                if not registry.list_names():
                    return None
                self._humanizer = PaperHumanizer(registry)
            except Exception:
                return None
        return self._humanizer

    # ----- Web模式 -----

    def get_web_executor(self, **kwargs) -> WebDebateExecutor:
        if self._web_executor is None:
            config = DebateConfig(**kwargs)
            self._web_executor = WebDebateExecutor(config)
        return self._web_executor

    async def run_web_debate(self, user_requirement: str, topic: str,
                            task_type: str = "sci_paper", **web_kwargs) -> dict:
        """Web模式：Playwright网页辩论"""
        # 创建记忆记录
        memory = self.palace.create_task(user_requirement, topic, task_type)

        # 启动网页辩论
        executor = self.get_web_executor(**web_kwargs)
        result = await executor.run_debate(memory.task_id, user_requirement)

        return {
            "task_id": memory.task_id,
            "mode": "web",
            "debate_result": result,
            "context_for_claude": self.palace.build_context_for_claude(memory.task_id)
        }

    # ----- API模式（预留接口） -----

    async def run_api_debate(self, user_requirement: str, topic: str,
                            task_type: str = "sci_paper") -> dict:
        """API模式：使用LLM Provider辩论"""
        # TODO: 集成 providers.py 的 ProviderRouter
        return {"error": "API mode not yet integrated. Use web mode."}

    # ----- 人味化降重 -----

    async def humanize_paper(self, text: str, strategies: list[str] = None) -> dict:
        """
        对论文文本进行人味化降重处理

        Args:
            text: 论文全文或段落文本
            strategies: 改写策略列表，可选值:
                - sentence_restructure: 句式重组
                - logic_reorder: 逻辑重排
                - style_injection: 风格注入
                - academic_polish: 学术润色
                - deep_rewrite: 深度改写（综合）

        Returns:
            改写结果字典，包含原文、改写后文本、使用的策略等
        """
        humanizer = self._get_humanizer()
        if not humanizer:
            return {"error": "Humanizer not available. Check API provider configuration."}

        from humanize import RewriteStrategy
        strategy_enums = None
        if strategies:
            strategy_enums = []
            for s in strategies:
                try:
                    strategy_enums.append(RewriteStrategy(s))
                except ValueError:
                    pass

        return await humanizer.humanize(text, strategy_enums)

    async def humanize_paper_sections(self, text: str) -> dict:
        """
        按论文章节自动拆分并分别改写

        自动识别摘要、引言、方法、实验、讨论、结论等章节，
        对不同章节使用不同的改写策略。
        """
        humanizer = self._get_humanizer()
        if not humanizer:
            return {"error": "Humanizer not available. Check API provider configuration."}

        from humanize import split_paper_sections
        sections = split_paper_sections(text)
        if not sections:
            return {"error": "No sections detected in the text."}

        return await humanizer.humanize_sections(sections)

    # ----- 统一入口 -----

    async def run(self, user_requirement: str, topic: str,
                 task_type: str = "sci_paper",
                 mode: Optional[Literal["api", "web"]] = None,
                 **kwargs) -> dict:
        mode = mode or self.mode
        if mode == "web":
            return await self.run_web_debate(user_requirement, topic, task_type, **kwargs)
        else:
            return await self.run_api_debate(user_requirement, topic, task_type)

    # ----- 记忆查询 -----

    def get_context(self, task_id: str) -> str:
        return self.palace.build_context_for_claude(task_id)

    def get_memory(self, task_id: str) -> Optional[DebateMemory]:
        return self.palace.get_task(task_id)
