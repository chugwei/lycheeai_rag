"""
BGE-Reranker - 封装为 LangChain BaseDocumentCompressor

使用 FlagEmbedding 的 FlagReranker 进行交叉编码器精排。
"""
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as LCDocument
from langchain_core.documents.compressor import BaseDocumentCompressor
from loguru import logger

from config.settings import get_config


class FlagEmbeddingReranker(BaseDocumentCompressor):
    """
    BGE-Reranker 压缩器

    封装 FlagEmbedding.FlagReranker，实现 LangChain BaseDocumentCompressor 接口。
    """

    model: Any = None
    top_k: int = 5
    _available: bool = True

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, top_k: int = None, **kwargs):
        super().__init__(**kwargs)
        self.top_k = top_k or get_config("reranker.top_k", 5)
        self._load_model()

    def _load_model(self):
        """懒加载 Reranker 模型"""
        try:
            from FlagEmbedding import FlagReranker

            from utils.device import get_devices

            model_name = get_config("reranker.model_name", "BAAI/bge-reranker-base")
            use_fp16 = get_config("reranker.use_fp16", True)

            # 设备选择：统一走 utils.device，CUDA 可用时强制上 GPU。
            # 注意：FlagReranker 在 devices=None 时依赖加载瞬间的
            # torch.cuda.is_available() 自动选设备，若服务在 CUDA 就绪前启动
            # 会静默降级到 CPU（实测 20 篇候选 ~13s）。因此显式指定设备，
            # 避免受启动时机影响。
            devices = get_devices()
            if devices[0].startswith("cuda"):
                # GPU 上 fp16 更快且省显存，bge-reranker-base fp16 安全
                if not use_fp16:
                    use_fp16 = True
                    logger.info("CUDA 可用: Reranker 强制 cuda:0 并启用 fp16")
            else:
                use_fp16 = False
                logger.info("CPU 模式: Reranker 关闭 fp16, 使用 float32")

            logger.info(f"正在加载 Reranker 模型: {model_name} (devices={devices}, use_fp16={use_fp16})")
            self.model = FlagReranker(model_name, use_fp16=use_fp16, devices=devices)
            logger.info(f"Reranker 模型已加载: {model_name}, use_fp16={use_fp16}, devices={devices}")
        except Exception as e:
            logger.warning(f"Reranker 模型加载失败，将使用简化排序: {e}")
            self._available = False
            self.model = None

    def _enrich_for_rerank(self, doc: LCDocument) -> str:
        """丰富文档文本，帮助 Reranker 理解上下文"""
        parts = []
        metadata = doc.metadata

        if metadata.get("phenology_stages"):
            stages = metadata["phenology_stages"]
            if isinstance(stages, str):
                stages = stages.split(",")
            parts.append(f"[物候期: {', '.join(stages)}]")

        if metadata.get("knowledge_type"):
            parts.append(f"[类型: {metadata['knowledge_type']}]")

        parts.append(doc.page_content)
        return " ".join(parts)

    def compress_documents(
        self,
        documents: Sequence[LCDocument],
        query: str,
        callbacks: Optional[CallbackManagerForRetrieverRun] = None,
    ) -> List[LCDocument]:
        """
        对文档进行精排

        Args:
            documents: 候选文档列表
            query: 查询文本
            callbacks: 回调管理器

        Returns:
            精排后的 top_k 文档
        """
        if not documents:
            return []

        if len(documents) <= self.top_k:
            return list(documents)

        if not self._available or self.model is None:
            # 降级：按现有分数排序
            return self._fallback_rerank(list(documents))

        try:
            # 构建 (query, doc) 对
            pairs = []
            for doc in documents:
                enriched = self._enrich_for_rerank(doc)
                pairs.append((query, enriched))

            # 交叉编码器打分
            scores = self.model.compute_score(pairs, normalize=True)
            if isinstance(scores, float):
                scores = [scores]

            # 按分数排序
            import numpy as np
            ranked = []
            for idx in np.argsort(scores)[::-1][:self.top_k]:
                doc = documents[idx]
                # 将 rerank 分数写入 metadata
                new_metadata = {**doc.metadata, "rerank_score": float(scores[idx])}
                ranked.append(LCDocument(
                    page_content=doc.page_content,
                    metadata=new_metadata,
                ))

            logger.info(f"Rerank 完成: {len(documents)} → {len(ranked)}")
            return ranked

        except Exception as e:
            logger.error(f"Rerank 失败，使用降级排序: {e}")
            return self._fallback_rerank(list(documents))

    def _fallback_rerank(self, docs: List[LCDocument]) -> List[LCDocument]:
        """降级排序：按 RRF 分数排序"""
        sorted_docs = sorted(
            docs,
            key=lambda x: x.metadata.get("rrf_score", x.metadata.get("score", 0)),
            reverse=True,
        )
        for doc in sorted_docs[:self.top_k]:
            doc.metadata["rerank_score"] = doc.metadata.get(
                "rrf_score", doc.metadata.get("score", 0)
            )
        return sorted_docs[:self.top_k]
