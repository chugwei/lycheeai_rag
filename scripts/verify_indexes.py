"""验证 BM25、Chroma、构建清单的一致性，并运行固定检索回归集。"""
import argparse
import json
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import Config, get_config
Config.load()


def ranking_metrics(queries, search, top_k=5):
    hits = 0
    reciprocal = 0.0
    misses = []
    latencies_ms = []
    for case in queries:
        started = time.perf_counter()
        results = search(case["query"], top_k=top_k)
        latencies_ms.append((time.perf_counter() - started) * 1000)
        rank = next((i for i, r in enumerate(results, 1)
                     if case["source_contains"] in r.get("source", "")), None)
        if rank:
            hits += 1
            reciprocal += 1 / rank
        else:
            misses.append({"query": case["query"], "expected": case["source_contains"],
                           "top_sources": [r.get("source", "") for r in results[:3]]})
    total = len(queries)
    ordered_latency = sorted(latencies_ms)
    return {"recall_at_5": hits / total, "mrr_at_5": reciprocal / total,
            "hits": hits, "total": total, "misses": misses,
            "latency_ms": {
                "mean": round(sum(latencies_ms) / total, 2),
                "p50": round(ordered_latency[int(total * .50)], 2),
                "p95": round(ordered_latency[min(total - 1, int(total * .95))], 2),
            }}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-vector", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cache = json.loads((ROOT / "indexes/chunks_cache.json").read_text(encoding="utf-8"))
    with (ROOT / "indexes/bm25_index.pkl").open("rb") as f:
        bm25_data = pickle.load(f)
    bm25_ids = {x["chunk_id"] for x in bm25_data["corpus_meta"]}
    cache_ids = {x["chunk_id"] for x in cache["chunks"]}
    checks = {
        "manifest_v3": cache.get("version") == 3,
        "quality_gate_passed": cache.get("quality_report", {}).get("passed") is True,
        "bm25_cache_count_equal": len(bm25_ids) == len(cache_ids) == cache["total_chunks"],
        "bm25_cache_ids_equal": bm25_ids == cache_ids,
        "chunker_version_rule_v3": cache.get("chunker_params", {}).get("type") == "rule-v3",
    }
    queries = json.loads((ROOT / "tests/chunking_eval_queries.json").read_text(encoding="utf-8"))
    from data_pipeline.bm25_indexer import BM25Indexer
    bm25 = BM25Indexer()
    bm25.load()
    bm25.search(queries[0]["query"], top_k=1)  # 预热 jieba，不计入在线延迟
    retrieval = {"bm25": ranking_metrics(queries, bm25.search)}

    if not args.skip_vector:
        import chromadb
        client = chromadb.PersistentClient(path=get_config("vector_db.chroma_path"))
        collection = client.get_collection(get_config("vector_db.collection_name"))
        vector_ids = set(collection.get(include=[])["ids"])
        checks["vector_cache_count_equal"] = collection.count() == len(cache_ids)
        checks["vector_cache_ids_equal"] = vector_ids == cache_ids
        checks["vector_model_recorded"] = bool(collection.metadata.get("embedding_model"))
        from retrieval.vector_searcher import VectorSearcher
        vector_searcher = VectorSearcher()
        vector_searcher.search(queries[0]["query"], top_k=1)  # 预热模型，不计入在线延迟
        retrieval["vector"] = ranking_metrics(queries, vector_searcher.search)

    passed = all(checks.values()) and retrieval["bm25"]["recall_at_5"] >= .80
    passed = passed and retrieval["bm25"]["latency_ms"]["p95"] <= 500
    if "vector" in retrieval:
        passed = (passed and retrieval["vector"]["recall_at_5"] >= .65
                  and retrieval["vector"]["latency_ms"]["p95"] <= 2000)
    report = {"checks": checks, "retrieval": retrieval, "passed": passed}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
