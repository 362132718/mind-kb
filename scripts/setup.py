"""
初始化脚本 - 创建目录、初始化 zvec、验证 API Key
"""
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import (
    BASE_DIR, QUEUE_DIR, CARDS_DIR, ARCHIVE_DIR, ZVEC_DATA_DIR,
    LOG_DIR, PROMPTS_DIR, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
    EMBEDDING_BASE_URL, EMBEDDING_MODEL, EMBEDDING_DIM,
)
from src.logger import get_logger

log = get_logger("setup")


def setup():
    print("=" * 50)
    print("个人经验知识库系统 - 初始化")
    print("=" * 50)

    # 1. 创建目录
    dirs = [QUEUE_DIR, CARDS_DIR, ARCHIVE_DIR, ZVEC_DATA_DIR, LOG_DIR, PROMPTS_DIR]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] 目录: {d}")

    # 2. 初始化 zvec
    print("\n初始化 zvec 向量数据库...")
    try:
        from src.vector_store import init_collection, count
        coll = init_collection()
        n = count()
        print(f"  [OK] zvec 初始化成功 (已有 {n} 条向量)")
    except Exception as e:
        print(f"  [FAIL] zvec 初始化失败: {e}")

    # 3. 验证配置
    print("\n当前配置:")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  Embedding: {EMBEDDING_MODEL} @ {EMBEDDING_BASE_URL} (dim={EMBEDDING_DIM})")
    print(f"  API Key: {'已配置' if LLM_API_KEY and LLM_API_KEY != 'sk-xxxxxxxxxx' else '未配置 (请编辑 .env)'}")

    # 4. 验证 API 连通性
    if LLM_API_KEY and LLM_API_KEY != "sk-xxxxxxxxxx":
        print("\n验证 API 连通性...")
        try:
            from src.embedding_client import get_embedding
            vec = get_embedding("测试")
            print(f"  [OK] Embedding API 连通 (向量维度: {len(vec)})")
        except Exception as e:
            print(f"  [FAIL] Embedding API 连接失败: {e}")
    else:
        print("\n[!] 请先在 .env 中配置 LLM_API_KEY")

    print("\n初始化完成！")


if __name__ == "__main__":
    setup()
