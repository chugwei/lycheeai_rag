# AGENTS.md — LycheeAI RAG (荔知君)

Lychee-cultivation vertical-domain RAG Q&A system built on LangChain + FastAPI, with a Vue 3 web client and a WeChat miniprogram client. Chinese-language project; comments/prompts/dicts are Chinese.

## Run / build / test commands

- **Backend:** `python main.py` (FastAPI on port **18888** — note: README says 18889, but `config/settings.yaml` `server.api_port` and `start_all.bat` use 18888). First launch preloads the RAG pipeline (~1-2 min).
- **One-click (Windows):** `start_all.bat` (or `.ps1`) — start services or rebuild indexes via menu. `start_backend.bat` / `start_frontend.bat` / `stop_all.bat` also available.
- **Python env:** conda env `lycheeai` at `E:\miniconda3\envs\lycheeai\python.exe` (hardcoded in the .bat scripts). Python ≥ 3.8 (3.8 compat shims exist in `main.py`).
- **Indexes:** `python scripts/build_index.py` — incremental by default; `--force` for full rebuild; `--skip-vector` for BM25 only. Reads `data/raw/`, writes `indexes/` (ChromaDB, `bm25_index.pkl`, `chunks_cache.json`). `rebuild_index.bat` wraps it.
- **Recall eval:** `python scripts/eval_recall.py` (compares BM25 / vector / RRF / +dict expansion).
- **Tests:** `python -m pytest tests/` (unittest-style: `test_chunker.py`, `test_chunk_quality.py`).
- **Frontend (`web/`):** `npm run dev` (Vite dev), `npm run build` (outputs `web/dist/`, served by FastAPI as SPA), `npm run preview`. Stack: Vue 3 + Element Plus + Tailwind + axios + marked/dompurify.
- **Docker infra (optional):** `docker-compose up -d` for MySQL 8.0 + Milvus 2.4 + etcd + MinIO (only needed when `vector_db.type` = `milvus` / `milvus_mysql`).

## Configuration & logging conventions

- Config is a singleton: `config.settings.Config` loads `config/settings.yaml` + `.env`, applies `${VAR_NAME}` interpolation, resolves relative paths against project root, then applies `.env` overrides for keys like `VECTOR_DB_TYPE`, `MYSQL_*`, `EXTERNAL_API_KEY`, `EXTERNAL_LLM_MODEL`. Access via `Config.get("llm.external.model")` or `get_config(...)`.
- **Always call `Config.load()` before reading config**, and `utils.logging_setup.setup_logging()` before any loguru/stdlib logging — `main.py` does this ordering; new entrypoints must match. Logging is loguru with an `InterceptHandler` bridging stdlib libs; noisy third-party loggers are silenced.
- `.env` holds secrets (API keys, DB passwords) and is gitignored — never commit. No `.env.example` exists; required keys are referenced in `settings.py` `env_overrides` and as `${...}` placeholders in `settings.yaml`.
- `PROJECT_ROOT` is inserted into `sys.path` at the top of `main.py` and `scripts/*.py`; scripts assume they can import top-level modules (`from config.settings import ...`). Preserve this pattern in new scripts.

## Architecture boundaries (what lives where)

- `main.py` — FastAPI entry, ~22 endpoints + SPA frontend mount + lifespan preload. Do not put RAG logic here.
- `rag_chain.py` — `LangChainRAGPipeline` (14-step LCEL pipeline). Entry point `get_pipeline()` (cached singleton). Core data flow: query parse → expansion → parallel retrieval → RRF fusion → BGE rerank → prompt assembly → LLM → post-process (citations + CoT cleanup) → dict sedimentation.
- `retrievers.py` — `MilvusMySQLRetriever` + `BM25Retriever` (LangChain `BaseRetriever` subclasses).
- `retrieval/` — retrieval internals: `fusion.py` (RRF + dynamic BM25 weighting), `vector_searcher.py`, `query_expansion.py`, `query_parser.py`, `domain_expander.py` + `domain_learner.py` (domain-dict expansion + auto-sedimentation).
- `reranker.py` — `FlagEmbeddingReranker` (`BaseDocumentCompressor`, BGE cross-encoder).
- `post_processor.py` — citation `[1][2]` extraction + 4-layer LLM CoT/thinking-chain stripping.
- `prompts.py` + `config/prompts/*.txt` — prompt templates (system/diagnosis/agronomy/knowledge_qa/relation_reasoning). Edit prompts in the `.txt` files, not in code.
- `llm_factory.py` — `ChatOpenAI` factory; backend selectable (`external` DeepSeek via SenseNova / `openai` local / `ollama` / `auto`).
- `data_pipeline/` — document loading, `RuleChunker` (rule-v3, structure-first recursive split with production gates), `vector_indexer.py`, `bm25_indexer.py`, `models.py` (Document/Chunk).
- `external_apis/api_client.py` — 13 lychee image-recognition / prediction APIs (`external_api.base_url` in config).
- `conversation/state_manager.py` — multi-turn dialog (memory/redis).
- `api/` — `schemas.py` (Pydantic models) + `knowledge_routes.py` (knowledge-base file CRUD router).
- `data/domain_dict.json` — 253-entry domain dictionary (synonyms/colloquial/abbreviations/stage_aliases/learned). The `learned` layer is written at runtime by `domain_learner.py`.
- `indexes/` — generated artifacts (ChromaDB, BM25 pickle, GraphML KG, HuggingFace `model_cache/`). Regenerable; do not hand-edit.

## Gotchas

- **Vector DB is pluggable:** `vector_db.type` in `settings.yaml` can be `chroma` (default, local, no Docker) / `milvus` / `milvus_mysql`. Code paths differ — check the configured type before assuming Milvus/MySQL availability.
- **Embedding model:** default `BAAI/bge-base-zh-v1.5` (768-dim), fallback `intfloat/multilingual-e5-small`. Reranker `use_fp16: false` on CPU. Models download into `indexes/model_cache/` (gitignored).
- **Chunker versioning:** `chunker.version` (`rule-v3`) is recorded in the build manifest for traceability/compat. Index build enforces production gates (length caps, dup %, metadata completeness) — see `docs/chunking-production.md` before changing `data_pipeline/chunker.py`.
- **Phenology:** 9 growth stages auto-matched by month via `config/settings.yaml` `phenology.stage_month_mapping`; `query_parser.py` uses this.
- **Windows-first:** shell scripts are `.bat`/`.ps1`; paths use `E:\github_project\lycheeai_rag`. Git Bash is available but the Python interpreter path is Windows-specific.
- **Read before changing sensitive areas:** `docs/chunking-production.md` (chunker/index gates), `README.md` (architecture overview), `config/settings.yaml` (all tunable params + their documented constraints).
