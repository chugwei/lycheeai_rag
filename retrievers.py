"""
自定义 Retriever - Milvus+MySQL 混合检索 + BM25 检索

封装现有 VectorSearcher 和 BM25Indexer 为 LangChain BaseRetriever。
"""
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as LCDocument
from langchain_core.retrievers import BaseRetriever
from loguru import logger

from config.settings import get_config

# 模块级单例（Pydantic BaseRetriever 不允许 _ 开头的字段）
_vector_searcher = None
_bm25_indexer = None


def _get_vector_searcher():
    global _vector_searcher
    if _vector_searcher is None:
        from retrieval.vector_searcher import VectorSearcher
        _vector_searcher = VectorSearcher()
    return _vector_searcher


def _get_bm25_indexer():
    global _bm25_indexer
    if _bm25_indexer is None:
        from data_pipeline.bm25_indexer import BM25Indexer
        _bm25_indexer = BM25Indexer()
        _bm25_indexer.load()
    return _bm25_indexer


class MilvusMySQLRetriever(BaseRetriever):
    """
    Milvus + MySQL 混合检索器

    封装现有 VectorSearcher，返回 LangChain Document 格式。
    """
    top_k: int = 20

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
        filters: Optional[dict] = None,
        expansion_queries: Optional[List[str]] = None,
    ) -> List[LCDocument]:
        """执行向量检索（仅用原始 query，语义泛化）"""
        try:
            results = _get_vector_searcher().search(
                query=query,
                top_k=self.top_k,
                filters=filters,
            )
            return self._to_langchain_docs(results)
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []

    @staticmethod
    def _to_langchain_docs(results: List[dict]) -> List[LCDocument]:
        """转换为 LangChain Document 格式"""
        docs = []
        for r in results:
            metadata = {
                "source": r.get("source", ""),
                "page": r.get("page", 0),
                "score": r.get("score", 0),
                "chunk_id": r.get("id", ""),
                "retrieval_paths": ["vector"],
            }
            # 合并元数据
            if "metadata" in r:
                metadata.update(r["metadata"])

            docs.append(LCDocument(
                page_content=r.get("text", ""),
                metadata=metadata,
            ))
        return docs


class BM25Retriever(BaseRetriever):
    """
    BM25 关键词检索器

    封装现有 BM25Indexer，返回 LangChain Document 格式。
    """
    top_k: int = 20
    language: str = "auto"

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
        filters: Optional[dict] = None,
        expansion_queries: Optional[List[str]] = None,
    ) -> List[LCDocument]:
        """
        执行 BM25 检索（支持扩展查询）

        与向量检索保持一致：如果有扩展查询（口语→专业术语），
        每个变体分别检索后合并去重，提升精确匹配的召回率。
        """
        try:
            queries = [query]
            if expansion_queries:
                queries.extend(expansion_queries)

            all_results = []
            for q in queries:
                results = _get_bm25_indexer().search(
                    query=q,
                    top_k=self.top_k,
                    filters=filters,
                    language=self.language,
                )
                all_results.extend(results)

            # 按 chunk_id 去重，保留最高分
            seen = {}
            for r in all_results:
                cid = r.get("chunk_id", r.get("id", ""))
                if cid not in seen or r.get("score", 0) > seen[cid].get("score", 0):
                    seen[cid] = r

            deduplicated = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
            return self._to_langchain_docs(deduplicated[:self.top_k])
        except Exception as e:
            logger.warning(f"BM25 检索失败: {e}")
            return []

    @staticmethod
    def _to_langchain_docs(results: List[dict]) -> List[LCDocument]:
        """转换为 LangChain Document 格式"""
        docs = []
        for r in results:
            metadata = {
                "source": r.get("source", ""),
                "page": r.get("page", 0),
                "score": r.get("score", 0),
                "chunk_id": r.get("id", ""),
                "retrieval_paths": ["bm25"],
            }
            if "metadata" in r:
                metadata.update(r["metadata"])

            docs.append(LCDocument(
                page_content=r.get("text", ""),
                metadata=metadata,
            ))
        return docs


def parallel_retrieve(
    query: str,
    vector_retriever: MilvusMySQLRetriever,
    bm25_retriever: BM25Retriever,
    filters: Optional[dict] = None,
    expansion_queries: Optional[List[str]] = None,
    language: str = "zh",
    timings: Optional[dict] = None,
) -> Dict[str, List[LCDocument]]:
    """
    并行执行向量检索和 BM25 检索

    Args:
        query: 查询文本
        vector_retriever: 向量检索器
        bm25_retriever: BM25 检索器
        filters: 过滤条件
        expansion_queries: 扩展查询
        language: 语言
        timings: 可选，接收 {"vector": 秒, "bm25": 秒} 的耗时记录

    Returns:
        {"vector": [...], "bm25": [...]}
    """
    results = {}

    def _vector_search():
        t0 = time.time()
        try:
            res = vector_retriever._get_relevant_documents(
                query, filters=filters, expansion_queries=expansion_queries
            )
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            res = []
        if timings is not None:
            timings["vector"] = time.time() - t0
        return res

    def _bm25_search():
        t0 = time.time()
        try:
            res = bm25_retriever._get_relevant_documents(
                query, filters=filters, expansion_queries=expansion_queries
            )
        except Exception as e:
            logger.warning(f"BM25 检索失败: {e}")
            res = []
        if timings is not None:
            timings["bm25"] = time.time() - t0
        return res

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_vec = executor.submit(_vector_search)
        future_bm25 = executor.submit(_bm25_search)
        results["vector"] = future_vec.result()
        results["bm25"] = future_bm25.result()

    return results


def rrf_fusion(
    all_results: Dict[str, List[LCDocument]],
    weights: Optional[Dict[str, float]] = None,
    k: int = 60,
    top_k: int = 20,
) -> List[dict]:
    """
    RRF (Reciprocal Rank Fusion) 融合排序

    与原系统 RRFFusion 完全一致的算法。

    Args:
        all_results: 各检索路径的结果 {"vector": [...], "bm25": [...]}
        weights: 各路径权重
        k: RRF 参数（默认60）
        top_k: 返回数量

    Returns:
        融合后的文档列表（dict 格式，含 rrf_score 和 retrieval_paths）
    """
    if weights is None:
        weights = {"vector": 1.0, "bm25": 0.8}

    # 收集所有文档，按 doc_id 分组
    doc_map: Dict[str, dict] = {}

    for path_name, docs in all_results.items():
        weight = weights.get(path_name, 1.0)
        for rank, doc in enumerate(docs):
            # 生成文档 ID
            text = doc.page_content if hasattr(doc, 'page_content') else doc.get('text', '')
            source = doc.metadata.get('source', '') if hasattr(doc, 'metadata') else doc.get('source', '')
            doc_id = f"{source}::{hash(text[:200])}"

            if doc_id not in doc_map:
                doc_map[doc_id] = {
                    "text": text,
                    "source": source,
                    "page": doc.metadata.get("page", 0) if hasattr(doc, 'metadata') else 0,
                    "metadata": doc.metadata if hasattr(doc, 'metadata') else {},
                    "rrf_score": 0.0,
                    "retrieval_paths": [],
                }

            # RRF 公式: weight / (k + rank + 1)
            doc_map[doc_id]["rrf_score"] += weight / (k + rank + 1)
            if path_name not in doc_map[doc_id]["retrieval_paths"]:
                doc_map[doc_id]["retrieval_paths"].append(path_name)

    # 按 RRF 分数排序
    sorted_docs = sorted(doc_map.values(), key=lambda x: x["rrf_score"], reverse=True)
    return sorted_docs[:top_k]
