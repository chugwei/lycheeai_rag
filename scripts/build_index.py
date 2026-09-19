"""
索引构建脚本 - 从 data/raw 目录读取文件，构建完整索引

功能：
1. 加载所有 PDF/MD/TXT/DOCX/XLSX 文件
2. 分块
3. 构建 BM25 索引
4. 构建向量索引（ChromaDB）
5. 保存 chunks_cache.json（供前端分块浏览使用）

增量模式（默认）：
- 自动检测新增 / 修改 / 删除的文件
- 新增/修改的文件重新加载+分块
- 未改动的文件保留原分块
- 被删除的文件从 ChromaDB 中清除
- BM25 全量重建（~7s，不值得做增量）
- --force 标记跳过增量检测，强制全量重建

用法：
    python scripts/build_index.py
    python scripts/build_index.py --data-dir data/raw  # 指定其他目录
    python scripts/build_index.py --skip-vector        # 跳过向量索引（仅 BM25）
    python scripts/build_index.py --force              # 强制全量重建
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from config.settings import Config, get_config
from data_pipeline.document_loader import DocumentLoader
from data_pipeline.chunker import RuleChunker
from data_pipeline.bm25_indexer import BM25Indexer
from data_pipeline.vector_indexer import VectorIndexer
from scripts.evaluate_chunking import evaluate as evaluate_chunking
from utils.logging_setup import setup_logging


# ===================================================================
# 文件清单管理
# ===================================================================

def _get_file_stats(data_dir: str = None) -> Dict[str, dict]:
    """
    扫描 data 目录，计算每个文件的 mtime 和 content_hash

    Returns:
        {filename: {"mtime": float, "content_hash": str, "size": int}}
    """
    stats = {}
    target_dir = Path(data_dir) if data_dir else Path(get_config("paths.raw_data_dir", "./data/raw"))
    if not target_dir.exists():
        return stats

    loader = DocumentLoader()
    for fpath in sorted(target_dir.rglob('*')):
        if fpath.is_dir() or fpath.name.startswith('.'):
            continue
        suffix = fpath.suffix.lower()
        if suffix not in loader.supported_extensions:
            continue

        try:
            mtime = fpath.stat().st_mtime
            # 快速 content hash（前 8 位足矣）
            hasher = hashlib.sha256()
            hasher.update(fpath.read_bytes()[:65536])  # 最多读 64KB
            content_hash = hasher.hexdigest()[:8]
            stats[fpath.name] = {
                "mtime": mtime,
                "content_hash": content_hash,
                "size": fpath.stat().st_size,
            }
        except OSError as e:
            logger.warning(f"无法读取文件 {fpath.name}: {e}")
    return stats


def _classify_files(
    new_stats: Dict[str, dict],
    old_manifest: Dict[str, dict],
) -> Dict[str, List[str]]:
    """
    将文件分类为 unchanged / modified / new / deleted

    Returns:
        {"unchanged": [...], "modified": [...], "new": [...], "deleted": [...]}
    """
    classification = {
        "unchanged": [],
        "modified": [],
        "new": [],
        "deleted": [],
    }

    old_names = set(old_manifest.keys())
    new_names = set(new_stats.keys())

    for name in new_names & old_names:
        old = old_manifest[name]
        cur = new_stats[name]
        if old["content_hash"] == cur["content_hash"] and old["mtime"] == cur["mtime"]:
            classification["unchanged"].append(name)
        else:
            classification["modified"].append(name)

    for name in new_names - old_names:
        classification["new"].append(name)

    for name in old_names - new_names:
        classification["deleted"].append(name)

    return classification


# ===================================================================
# 索引构建
# ===================================================================

def build_index(data_dir: str = None, skip_vector: bool = False, force: bool = False):
    """构建完整索引（支持增量）"""
    start_time = time.time()

    # 加载旧 cache（用于增量检测）
    cache_path = Path(get_config("paths.indexes_dir", "./indexes")) / "chunks_cache.json"
    old_cache = {}
    if cache_path.exists() and not force:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                old_cache = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"无法读取旧 cache，将全量重建: {e}")
            old_cache = {}

    old_manifest = old_cache.get("file_manifest", {})

    # ─── 文件分类 ───
    logger.info("=" * 50)
    logger.info("Step 0: 文件变更检测")
    logger.info("=" * 50)
    new_stats = _get_file_stats(data_dir or get_config("paths.raw_data_dir", "./data/raw"))
    classification = _classify_files(new_stats, old_manifest)

    changed_count = len(classification["modified"]) + len(classification["new"]) + len(classification["deleted"])
    exists = old_manifest != {}
    if not exists or force:
        logger.info(f"  → 全量重建模式 (force={force}, 已有旧manifest={exists})")
        # 全量重建：所有现有文件视为新增
        classification["new"] = list(new_stats.keys())
        classification["modified"] = []
        classification["unchanged"] = []
        # deleted 不处理（全量重建覆盖）
        classification["deleted"] = []
    else:
        logger.info(f"  不变: {len(classification['unchanged'])} 个文件")
        logger.info(f"  修改: {len(classification['modified'])} 个文件")
        logger.info(f"  新增: {len(classification['new'])} 个文件")
        logger.info(f"  删除: {len(classification['deleted'])} 个文件")

    if changed_count == 0 and old_manifest and not force:
        logger.info("没有需要处理的变更，索引已是最新")
        return True

    # 从旧 cache 中提取未变动的 chunk_ids
    old_chunks = old_cache.get("chunks", [])
    unchanged_chunk_ids = set()
    deleted_chunk_ids = set()
    if old_manifest:
        for name in classification["unchanged"]:
            ids = old_manifest[name].get("chunk_ids", [])
            unchanged_chunk_ids.update(ids)
        for name in classification["deleted"]:
            ids = old_manifest[name].get("chunk_ids", [])
            deleted_chunk_ids.update(ids)

    # ─── Step 1: 加载文档 ───
    logger.info("=" * 50)
    logger.info("Step 1/5: 加载文档")
    logger.info("=" * 50)
    loader = DocumentLoader()

    if old_manifest and not force:
        # 增量模式：只加载新增和修改的文件
        delta_names = set(classification["modified"] + classification["new"])
        actual_dir = data_dir or get_config("paths.raw_data_dir", "./data/raw")
        docs = []
        for fpath in sorted(Path(actual_dir).rglob('*')):
            if fpath.is_dir() or fpath.name.startswith('.'):
                continue
            if fpath.name in delta_names:
                try:
                    docs.extend(loader.load_file(str(fpath)))
                except Exception as e:
                    logger.warning(f"加载文件 {fpath.name} 失败: {e}")

        # 从旧 cache 中恢复未变动的文档内容（用于 chunk 重建和 metadata）
        # 但未变动的 chunk 保持不变，不需要重新分块
    else:
        docs = loader.load_directory(data_dir or get_config("paths.raw_data_dir", "./data/raw"))

    if not docs:
        logger.error("没有加载到任何文档，请检查 data/raw 目录")
        return False

    if not old_manifest or force:
        # 全量模式：质量门禁
        ingest_report = loader.load_report
        missing_rate = (len(ingest_report["empty_files"]) + len(ingest_report["failed_files"])) / max(
            1, ingest_report["candidate_files"]
        )
        if missing_rate > 0.01:
            logger.error(f"文档加载失败/空文档比例 {missing_rate:.2%} 超过 1% 门禁: {ingest_report}")
            return False

    ingest_report = getattr(loader, 'load_report', {})
    logger.info(f"  → 本次处理 {len(docs)} 个文档片段")

    # ─── Step 2: 分块 ───
    logger.info("=" * 50)
    logger.info("Step 2/5: 文档分块")
    logger.info("=" * 50)
    chunker = RuleChunker()
    new_chunks = chunker.chunk(docs)
    logger.info(f"  → 新生成 {len(new_chunks)} 个分块")

    # 质量门禁（全量模式才检查）
    if not old_manifest or force:
        quality_report = evaluate_chunking([
            {"text": c.content, "source": c.metadata.get("source", ""), "metadata": c.metadata}
            for c in new_chunks
        ], chunker.chunk_size)
        if not quality_report["passed"]:
            logger.error(f"分块质量门禁未通过: {quality_report['gates']}")
            return False
    else:
        quality_report = {}

    # 合并未变动的旧 chunk + 新 chunk
    if old_manifest and unchanged_chunk_ids:
        # 从旧 cache 中恢复未变动的 chunk
        kept_chunks = [c for c in old_chunks if c["chunk_id"] in unchanged_chunk_ids]
        logger.info(f"  → 保留未变动分块: {len(kept_chunks)} 个")

        # 将旧 chunk 转回 Chunk 对象（需要重构）
        from data_pipeline.models import Chunk
        kept = []
        for c in kept_chunks:
            chunk_meta = {k: c.get(k, "") for k in (
                "source", "page", "domain", "knowledge_type",
                "phenology_stages", "entities", "risk_level", "chunk_id"
            )}
            kept.append(Chunk(
                content=c.get("content", ""),
                metadata=chunk_meta,
                chunk_id=c["chunk_id"],
            ))
        all_chunks = kept + new_chunks
    else:
        all_chunks = new_chunks

    logger.info(f"  → 全量分块: {len(all_chunks)} 个")

    # ─── Step 3: 构建 BM25 索引 ───
    logger.info("=" * 50)
    logger.info("Step 3/5: 构建 BM25 索引")
    logger.info("=" * 50)
    bm25 = BM25Indexer()
    bm25.build(all_chunks)

    # ─── Step 4: 构建向量索引（ChromaDB） ───
    if not skip_vector:
        logger.info("=" * 50)
        logger.info("Step 4/5: 构建向量索引 (ChromaDB)")
        logger.info("=" * 50)
        try:
            vi = VectorIndexer()

            if old_manifest and not force and (deleted_chunk_ids or classification["modified"]):
                # 增量：删除旧 chunks + 只索引新 chunks
                old_source_chunk_ids = set()
                for name in classification["modified"] + classification["deleted"]:
                    ids = old_manifest[name].get("chunk_ids", [])
                    old_source_chunk_ids.update(ids)

                if old_source_chunk_ids:
                    logger.info(f"  → 需删除旧分块: {len(old_source_chunk_ids)} 个")
                    vi.delete_chunks(list(old_source_chunk_ids))

                # 只索引新/修改文件的分块
                vi.build_index(new_chunks)
            else:
                # 全量重建
                vi.build_index(all_chunks)
        except Exception as e:
            logger.error(f"向量索引构建失败: {e}")
            logger.error("为避免 BM25/向量索引版本不一致，本次构建判定失败")
            return False
    else:
        logger.info("Step 4/5: 跳过向量索引（--skip-vector 指定）")

    # ─── Step 5: 保存 chunks_cache.json ───
    _save_chunks_cache(all_chunks, chunker, quality_report, ingest_report,
                       new_stats, old_chunks)

    elapsed = time.time() - start_time
    logger.info("=" * 50)
    logger.info(f"✓ 索引构建完成！耗时 {elapsed:.1f}s")
    logger.info(f"  - 分块: {len(all_chunks)} 个")
    logger.info(f"  - BM25: {bm25.index_path}")
    if not skip_vector:
        logger.info(f"  - ChromaDB: {get_config('vector_db.chroma_path', './indexes/chroma_db')}")
    logger.info("=" * 50)
    return True


# ===================================================================
# Cache 保存
# ===================================================================

def _save_chunks_cache(
    chunks_list, chunker, quality_report, ingest_report,
    new_stats, old_cache_chunks=None
):
    """保存分块缓存（供前端 /api/chunks 使用）"""
    cache_path = Path(get_config("paths.indexes_dir", "./indexes")) / "chunks_cache.json"

    # 按文件分组统计
    from data_pipeline.chunker import Chunk
    files = {}
    for c in chunks_list:
        if isinstance(c, Chunk):
            source = c.metadata.get("source", "unknown")
            content = c.content
        else:
            source = c.get("source", "unknown")
            content = c.get("content", "")

        if source not in files:
            files[source] = {"chunk_count": 0, "char_count": 0}
        files[source]["chunk_count"] = files[source].get("chunk_count", 0) + 1
        files[source]["char_count"] = files[source].get("char_count", 0) + len(content)

    # 构建分块列表（用于前端表格展示）
    chunks_output = []
    for c in chunks_list:
        if isinstance(c, Chunk):
            meta = c.metadata
            chunks_output.append({
                "chunk_id": c.chunk_id,
                "content": c.content[:500],  # 前端只显示前500字
                "content_length": len(c.content),
                "truncated": len(c.content) > 500,
                "source": meta.get("source", ""),
                "page": meta.get("page", 0),
                "domain": meta.get("domain", "general"),
                "knowledge_type": meta.get("knowledge_type", "general"),
                "phenology_stages": meta.get("phenology_stages", ""),
                "entities": meta.get("entities", ""),
                "risk_level": meta.get("risk_level", "低"),
                "has_table": meta.get("has_table", False),
                "table_type": meta.get("table_type", ""),
                "table_rows": meta.get("table_rows", meta.get("num_rows", 0)),
                "table_cols": meta.get("table_cols", meta.get("num_cols", 0)),
            })
        else:
            chunks_output.append(c)

    # 构建 file_manifest（用于增量检测）
    file_manifest = {}
    for filename, stat in new_stats.items():
        # 收集该文件对应的 chunk_ids
        chunk_ids = []
        for c in chunks_list:
            if isinstance(c, Chunk):
                source = c.metadata.get("source", "")
            else:
                source = c.get("source", "")
            if source == filename:
                if isinstance(c, Chunk):
                    chunk_ids.append(c.chunk_id)
                else:
                    chunk_ids.append(c["chunk_id"])

        file_manifest[filename] = {
            "mtime": stat["mtime"],
            "content_hash": stat["content_hash"],
            "chunk_ids": chunk_ids,
        }

    cache = {
        "version": 3,
        "build_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chunker_params": {
            "type": "rule-v3",
            "chunk_size": chunker.chunk_size,
            "overlap": chunker.overlap,
            "merge_threshold": chunker.merge_threshold,
            "merge_similarity_threshold": chunker.merge_similarity_threshold,
        },
        "chunker_code_sha256": hashlib.sha256(
            (PROJECT_ROOT / "data_pipeline" / "chunker.py").read_bytes()
        ).hexdigest(),
        "corpus_fingerprint": hashlib.sha256(
            "\n".join(sorted(f"{c['chunk_id']}:{c['content_length']}" for c in chunks_output)).encode("utf-8")
        ).hexdigest(),
        "quality_report": quality_report,
        "ingest_report": ingest_report,
        "files": files,
        "file_manifest": file_manifest,
        "total_chunks": len(chunks_output),
        "chunks": chunks_output,
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
        f.flush()
    tmp_path.replace(cache_path)

    logger.info(f"分块缓存已保存: {cache_path} ({len(chunks_output)} 条)")


# ===================================================================
# 入口
# ===================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LycheeAI 索引构建工具")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认 data/raw）")
    parser.add_argument("--skip-vector", action="store_true", help="跳过向量索引构建")
    parser.add_argument("--force", action="store_true", help="强制全量重建（跳过增量检测）")
    args = parser.parse_args()

    Config.load()
    setup_logging()
    success = build_index(data_dir=args.data_dir, skip_vector=args.skip_vector, force=args.force)
    sys.exit(0 if success else 1)
