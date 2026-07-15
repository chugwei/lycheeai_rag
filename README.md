<div align="center">

# 🍒 LycheeAI 荔知君

### 基于 LangChain 框架的荔枝种植垂直领域 RAG 智能问答系统

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-0.2+-green.svg)](https://www.langchain.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue.js](https://img.shields.io/badge/Vue.js-3.4+-4FC08D.svg)](https://vuejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 📖 项目简介

**LycheeAI 荔知君（LangChain 版）** 是基于 LangChain 框架重构的荔枝种植垂直领域 RAG 智能问答系统。系统融合检索增强生成（RAG）技术与 13 个已部署模型 API 的实时数据，实现对荔枝全生长周期病虫害诊断、农事指导及种植管理的精准问答。

### 🎯 核心特性

| 特性 | 说明 |
|------|------|
| **图文多模态输入** | 文本问答 + 图片上传，9 种图像识别 + LLM 分析建议 |
| **LangChain LCEL 管线** | 使用 LangChain 表达式语言编排 14 步 RAG 管线 |
| **多路检索融合** | Milvus 向量检索 + BM25 关键词检索，RRF 融合排序 |
| **并行检索** | 向量 + BM25 通过 ThreadPoolExecutor 并行执行 |
| **BGE-Reranker 精排** | 交叉编码器精排，Top-K 相关度评分 |
| **混合存储架构** | Milvus（向量）+ MySQL（元数据），兼顾性能与灵活性 |
| **9 种图像识别** | 雌雄花/花穗/梢量/坐果率/果实/新梢/白点/蒂蛀虫 + LLM 分析 |
| **物候期感知** | 根据当前日期自动匹配荔枝生长阶段（9 个物候期） |
| **知识库管理** | 文件上传/预览/下载/批量操作，分块可视化查看与编辑 |
| **Vue 3 前端** | Element Plus + Tailwind CSS，对话历史持久化，SPA 路由 |
| **LLM 思考链清理** | 4 层防御机制，自动剥离 LLM 输出的思考过程/推理链 |
| **来源溯源** | 回答中 `[1][2]` 引用标记，点击可查阅完整 chunk 内容及相关度评分 |
| **领域专有词典** | 253 条荔枝领域术语（病虫害别名、农药俗名、农民口语→专业术语映射） |
| **查询自动扩展** | 口语→专业术语 + 同义词展开，无 LLM 开销，毫秒级 |
| **词典自动沉淀** | 规则粗筛 + LLM 确认，随用户查询持续积累新术语，系统越用越准 |
| **动态 RRF 权重** | 查询含领域专名时自动提升 BM25 权重（×1.3），增强精确匹配 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────┐
│            Vue 3 前端 (localhost:18889)              │
│  智能问答 │ 果园识病 │ 风险预警 │ 荔枝知识库        │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────┐
│              FastAPI 后端 (18889端口)                │
│  /api/query  /api/image/analyze  /api/predict       │
│  /api/knowledge/*  /api/llm/config  /api/health     │
├─────────────────────────────────────────────────────┤
│              LangChain RAG 管线 (14步)               │
│  ┌─────────────────────────────────────────────┐    │
│  │ 查询解析 → 查询扩展 → 并行检索              │    │
│  │ → RRF融合 → Rerank精排 → Prompt组装        │    │
│  │ → LLM生成 → 后处理 → 引用提取              │    │
│  └─────────────────────────────────────────────┘    │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐     │
│  │ ChatOpenAI│  │MilvusMySQL│  │FlagEmbedding │     │
│  │  (LLM)   │  │ Retriever │  │  Reranker    │     │
│  └──────────┘  └──────────┘  └──────────────┘     │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐     │
│  │  Milvus  │  │  MySQL   │  │    BM25      │     │
│  │ 向量检索  │  │ 元数据    │  │ 关键词检索   │     │
│  └──────────┘  └──────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│           外部 API (13个图像/预测接口)               │
│  雌雄花 │ 花穗 │ 梢量 │ 开花率 │ 坐果率 │ 果实     │
│  新梢 │ 白点 │ 蒂蛀虫 │ 椿象 │ 霜疫霉病 │ 炭疽病   │
└─────────────────────────────────────────────────────┘
```

### RAG 管线流程

```
用户查询
    │
    ▼
[1] 查询解析：意图分类 + 物候期匹配 + 语言检测
    │
    ▼
[2] 查询扩展：
    ├── 领域词典扩展（口语→专业术语 + 同义词，始终执行）
    └── LLM 改写（可选，生成 3 个语义变体）
    │
    ▼
[3] 并行检索（ThreadPoolExecutor）
    ├── MilvusMySQLRetriever（向量检索, Top-K）
    └── BM25Retriever（关键词检索, Top-K）
    │
    ▼
[4] RRF 融合排序（k=60）+ 动态权重调整
    └── 查询含领域专名时 BM25×1.3, vector×0.9
    │
    ▼
[5] FlagEmbeddingReranker 精排（交叉编码器, Top-5）
    │
    ▼
[6] Prompt 组装 → [7] ChatOpenAI 生成（思考链清理）
    │
    ▼
[8] 后处理：引用提取 → 来源构建 → 置信度计算
    │
    ▼
[9] 词典自动沉淀：提取未知词 → LLM 确认 → 写入 learned 层
    │
    ▼
输出：回答 + 引用来源（含相关度评分）+ 意图 + 置信度
```

---

## 🛠️ 技术栈

| 层 | 技术 | 说明 |
|-----|------|------|
| **框架** | LangChain 0.2 + LCEL | 管线编排、Retriever 抽象、文档压缩 |
| **推理** | DeepSeek-v4-Flash (SenseNova) | OpenAI 兼容 API，通过 `langchain_openai.ChatOpenAI` 调用 |
| **后端** | FastAPI + uvicorn | REST API 服务，SPA 路由 |
| **前端** | Vue 3 + Element Plus + Tailwind CSS | 单页应用，四功能模块 |
| **向量库** | Milvus 2.4 + MySQL 8.0 | 混合存储，Docker 部署 |
| **Embedding** | intfloat/multilingual-e5-small | 多语言模型，384 维 |
| **Reranker** | BAAI/bge-reranker-base | 交叉编码器，278M 参数 |
| **BM25** | rank-bm25 + jieba | 中英文双语分词 |



## 📁 目录结构

```
lycheeai_langchain/
├── main.py                 # FastAPI 入口（22 个端点 + SPA 前端）
├── rag_chain.py            # LangChain RAG 管线核心（14 步）
├── retrievers.py           # MilvusMySQLRetriever + BM25Retriever
├── reranker.py             # FlagEmbeddingReranker（BGE 交叉编码器）
├── prompts.py              # 5 种意图 Prompt 模板组装
├── llm_factory.py          # ChatOpenAI 工厂（DeepSeek 配置）
├── post_processor.py       # 引用提取 + 4 层思考链清理
├── confidence.py           # 置信度计算
├── query_parser.py         # 意图分类 + 物候期匹配
├── config/
│   ├── settings.yaml       # 全局配置
│   ├── settings.py         # 配置加载器（YAML + .env）
│   └── prompts/            # 5 个 Prompt 模板文件
├── api/
│   ├── schemas.py          # Pydantic 请求/响应模型
│   └── knowledge_routes.py # 知识库文件 CRUD API
├── retrieval/              # 检索层
│   ├── fusion.py           # RRF 融合 + 动态权重
│   ├── vector_searcher.py  # Milvus+MySQL 向量检索
│   ├── query_parser.py     # 查询解析
│   └── query_expansion.py  # 查询扩展
├── data_pipeline/          # 数据管线（复用原版）
│   ├── bm25_indexer.py     # BM25 索引
│   └── models.py           # Document/Chunk 数据模型
├── external_apis/          # 13 个外部 API 客户端
│   └── api_client.py       # 图像识别 + 预测 API
├── conversation/           # 对话状态管理
│   └── state_manager.py    # 多轮对话（memory/redis）
├── utils/                  # 工具模块
│   ├── lang_detector.py    # 双语语言检测
│   └── milvus_http.py      # Milvus REST 客户端
├── web/                    # Vue 3 前端
│   ├── dist/               # 生产构建产物
│   └── src/                # 源码
├── data/                   # 知识库数据
│   ├── raw/                # 28 个源文档
│   └── kg_data/            # 知识图谱 JSON
├── indexes/                # 索引文件
│   ├── bm25_index.pkl      # BM25 索引
│   ├── chroma_db/          # ChromaDB
│   └── model_cache/        # Embedding 模型缓存
├── .env                    # 环境变量
├── docker-compose.yml      # Docker 服务
├── requirements.txt        # Python 依赖
├── start_all.bat           # 一键启动
├── start_backend.bat       # 启动后端
├── start_frontend.bat      # 启动前端
└── stop_all.bat            # 停止服务
```

---

## 🚀 快速开始

### 环境要求

| 组件 | 要求 | 说明 |
|------|------|------|
| Python | ≥ 3.8 | 推荐 3.11 |
| Node.js | ≥ 18 | 前端构建（可选，已有预构建） |
| Docker | 20.10+ | 运行 MySQL + Milvus |
| GPU（可选） | NVIDIA ≥ 8GB | 本地推理用，无 GPU 可用外部 LLM |

### 1. 克隆项目

```bash
git clone https://github.com/your-username/lycheeai_langchain.git
cd lycheeai_langchain
```

### 2. 安装依赖

```bash
conda create -n lycheeai python=3.11 -y
conda activate lycheeai
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 API Key
```

关键配置：
```env
EXTERNAL_API_KEY=sk-xxx              # SenseNova API Key
EXTERNAL_LLM_MODEL=deepseek-v4-flash # LLM 模型
VECTOR_DB_TYPE=milvus_mysql          # 向量库类型
MYSQL_PASSWORD=your-password         # MySQL 密码
```

### 4. 启动 Docker 服务

```bash
docker-compose up -d
```

启动 MySQL 8.0 + Milvus 2.4 + etcd + MinIO。

### 5. 构建知识库索引

```bash
python -c "
from data_pipeline.document_loader import DocumentLoader
from data_pipeline.chunker import RuleChunker
from data_pipeline.vector_indexer import VectorIndexer
from data_pipeline.bm25_indexer import BM25Indexer

loader = DocumentLoader()
docs = loader.load_directory('data/raw')
chunker = RuleChunker()
chunks = chunker.chunk(docs)

vi = VectorIndexer()
vi.build_index(chunks)

bi = BM25Indexer()
bi.build(chunks)
print(f'索引构建完成: {len(chunks)} 个分块')
"
```

### 6. 启动服务

```bash
# 方式一：一键启动
start_all.bat

# 方式二：手动启动
python main.py
```

### 7. 访问

| 服务 | 地址 |
|------|------|
| **前端** | http://localhost:18889 |
| **API 文档** | http://localhost:18889/docs |
| **健康检查** | http://localhost:18889/api/health |

---

## 📡 API 文档

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/query` | POST | RAG 文本问答 |
| `/api/query/image` | POST | RAG 图文问答 |
| `/api/image/analyze` | POST | 图像识别 + LLM 分析建议 |
| `/api/predict` | POST | 病虫害/产量预测（4 种） |
| `/api/health` | GET | 健康检查 |
| `/api/llm/config` | GET/POST | LLM 配置管理 |
| `/api/chunks` | GET | 分块数据浏览 |
| `/api/chunks/{id}` | GET | 分块详情 |
| `/api/auth/login` | POST | 管理员登录 |
| `/api/knowledge/*` | 多种 | 知识库文件 CRUD |

```bash
# 文本问答
curl -X POST http://localhost:18889/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "荔枝霜疫霉病怎么防治？"}'

# 图像识别
curl -X POST http://localhost:18889/api/image/analyze \
  -F "image=@test.jpg" \
  -F "api_type=guoshi"
```

---

## 🔧 LangChain 架构详解

### 核心组件

| 组件 | 类 | 用途 |
|------|-----|------|
| **LLM** | `ChatOpenAI` | DeepSeek-v4-Flash 调用 |
| **向量检索** | `MilvusMySQLRetriever(BaseRetriever)` | Milvus 向量 + MySQL 元数据 |
| **BM25 检索** | `BM25Retriever(BaseRetriever)` | 中英文 BM25 检索 |
| **Reranker** | `FlagEmbeddingReranker(BaseDocumentCompressor)` | BGE 交叉编码器精排 |
| **管线** | `LangChainRAGPipeline` | 14 步完整 RAG 流程 |

### 领域专有词典

`data/domain_dict.json` 包含 253 条荔枝领域术语：

| 层 | 条目数 | 示例 |
|---|--------|------|
| **synonyms** | 65 | 蒂蛀虫 ↔ 荔枝蛀蒂虫 ↔ 果蛀虫 |
| **colloquial** | 148 | "叶子长白毛"→霜疫霉病, "臭屁虫"→荔枝蝽, "果子臭了流酸水"→酸腐病 |
| **abbreviations** | 10 | 波尔多→波尔多液, 甲托→甲基托布津 |
| **stage_aliases** | 19 | 抽穗期→花穗生长期, 膨果期→果实膨大期 |
| **learned** | 动态 | 系统自动沉淀的新术语 |

**词典自动沉淀机制：**
```
用户query → 提取未知词 → 检索命中实体 → LLM确认 → 写入learned层
```

示例：用户问"果子冒白烟怎么治"，系统检索命中霜疫霉病相关文档，LLM确认"果子冒白烟"指代霜疫霉病后，自动写入词典。下次有相同描述时直接扩展为专业术语。

**Recall 评测：**
```bash
python scripts/eval_recall.py
```
对比 4 种配置的 Recall@5 / MRR@10：纯 BM25 → 纯向量 → RRF 融合 → +词典扩展

### 数据流

```python
# 核心调用
from rag_chain import get_pipeline

pipeline = get_pipeline()
result = pipeline.run(
    query="荔枝霜疫霉病怎么防治？",
    conversation_id="conv_123",
    use_query_expansion=True,
)

# 返回
result.answer          # LLM 生成的回答
result.sources         # 引用来源列表（含 rerank_score）
result.intent          # 意图分类
result.confidence      # 置信度 0-1
result.latency         # 耗时（秒）
```

---

## 📊 性能指标

| 指标 | 数值 |
|------|------|
| 向量检索 | 0.1-0.3 秒 |
| BM25 检索 | 0.01-0.05 秒 |
| RRF 融合 | < 0.01 秒 |
| Rerank 精排 | 1-3 秒 |
| LLM 生成 | 3-10 秒 |
| 端到端 | 5-15 秒 |
| 知识库规模 | 260 个分块，28 个文档 |
| 向量维度 | 384 维（multilingual-e5-small） |
| 领域词典 | 253 条术语（65同义词 + 148口语映射 + 10农药简称 + 19物候期别名） |
| 词典扩展 | 无 LLM 开销，毫秒级 |
| Recall@5 | 纯 BM25 58% → RRF 82% → +词典 89% → +Rerank 91% [待确认] |

---


## 🙏 致谢

- [LangChain](https://www.langchain.com/) - LLM 应用开发框架
- [Milvus](https://milvus.io/) - 向量数据库
- [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) - BGE Reranker
- [SenseNova](https://sensenova.cn/) - DeepSeek-v4-Flash 推理服务
- [Element Plus](https://element-plus.org/) - Vue 3 UI 组件库
