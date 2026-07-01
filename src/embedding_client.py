"""
向量模型客户端 - 文本→embedding
"""
import time
from typing import List

from openai import OpenAI

from src.config import EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM
from src.logger import get_logger

log = get_logger("embedding")


def _get_client() -> OpenAI:
    return OpenAI(base_url=EMBEDDING_BASE_URL, api_key=EMBEDDING_API_KEY)


def get_embedding(text: str, max_retries: int = 3) -> List[float]:
    """
    将文本转换为向量
    :param text: 输入文本
    :param max_retries: 最大重试次数
    :return: 向量 (list[float])
    """
    client = _get_client()
    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
            )
            vector = resp.data[0].embedding
            if len(vector) != EMBEDDING_DIM:
                log.warning(f"向量维度不匹配: 期望 {EMBEDDING_DIM}，实际 {len(vector)}")
            return vector
        except Exception as e:
            wait = 2 ** attempt
            log.warning(f"Embedding 调用失败 (尝试 {attempt+1}/{max_retries}): {e}，{wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"Embedding 调用失败，已重试 {max_retries} 次")


def get_embeddings_batch(texts: List[str], max_retries: int = 3) -> List[List[float]]:
    """
    批量将文本转换为向量
    :param texts: 文本列表
    :param max_retries: 最大重试次数
    :return: 向量列表
    """
    if not texts:
        return []
    client = _get_client()
    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            )
            # 按 index 排序确保顺序正确
            sorted_data = sorted(resp.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]
        except Exception as e:
            wait = 2 ** attempt
            log.warning(f"批量 Embedding 调用失败 (尝试 {attempt+1}/{max_retries}): {e}，{wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"批量 Embedding 调用失败，已重试 {max_retries} 次")
