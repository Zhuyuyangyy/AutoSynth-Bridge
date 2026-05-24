"""配置文件 - 多Provider+模型配置"""
import os
from pydantic_settings import BaseSettings
from typing import Literal, Optional

class Settings(BaseSettings):
    # ===== Provider配置 =====
    # 主路径：4SAPI OpenAI-compatible聚合网关
    api_4s_key: str = os.getenv("API_4S_KEY", "")
    api_4s_base: str = os.getenv("API_4S_BASE", "https://open.ai-api.cn/v1")
    
    # 备用1：Poe 官方 OpenAI-compatible API
    poe_api_key: str = os.getenv("POE_API_KEY", "")
    poe_base: str = os.getenv("POE_BASE", "https://api.poe.com/openai/v1")
    
    # 备用2：OpenAI 官方 API
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base: str = os.getenv("OPENAI_BASE", "https://api.openai.com/v1")
    
    # ===== 模型配置 =====
    gpt_model: str = "gpt-4.5-mini"
    gemini_model: str = "gemini-3.1-flash"
    claude_model: str = "claude-sonnet-4-7-20250514"
    
    # ===== 辩论配置 =====
    debate_rounds: int = 3
    consistency_threshold: float = 0.85
    embedding_model: str = "all-MiniLM-L6-v2"
    
    # ===== Claude Code配置 =====
    claude_code_timeout: int = 300
    claude_code_max_retries: int = 1
    claude_workspace: str = "./outputs"
    
    # ===== 日志配置 =====
    db_path: str = "./database/autosynth.db"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
