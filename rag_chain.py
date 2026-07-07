"""
LangChain RAG 管线 - 基于 LCEL 的完整 RAG 链

14 步管线，与原系统逻辑完全一致：
1.  查询解析（意图 + 物候期 + 语言）
2.  图像分析（如有图片）
3.  查询扩展（LLM 改写，可选）
4.  动态权重调整
5.  构建过滤条件
6.  并行检索（向量 + BM25）
7.  RRF 融合
8.  Rerank 精排
9.  Prompt 组装
10. LLM 生成
11. 后处理（引用提取 + 思考链清理）
12. 更新对话状态
13. 置信度计算
"""
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from config.settings import get_config
from retrieval.fusion import DynamicWeightAdjuster

from llm_factory import create_llm, create_llm_for_expansion
from retrievers import (
    MilvusMySQLRetriever, BM25Retriever,
    parallel_retrieve, rrf_fusion,
)
from reranker import FlagEmbeddingReranker
from query_parser import parse_query, ParsedQuery
from prompts import build_chat_messages
from post_processor import extract_citations
from confidence import compute_confidence


class _LLMWrapper:
    """LangChain LLM 适配器，提供 .generate() 方法兼容 QueryExpander"""

    def __init__(self, llm):
        self._llm = llm

    def generate(self, prompt: str, temperature: float = None, max_tokens: int = None, **kwargs) -> str:
        try:
            messages = [{"role": "user", "content": prompt}]
            if temperature is not None:
                self._llm.temperature = temperature
            if max_tokens is not None:
                self._llm.max_tokens = max_tokens
            response = self._llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.warning(f"LLM generate 失败: {e}")
            return ""


@dataclass
class RAGResult:
    """RAG 管线完整输出（与原系统格式一致）"""
    answer: str
    sources: List[dict] = field(default_factory=list)
    intent: str = ""
    confidence: float = 0.0
    conversation_id: str = ""
    retrieval_paths_used: List[str] = field(default_factory=list)
    phenology: Optional[dict] = None
    image_analysis: Optional[dict] = None
    latency: float = 0.0


