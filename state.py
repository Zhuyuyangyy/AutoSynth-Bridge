"""辩论状态定义 - LangGraph状态机数据结构（V0.1）"""
from typing import TypedDict, Optional
from pydantic import BaseModel, Field
from typing import Literal

class Argument(BaseModel):
    """单条观点/论点"""
    round: int
    content: str
    source: str  # "GPT" | "Gemini"
    timestamp: float

class ConvergenceResult(BaseModel):
    """收敛结果（V0.1 - 三段式评分）"""
    consensus: str
    consistency_score: float
    semantic_similarity: float
    gpt_final: str
    gemini_final: str
    need_human_review: bool = False
    converged: bool = False
    critical_unresolved_count: int = 0

class DebateState(TypedDict):
    """LangGraph辩论状态"""
    query: str
    topic: str
    round: int
    gpt_arguments: list[Argument]
    gemini_arguments: list[Argument]
    convergence: Optional[ConvergenceResult]
    consistency_score: float
    need_human_review: bool
    task_type: str
    output_format: str
    error_log: list[str]
    final_plan: Optional[str]
    claude_output: Optional[dict]
    run_id: Optional[str]

class ExecutionTask(BaseModel):
    """给Claude Code的执行任务"""
    plan: str
    task_type: str
    output_dir: str
    requirements: list[str] = Field(default_factory=list)
