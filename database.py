"""SQLite运行日志 + 成本记录"""
import json
import sqlite3
import os
import uuid
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "database", "autosynth.db")

def _get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库表"""
    conn = _get_db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS debate_runs (
        id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        topic TEXT,
        task_type TEXT,
        rounds INTEGER,
        final_score REAL,
        converged INTEGER,
        need_human INTEGER,
        final_plan TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS debate_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        round_num INTEGER,
        agent TEXT,
        content TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES debate_runs(id)
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS model_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        provider TEXT,
        model TEXT,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        latency_ms INTEGER,
        cost_usd REAL,
        error TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES debate_runs(id)
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS claude_executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        task_id TEXT,
        task TEXT,
        task_dir TEXT,
        success INTEGER,
        returncode INTEGER,
        files_created TEXT,
        error TEXT,
        duration_sec REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES debate_runs(id)
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS cost_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        date TEXT,
        total_cost_usd REAL,
        total_tokens INTEGER,
        model_calls INTEGER,
        FOREIGN KEY (run_id) REFERENCES debate_runs(id)
    )""")
    conn.commit()
    conn.close()
    print(f"[DB] Initialized at {DB_PATH}")

class DebateDB:
    def __init__(self):
        init_db()
        self.conn = _get_db()

    def create_run(self, query: str, topic: str, task_type: str) -> str:
        run_id = str(uuid.uuid4())[:8]
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO debate_runs (id, query, topic, task_type) VALUES (?, ?, ?, ?)",
            (run_id, query, topic, task_type)
        )
        self.conn.commit()
        return run_id

    def log_message(self, run_id: str, round_num: int, agent: str, content: str):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO debate_messages (run_id, round_num, agent, content) VALUES (?, ?, ?, ?)",
            (run_id, round_num, agent, content)
        )
        self.conn.commit()

    def finalize_run(self, run_id: str, rounds: int, final_score: float,
                     converged: bool, need_human: bool, final_plan: str):
        c = self.conn.cursor()
        c.execute(
            "UPDATE debate_runs SET rounds=?, final_score=?, converged=?, need_human=?, final_plan=? WHERE id=?",
            (rounds, final_score, int(converged), int(need_human), final_plan, run_id)
        )
        self.conn.commit()

    def log_model_call(self, provider: str, model: str,
                       prompt_tokens: int, completion_tokens: int,
                       latency_ms: int, cost_usd: float,
                       error: Optional[str] = None, run_id: str = None):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO model_calls (run_id, provider, model, prompt_tokens, completion_tokens, latency_ms, cost_usd, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, provider, model, prompt_tokens, completion_tokens, latency_ms, cost_usd, error)
        )
        self.conn.commit()

    def log_claude_execution(self, run_id: str, task_id: str, task: str,
                             task_dir: str, success: bool, returncode: int,
                             files_created: list, error: str, duration_sec: float):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO claude_executions (run_id, task_id, task, task_dir, success, returncode, files_created, error, duration_sec) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, task_id, task, task_dir, int(success), returncode,
             json.dumps(files_created), error, duration_sec)
        )
        self.conn.commit()

    def get_run_summary(self, run_id: str) -> dict:
        c = self.conn.cursor()
        r = c.execute("SELECT * FROM debate_runs WHERE id=?", (run_id,)).fetchone()
        if not r:
            return {}
        return dict(r)

    def get_cost_summary(self) -> dict:
        c = self.conn.cursor()
        rows = c.execute("""
            SELECT provider, model, SUM(prompt_tokens) as p,
                   SUM(completion_tokens) as c, SUM(cost_usd) as cost
            FROM model_calls GROUP BY provider, model
        """).fetchall()
        return {"by_model": [dict(row) for row in rows]}

    def close(self):
        self.conn.close()

db = DebateDB()
