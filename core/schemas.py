from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class DebateRole(str, Enum):
    ARCHITECT = "architect"
    CRITIC = "critic"
    EXECUTOR = "executor"
    RESEARCHER = "researcher"
    JUDGE = "judge"


@dataclass
class ParticipantRole:
    provider_name: str
    role: DebateRole


@dataclass
class DebateRequest:
    query: str
    topic: str
    task_type: str = "sci_paper"
    participants: list[str] = field(default_factory=lambda: ["gpt", "gemini"])
    participant_roles: Optional[list[ParticipantRole]] = None
    rounds: int = 3
    extra: dict = field(default_factory=dict)


@dataclass
class DebateRound:
    round_num: int
    participant: str
    content: str
    role: Optional[str] = None
    model: str = ""
    provider_name: str = ""
    latency_ms: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ConsensusResult:
    consistency_score: float = 0.0
    semantic_similarity: float = 0.0
    converged: bool = False
    need_human_review: bool = True
    summary: str = ""
    agreement_points: List[str] = field(default_factory=list)
    disagreement_points: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    recommended_plan: List[str] = field(default_factory=list)
    confidence: float = 0.0
    critical_unresolved: List[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    title: str = ""
    summary: str = ""
    goal: str = ""
    project_path: str = ""
    steps: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    allowed_files: List[str] = field(default_factory=list)
    forbidden_files: List[str] = field(default_factory=list)
    allowed_commands: List[str] = field(default_factory=list)
    forbidden_commands: List[str] = field(default_factory=list)
    acceptance_tests: List[str] = field(default_factory=list)
    rollback_required: bool = False
    raw_plan: str = ""

    def has_safety_constraints(self) -> bool:
        return bool(self.forbidden_files or self.forbidden_commands)

    def is_step_safe(self, step: str) -> tuple[bool, str]:
        lower = step.lower()
        for cmd in self.forbidden_commands:
            if cmd.lower() in lower:
                return False, f"Step contains forbidden command: '{cmd}'"
        for f in self.forbidden_files:
            if f.lower() in lower:
                return False, f"Step references forbidden file: '{f}'"
        return True, ""


@dataclass
class DebateResult:
    task_id: str
    query: str
    topic: str
    task_type: str
    rounds: List[DebateRound] = field(default_factory=list)
    consensus: Optional[ConsensusResult] = None
    execution_plan: Optional[ExecutionPlan] = None
    status: str = "pending"
    started_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now().isoformat()


@dataclass
class TrajectoryRecord:
    task_id: str
    query: str
    topic: str
    task_type: str
    status: str = "pending"
    participants: List[str] = field(default_factory=list)
    rounds: List[dict] = field(default_factory=list)
    consensus: Optional[dict] = None
    execution_plan: Optional[dict] = None
    summary: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
