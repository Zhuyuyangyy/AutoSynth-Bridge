import sys
sys.path.insert(0, '/mnt/d/ZYY Project/AutoSynth-Bridge')

import os
os.makedirs('/mnt/d/ZYY Project/AutoSynth-Bridge/runs', exist_ok=True)

from memory_palace import palace
palace.storage_dir = '/mnt/d/ZYY Project/AutoSynth-Bridge/runs'

task = palace.create_task("测试SCI论文创新方向", "中医RAG", "sci_paper")
print("task_id:", task.task_id)

palace.add_round(task.task_id, "GPT观点A-需验证实验设计", "Gemini观点B-跨学科创新", 0.72)
ctx = palace.build_context_for_claude(task.task_id)
print("ctx_len:", len(ctx), "status:", task.status)

from bridge import Bridge
b = Bridge(mode="web")
print("Bridge OK, mode:", b.mode)

from config import settings
print("config OK, db_path:", settings.db_path)

from database import db, DebateDB
print("database OK")

from web_debate import WebDebateExecutor, HAS_PLAYWRIGHT
print("web_debate OK, playwright:", HAS_PLAYWRIGHT)

print("\n=== All Framework Tests Passed ===")
