"""AutoSynth-Bridge FastAPI入口（V0.2 - P0.5）"""
import os
import uuid
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from config import settings
from state import DebateState, ExecutionTask
from graph.debate_graph import DebateGraph, build_provider_router
from agents.claude_executor import ClaudeExecutor
from database import db
from bridge import Bridge
from providers.base import BaseProvider, ModelMessage
from providers.openai_compatible import OpenAICompatibleProvider
from providers.registry import ProviderRegistry, get_registry
from providers.errors import ProviderNotFoundError
from core.debate_engine import DebateEngine
from core.schemas import DebateRequest as V2DebateRequest, DebateResult
from memory.trajectory_store import TrajectoryStore

_debate_graph: Optional[DebateGraph] = None
_claude_executor: Optional[ClaudeExecutor] = None
_bridge: Optional[Bridge] = None
_registry: Optional[ProviderRegistry] = None
_debate_engine: Optional[DebateEngine] = None
_trajectory_store: Optional[TrajectoryStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _debate_graph, _claude_executor, _bridge, _registry, _debate_engine, _trajectory_store
    try:
        _debate_graph = DebateGraph()
    except RuntimeError as e:
        print(f"[AutoSynth-Bridge] WARNING: {e}")
        _debate_graph = None
    _claude_executor = ClaudeExecutor(workspace_dir=settings.claude_workspace)
    _bridge = Bridge(mode="web")

    _registry = get_registry()
    base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "").rstrip("/") or settings.api_4s_base
    api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "") or settings.api_4s_key
    gpt_model = os.getenv("OPENAI_COMPATIBLE_MODEL", "") or settings.gpt_model
    gemini_model = os.getenv("OPENAI_COMPATIBLE_MODEL", "") or settings.gemini_model

    if api_key and base_url:
        _registry.register("gpt", OpenAICompatibleProvider(
            api_key=api_key, base_url=base_url, model=gpt_model, env_prefix="",
        ))
        _registry.register("gemini", OpenAICompatibleProvider(
            api_key=api_key, base_url=base_url, model=gemini_model, env_prefix="",
        ))

    _debate_engine = DebateEngine(_registry)
    trajectory_dir = os.getenv("AUTOSYNTH_TRAJECTORY_DIR", "./trajectories")
    trajectory_db = os.getenv("AUTOSYNTH_DB_PATH", "./database/trajectories.db")
    _trajectory_store = TrajectoryStore(storage_dir=trajectory_dir, db_path=trajectory_db)

    print("[AutoSynth-Bridge] V0.2 P0.5 started on http://127.0.0.1:8090")
    print(f"[V2] Providers registered: {_registry.list_names()}")
    yield
    print("[AutoSynth-Bridge] shutdown")


app = FastAPI(
    title="AutoSynth-Bridge 智研桥 V0.1",
    version="0.1.0",
    description="三模型辩论与代码执行桥接系统",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DebateRequest(BaseModel):
    query: str
    topic: str
    task_type: str = "sci_paper"


class ExecuteRequest(BaseModel):
    plan: str
    task_type: str = "sci_paper"
    requirements: list[str] = Field(default_factory=list)
    task_id: Optional[str] = None


class WebDebateRequest(BaseModel):
    user_requirement: str
    topic: str
    task_type: str = "sci_paper"
    max_rounds: int = 3
    headless: bool = True


class FullPipelineRequest(BaseModel):
    query: str
    topic: str
    task_type: str = "sci_paper"
    execute_after_debate: bool = True


class HumanizeRequest(BaseModel):
    text: str
    strategies: list[str] = Field(
        default_factory=lambda: ["sentence_restructure", "style_injection", "academic_polish"],
        description="改写策略: sentence_restructure, logic_reorder, style_injection, academic_polish, deep_rewrite"
    )


class HumanizeSectionsRequest(BaseModel):
    text: str


class V2Debate2Request(BaseModel):
    query: str
    topic: str
    task_type: str = "sci_paper"
    participants: list[str] = Field(default_factory=lambda: ["gpt", "gemini"])
    rounds: int = 2


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "AutoSynth-Bridge V0.1",
        "providers_configured": len(settings.api_4s_key or "") > 0,
        "db_path": settings.db_path
    }


