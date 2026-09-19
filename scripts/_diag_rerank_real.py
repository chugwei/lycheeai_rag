"""用真实检索结果复现服务端 rerank 工作量，定位 15s 来源。"""
import os, time, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import get_config
from retrieval.fusion import DynamicWeightAdjuster
from langchain_core.documents import Document as LCDocument
from reranker import FlagEmbeddingReranker

query = "荔枝霜疫霉病怎么防治？"

print("加载 retriever + reranker ...")
from retrievers import MilvusMySQLRetriever, BM25Retriever, parallel_retrieve, rrf_fusion
vector_top_k = get_config("retrieval.vector_top_k", 20)
bm25_top_k = get_config("retrieval.bm25_top_k", 20)
vector_retriever = MilvusMySQLRetriever(top_k=vector_top_k)
bm25_retriever = BM25Retriever(top_k=bm25_top_k)
reranker = FlagEmbeddingReranker()

from query_parser import parse_query
parsed = parse_query(query=query, has_image=False, phenology_date=None)
weights = DynamicWeightAdjuster.adjust(parsed.intent, parsed.phenology, language=parsed.language, has_domain_terms=True)

t0 = time.perf_counter()
all_results = parallel_retrieve(query=query, vector_retriever=vector_retriever,
                                bm25_retriever=bm25_retriever, filters={},
                                expansion_queries=None, language=parsed.language, timings={})
print("retrieval done: %.2fs keys=%s" % (time.perf_counter()-t0, list(all_results.keys())))

fused = rrf_fusion(all_results, weights=weights, k=get_config("retrieval.rrf_k", 60), top_k=20)
fused_docs = [LCDocument(page_content=r["text"],
              metadata={**r.get("metadata", {}), "rrf_score": r["rrf_score"],
                        "retrieval_paths": r["retrieval_paths"], "source": r["source"]})
              for r in fused]
print("fused docs:", len(fused_docs), "| avg chars:",
      sum(len(d.page_content) for d in fused_docs)//max(1,len(fused_docs)))

t1 = time.perf_counter()
ranked = reranker.compress_documents(fused_docs, query)
print("REAL rerank time: %.3fs  -> top_k=%d" % (time.perf_counter()-t1, len(ranked)))
try:
    print("reranker model device:", next(reranker.model.model.parameters()).device)
except Exception as e:
    print("device probe err:", e)
print("DONE")
