# LycheeAI 荔知君

基于 LangChain 的荔枝种植垂直领域 RAG 智能问答系统。

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-0.2+-green.svg)](https://www.langchain.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 简介

LycheeAI 是面向荔枝种植的垂直领域 RAG 问答系统，覆盖病虫害诊断、农事指导与全生长周期管理。检索侧采用多路融合（Milvus 向量 + BM25 关键词，RRF 融合 + BGE 精排），回答附带可溯源的引用标记；同时对接 13 个已部署的图像识别 / 预测模型 API，支持图文多模态问答。

## 核心特性

- **图文多模态问答**：文本问答 + 图片上传，对接 13 个外部图像识别 / 预测 API（花穗、坐果率、蒂蛀虫、霜疫霉病等）
- **多路检索融合**：Milvus 向量与 BM25 关键词检索并行执行，RRF 融合排序，查询含领域专名时自动提升 BM25 权重
- **BGE 交叉编码器精排**：bge-reranker-base 对候选分块精排，逐条输出相关度评分
- **来源溯源**：回答中 `[1][2]` 引用标记，可查看完整 chunk 内容与相关度评分
- **领域专有词典**：253 条荔枝术语（同义词 / 农民口语→专业术语 / 农药简称 / 物候期别名），毫秒级查询扩展，并随用户查询自动沉淀新术语
- **物候期感知**：按当前日期自动匹配 9 个荔枝生长阶段并注入 Prompt
- **LangChain LCEL 管线**：14 步 RAG 流程编排，含思考链清理与置信度计算
- **完整 Web 应用**：Vue 3 前端（问答 / 识病 / 预警 / 知识库管理）+ FastAPI 后端，Docker 一键启动存储

## 系统架构

```text
┌─ Vue 3 前端：智能问答 · 果园识病 · 风险预警 · 荔枝知识库 ─────────┐
                                │ HTTP
┌─ FastAPI 后端（:18889）：/api/query · /api/image/analyze · /api/predict · /api/knowledge ─┐
│  LangChain RAG 管线：查询解析 → 词典扩展 → 并行检索
│                     → RRF 融合 → Rerank 精排 → LLM 生成 → 引用提取
├─ 存储：Milvus 2.4（向量）· MySQL 8.0（元数据）· BM25 索引（关键词）
└─ 外部 API：13 个图像识别 / 预测接口
```

## 检索评测

在自建评测集上对比四种检索配置的 Recall@5，复现命令：`python scripts/eval_recall.py`。

| 检索配置 | Recall@5 |
|----------|----------|
| 纯 BM25 | 58% |
| 纯向量（multilingual-e5 + Milvus） | 82% |
| 向量 + BM25，RRF 融合 | 89% |
| + 领域词典扩展 + BGE Rerank | 91% |

> 以上为内部评测的初步结果，**待复核确认**，最终数值以评测脚本复现输出为准。

## 技术栈

| 层 | 选型 |
|----|------|
| 管线框架 | LangChain 0.2 + LCEL |
| LLM | DeepSeek-v4-Flash（SenseNova，OpenAI 兼容 API） |
| 后端 / 前端 | FastAPI + uvicorn / Vue 3 + Element Plus + Tailwind CSS |
| 向量库 | Milvus 2.4（Docker）+ MySQL 8.0 元数据 |
| Embedding | intfloat/multilingual-e5-small（384 维） |
| Reranker | BAAI/bge-reranker-base（交叉编码器） |
| BM25 | rank-bm25 + jieba 中英文分词 |

## 快速开始

环境要求：Python ≥ 3.8（推荐 3.11）、Docker。

```bash
# 1. 启动存储服务（MySQL 8.0 + Milvus 2.4 + etcd + MinIO）
docker-compose up -d

# 2. 安装依赖
pip install -r requirements.txt

# 3. 创建 .env 并填入关键配置
#    EXTERNAL_API_KEY=<SenseNova API Key>
#    EXTERNAL_LLM_MODEL=deepseek-v4-flash
#    MYSQL_PASSWORD=<密码>

# 4. 构建知识库索引（data/raw → 分块 → 向量索引 + BM25 索引）
#    见 data_pipeline/ 下 DocumentLoader / RuleChunker / VectorIndexer / BM25Indexer

# 5. 启动
start_all.bat    # 或 python main.py
```

启动后访问 http://localhost:18889，API 文档见 `/docs`。

## 目录结构

```text
├── main.py、rag_chain.py、retrievers.py、reranker.py 等   # 后端核心模块
├── api/            # Pydantic 请求/响应模型，知识库文件 CRUD 路由
├── config/         # settings.yaml 全局配置与 Prompt 模板
├── retrieval/      # 检索层：RRF 融合、向量检索、查询解析与扩展
├── data_pipeline/  # 文档加载、规则分块、索引构建
├── external_apis/  # 13 个外部图像识别 / 预测 API 客户端
├── conversation/   # 多轮对话状态管理
├── utils/          # 双语语言检测、Milvus REST 客户端等工具
├── web/            # Vue 3 前端源码（含预构建 dist/）
├── data/           # 知识库源文档、知识图谱数据与领域词典
├── indexes/        # BM25 / 向量索引文件与模型缓存
└── scripts/        # 评测脚本（eval_recall.py）
```

## 开发历程

- v1 基础版：先跑通"单路向量检索 + LLM 生成"的最小可用问答系统
- 架构重构：迁移到 LangChain，用 LCEL 编排 RAG 管线，抽象 Retriever / Reranker 组件
- 检索强化与评测：加入 BM25 多路检索、RRF 融合、领域词典扩展与 Rerank 精排，并建立评测脚本量化各配置的召回差异（评测数据待复核）

## API 示例

```bash
# RAG 文本问答
curl -X POST http://localhost:18889/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "荔枝霜疫霉病怎么防治？"}'

# 图像识别 + LLM 分析建议
curl -X POST http://localhost:18889/api/image/analyze \
  -F "image=@test.jpg" -F "api_type=guoshi"
```

完整端点列表（`/api/predict`、`/api/knowledge/*`、`/api/chunks` 等）见 `/docs`。

## 许可证

[MIT](LICENSE)

