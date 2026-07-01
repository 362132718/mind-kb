"""
向量存储 - zvec 向量数据库管理
设计原则：zvec 只存向量，元数据直接从 MD 卡片文件读取
"""
from pathlib import Path
from typing import List, Optional, Tuple

import zvec
from zvec import CollectionSchema, FieldSchema, VectorSchema, DataType, Query, Doc

from src.config import ZVEC_DATA_DIR, EMBEDDING_DIM
from src.logger import get_logger

log = get_logger("vector_store")

COLLECTION_NAME = "kb_vectors"
VECTOR_FIELD = "embedding"

# 缓存 collection 实例，避免重复打开
_cached_collection = None


def _get_collection_path() -> str:
    return str(ZVEC_DATA_DIR / COLLECTION_NAME)


def _build_schema() -> CollectionSchema:
    """构建 zvec collection schema"""
    return CollectionSchema(
        name=COLLECTION_NAME,
        vectors=VectorSchema(
            name=VECTOR_FIELD,
            dimension=EMBEDDING_DIM,
            data_type=DataType.VECTOR_FP32,
        ),
    )


def init_collection() -> zvec.Collection:
    """初始化或打开 zvec collection（缓存实例）"""
    global _cached_collection
    if _cached_collection is not None:
        return _cached_collection

    path = _get_collection_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # 如果 collection 目录已存在且有内容，尝试打开
    if Path(path).exists() and any(Path(path).iterdir()):
        try:
            _cached_collection = zvec.open(path)
            log.info(f"打开已有 zvec collection: {path}")
            return _cached_collection
        except Exception:
            pass

    # 创建新 collection
    schema = _build_schema()
    _cached_collection = zvec.create_and_open(path, schema)
    _cached_collection.create_index(VECTOR_FIELD, zvec.HnswIndexParam())
    log.info(f"创建新 zvec collection: {path}, 维度={EMBEDDING_DIM}")
    return _cached_collection


def insert(card_id: str, vector: List[float]) -> None:
    """插入向量（card_id 与 MD 文件名对应）"""
    coll = init_collection()
    doc = Doc(id=card_id, vectors={VECTOR_FIELD: vector})
    coll.upsert(doc)
    coll.flush()
    log.debug(f"插入向量: {card_id}")


def search(query_vector: List[float], top_k: int = 10) -> List[Tuple[str, float]]:
    """
    向量相似度搜索
    :return: [(card_id, score), ...] 按相似度降序
    """
    coll = init_collection()
    q = Query(field_name=VECTOR_FIELD, vector=query_vector)
    results = coll.query(queries=q, topk=top_k)
    return [(doc.id, doc.score) for doc in results]


def delete(card_id: str) -> None:
    """删除指定 card_id 的向量"""
    coll = init_collection()
    coll.delete(card_id)
    coll.flush()
    log.info(f"删除向量: {card_id}")


def get_all_card_ids() -> List[str]:
    """获取 zvec 中所有 card_id"""
    coll = init_collection()
    stats = coll.stats
    # 通过 fetch 获取所有文档 ID
    # zvec 没有直接的 list_all，我们用 query with include_vector=False
    # 这里用一个大的 topk 查询零向量来近似
    # 更好的方式：遍历 cards/ 目录
    return []  # 由调用方通过遍历 cards/ 获取


def count() -> int:
    """获取向量总数"""
    coll = init_collection()
    return coll.stats.doc_count


def rebuild_vectors(card_ids: List[str], vectors: List[List[float]]) -> None:
    """
    批量重建向量（用于 zvec 损坏后从 cards/ 重建）
    :param card_ids: card_id 列表
    :param vectors: 对应的向量列表
    """
    coll = init_collection()
    # 先清空
    all_ids = _get_all_ids(coll)
    if all_ids:
        coll.delete(all_ids)
    # 批量插入
    docs = [
        Doc(id=cid, vectors={VECTOR_FIELD: vec})
        for cid, vec in zip(card_ids, vectors)
    ]
    if docs:
        coll.upsert(docs)
        coll.flush()
    log.info(f"重建向量完成: {len(docs)} 条")


def _get_all_ids(coll) -> List[str]:
    """内部方法：获取 collection 中所有 ID"""
    # zvec 没有直接方法，通过大 topk 查询获取
    # 实际使用中，card_ids 从 cards/ 目录遍历获取
    try:
        zero_vec = [0.0] * EMBEDDING_DIM
        q = Query(field_name=VECTOR_FIELD, vector=zero_vec)
        results = coll.query(queries=q, topk=100000)
        return [doc.id for doc in results]
    except Exception:
        return []
