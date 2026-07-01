"""
卡片管理 - 解析文章、生成卡片、读写卡片
"""
import re
from datetime import date
from pathlib import Path
from typing import Optional

import yaml
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

from src.config import CARDS_DIR, ARCHIVE_DIR
from src.llm_client import Article, ExtractedInfo
from src.logger import get_logger

log = get_logger("card_manager")

# card_id 计数器（同一天内递增）
_card_counter = 0


def _generate_card_id() -> str:
    """生成唯一的 card_id"""
    global _card_counter
    _card_counter += 1
    return f"kb_{date.today().strftime('%Y%m%d')}_{_card_counter:03d}"


def parse_article(file_path: str) -> Article:
    """
    读取 queue/ 中任意格式的文件，将完整内容传递给 LLM
    支持 .md, .txt, .html, .pdf
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    ext = path.suffix.lower()
    title = path.stem  # 文件名作为标题

    try:
        if ext in (".md", ".txt", ".markdown"):
            content = path.read_text(encoding="utf-8")
            # 尝试从第一行 # 标题提取
            first_line = content.split("\n")[0].strip()
            if first_line.startswith("#"):
                title = first_line.lstrip("#").strip()
        elif ext == ".html":
            html = path.read_text(encoding="utf-8")
            soup = BeautifulSoup(html, "html.parser")
            # 提取 title
            title_tag = soup.find("title") or soup.find("h1")
            if title_tag:
                title = title_tag.get_text(strip=True)
            content = soup.get_text(separator="\n", strip=True)
        elif ext == ".pdf":
            reader = PdfReader(str(path))
            content = ""
            for page in reader.pages:
                content += page.extract_text() or ""
            if not content.strip():
                title = title  # 保持文件名作为标题
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        log.error(f"读取文件失败 {file_path}: {e}")
        content = ""

    return Article(title=title, content=content, file_path=str(path))


# 各类型的正文模板
CARD_TEMPLATES = {
    "tutorial": """## 一句话摘要
{summary}

## 适用场景
{applicable_scenarios}

## 前置条件
{prerequisites}

## 关键步骤
{key_steps}

## 代码/命令示例
{code_snippets}

## 常见问题
{common_issues}

## 个人思考
{personal_thoughts}

## 原始摘录
{raw_excerpt}
""",
    "news": """## 一句话摘要
{summary}

## 核心事件
{core_events}

## 关键结论
{key_conclusions}

## 个人思考
{personal_thoughts}

## 原始摘录
{raw_excerpt}
""",
    "opinion": """## 一句话摘要
{summary}

## 核心观点
{multiple_viewpoints}

## 关键结论
{key_conclusions}

## 个人思考
{personal_thoughts}

## 原始摘录
{raw_excerpt}
""",
    "review": """## 一句话摘要
{summary}

## 对比总结
{comparison_table}

## 适用场景
{applicable_scenarios}

## 优缺点对比
{comparison_table}

## 关键结论
{key_conclusions}

## 个人思考
{personal_thoughts}

## 原始摘录
{raw_excerpt}
""",
    "experience": """## 一句话摘要
{summary}

## 踩坑/最佳实践
{lessons_learned}

## 关键步骤
{key_steps}

## 适用场景
{applicable_scenarios}

## 经验教训
{lessons_learned}

## 个人思考
{personal_thoughts}

