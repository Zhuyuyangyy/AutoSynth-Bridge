import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from typing import Optional
import datetime
import uuid
import tempfile
import shutil
import os

from providers.registry import ProviderRegistry
from providers.base import BaseProvider, ModelMessage, ModelResponse
from core.debate_engine import DebateEngine
from core.schemas import DebateRequest
from memory.trajectory_store import TrajectoryStore


class MockProvider(BaseProvider):
    def __init__(self, name: str, responses: list[str] = None, fail_on_call: int = 999):
        super().__init__(model="mock-v1")
        self._name = name
        self._responses = responses or ["mock reply"]
        self._call_count = 0
        self._fail_on_call = fail_on_call

    @property
    def name(self):
        return self._name

    async def generate(self, messages: list[ModelMessage], **kwargs) -> ModelResponse:
        self._call_count += 1
        if self._fail_on_call <= self._call_count:
            self._record_failure()
            return ModelResponse(
                content="[ERROR] mock failure",
                model=self.model,
                provider_name=self._name,
                error="mock failure",
            )
        idx = min(self._call_count - 1, len(self._responses) - 1)
        content = self._responses[idx]
        self._record_success()
        return ModelResponse(content=content, model=self.model, provider_name=self._name, latency_ms=5)


@pytest.fixture
def temp_dir():
    tmp = tempfile.mkdtemp(prefix="autosynth_route_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def temp_store(temp_dir):
    return TrajectoryStore(
        storage_dir=os.path.join(temp_dir, "traj"),
        db_path=os.path.join(temp_dir, "db", "traj.db"),
    )


@pytest.fixture
def mock_app(temp_store):
    registry = ProviderRegistry()
    gpt = MockProvider("gpt", ["GPT innovation view", "GPT response"])
    gemini = MockProvider("gemini", ["Gemini creative view", "Gemini response"])
    registry.register("gpt", gpt)
    registry.register("gemini", gemini)
    engine = DebateEngine(registry)

    app = FastAPI()

    class V2Debate2Request(BaseModel):
        query: str
        topic: str
        task_type: str = "sci_paper"
        participants: list[str] = Field(default_factory=lambda: ["gpt", "gemini"])
        rounds: int = 2

    @app.get("/api/v1/providers/health")
    async def health():
        results = []
        for name, provider in registry.get_all().items():
            h = await provider.health_check()
            results.append({
                "name": name,
                "type": provider.name,
                "available": h.available,
                "success_rate": round(h.success_rate, 3),
            })
        return {"providers": results, "total": len(results)}

    @app.post("/api/v1/debate2")
    async def debate2(req: V2Debate2Request):
        if engine is None:
            raise HTTPException(status_code=503, detail="Engine not initialized")
        available = registry.list_names()
        missing = [p for p in req.participants if p not in available]
        if missing:
            raise HTTPException(status_code=400, detail=f"Participants not available: {missing}")

        debate_req = DebateRequest(
            query=req.query, topic=req.topic, task_type=req.task_type,
            participants=req.participants, rounds=req.rounds,
        )
        try:
            result = await engine.run(debate_req)
        except Exception as e:
            task_id = (req.topic or "x")[:20] + "_" + uuid.uuid4().hex[:4]
            from core.schemas import DebateResult
            dummy = DebateResult(
                task_id=task_id, query=req.query, topic=req.topic,
                task_type=req.task_type, status="failed", error=str(e),
            )
            dummy.started_at = datetime.datetime.now().isoformat()
            dummy.completed_at = datetime.datetime.now().isoformat()
            temp_store.save(dummy)
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

        has_error = any(r.content.startswith("[ERROR]") for r in result.rounds)
        if has_error:
            result.status = "failed"
            result.error = "Provider call failed"
            temp_store.save(result)
            raise HTTPException(status_code=502, detail="Provider call failed")

        temp_store.save(result)
        return {
            "task_id": result.task_id,
            "status": result.status,
            "rounds": len(result.rounds),
            "consensus_score": result.consensus.consistency_score if result.consensus else None,
            "trajectory_saved": True,
        }

    @app.get("/api/v1/trajectories")
    async def list_traj(limit: int = 20, status: Optional[str] = None):
        return {"trajectories": temp_store.list_records(limit=limit, status=status)}

    return app


@pytest.fixture
def client(mock_app):
    return TestClient(mock_app)


def test_health_returns_providers(client):
    response = client.get("/api/v1/providers/health")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    names = {p["name"] for p in data["providers"]}
    assert "gpt" in names
    assert "gemini" in names


def test_debate2_success(client):
    response = client.post("/api/v1/debate2", json={
        "query": "分析中医RAG创新方向",
        "topic": "中医RAG",
        "participants": ["gpt", "gemini"],
        "rounds": 2,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["rounds"] > 0
    assert data["trajectory_saved"] is True
    assert "task_id" in data


def test_debate2_missing_participant(client):
    response = client.post("/api/v1/debate2", json={
        "query": "test",
        "topic": "test",
        "participants": ["gpt", "nonexistent"],
        "rounds": 1,
    })
    assert response.status_code == 400
    assert "not available" in response.json()["detail"]


def test_debate2_provider_failure_returns_502(temp_dir):
    registry = ProviderRegistry()
    registry.register("gpt", MockProvider("gpt", ["ok"], fail_on_call=1))
    registry.register("gemini", MockProvider("gemini", ["ok"]))
    engine = DebateEngine(registry)

    store = TrajectoryStore(
        storage_dir=os.path.join(temp_dir, "traj2"),
        db_path=os.path.join(temp_dir, "db2", "traj.db"),
    )

    app = FastAPI()

    class V2Debate2Request(BaseModel):
        query: str
        topic: str
        task_type: str = "sci_paper"
        participants: list[str] = Field(default_factory=lambda: ["gpt", "gemini"])
        rounds: int = 2

    @app.post("/api/v1/debate2")
    async def debate2_fail(req: V2Debate2Request):
        available = registry.list_names()
        missing = [p for p in req.participants if p not in available]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing: {missing}")
        debate_req = DebateRequest(
            query=req.query, topic=req.topic, task_type=req.task_type,
            participants=req.participants, rounds=req.rounds,
        )
        result = await engine.run(debate_req)
        has_error = any(r.content.startswith("[ERROR]") for r in result.rounds)
        if has_error or result.status in ("failed", "error"):
            result.status = "failed"
            result.error = result.error or "Provider call failed"
            store.save(result)
            raise HTTPException(status_code=502, detail="Provider call failed")
        store.save(result)
        return {"status": result.status}

    fail_client = TestClient(app)
    response = fail_client.post("/api/v1/debate2", json={
        "query": "test",
        "topic": "test",
        "participants": ["gpt", "gemini"],
        "rounds": 2,
    })
    assert response.status_code == 502


def test_list_trajectories(client):
    resp = client.get("/api/v1/trajectories?limit=5")
    assert resp.status_code == 200
    assert "trajectories" in resp.json()