class LangChainRAGPipeline:
    """
    基于 LangChain 的 RAG 管线

    使用 LCEL (LangChain Expression Language) 组装管线，
    保持与原系统完全一致的 14 步逻辑。
    """

    def __init__(self):
        # LLM
        self.llm = create_llm()

        # Retriever
        vector_top_k = get_config("retrieval.vector_top_k", 20)
        bm25_top_k = get_config("retrieval.bm25_top_k", 20)
        self.vector_retriever = MilvusMySQLRetriever(top_k=vector_top_k)
        self.bm25_retriever = BM25Retriever(top_k=bm25_top_k)

        # Reranker
        self.reranker = FlagEmbeddingReranker()

        # 对话状态管理
        from conversation.state_manager import StateManager
        self.state_manager = StateManager()

        # 图像分析
        from external_apis.api_client import LycheeAPIClient
        self.api_client = LycheeAPIClient()

        # 领域词典扩展器
        from retrieval.domain_expander import DomainExpander
        self.domain_expander = DomainExpander()

        # 领域词典自动沉淀引擎
        from retrieval.domain_learner import DomainLearner
        self.domain_learner = DomainLearner(self.domain_expander, self.llm)

        logger.info("LangChain RAG 管线初始化完成")

    def run(
        self,
        query: str,
        image_bytes: bytes = None,
        image_api_type: str = "guoshi",
        conversation_id: str = None,
        phenology_date: str = None,
        use_query_expansion: bool = False,
    ) -> RAGResult:
        """
        RAG 管线主入口

        Args:
            query: 用户查询
            image_bytes: 图片字节（可选）
            image_api_type: 图像识别 API 类型
            conversation_id: 对话 ID
            phenology_date: 物候期日期（YYYY-MM-DD）
            use_query_expansion: 是否启用查询扩展

        Returns:
            RAGResult 对象
        """
        start_time = time.time()

        # Step 1: 获取/创建对话状态
        state = self.state_manager.get_or_create(conversation_id)

        # Step 2: 查询解析
        parsed = parse_query(
            query=query,
            has_image=(image_bytes is not None),
            phenology_date=phenology_date,
        )
        intent = parsed.intent
        phenology_info = parsed.phenology
        query_lang = parsed.language
        state.current_intent = intent
        state.current_phenology = phenology_info

        logger.info(f"查询意图: {intent}, 物候期: {phenology_info}")

        # Step 3: 图像分析（如有图片）
        image_analysis = None
        if image_bytes:
            image_analysis = self._analyze_image(image_bytes, image_api_type)

        # Step 4: 查询扩展（领域词典 + LLM改写）
        expansion_queries = None
        # 领域词典扩展始终执行（无LLM开销）
        dict_variants = self.domain_expander.expand_query(query)
        has_domain_terms = self.domain_expander.has_domain_terms(query)
        if len(dict_variants) > 1:
            expansion_queries = dict_variants
            logger.debug(f"词典扩展: {len(dict_variants)} 个变体")
        # LLM改写（可选）
        if use_query_expansion:
            llm_rewrites = self._expand_query(query)
            if llm_rewrites:
                if expansion_queries:
                    expansion_queries.extend(llm_rewrites)
                else:
                    expansion_queries = [query] + llm_rewrites

        # Step 5: 动态权重调整（含领域术语感知）
        weights = DynamicWeightAdjuster.adjust(
            intent, phenology_info, language=query_lang,
            has_domain_terms=has_domain_terms
        )

        # Step 6: 构建过滤条件
        filters = {}
        phenology_filter_intents = {"agronomy"}
        if phenology_info and intent in phenology_filter_intents:
            filters["phenology_stage"] = phenology_info["name"]
            logger.debug(f"启用物候期过滤: intent={intent}, stage={phenology_info['name']}")

        # Step 7: 并行检索
        retrieval_start = time.time()
        all_results = parallel_retrieve(
            query=query,
            vector_retriever=self.vector_retriever,
            bm25_retriever=self.bm25_retriever,
            filters=filters,
            expansion_queries=expansion_queries,
            language=query_lang,
        )
        logger.info(f"多路检索完成: {list(all_results.keys())}, 耗时 {time.time()-retrieval_start:.2f}s")

        # Step 8: RRF 融合
        fused_results = rrf_fusion(
            all_results,
            weights=weights,
            k=get_config("retrieval.rrf_k", 60),
            top_k=20,
        )

        # Step 9: Rerank 精排
        top_k = get_config("reranker.top_k", 5)
        # 转换为 LangChain Document 格式用于 Reranker
        from langchain_core.documents import Document as LCDocument
        fused_docs = [
            LCDocument(
                page_content=r["text"],
                metadata={**r.get("metadata", {}), "rrf_score": r["rrf_score"],
                          "retrieval_paths": r["retrieval_paths"], "source": r["source"]},
            )
            for r in fused_results
        ]
        reranked_docs = self.reranker.compress_documents(fused_docs, query)

        # 转换回 dict 格式
        top_docs = []
        for doc in reranked_docs:
            top_docs.append({
                "id": doc.metadata.get("chunk_id", ""),
                "text": doc.page_content,
                "source": doc.metadata.get("source", ""),
                "page": doc.metadata.get("page", 0),
                "score": doc.metadata.get("score", 0),
                "rrf_score": doc.metadata.get("rrf_score", 0),
                "rerank_score": doc.metadata.get("rerank_score", 0),
                "retrieval_paths": doc.metadata.get("retrieval_paths", []),
                "metadata": doc.metadata,
            })

        state.last_retrieved_docs = top_docs

        # Step 10: Prompt 组装
        messages = build_chat_messages(
            query=query,
            docs=top_docs,
            intent=intent,
            phenology=phenology_info,
            image_analysis=image_analysis,
            history=state.history,
        )

        # Step 11: LLM 生成
        try:
            response = self.llm.invoke(messages)
            llm_response = response.content
        except Exception as e:
            logger.error(f"LLM 生成失败: {e}")
            llm_response = self._fallback_response(query, top_docs, intent)

        # Step 12: 后处理
        answer, sources = extract_citations(llm_response, top_docs)

        # Step 12.5: 词典自动沉淀（异步，不影响主流程）
        self.domain_learner.maybe_learn(query, parsed.entities, answer)

        # Step 13: 更新对话状态
        self.state_manager.update(state, query, answer)

        # Step 14: 置信度计算
        confidence = compute_confidence(top_docs, intent)

        latency = time.time() - start_time
        logger.info(f"RAG 完成: intent={intent}, confidence={confidence:.2f}, latency={latency:.2f}s")

        return RAGResult(
            answer=answer,
            sources=sources,
            intent=intent,
            confidence=confidence,
            conversation_id=state.conversation_id,
            retrieval_paths_used=list(all_results.keys()),
            phenology=phenology_info,
            image_analysis=image_analysis,
            latency=latency,
        )

    def _analyze_image(self, image_bytes: bytes, api_type: str) -> dict:
        """调用外部图像识别 API"""
        try:
            api_map = {
                "cixionghua": self.api_client.detect_cixionghua,
                "huasui": self.api_client.detect_huasui,
                "shaoliang": self.api_client.detect_shaoliang,
                "kaihualv": self.api_client.detect_kaihualv,
                "zuoguolv": self.api_client.detect_zuoguolv,
                "baidian": self.api_client.detect_baidian,
                "guoshi": self.api_client.detect_guoshi,
                "shao": self.api_client.detect_shao,
                "dizhuchong": self.api_client.detect_dizhuchong,
            }
            if api_type in api_map:
                return api_map[api_type](image_bytes)
            return {"error": f"不支持的 API 类型: {api_type}"}
        except Exception as e:
            logger.error(f"图像分析失败: {e}")
            return {"error": str(e)}

    def _expand_query(self, query: str) -> Optional[List[str]]:
        """查询扩展（LLM 改写）"""
        try:
            from retrieval.query_expansion import QueryExpander
            expander = QueryExpander(_LLMWrapper(create_llm_for_expansion()))
            return expander.expand(query, strategy="rewrite")
        except Exception as e:
            logger.warning(f"查询扩展失败: {e}")
            return None

    def _fallback_response(self, query: str, docs: List[dict], intent: str) -> str:
        """LLM 不可用时的降级响应"""
        if not docs:
            return "知识库中暂无此方面的信息，建议咨询当地农技部门。"

        parts = ["【基于知识库检索结果】\n"]
        for i, doc in enumerate(docs, 1):
            source = doc.get("source", "未知来源")
            text = doc.get("text", "")[:500]
            parts.append(f"[{i}] 来源：{source}\n{text}\n")

        parts.append(f"\n（注：LLM 未配置，以上为检索到的原始文档。"
                     f"请启动推理服务以获得 AI 完整回答。）")
        return "\n".join(parts)


# 模块级单例
_pipeline: Optional[LangChainRAGPipeline] = None


def get_pipeline() -> LangChainRAGPipeline:
    """获取 RAG 管线单例"""
    global _pipeline
    if _pipeline is None:
        _pipeline = LangChainRAGPipeline()
    return _pipeline
