"""
直接创建新卡片（无需原始文章）
用法: python scripts/new_card.py [--input "我的想法内容"]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm_client import Article, ExtractedInfo, _call_llm_with_retry, _extract_json_from_response
from src.embedding_client import get_embedding
from src.vector_store import search as vec_search, insert as vec_insert
from src.card_manager import generate_card, save_card, update_card_related_cards, CARDS_DIR
from src.config import CONTENT_DUPLICATE_THRESHOLD, RELATED_THRESHOLD
from src.logger import get_logger

log = get_logger("new_card")

SYSTEM_PROMPT = """你是一个知识库助手。用户会输入一些想法/灵感/经验，请帮助整理成结构化的知识卡片。
输出 JSON 格式，包含以下字段：
- summary: 一句话摘要
- key_points: 关键要点（3-5条）
- tags: 标签（3-8个）
- importance: 重要度（1-5）
- topic: 分类（llm/hardware/security/trends/ideas/other）
- personal_thoughts: 思考性总结
- related_keywords: 核心概念关键词"""


def create_new_card(input_text: str) -> str:
    """从用户输入创建新卡片"""
    print("正在让 LLM 整理你的想法...")

    # 1. LLM 整理
    try:
        resp = _call_llm_with_retry(SYSTEM_PROMPT, input_text)
        data = _extract_json_from_response(resp)
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        return ""

    if not data:
        print("LLM 返回无法解析")
        return ""

    # 2. 构建 ExtractedInfo
    info = ExtractedInfo()
    info.summary = data.get("summary", "")
    info.key_points = data.get("key_points", [])
    info.tags = data.get("tags", [])
    info.importance = data.get("importance", 3)
    info.topic = data.get("topic", "other")
    info.personal_thoughts = data.get("personal_thoughts", "")
    info.related_keywords = data.get("related_keywords", [])
    info.article_type = "experience"

    # 3. 预览
    print("\n" + "=" * 40)
    print("预览生成的卡片:")
    print(f"  摘要: {info.summary}")
    print(f"  要点: {', '.join(info.key_points[:3])}")
    print(f"  标签: {', '.join(info.tags)}")
    print(f"  重要度: {'*' * info.importance}")
    print(f"  分类: {info.topic}")
    print("=" * 40)

    # 4. 去重与关联检查
    print("\n检查是否已有相似卡片...")
    check_text = f"{info.summary} {' '.join(info.tags)}"
    related_ids = []
    merge_target = None

    try:
        check_vector = get_embedding(check_text)
        similar = vec_search(check_vector, top_k=5)

        for card_id, score in similar:
            if score >= CONTENT_DUPLICATE_THRESHOLD:
                merge_target = card_id
                print(f"  发现高度相似卡片 (score={score:.3f}): {card_id}")
                break
            elif score >= RELATED_THRESHOLD:
                related_ids.append(card_id)
                print(f"  发现相似卡片 (score={score:.3f}): {card_id}")
    except Exception as e:
        log.warning(f"去重检查失败: {e}")

    if merge_target:
        print(f"\n将合并到已有卡片: {merge_target}")
        # 合并逻辑
        from src.pipeline import _merge_to_existing
        article = Article(title=info.summary, content=input_text)
        _merge_to_existing(article, info, merge_target, "")
        return merge_target

    # 5. 创建新卡片
    info.related_cards = related_ids
    article = Article(title=info.summary, content=input_text)
    card = generate_card(article, info, raw_content=input_text[:2000])
    card_path = save_card(card)
    print(f"\n[OK] 卡片已保存: {card['card_id']}")

    # 6. 向量化
    try:
        from src.card_manager import get_card_text_for_vector
        vector = get_embedding(get_card_text_for_vector(card))
        vec_insert(card["card_id"], vector)
        print("[OK] 向量化完成")
    except Exception as e:
        print(f"[FAIL] 向量化失败: {e}")

    # 7. 双向关联
    for rid in related_ids:
        existing_path = CARDS_DIR / f"{rid}.md"
        if existing_path.exists():
            update_card_related_cards(str(existing_path), card["card_id"])

    return card["card_id"]


def main():
    parser = argparse.ArgumentParser(description="直接创建新知识卡片")
    parser.add_argument("--input", "-i", type=str, help="输入内容")
    args = parser.parse_args()

    if args.input:
        text = args.input
    else:
        print("请输入你的想法/灵感/经验（输入完成后按回车）:")
        text = input("> ").strip()

    if not text:
        print("输入为空")
        return

    card_id = create_new_card(text)
    if card_id:
        print(f"\n完成！卡片 ID: {card_id}")


if __name__ == "__main__":
    main()
