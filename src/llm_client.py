"""
大模型客户端 - 两阶段提取（分类 → 类型专属提取）
"""
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openai import OpenAI

from src.config import (
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
    LLM_TEMPERATURE, LLM_MAX_TOKENS, PROMPTS_DIR,
)
from src.logger import get_logger

log = get_logger("llm")

# 支持的文章类型
ARTICLE_TYPES = ["tutorial", "news", "opinion", "review", "experience"]

# 分类 prompt
CLASSIFY_PROMPT = """请判断以下文章属于哪种类型，只返回 JSON 格式：{{"article_type": "类型"}}

可选类型：
- tutorial：教程、使用指南、部署指南、实操攻略
- news：资讯、行业动态、产品发布
- opinion：技术评论、观点分析、深度思考
- review：评测、对比、选型分析
- experience：个人经验分享、踩坑记录、最佳实践

文章标题：{title}
文章内容（前500字）：
{content_preview}"""


@dataclass
class Article:
    """待处理的文章"""
    title: str
    content: str
    source: str = ""
    file_path: str = ""


@dataclass
class ExtractedInfo:
    """LLM 提取的结构化信息"""
    article_type: str = "experience"
    summary: str = ""
    key_points: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    importance: int = 3
    topic: str = "other"
    personal_thoughts: str = ""
    related_keywords: list = field(default_factory=list)
    related_cards: list = field(default_factory=list)
    needs_review: bool = False
    # 类型专属字段
    prerequisites: list = field(default_factory=list)
    applicable_scenarios: list = field(default_factory=list)
    key_steps: list = field(default_factory=list)
    code_snippets: list = field(default_factory=list)
    common_issues: list = field(default_factory=list)
    core_events: list = field(default_factory=list)
    key_conclusions: list = field(default_factory=list)
    multiple_viewpoints: list = field(default_factory=list)
    comparison_table: list = field(default_factory=list)
    lessons_learned: list = field(default_factory=list)


def _get_client() -> OpenAI:
    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def _load_prompt_template(article_type: str) -> dict:
    """加载指定类型的 prompt 模板"""
    path = PROMPTS_DIR / f"{article_type}.json"
    if not path.exists():
        log.warning(f"Prompt 模板不存在: {path}，使用 base 模板")
        path = PROMPTS_DIR / "base.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_base_prompt() -> dict:
    path = PROMPTS_DIR / "base.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_json_from_response(text: str) -> Optional[dict]:
    """从 LLM 响应中提取 JSON 子串，自动修复无效转义"""
    
    def _try_parse(s: str) -> Optional[dict]:
        """尝试解析 JSON，处理无效转义"""
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        # 修复无效转义序列（如 \( \) \: 等）
        import re as _re
        fixed = _re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None
    
    # 尝试直接解析
    result = _try_parse(text)
    if result:
        return result
    
    # 尝试从 ```json ... ``` 中提取
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        result = _try_parse(match.group(1))
        if result:
            return result
    
    # 尝试找到第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        result = _try_parse(text[start:end + 1])
        if result:
            return result
    
    return None


def _call_llm_with_retry(system_prompt: str, user_content: str, max_retries: int = 3) -> str:
    """调用 LLM，带指数退避重试"""
    client = _get_client()
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            wait = 2 ** attempt
            log.warning(f"LLM 调用失败 (尝试 {attempt+1}/{max_retries}): {e}，{wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"LLM 调用失败，已重试 {max_retries} 次")


def classify_article(article: Article) -> str:
    """阶段 1：识别文章类型"""
    prompt = CLASSIFY_PROMPT.format(
        title=article.title,
        content_preview=article.content[:500],
    )
    base = _load_base_prompt()
    try:
        resp = _call_llm_with_retry(base["system_prompt"], prompt)
        data = _extract_json_from_response(resp)
        if data and data.get("article_type") in ARTICLE_TYPES:
            log.info(f"文章类型识别: {article.title[:30]}... → {data['article_type']}")
            return data["article_type"]
    except Exception as e:
        log.error(f"文章类型识别失败: {e}")
    # 默认返回 experience
    log.warning(f"无法识别文章类型，默认使用 experience: {article.title[:30]}...")
    return "experience"


def _validate_result(data: dict, article_type: str) -> ExtractedInfo:
    """验证 LLM 提取结果"""
    info = ExtractedInfo()
    info.article_type = article_type

    # 通用字段
    info.summary = str(data.get("summary", ""))
    info.key_points = data.get("key_points", []) if isinstance(data.get("key_points"), list) else []
    info.tags = data.get("tags", []) if isinstance(data.get("tags"), list) else []
    info.personal_thoughts = str(data.get("personal_thoughts", ""))
    info.related_keywords = data.get("related_keywords", []) if isinstance(data.get("related_keywords"), list) else []

    # importance 验证 (1-5)
    try:
        imp = int(data.get("importance", 3))
        info.importance = max(1, min(5, imp))
    except (ValueError, TypeError):
        info.importance = 3

    # topic 验证
    valid_topics = ["llm", "hardware", "security", "trends", "ideas", "other"]
    topic = str(data.get("topic", "other")).lower()
    info.topic = topic if topic in valid_topics else "other"

    # tags 数量限制
    if len(info.tags) > 8:
        info.tags = info.tags[:8]
    if len(info.tags) < 1:
        info.tags = ["未分类"]

    # 类型专属字段
    type_fields = [
        "prerequisites", "applicable_scenarios", "key_steps", "code_snippets",
        "common_issues", "core_events", "key_conclusions", "multiple_viewpoints",
        "comparison_table", "lessons_learned",
    ]
    for f in type_fields:
        val = data.get(f, [])
        setattr(info, f, val if isinstance(val, list) else [])

    return info


def extract_card_info(article: Article) -> ExtractedInfo:
    """
    完整的两阶段提取流程：
    1. 类型识别
    2. 类型专属提取
    3. 验证与容错
    """
    # 阶段 1: 类型识别
    article_type = classify_article(article)

    # 阶段 2: 类型专属提取
    base_prompt = _load_base_prompt()
    type_prompt = _load_prompt_template(article_type)

    # 组合 system prompt
    system_prompt = base_prompt["system_prompt"] + "\n\n" + type_prompt["system_prompt"]

    # 构建 user content
    user_content = f"文章标题：{article.title}\n\n文章内容：\n{article.content}"

    # 尝试提取，最多重试 3 次
    for attempt in range(3):
        try:
            resp = _call_llm_with_retry(system_prompt, user_content, max_retries=1)
            data = _extract_json_from_response(resp)
            if data:
                info = _validate_result(data, article_type)
                # 检查必填字段
                missing = [f for f in base_prompt["required_fields"] if not getattr(info, f, None)]
                if not missing:
                    log.info(f"提取成功: {article.title[:30]}... (类型={article_type})")
                    return info
                else:
                    log.warning(f"缺少必填字段 {missing}，重试 ({attempt+1}/3)")
            else:
                log.warning(f"JSON 解析失败，重试 ({attempt+1}/3)")
        except Exception as e:
            log.warning(f"提取异常: {e}，重试 ({attempt+1}/3)")

    # 最终降级：生成模板卡片
    log.error(f"提取 3 次均失败，生成模板卡片: {article.title[:30]}...")
    info = ExtractedInfo()
    info.article_type = article_type
    info.summary = "【待补充】"
    info.key_points = ["【待补充】"]
    info.tags = ["待分类"]
    info.needs_review = True
    # 尝试从文章标题推断 topic
    info.topic = "other"
    return info
