import pytest
import asyncio
import tempfile
import shutil
import os

from providers.base import BaseProvider, ModelMessage, ModelResponse
from providers.registry import ProviderRegistry
from core.debate_engine import DebateEngine
from core.schemas import DebateRequest
from memory.trajectory_store import TrajectoryStore


class FailingProvider(BaseProvider):
    def __init__(self, name: str = "failing"):
        super().__init__(model="fail-v1")
        self._name = name
        self._call_count = 0

    @property
    def name(self):
        return self._name

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        self._call_count += 1
        self._record_failure()
        return ModelResponse(
            content="",
            model=self.model,
            provider_name=self._name,
            error=f"Intentional failure #{self._call_count}",
        )


class PartialFailingProvider(BaseProvider):
    def __init__(self, name: str = "partial", fail_on_call: int = 999):
        super().__init__(model="partial-v1")
        self._name = name
        self._call_count = 0
        self._fail_on_call = fail_on_call

    @property
    def name(self):
        return self._name

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        self._call_count += 1
        if self._call_count >= self._fail_on_call:
            self._record_failure()
            return ModelResponse(
                content="",
                model=self.model,
                provider_name=self._name,
                error="failed on this call",
            )
        self._record_success()
        return ModelResponse(
            content=f"success on call {self._call_count}",
            model=self.model,
            provider_name=self._name,
        )


@pytest.fixture
def temp_store():
    tmp = tempfile.mkdtemp(prefix="autosynth_fail_traj_")
    store = TrajectoryStore(
        storage_dir=os.path.join(tmp, "traj"),
        db_path=os.path.join(tmp, "db", "traj.db"),
    )
    yield store
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_debate_engine_returns_error_result_on_exception():
    p1 = FailingProvider("gpt")
    p2 = PartialFailingProvider("gemini", fail_on_call=999)
    engine = DebateEngine(registry_or_providers={"gpt": p1, "gemini": p2})
    req = DebateRequest(query="test", topic="test", participants=["gpt", "gemini"], rounds=1)
    result = await engine.run(req)
    assert result.status in ("error", "completed")


@pytest.mark.asyncio
async def test_debate_engine_partial_failure_continues(temp_store):
    p1 = PartialFailingProvider("gpt", fail_on_call=2)
    p2 = PartialFailingProvider("gemini", fail_on_call=999)
    engine = DebateEngine(registry_or_providers={"gpt": p1, "gemini": p2})
    req = DebateRequest(query="test", topic="test", participants=["gpt", "gemini"], rounds=2)
    result = await engine.run(req)
    assert len(result.rounds) > 0


@pytest.mark.asyncio
async def test_failed_result_can_be_saved(temp_store):
    p1 = PartialFailingProvider("gpt", fail_on_call=999)
    p2 = PartialFailingProvider("gemini", fail_on_call=999)
    engine = DebateEngine(registry_or_providers={"gpt": p1, "gemini": p2})
    req = DebateRequest(query="test", topic="test", participants=["gpt", "gemini"], rounds=1)
    result = await engine.run(req)
    record = temp_store.save(result)
    assert record.task_id == result.task_id
    fetched = temp_store.get(result.task_id)
    assert fetched is not None


@pytest.mark.asyncio
async def test_failed_trajectory_has_rounds_data(temp_store):
    p1 = PartialFailingProvider("gpt", fail_on_call=999)
    p2 = PartialFailingProvider("gemini", fail_on_call=999)
    engine = DebateEngine(registry_or_providers={"gpt": p1, "gemini": p2})
    req = DebateRequest(query="analyze", topic="test", participants=["gpt", "gemini"], rounds=1)
    result = await engine.run(req)
    record = temp_store.save(result)
    assert len(record.rounds) > 0


def test_trajectory_store_saves_failed_status(temp_store):
    from core.schemas import DebateResult
    result = DebateResult(
        task_id="failed_test_001",
        query="test query",
        topic="test topic",
        task_type="sci_paper",
        status="failed",
        error="All providers failed",
    )
    result.started_at = "2026-05-15T10:00:00"
    result.completed_at = "2026-05-15T10:00:01"
    record = temp_store.save(result)
    assert record.status == "failed"
    rows = temp_store.list_records(status="failed")
    assert len(rows) == 1
    assert rows[0]["task_id"] == "failed_test_001"
    assert rows[0]["status"] == "failed"


def test_trajectory_store_saves_error_status(temp_store):
    from core.schemas import DebateResult
    result = DebateResult(
        task_id="error_test_001",
        query="test",
        topic="test",
        task_type="sci_paper",
        status="error",
        error="Unexpected exception",
    )
    result.started_at = "2026-05-15T10:00:00"
    result.completed_at = "2026-05-15T10:00:01"
    temp_store.save(result)
    rows = temp_store.list_records(status="error")
    error_rows = [r for r in rows if r["task_id"] == "error_test_001"]
    assert len(error_rows) == 1


def test_trajectory_store_multiple_failed_records(temp_store):
    from core.schemas import DebateResult
    for i in range(3):
        result = DebateResult(
            task_id=f"multi_fail_{i}",
            query="test",
            topic="test",
            task_type="sci_paper",
            status="failed",
            error=f"Failure {i}",
        )
        result.started_at = "2026-05-15T10:00:00"
        result.completed_at = "2026-05-15T10:00:01"
        temp_store.save(result)
    failed_rows = temp_store.list_records(status="failed")
    assert len(failed_rows) == 3