## 原始摘录
{raw_excerpt}
""",
}


def _format_list(items: list) -> str:
    """将列表格式化为 Markdown"""
    if not items:
        return "（无）"
    return "\n".join(f"- {item}" for item in items)


def generate_card(article: Article, info: ExtractedInfo, raw_content: str = "") -> dict:
    """
    根据 article_type 动态生成卡片
    :return: {"card_id": str, "content": str, "front_matter": dict}
    """
    card_id = _generate_card_id()

    # YAML front matter
    front_matter = {
        "title": info.summary[:50] if not article.title else article.title,
        "source": article.source,
        "date": date.today().isoformat(),
        "tags": info.tags,
        "importance": info.importance,
        "topic": info.topic,
        "card_id": card_id,
        "article_type": info.article_type,
        "needs_review": info.needs_review,
        "related_cards": info.related_cards,
        "related_keywords": info.related_keywords,
    }

    # 正文
    template = CARD_TEMPLATES.get(info.article_type, CARD_TEMPLATES["experience"])
    body = template.format(
        summary=info.summary,
        key_points=_format_list(info.key_points),
        personal_thoughts=info.personal_thoughts or "（待补充）",
        raw_excerpt=raw_content[:2000] if raw_content else "（无）",
        # tutorial
        prerequisites=_format_list(info.prerequisites),
        applicable_scenarios=_format_list(info.applicable_scenarios),
        key_steps=_format_list(info.key_steps),
        code_snippets=_format_list(info.code_snippets) if info.code_snippets else "（无）",
        common_issues=_format_list(info.common_issues) if info.common_issues else "（无）",
        # news
        core_events=_format_list(info.core_events),
        key_conclusions=_format_list(info.key_conclusions) if info.key_conclusions else _format_list(info.key_points),
        # opinion/review
        multiple_viewpoints=_format_list(info.multiple_viewpoints) if info.multiple_viewpoints else "（无）",
        comparison_table=_format_list(info.comparison_table) if info.comparison_table else "（无）",
        # experience
        lessons_learned=_format_list(info.lessons_learned) if info.lessons_learned else "（无）",
    )

    # 组装完整 Markdown
    yaml_str = yaml.dump(front_matter, allow_unicode=True, default_flow_style=False).strip()
    content = f"---\n{yaml_str}\n---\n\n{body}"

    return {
        "card_id": card_id,
        "content": content,
        "front_matter": front_matter,
    }


def save_card(card: dict) -> Path:
    """保存卡片到 cards/ 目录"""
    card_id = card["card_id"]
    card_path = CARDS_DIR / f"{card_id}.md"
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    card_path.write_text(card["content"], encoding="utf-8")
    log.info(f"卡片已保存: {card_path}")
    return card_path


def read_card(card_path: str) -> Optional[dict]:
    """从 Markdown 文件读取卡片，返回 front_matter + body"""
    path = Path(card_path)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        # 解析 YAML front matter
        match = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
        if match:
            front_matter = yaml.safe_load(match.group(1))
            body = match.group(2)
            return {"front_matter": front_matter, "body": body, "path": str(path)}
        else:
            return {"front_matter": {}, "body": text, "path": str(path)}
    except Exception as e:
        log.error(f"读取卡片失败 {card_path}: {e}")
        return None


def update_card_related_cards(card_path: str, new_related_id: str) -> None:
    """更新卡片的 related_cards 字段"""
    card = read_card(card_path)
    if not card:
        return
    fm = card["front_matter"]
    related = fm.get("related_cards", [])
    if new_related_id not in related:
        related.append(new_related_id)
        fm["related_cards"] = related
        # 重新生成文件
        yaml_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
        content = f"---\n{yaml_str}\n---\n{card['body']}"
        Path(card_path).write_text(content, encoding="utf-8")
        log.info(f"更新 related_cards: {card_path} → +{new_related_id}")


def get_card_text_for_vector(card: dict) -> str:
    """拼接用于生成向量的文本（标题+摘要+标签）"""
    fm = card.get("front_matter", {})
    parts = [
        fm.get("title", ""),
        fm.get("summary", "") if "summary" in fm else "",
        " ".join(fm.get("tags", [])),
    ]
    # 如果 front_matter 里没有 summary，从 body 提取第一行
    if not parts[1] and card.get("body"):
        lines = card["body"].strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                parts[1] = line.strip()
                break
    return " | ".join(p for p in parts if p)


def archive_article(file_path: str) -> None:
    """将原始文章从 queue/ 移至 archive/"""
    src = Path(file_path)
    if not src.exists():
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dst = ARCHIVE_DIR / src.name
    # 如果目标已存在，加时间戳
    if dst.exists():
        stem = src.stem
        suffix = src.suffix
        dst = ARCHIVE_DIR / f"{stem}_{date.today().strftime('%Y%m%d')}{suffix}"
    src.rename(dst)
    log.info(f"存档: {src.name} → archive/")


def list_all_cards() -> list:
    """列出 cards/ 目录下所有卡片"""
    if not CARDS_DIR.exists():
        return []
    cards = []
    for f in CARDS_DIR.glob("*.md"):
        card = read_card(str(f))
        if card:
            cards.append(card)
    return cards