@app.post("/api/web/debate")
async def web_debate(req: WebDebateRequest):
    """Web模式：Playwright网页自动化辩论（零成本）"""
    try:
        result = await _bridge.run_web_debate(
            user_requirement=req.user_requirement,
            topic=req.topic,
            task_type=req.task_type,
            max_rounds=req.max_rounds,
            headless=req.headless
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/{task_id}")
async def get_memory(task_id: str):
    memory = _bridge.get_memory(task_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Task not found")
    return memory


@app.get("/api/memory/{task_id}/context")
async def get_memory_context(task_id: str):
    context = _bridge.get_context(task_id)
    return {"task_id": task_id, "context": context}


@app.get("/api/memory/list")
async def list_memories(limit: int = 20):
    return {"tasks": _bridge.palace.list_tasks(limit=limit)}


@app.post("/api/debate")
async def run_debate(req: DebateRequest):
    """API模式：LLM辩论"""
    if _debate_graph is None:
        raise HTTPException(status_code=503, detail="No LLM providers configured")
    run_id = db.create_run(req.query, req.topic, req.task_type)
    try:
        result = await _debate_graph.run(
            query=req.query,
            topic=req.topic,
            task_type=req.task_type
        )
        for arg in result.get("gpt_arguments", []):
            db.log_message(run_id, arg.round, "GPT", arg.content)
        for arg in result.get("gemini_arguments", []):
            db.log_message(run_id, arg.round, "Gemini", arg.content)
        convergence = result.get("convergence")
        db.finalize_run(
            run_id=run_id,
            rounds=result["round"],
            final_score=result.get("consistency_score", 0.0),
            converged=convergence.converged if convergence else False,
            need_human=result.get("need_human_review", False),
            final_plan=result.get("final_plan", "")[:2000]
        )
        return {
            "success": True,
            "run_id": run_id,
            "round": result["round"],
            "consistency_score": result.get("consistency_score", 0.0),
            "need_human_review": result.get("need_human_review", False),
            "final_plan": result.get("final_plan", "")[:1000],
            "converged": convergence.converged if convergence else False,
            "errors": result.get("error_log", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/execute")
async def execute_plan(req: ExecuteRequest):
    task_id = req.task_id or str(uuid.uuid4())[:8]
    result = await _claude_executor.execute_task(
        task=req.plan,
        task_id=task_id,
        timeout=300
    )
    return {"success": result.get("success", False), "task_id": task_id, "result": result}


@app.post("/api/pipeline/full")
async def full_pipeline(req: FullPipelineRequest):
    if _debate_graph is None:
        raise HTTPException(status_code=503, detail="No LLM providers configured")
    run_id = db.create_run(req.query, req.topic, req.task_type)
    try:
        result = await _debate_graph.run(
            query=req.query,
            topic=req.topic,
            task_type=req.task_type
        )
        convergence = result.get("convergence")
        for arg in result.get("gpt_arguments", []):
            db.log_message(run_id, arg.round, "GPT", arg.content)
        for arg in result.get("gemini_arguments", []):
            db.log_message(run_id, arg.round, "Gemini", arg.content)
        if not result.get("final_plan"):
            db.finalize_run(run_id, result["round"], 0.0, False, True, "")
            return {"success": False, "stage": "debate", "error": "辩论未收敛"}
        plan = result["final_plan"]
        db.finalize_run(
            run_id=run_id, rounds=result["round"],
            final_score=result.get("consistency_score", 0.0),
            converged=convergence.converged if convergence else False,
            need_human=result.get("need_human_review", False),
            final_plan=plan[:2000]
        )
        if not req.execute_after_debate:
            return {
                "success": True, "stage": "debate_only",
                "plan": plan[:2000],
                "consistency_score": result.get("consistency_score", 0.0)
            }
        exec_task_id = str(uuid.uuid4())[:8]
        exec_result = await _claude_executor.execute_task(
            task="根据以下方案执行" + req.task_type + "任务：\n" + plan,
            task_id=exec_task_id
        )
        return {
            "success": exec_result.get("success", False),
            "stage": "full_pipeline",
            "exec_task_id": exec_task_id,
            "plan": plan[:1000],
            "consistency_score": result.get("consistency_score", 0.0),
            "execution": exec_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/runs")
async def list_runs(limit: int = 20):
    try:
        c = db.conn.cursor()
        rows = c.execute(
            "SELECT id, query, topic, task_type, rounds, final_score, converged, need_human, created_at FROM debate_runs ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return {"runs": [{"id": r[0], "query": r[1][:100], "topic": r[2], "task_type": r[3],
                          "rounds": r[4], "final_score": r[5], "converged": bool(r[6]),
                          "need_human": bool(r[7]), "created_at": r[8]} for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/costs")
async def get_cost_summary():
    try:
        return db.get_cost_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/providers/stats")
async def get_provider_stats():
    if _debate_graph is None:
        return {"stats": {}}
    return {"stats": _debate_graph.router.get_stats()}


@app.post("/api/humanize")
async def humanize_paper(req: HumanizeRequest):
    """人味化降重：对论文文本进行LLM驱动的多层改写"""
    try:
        result = await _bridge.humanize_paper(req.text, req.strategies)
        if "error" in result:
            raise HTTPException(status_code=503, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/humanize/sections")
async def humanize_paper_sections(req: HumanizeSectionsRequest):
    """按论文章节自动拆分并分别改写"""
    try:
        result = await _bridge.humanize_paper_sections(req.text)
        if "error" in result:
            raise HTTPException(status_code=503, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== V2 API (新主链 P0.5) =====

@app.get("/api/v1/providers/health")
async def v2_providers_health():
    """返回所有已注册 Provider 的健康状态"""
    if _registry is None:
        raise HTTPException(status_code=503, detail="ProviderRegistry not initialized")

    providers = _registry.get_all()
    if not providers:
        return {"providers": [], "total": 0}

    results = []
    for name, provider in providers.items():
        health = await provider.health_check()
        results.append({
            "name": name,
            "type": provider.name,
            "available": health.available,
            "last_check": health.last_check,
            "success_rate": round(health.success_rate, 3),
            "last_error": getattr(health, "last_error", None),
            "latency_ms": getattr(health, "latency_ms", 0),
        })

    return {"providers": results, "total": len(results)}


@app.post("/api/v1/debate2")
async def v2_debate(req: V2Debate2Request):
    """V2辩论接口：Provider → DebateEngine → TrajectoryStore（含完整错误处理）"""
    if _debate_engine is None:
        raise HTTPException(status_code=503, detail="DebateEngine not initialized")

    available = _registry.list_names() if _registry else []
    missing = [p for p in req.participants if p not in available]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Participants not available: {missing}. Available: {available}",
        )

    debate_req = V2DebateRequest(
        query=req.query,
        topic=req.topic,
        task_type=req.task_type,
        participants=req.participants,
        rounds=req.rounds,
    )

    import dataclasses

    def _build_response(result: DebateResult, saved: bool):
        return {
            "task_id": result.task_id,
            "status": result.status,
            "rounds": [
                {
                    "round_num": r.round_num,
                    "participant": r.participant,
                    "content": r.content[:300],
                    "model": r.model,
                    "latency_ms": r.latency_ms,
                }
                for r in result.rounds
            ],
            "consensus": dataclasses.asdict(result.consensus) if result.consensus else None,
            "execution_plan": dataclasses.asdict(result.execution_plan) if result.execution_plan else None,
            "trajectory_saved": saved,
            "error": result.error,
        }

    try:
        result = await _debate_engine.run(debate_req)
    except ProviderNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        task_id = (debate_req.topic or "unknown")[:20] + "_" + str(uuid.uuid4())[:4]
        dummy_result = DebateResult(
            task_id=task_id,
            query=debate_req.query,
            topic=debate_req.topic,
            task_type=debate_req.task_type,
            status="failed",
            error=str(e),
        )
        dummy_result.started_at = datetime.now().isoformat()
        dummy_result.completed_at = datetime.now().isoformat()
        if _trajectory_store is not None:
            _trajectory_store.save(dummy_result)
        raise HTTPException(status_code=500, detail=f"DebateEngine internal error: {str(e)}")

    has_provider_error = any(
        r.content.startswith("[ERROR]") for r in result.rounds
    )
    if has_provider_error:
        result.status = "failed"
        result.error = "One or more provider calls failed"
        if _trajectory_store is not None:
            _trajectory_store.save(result)
        raise HTTPException(
            status_code=502,
            detail="Provider call failed during debate. See trajectory for details.",
        )

    saved = False
    if _trajectory_store is not None:
        _trajectory_store.save(result)
        saved = True

    return _build_response(result, saved)


@app.get("/api/v1/trajectories")
async def v2_list_trajectories(limit: int = 20, status: Optional[str] = None):
    if _trajectory_store is None:
        raise HTTPException(status_code=503, detail="TrajectoryStore not initialized")
    return {"trajectories": _trajectory_store.list_records(limit=limit, status=status)}


@app.get("/api/v1/trajectories/{task_id}")
async def v2_get_trajectory(task_id: str):
    if _trajectory_store is None:
        raise HTTPException(status_code=503, detail="TrajectoryStore not initialized")
    record = _trajectory_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return record.to_dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)
