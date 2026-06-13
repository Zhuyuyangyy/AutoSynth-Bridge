"""LangGraph辩论状态机 - 核心流程编排（V0.1）

MIGRATION NOTE: This module still uses the legacy ProviderRouter from
providers.py for backward compatibility with DebateGraph.  New code should
use ProviderRegistry (providers/registry.py) + BaseProvider.generate()
instead.  The legacy providers.py module is deprecated and will be removed
once DebateGraph is fully migrated.
"""
from langgraph.graph import StateGraph, END
from typing import Literal, Optional

from state import DebateState, Argument, ConvergenceResult
from providers.registry import ProviderRegistry, get_registry
from providers.openai_compatible import OpenAICompatibleProvider
from providers.base import ModelMessage
from agents.gpt_agent import GPTAgent
from agents.gemini_agent import GeminiAgent
from graph.convergence import ConvergenceChecker
from config import settings


def build_provider_registry() -> ProviderRegistry:
    """构建多Provider注册表（使用新的 ProviderRegistry 系统）"""
    registry = get_registry()

    # 主路径：4SAPI
    if settings.api_4s_key and not registry.has("4sapi"):
        registry.register("4sapi", OpenAICompatibleProvider(
            api_key=settings.api_4s_key,
            base_url=settings.api_4s_base,
        ))

    # 备用1：Poe 官方 OpenAI-compatible API
    if settings.poe_api_key and not registry.has("poe"):
        registry.register("poe", OpenAICompatibleProvider(
            api_key=settings.poe_api_key,
            base_url=settings.poe_base,
        ))

    # 备用2：OpenAI 官方 API
    if settings.openai_api_key and not registry.has("openai"):
        registry.register("openai", OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base,
        ))

    if not registry.list_names():
        raise RuntimeError("No LLM providers configured. Set at least one of API_4S_KEY, POE_API_KEY, or OPENAI_API_KEY")

    return registry


# Backward-compatible alias kept so existing callers of
# build_provider_router() still work during migration.
build_provider_router = build_provider_registry


class DebateGraph:
    """三模型辩论状态机"""

    def __init__(self, registry: Optional[ProviderRegistry] = None):
        self.registry = registry or build_provider_registry()
        self.gpt = GPTAgent(self.registry, provider_name="gpt")
        self.gemini = GeminiAgent(self.registry, provider_name="gemini")
        self.convergence = ConvergenceChecker()
        self._graph = None

    def _should_continue(self, state: DebateState) -> Literal["gemini_node", "gpt_review", "converge_node", END]:
        """路由决策"""
        if state["round"] >= settings.debate_rounds:
            return "converge_node"

        score = state.get("consistency_score", 0.0)
        if score >= settings.consistency_threshold:
            return "converge_node"

        if state["round"] == 0:
            return "gemini_node"
        elif state["round"] % 2 == 1:
            return "gpt_review"
        else:
            return "gemini_node"

    def _init_debate(self, state: DebateState) -> DebateState:
        """初始化辩论"""
        state["round"] = 0
        state["gpt_arguments"] = []
        state["gemini_arguments"] = []
        state["consistency_score"] = 0.0
        state["need_human_review"] = False
        state["error_log"] = []
        state["final_plan"] = None
        return state

    async def _gemini_node(self, state: DebateState) -> DebateState:
        """Gemini发散节点"""
        try:
            round_num = state["round"]

            if round_num == 0:
                content = await self.gemini.brainstorm(state["query"], round_num)
            else:
                last_gpt = state["gpt_arguments"][-1].content if state["gpt_arguments"] else state["query"]
                content = await self.gemini.respond(last_gpt, round_num)

            arg = Argument(round=round_num, content=content, source="Gemini")
            state["gemini_arguments"].append(arg)
            state["round"] += 1

        except Exception as e:
            state["error_log"].append(f"Gemini Error: {str(e)}")

        return state

    async def _gpt_review_node(self, state: DebateState) -> DebateState:
        """GPT审查节点"""
        try:
            round_num = state["round"]
            last_gemini = state["gemini_arguments"][-1].content

            content = await self.gpt.debate(last_gemini, round_num)

            arg = Argument(round=round_num, content=content, source="GPT")
            state["gpt_arguments"].append(arg)

            # 更新三段式一致性分数
            if state["gemini_arguments"]:
                gpt_latest = content
                gemini_latest = last_gemini
                check = self.convergence.check_convergence(gpt_latest, gemini_latest)
                state["consistency_score"] = check.consistency_score

        except Exception as e:
            state["error_log"].append(f"GPT Error: {str(e)}")

        return state

    async def _converge_node(self, state: DebateState) -> DebateState:
        """收敛节点"""
        try:
            gpt_final = state["gpt_arguments"][-1].content if state["gpt_arguments"] else ""
            gemini_final = state["gemini_arguments"][-1].content if state["gemini_arguments"] else state["query"]

            # 三段式收敛检查
            result = self.convergence.check_convergence(gpt_final, gemini_final)

            state["consistency_score"] = result.consistency_score
            state["need_human_review"] = result.need_human_review
            state["final_plan"] = result.consensus

            state["convergence"] = ConvergenceResult(
                consensus=result.consensus,
                consistency_score=result.consistency_score,
                semantic_similarity=result.semantic_similarity,
                gpt_final=gpt_final[:500],
                gemini_final=gemini_final[:500],
                need_human_review=result.need_human_review,
                converged=result.converged,
                critical_unresolved_count=len(result.critical_unresolved)
            )

        except Exception as e:
            state["error_log"].append(f"Convergence Error: {str(e)}")
            state["need_human_review"] = True

        return state

    def build(self) -> StateGraph:
        """构建状态机图"""
        g = StateGraph(DebateState)

        g.add_node("init", self._init_debate)
        g.add_node("gemini_node", self._gemini_node)
        g.add_node("gpt_review", self._gpt_review_node)
        g.add_node("converge_node", self._converge_node)

        g.set_entry_point("init")

        for node in ["init", "gemini_node", "gpt_review"]:
            g.add_conditional_edges(
                node,
                self._should_continue,
                {
                    "gemini_node": "gemini_node",
                    "gpt_review": "gpt_review",
                    "converge_node": "converge_node",
                    END: END
                }
            )

        g.add_edge("converge_node", END)

        return g

    async def run(self, query: str, topic: str, task_type: str = "sci_paper") -> DebateState:
        """运行辩论"""
        if self._graph is None:
            self._graph = self.build()

        initial_state: DebateState = {
            "query": query,
            "topic": topic,
            "round": 0,
            "gpt_arguments": [],
            "gemini_arguments": [],
            "convergence": None,
            "consistency_score": 0.0,
            "need_human_review": False,
            "task_type": task_type,
            "output_format": "full",
            "error_log": [],
            "final_plan": None,
            "claude_output": None,
            "run_id": None
        }

        result = await self._graph.ainvoke(initial_state)
        return result

    def run_sync(self, query: str, topic: str, task_type: str = "sci_paper") -> DebateState:
        """同步运行辩论（仅在非async上下文中使用）"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 已有运行中的事件循环（如FastAPI），不能嵌套调用
            raise RuntimeError(
                "Cannot call run_sync() inside an already-running event loop. "
                "Use 'await debate_graph.run()' instead."
            )
        return asyncio.run(self.run(query, topic, task_type))
