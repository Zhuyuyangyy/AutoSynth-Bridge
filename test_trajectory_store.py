import pytest
import json
import os
import tempfile
import shutil
from pathlib import Path

from core.schemas import DebateResult, DebateRound, ConsensusResult, ExecutionPlan
from memory.trajectory_store import TrajectoryStore


@pytest.fixture
def temp_store():
    tmp = tempfile.mkdtemp(prefix="autosynth_test_")
    storage_dir = os.path.join(tmp, "trajectories")
    db_path = os.path.join(tmp, "db", "trajectories.db")
    store = TrajectoryStore(storage_dir=storage_dir, db_path=db_path)
    yield store
    shutil.rmtree(tmp, ignore_errors=True)


def _make_result(task_id: str = "20260515_120000_abcd", status: str = "completed") -> DebateResult:
    return DebateResult(
        task_id=task_id,
        query="分析中医RAG创新方向",
        topic="中医RAG",
        task_type="sci_paper",
        status=status,
        started_at="2026-05-15T12:00:00",
        completed_at="2026-05-15T12:01:00",
        rounds=[
            DebateRound(round_num=0, participant="gpt", content="GPT观点：创新点A", model="gpt-4.5-mini", provider_name="openai_compatible"),
            DebateRound(round_num=1, participant="gemini", content="Gemini观点：创新点B", model="gemini-3.1-flash", provider_name="openai_compatible"),
            DebateRound(round_num=2, participant="gpt", content="GPT审查：认可B", model="gpt-4.5-mini", provider_name="openai_compatible"),
            DebateRound(round_num=2, participant="gemini", content="Gemini回应：补充证据", model="gemini-3.1-flash", provider_name="openai_compatible"),
        ],
        consensus=ConsensusResult(
            consistency_score=0.82,
            semantic_similarity=0.78,
            converged=False,
            need_human_review=True,
            critical_unresolved=["实验设计细节"],
        ),
        execution_plan=ExecutionPlan(
            title="中医RAG - 执行计划",
            summary="综合GPT和Gemini观点",
            steps=["整合观点", "验证可行性"],
            constraints=["需通过学术审查"],
        ),
    )


def test_save_and_get(temp_store):
    result = _make_result()
    record = temp_store.save(result)

    assert record.task_id == result.task_id
    assert record.status == "completed"
    assert len(record.rounds) == 4
    assert record.consensus is not None
    assert record.consensus["consistency_score"] == 0.82
    assert record.execution_plan is not None

    fetched = temp_store.get(result.task_id)
    assert fetched is not None
    assert fetched.task_id == result.task_id
    assert fetched.status == "completed"


def test_json_file_created(temp_store):
    result = _make_result()
    temp_store.save(result)

    json_path = Path(temp_store.storage_dir) / f"{result.task_id}.json"
    assert json_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["task_id"] == result.task_id
    assert len(data["rounds"]) == 4


def test_list_records(temp_store):
    for i in range(3):
        r = _make_result(task_id=f"20260515_12000{i}_abcd")
        temp_store.save(r)

    records = temp_store.list_records(limit=10)
    assert len(records) == 3


def test_list_records_filter_by_status(temp_store):
    r1 = _make_result(task_id="20260515_120000_aaaa", status="completed")
    r2 = _make_result(task_id="20260515_120001_bbbb", status="error")
    temp_store.save(r1)
    temp_store.save(r2)

    completed = temp_store.list_records(limit=10, status="completed")
    assert len(completed) == 1
    assert completed[0]["status"] == "completed"


def test_get_nonexistent(temp_store):
    assert temp_store.get("nonexistent_id") is None


def test_trajectory_record_to_dict(temp_store):
    result = _make_result()
    record = temp_store.save(result)
    d = record.to_dict()
    assert isinstance(d, dict)
    assert d["task_id"] == result.task_id
    assert isinstance(d["rounds"], list)
    assert isinstance(d["consensus"], dict)


def test_sqlite_index_fields(temp_store):
    result = _make_result()
    temp_store.save(result)

    records = temp_store.list_records(limit=1)
    assert len(records) == 1
    r = records[0]
    assert "task_id" in r
    assert "created_at" in r
    assert "status" in r
    assert "participants" in r
    assert "summary" in r
    assert "topic" in r
    assert "task_type" in r
