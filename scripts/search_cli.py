"""
命令行语义搜索
用法: python scripts/search_cli.py "查询文本" [--top 5] [--topic llm] [--save]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.search import search, save_search_as_card
from src.config import DEFAULT_TOP_K
from src.logger import get_logger

log = get_logger("search_cli")


def main():
    parser = argparse.ArgumentParser(description="语义搜索知识卡片")
    parser.add_argument("query", type=str, help="搜索查询")
    parser.add_argument("--top", "-n", type=int, default=DEFAULT_TOP_K, help="返回结果数")
    parser.add_argument("--topic", "-t", type=str, default=None, help="按主题过滤")
    parser.add_argument("--tag", type=str, default=None, help="按标签过滤")
    parser.add_argument("--save", "-s", action="store_true", help="将结果保存为汇总卡片")
    args = parser.parse_args()

    print(f"搜索: {args.query}")
    print("-" * 50)

    results = search(args.query, top_k=args.top, topic_filter=args.topic, tag_filter=args.tag)

    if not results:
        print("未找到相关卡片")
        return

    for i, r in enumerate(results, 1):
        fm = r.get("card", {}).get("front_matter", {})
        score = r.get("score", 0)
        print(f"\n[{i}] (score: {score:.3f})")
        print(f"  标题: {fm.get('title', '无标题')}")
        print(f"  标签: {', '.join(fm.get('tags', []))}")
        print(f"  重要度: {'*' * fm.get('importance', 0)}")
        print(f"  日期: {fm.get('date', '')}")
        # 提取摘要：优先 front_matter，否则从正文提取
        summary = fm.get('summary', '')
        if not summary:
            body = r.get('card', {}).get('body', '')
            # 从 "## 一句话摘要" 后提取第一行
            for line in body.split('\n'):
                if '一句话摘要' in line:
                    continue
                if line.strip() and not line.startswith('#'):
                    summary = line.strip()[:100]
                    break
        print(f"  摘要: {summary}")
        merged_tags = r.get("merged_tags", [])
        if len(merged_tags) > len(fm.get("tags", [])):
            print(f"  合并标签: {', '.join(merged_tags)}")
        related = r.get("related_ids", [])
        if related:
            print(f"  相关卡片: {', '.join(related)}")

    if args.save:
        print("\n保存为汇总卡片...")
        card_id = save_search_as_card(args.query, results)
        if card_id:
            print(f"[OK] 汇总卡片已保存: {card_id}")
        else:
            print("[FAIL] 保存失败")


if __name__ == "__main__":
    main()
