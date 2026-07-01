"""
处理流水线 - 核心调度模块
设计原则：每篇文章独立成卡，不合并，用关联代替合并
"""
import shutil
from pathlib import Path
from typing import Optional

from src.config import QUEUE_DIR, CONTENT_DUPLICATE_THRESHOLD, RELATED_THRESHOLD
from src.llm_client import extract_card_info, Article
from src.embedding_client import get_embedding
from src.vector_store import insert as vec_insert, search as vec_search
from src.card_manager import (
    parse_article, generate_card, save_card, read_card,
    archive_article, get_card_text_for_vector, update_card_related_cards,
    list_all_cards, CARDS_DIR,
)
from src.logger import get_logger

log = get_logger("pipeline")


def process_all() -> list:
    """处理 queue/ 中所有文件"""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    files = [f for f in QUEUE_DIR.iterdir() if f.is_file()]
    if not files:
        log.info("queue/ 为空，无需处理")
        return []

    log.info(f"发现 {len(files)} 个待处理文件")
    results = []
    for f in files:
        try:
            result = process_single(str(f))
            results.append(result)
        except Exception as e:
            log.error(f"处理文件失败 {f.name}: {e}")

    log.info(f"处理完成: {len(results)}/{len(files)} 成功")
    return results


def process_single(file_path: str) -> Optional[dict]:
    """
    单篇全自动处理流程：
    1. 解析文章
    2. 两阶段 LLM 提取
    3. 内容去重与关联检查
    4. 生成卡片
    5. 向量化
    6. 存档
    """
    log.info(f"开始处理: {Path(file_path).name}")

    # 1. 解析文章
    article = parse_article(file_path)
    if not article.content.strip():
        log.warning(f"文件内容为空: {file_path}")
        archive_article(file_path)
        return None

    # 2. 两阶段 LLM 提取
    info = extract_card_info(article)

    # 3. 内容去重与关联检查
    # 用 LLM 提取出的标题+摘要生成临时向量
    check_text = f"{article.title} {info.summary}"
    try:
        check_vector = get_embedding(check_text)
        similar = vec_search(check_vector, top_k=5)
    except Exception as e:
        log.warning(f"去重检查失败（可能 zvec 为空）: {e}")
        similar = []

    merge_target = None  # 要合并到的已有卡片
    related_ids = []     # 要关联的卡片

    for card_id, score in similar:
        if score >= CONTENT_DUPLICATE_THRESHOLD:
            merge_target = card_id
            log.info(f"内容高度相似 (score={score:.3f})，合并到已有卡片: {card_id}")
            break
        elif score >= RELATED_THRESHOLD:
            related_ids.append(card_id)
            log.info(f"内容相似 (score={score:.3f})，将关联卡片: {card_id}")

    # 4. 生成卡片
    if merge_target:
        # 合并到已有卡片
        _merge_to_existing(article, info, merge_target, file_path)
        return {"action": "merged", "target": merge_target, "file": file_path}
    else:
        # 创建新卡片
        card = generate_card(article, info, raw_content=article.content[:2000])
        # 过滤掉自引用（related_ids 中不应包含当前卡片）
        current_card_id = card["card_id"]
        info.related_cards = [rid for rid in related_ids if rid != current_card_id]
        # 重新生成 content（因为 related_cards 已更新）
        import yaml
        fm = card.get("front_matter", {})
        fm["related_cards"] = info.related_cards
        yaml_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
        # 提取正文部分（去掉旧的 front matter）
        body = card["content"].split("---\n", 2)[-1] if "---" in card["content"] else card["content"]
        card["content"] = f"---\n{yaml_str}\n---\n{body}"
        card_path = save_card(card)

        # 5. 向量化
        try:
            vector_text = get_card_text_vector(card)
            vector = get_embedding(vector_text)
            vec_insert(card["card_id"], vector)
            log.info(f"向量化完成: {card['card_id']}")
        except Exception as e:
            log.error(f"向量化失败: {e}，卡片已保存但向量待补录")

        # 双向更新 related_cards
        for rid in related_ids:
            existing_path = CARDS_DIR / f"{rid}.md"
            if existing_path.exists():
                update_card_related_cards(str(existing_path), card["card_id"])

        # 6. 存档
        archive_article(file_path)

        return {"action": "created", "card_id": card["card_id"], "file": file_path}


def _merge_to_existing(article: Article, info, target_card_id: str, file_path: str) -> None:
    """合并到已有卡片（≥0.95 时触发）"""
    target_path = CARDS_DIR / f"{target_card_id}.md"
    existing = read_card(str(target_path))
    if not existing:
        log.error(f"目标卡片不存在: {target_card_id}")
        return

    fm = existing["front_matter"]

    # 合并策略
    # 标签：取并集去重
    old_tags = fm.get("tags", [])
    new_tags = list(set(old_tags + info.tags))
    fm["tags"] = new_tags

    # 来源：追加
    if article.source and article.source not in fm.get("source", ""):
        old_source = fm.get("source", "")
        fm["source"] = f"{old_source}, {article.source}" if old_source else article.source

    # related_keywords：合并
    old_kw = fm.get("related_keywords", [])
    fm["related_keywords"] = list(set(old_kw + info.related_keywords))

    # 摘要/要点：由 LLM 综合（这里简单追加）
    # 实际生产中应调用 LLM 重新生成精炼版本
    body = existing.get("body", "")

    # 重新生成 YAML
    import yaml
    yaml_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
    new_content = f"---\n{yaml_str}\n---\n{body}"
    target_path.write_text(new_content, encoding="utf-8")

    # 更新向量
    try:
        vector_text = f"{fm.get('title', '')} {fm.get('summary', '')} {' '.join(fm.get('tags', []))}"
        vector = get_embedding(vector_text)
        vec_insert(target_card_id, vector)
    except Exception as e:
        log.error(f"更新向量失败: {e}")

    # 存档原文件
    archive_article(file_path)
    log.info(f"合并完成: → {target_card_id}")


def get_card_text_vector(card: dict) -> str:
    """拼接用于向量化的文本"""
    return get_card_text_for_vector(card)


def rebuild_vectors() -> None:
    """
    扫描 cards/ 中所有卡片，重新生成向量并重建 zvec
    用于 zvec 数据损坏或批量补录向量
    """
    from src.vector_store import rebuild_vectors as vs_rebuild
    from src.embedding_client import get_embeddings_batch

    cards = list_all_cards()
    if not cards:
        log.info("没有卡片需要重建向量")
        return

    card_ids = []
    texts = []
    for card in cards:
        cid = card["front_matter"].get("card_id", "")
        if cid:
            card_ids.append(cid)
            texts.append(get_card_text_for_vector(card))

    if not card_ids:
        return

    log.info(f"开始重建 {len(card_ids)} 张卡片的向量...")
    try:
        vectors = get_embeddings_batch(texts)
        vs_rebuild(card_ids, vectors)
        log.info(f"向量重建完成: {len(card_ids)} 条")
    except Exception as e:
        log.error(f"向量重建失败: {e}")
