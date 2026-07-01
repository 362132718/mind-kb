"""
语义搜索模块
"""
import math
from pathlib import Path
from typing import List, Optional

from src.config import (
    DEFAULT_TOP_K, SIMILARITY_MERGE_THRESHOLD,
    RELATED_THRESHOLD, CONTENT_DUPLICATE_THRESHOLD,
    RERANKER_ENABLED, RERANKER_BASE_URL, RERANKER_API_KEY,
    RERANKER_MODEL, RERANKER_TOP_N, CARDS_DIR,
)
from src.embedding_client import get_embedding
from src.vector_store import search as vec_search
from src.card_manager import read_card, save_card, generate_card, get_card_text_for_vector, update_card_related_cards
from src.llm_client import Article, ExtractedInfo, _call_llm_with_retry, _extract_json_from_response
from src.logger import get_logger

log = get_logger("search")


def search(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    topic_filter: Optional[str] = None,
    tag_filter: Optional[str] = None,
) -> list:
    """
    语义搜索
    1. 查询 → embedding → zvec 搜索
    2. 可选 Reranker
    3. 语义聚合去重
    4. 元数据过滤 → 返回结果
    """
    # 1. 生成查询向量并搜索
    try:
        query_vector = get_embedding(query)
    except Exception as e:
        log.error(f"Embedding 失败: {e}")
        return []

    candidates = vec_search(query_vector, top_k=top_k * 3)
    if not candidates:
        return []

    # 2. 可选 Reranker
    if RERANKER_ENABLED:
        candidates = _rerank(query, candidates)

    # 3. 读取卡片元数据并过滤
    results = []
    for card_id, score in candidates:
        card_path = CARDS_DIR / f"{card_id}.md"
        card = read_card(str(card_path))
        if not card:
            continue
        fm = card.get("front_matter", {})

        # topic 过滤
        if topic_filter and fm.get("topic") != topic_filter:
            continue
        # tag 过滤
        if tag_filter and tag_filter not in fm.get("tags", []):
            continue

        results.append({
            "card": card,
            "score": score,
            "card_id": card_id,
        })

    # 4. 语义聚合去重
    results = _semantic_aggregate(results)

    # 返回 top_k
    return results[:top_k]


def _rerank(query: str, candidates: list) -> list:
    """使用 Reranker 对候选结果重排序"""
    try:
        from openai import OpenAI
        client = OpenAI(base_url=RERANKER_BASE_URL, api_key=RERANKER_API_KEY)

        # 读取候选卡片内容
        docs = []
        for card_id, score in candidates:
            card_path = CARDS_DIR / f"{card_id}.md"
            card = read_card(str(card_path))
            if card:
                fm = card.get("front_matter", {})
                text = f"{fm.get('title', '')} {fm.get('summary', '')}"
                docs.append((card_id, score, text))

        if not docs:
            return candidates

        # 调用 Reranker API
        resp = client.post(
            "/rerank",
            json={
                "model": RERANKER_MODEL,
                "query": query,
                "documents": [d[2] for d in docs],
                "top_n": RERANKER_TOP_N,
            },
        )
        # 解析结果
        reranked = []
        for item in resp.get("results", []):
            idx = item["index"]
            reranked.append((docs[idx][0], docs[idx][1]))
        return reranked[:RERANKER_TOP_N]
    except Exception as e:
        log.warning(f"Reranker 失败，使用原始排序: {e}")
        return candidates


