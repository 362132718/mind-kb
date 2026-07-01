# 个人经验知识库系统

基于 LLM 自动提取 + 向量语义搜索的本地化个人知识库。将文章/笔记放入 `queue/`，系统自动提取摘要、标签、要点，生成结构化知识卡片，支持语义搜索。

## 核心特性

- **两阶段 LLM 提取**：自动识别文章类型（教程/资讯/观点/评测/经验），使用专属 prompt 提取结构化信息
- **语义搜索**：基于 zvec 向量数据库，支持语义相似度检索、可选 Reranker 重排序、语义聚合去重
- **去重与关联**：相似度 ≥0.95 自动合并，0.8~0.95 创建新卡并双向关联，<0.8 独立创建
- **模型配置解耦**：LLM、Embedding、Reranker 均通过 `.env` 配置，切换模型只改配置文件
- **全平台支持**：Windows / macOS / Linux

## 目录结构

```
d:\知识库\
├── .env                          # API 密钥与模型配置
├── requirements.txt              # Python 依赖
├── queue/                        # 待处理文章（放入后自动处理）
├── cards/                        # 知识卡片（Markdown 格式）
├── archive/                      # 已处理文章存档
├── zvec_data/                    # zvec 向量数据库（自动创建）
├── logs/                         # 运行日志
├── src/
│   ├── config.py                 # 全局配置
│   ├── logger.py                 # 日志模块
│   ├── llm_client.py             # 大模型客户端（两阶段提取）
│   ├── embedding_client.py       # 向量模型客户端
│   ├── vector_store.py           # zvec 向量数据库管理
│   ├── card_manager.py           # 卡片解析/生成/读写
│   ├── pipeline.py               # 处理流水线
│   ├── search.py                 # 语义搜索模块
│   └── prompts/                  # LLM prompt 模板（按文章类型）
│       ├── base.json
│       ├── tutorial.json
│       ├── news.json
│       ├── opinion.json
│       ├── review.json
│       └── experience.json
└── scripts/
    ├── setup.py                  # 初始化环境
    ├── process.py                # 手动触发处理
    ├── search_cli.py             # 命令行搜索
    ├── new_card.py               # 直接创建卡片
    └── watch_queue.py            # 监控 queue/ 自动处理
```

## 快速开始

### 1. 环境要求

- Python 3.10 ~ 3.12

### 2. 安装

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置

复制示例文件并填入 API Key：

```bash
cp .env.example .env
```

编辑 `.env`，将 `LLM_API_KEY` 改为你的真实 Key：

```env
# Silicon Flow API Key（必填）
LLM_API_KEY=sk-your-api-key-here

# 以下留空则与 LLM_API_KEY 相同
EMBEDDING_API_KEY=
RERANKER_API_KEY=
```

### 4. 初始化

```bash
python scripts/setup.py
```

### 5. 使用

**处理文章**：将文章（.md/.txt/.html/.pdf）放入 `queue/`，然后：

```bash
python scripts/process.py
```

**自动监控**（可选）：

```bash
python scripts/watch_queue.py
```

**语义搜索**：

```bash
python scripts/search_cli.py "查询内容"
python scripts/search_cli.py "查询内容" --top 10 --topic llm
```

**直接创建卡片**（无需原始文章）：

```bash
python scripts/new_card.py
python scripts/new_card.py --input "我的想法内容"
```

## 知识卡片格式

每张卡片为 Markdown 文件，包含 YAML front matter 元数据 + 类型专属正文：

```yaml
---
title: "标题"
source: "https://..."
date: "2026-07-01"
tags: ["tag1", "tag2"]
importance: 4
topic: "llm"
card_id: "kb_20260701_001"
article_type: "tutorial"
needs_review: false
related_cards: ["kb_xxx"]
related_keywords: ["关键词1", "关键词2"]
---
```

支持 5 种文章类型，各有专属正文模板：

| 类型 | 正文结构 |
|------|---------|
| tutorial | 摘要 → 适用场景 → 前置条件 → 关键步骤 → 代码示例 → 常见问题 → 个人思考 → 原始摘录 |
| news | 摘要 → 核心事件 → 关键结论 → 个人思考 → 原始摘录 |
| opinion | 摘要 → 核心观点 → 关键结论 → 个人思考 → 原始摘录 |
| review | 摘要 → 对比总结 → 适用场景 → 优缺点对比 → 关键结论 → 个人思考 → 原始摘录 |
| experience | 摘要 → 踩坑/最佳实践 → 关键步骤 → 适用场景 → 经验教训 → 个人思考 → 原始摘录 |

## 模型切换

只改 `.env`，不改代码：

```env
# 默认：Silicon Flow 云端
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B

# 切换到本地 Ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=nomic-embed-text
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 向量数据库 | zvec（阿里开源，嵌入式，支持 Linux/macOS/Windows） |
| LLM / Embedding | openai 兼容 API（Silicon Flow / Ollama / 任意兼容服务） |
| 文章解析 | beautifulsoup4 (HTML)、PyPDF2 (PDF)、原生 (MD/TXT) |
| 文件监控 | watchdog |
| 配置管理 | python-dotenv (.env) |
