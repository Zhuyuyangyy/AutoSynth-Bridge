from typing import List, Dict
from dataclasses import dataclass
from enum import Enum


class DebateRole(str, Enum):
    ARCHITECT = "architect"
    CRITIC = "critic"
    EXECUTOR = "executor"
    RESEARCHER = "researcher"
    JUDGE = "judge"


@dataclass
class RoleConfig:
    name: DebateRole
    description: str
    priority: int
    keywords: List[str]


DEFAULT_ROLE_CONFIGS = [
    RoleConfig(
        name=DebateRole.ARCHITECT,
        description="架构设计者，负责提出方案、设计结构、规划路线",
        priority=1,
        keywords=["架构", "设计", "方案", "规划", "结构"]
    ),
    RoleConfig(
        name=DebateRole.CRITIC,
        description="风险审查者，负责找问题、提反对、质疑可行性、要证据",
        priority=2,
        keywords=["问题", "风险", "质疑", "不可行", "漏洞", "证据"]
    ),
    RoleConfig(
        name=DebateRole.EXECUTOR,
        description="落地工程师，负责把方案拆成步骤、评估落地难度",
        priority=3,
        keywords=["步骤", "落地", "实施", "执行", "难度", "操作"]
    ),
    RoleConfig(
        name=DebateRole.RESEARCHER,
        description="资料分析者，负责找资料、查事实、补背景",
        priority=4,
        keywords=["资料", "背景", "事实", "依据", "数据"]
    ),
    RoleConfig(
        name=DebateRole.JUDGE,
        description="最终裁判，负责综合各方意见、生成共识、给出结论",
        priority=5,
        keywords=["结论", "共识", "总结", "裁判"]
    )
]


def get_default_role_map() -> Dict[str, DebateRole]:
    """默认 provider 到角色的映射"""
    return {
        "gemini": DebateRole.ARCHITECT,
        "gpt": DebateRole.CRITIC
    }


def get_role_by_priority(priority: int) -> DebateRole:
    for config in DEFAULT_ROLE_CONFIGS:
        if config.priority == priority:
            return config.name
    return DebateRole.ARCHITECT