def _semantic_aggregate(results: list) -> list:
    """
    语义聚合：两两计算余弦相似度，≥ 阈值的归为同一组
    每组保留相似度最高的卡片为代表，合并标签
    """
    if len(results) <= 1:
        return results

    # 简单聚合：按 score 排序，高分代表吸收低分
    results.sort(key=lambda x: x["score"], reverse=True)
    groups = []
    used = set()

    for i, r in enumerate(results):
        if r["card_id"] in used:
            continue
        group = {
            "card": r["card"],
            "score": r["score"],
            "card_id": r["card_id"],
            "merged_tags": list(r["card"].get("front_matter", {}).get("tags", [])),
            "related_ids": [],
            "related_count": 0,
        }
        used.add(r["card_id"])

        # 检查后续结果是否相似
        for j in range(i + 1, len(results)):
            if results[j]["card_id"] in used:
                continue
            # 简化：用 score 差值近似判断相似度
            if r["score"] - results[j]["score"] < (1 - SIMILARITY_MERGE_THRESHOLD):
                group["related_ids"].append(results[j]["card_id"])
                group["related_count"] += 1
                # 合并标签
                other_tags = results[j]["card"].get("front_matter", {}).get("tags", [])
                group["merged_tags"] = list(set(group["merged_tags"] + other_tags))
                used.add(results[j]["card_id"])

        groups.append(group)

    return groups



def get_related_cards(card_id: str) -> list:
    """获取指定卡片的相关卡片"""
    card_path = CARDS_DIR / f"{card_id}.md"
    card = read_card(str(card_path))
    if not card:
        return []

    related_ids = card.get("front_matter", {}).get("related_cards", [])
    results = []
    for rid in related_ids:
        rpath = CARDS_DIR / f"{rid}.md"
        rcard = read_card(str(rpath))
        if rcard:
            results.append(rcard)
    return results


def save_search_as_card(query: str, results: list) -> Optional[str]:
    """将搜索结果保存为新的汇总卡片"""
    if not results:
        return None

    # 构建 LLM 输入
    card_summaries = []
    source_card_ids = []
    for r in results[:5]:  # 最多取 5 个结果
        card = r.get("card", {})
        fm = card.get("front_matter", {})
        body = card.get("body", "")
        card_summaries.append(f"标题: {fm.get('title', '')}\n摘要: {fm.get('summary', '')}\n内容: {body[:500]}")
        cid = fm.get("card_id", r.get("card_id", ""))
        if cid:
            source_card_ids.append(cid)

    combined = "\n\n---\n\n".join(card_summaries)
    prompt = f"用户查询: {query}\n\n以下是搜索到的相关知识卡片内容:\n{combined}\n\n请综合以上内容，生成一张汇总卡片的信息。"

    system = "你是一个知识库助手。请根据用户查询和提供的知识卡片内容，生成一张汇总的知识卡片。输出 JSON 格式，包含: summary, key_points, tags, importance, topic, personal_thoughts, related_keywords"

    try:
        resp = _call_llm_with_retry(system, prompt)
        data = _extract_json_from_response(resp)
        if not data:
            log.error("LLM 返回无法解析")
            return None

        info = ExtractedInfo()
        info.summary = data.get("summary", f"关于「{query}」的汇总")
        info.key_points = data.get("key_points", [])
        info.tags = data.get("tags", [query])
        info.importance = data.get("importance", 3)
        info.topic = data.get("topic", "other")
        info.personal_thoughts = data.get("personal_thoughts", "")
        info.related_keywords = data.get("related_keywords", [])
        info.related_cards = source_card_ids
        info.article_type = "experience"

        article = Article(title=f"汇总: {query}", content=combined)
        card = generate_card(article, info, raw_content=combined[:2000])
        card_path = save_card(card)

        # 向量化
        try:
            vector = get_embedding(get_card_text_for_vector(card))
            from src.vector_store import insert as vec_insert
            vec_insert(card["card_id"], vector)
        except Exception as e:
            log.error(f"汇总卡片向量化失败: {e}")

        # 双向关联
        for cid in source_card_ids:
            existing_path = CARDS_DIR / f"{cid}.md"
            if existing_path.exists():
                update_card_related_cards(str(existing_path), card["card_id"])

        log.info(f"汇总卡片已保存: {card['card_id']}")
        return card["card_id"]
    except Exception as e:
        log.error(f"生成汇总卡片失败: {e}")
        return None
