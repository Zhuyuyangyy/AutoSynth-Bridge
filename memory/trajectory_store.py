import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import asdict

from core.schemas import TrajectoryRecord, DebateResult


class TrajectoryStore:
    def __init__(self, storage_dir: str = "./trajectories", db_path: str = "./database/trajectories.db"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trajectory_index (
                task_id TEXT PRIMARY KEY,
                created_at TEXT,
                status TEXT,
                participants TEXT,
                summary TEXT,
                topic TEXT,
                task_type TEXT
            )
        """)
        conn.commit()
        conn.close()

    def save(self, result: DebateResult) -> TrajectoryRecord:
        record = self._result_to_record(result)

        json_path = self.storage_dir / f"{record.task_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)

        self._upsert_index(record)

        return record

    def get(self, task_id: str) -> Optional[TrajectoryRecord]:
        json_path = self.storage_dir / f"{task_id}.json"
        if not json_path.exists():
            return None
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TrajectoryRecord(**data)

    def list_records(self, limit: int = 20, status: Optional[str] = None) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        query = "SELECT task_id, created_at, status, participants, summary, topic, task_type FROM trajectory_index"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _result_to_record(self, result: DebateResult) -> TrajectoryRecord:
        rounds_data = []
        for r in result.rounds:
            rounds_data.append({
                "round_num": r.round_num,
                "participant": r.participant,
                "content": r.content,
                "model": r.model,
                "provider_name": r.provider_name,
                "latency_ms": r.latency_ms,
                "timestamp": r.timestamp,
            })

        consensus_data = None
        if result.consensus:
            consensus_data = {
                "consistency_score": result.consensus.consistency_score,
                "converged": result.consensus.converged,
                "need_human_review": result.consensus.need_human_review,
                "semantic_similarity": result.consensus.semantic_similarity,
                "critical_unresolved": result.consensus.critical_unresolved,
            }

        plan_data = None
        if result.execution_plan:
            plan_data = {
                "title": result.execution_plan.title,
                "summary": result.execution_plan.summary,
                "steps": result.execution_plan.steps,
                "constraints": result.execution_plan.constraints,
            }

        participants = list({r.participant for r in result.rounds}) if result.rounds else []
        summary = result.rounds[-1].content[:200] if result.rounds else ""

        return TrajectoryRecord(
            task_id=result.task_id,
            query=result.query,
            topic=result.topic,
            task_type=result.task_type,
            status=result.status,
            participants=participants,
            rounds=rounds_data,
            consensus=consensus_data,
            execution_plan=plan_data,
            summary=summary,
            created_at=result.started_at,
            completed_at=result.completed_at,
            error=result.error,
        )

    def _upsert_index(self, record: TrajectoryRecord):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO trajectory_index
               (task_id, created_at, status, participants, summary, topic, task_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.task_id,
                record.created_at,
                record.status,
                json.dumps(record.participants, ensure_ascii=False),
                record.summary[:300],
                record.topic,
                record.task_type,
            ),
        )
        conn.commit()
        conn.close()
