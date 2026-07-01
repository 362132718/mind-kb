"""
配置模块 - 所有可配置项从 .env 读取，config.py 只做 os.getenv() 和默认值处理
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# === 路径常量（代码中固定） ===
QUEUE_DIR = BASE_DIR / "queue"
CARDS_DIR = BASE_DIR / "cards"
ARCHIVE_DIR = BASE_DIR / "archive"
ZVEC_DATA_DIR = BASE_DIR / "zvec_data"
LOG_DIR = BASE_DIR / "logs"
PROMPTS_DIR = BASE_DIR / "src" / "prompts"


# === 敏感信息（带 fallback 逻辑） ===
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
# EMBEDDING_API_KEY / RERANKER_API_KEY 留空时自动回退到 LLM_API_KEY
EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "").strip() or LLM_API_KEY
RERANKER_API_KEY: str = os.getenv("RERANKER_API_KEY", "").strip() or LLM_API_KEY


# === LLM 大模型配置 ===
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))


# === Embedding 向量模型配置 ===
EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")
EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))


# === Reranker 重排序配置 ===
RERANKER_ENABLED: bool = os.getenv("RERANKER_ENABLED", "false").lower() in ("true", "1", "yes")
RERANKER_BASE_URL: str = os.getenv("RERANKER_BASE_URL", "https://api.siliconflow.cn/v1")
RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_TOP_N: int = int(os.getenv("RERANKER_TOP_N", "5"))


# === 日志配置 ===
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE: str = os.getenv("LOG_FILE", "logs/kb.log")


# === 搜索配置 ===
DEFAULT_TOP_K: int = int(os.getenv("DEFAULT_TOP_K", "5"))
SIMILARITY_MERGE_THRESHOLD: float = float(os.getenv("SIMILARITY_MERGE_THRESHOLD", "0.85"))
RELATED_THRESHOLD: float = float(os.getenv("RELATED_THRESHOLD", "0.8"))
CONTENT_DUPLICATE_THRESHOLD: float = float(os.getenv("CONTENT_DUPLICATE_THRESHOLD", "0.95"))
