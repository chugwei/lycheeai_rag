"""
Recall@5 / MRR@10 评测脚本

从知识库分块自动生成测试query，对比4种配置的检索效果：
1. 纯BM25
2. 纯向量检索
3. RRF融合（向量+BM25）
4. RRF融合 + 词典扩展 + Rerank

用法:
    python scripts/eval_recall.py
"""
import sys
import os
import random
import time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Config
Config.load()


def load_chunks():
    """加载所有分块数据"""
    import chromadb
    from config.settings import get_config

    chroma_path = Path(get_config("vector_db.chroma_path"))
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        get_config("vector_db.collection_name", "lychee_knowledge")
    )
    all_data = collection.get()
    chunks = []
    for i, cid in enumerate(all_data["ids"]):
        text = all_data["documents"][i] if all_data["documents"] else ""
        meta = all_data["metadatas"][i] if all_data["metadatas"] else {}
        chunks.append({
            "id": cid,
            "text": text,
            "source": meta.get("source", ""),
            "entities": meta.get("entities", ""),
            "knowledge_type": meta.get("knowledge_type", ""),
        })
    return chunks


def generate_test_queries(chunks, n=120):
    """
    从分块内容自动生成测试query

    策略：从每个chunk中提取关键词，构造自然语言问题
    """
    import re

    queries = []

    # 实体→问题模板映射
    disease_templates = [
        "{entity}怎么防治？",
        "{entity}的症状是什么？",
        "如何预防{entity}？",
        "{entity}用什么药？",
    ]
    pest_templates = [
        "{entity}怎么治？",
        "{entity}的危害是什么？",
        "如何防治{entity}？",
    ]
    variety_templates = [
        "{entity}荔枝有什么特点？",
        "{entity}什么时候成熟？",
        "{entity}怎么管理？",
    ]
    general_templates = [
        "荔枝{keyword}怎么做？",
        "荔枝{keyword}的方法？",
        "{keyword}的注意事项？",
    ]

    for chunk in chunks:
        entities_str = chunk.get("entities", "")
        if isinstance(entities_str, str) and entities_str:
            entities = [e.strip() for e in entities_str.split(",") if e.strip()]
        elif isinstance(entities_str, list):
            entities = entities_str
        else:
            entities = []

        source = chunk.get("source", "")
        ktype = chunk.get("knowledge_type", "")

        # 根据实体类型选择问题模板
        for entity in entities[:2]:  # 每个chunk最多取2个实体
            if ktype == "disease_pest" or "病" in entity:
                template = random.choice(disease_templates)
            elif "虫" in entity or "蝽" in entity:
                template = random.choice(pest_templates)
            elif any(v in entity for v in ["桂味", "糯米糍", "妃子笑", "白糖罂", "黑叶"]):
                template = random.choice(variety_templates)
            else:
                template = random.choice(general_templates)

            query = template.format(entity=entity, keyword=entity)
            queries.append({
                "query": query,
                "relevant_source": source,
                "chunk_id": chunk["id"],
                "entity": entity,
            })

        # 从chunk文本中提取关键词生成通用问题
        if len(queries) < n and chunk["text"]:
            # 提取中文关键词（3-8字）
            keywords = re.findall(r'[\u4e00-\u9fff]{3,8}', chunk["text"][:200])
            if keywords:
                keyword = random.choice(keywords)
                template = random.choice(general_templates)
                query = template.format(keyword=keyword, entity=keyword)
                queries.append({
                    "query": query,
                    "relevant_source": source,
                    "chunk_id": chunk["id"],
                    "entity": keyword,
                })

    # 去重并取n条
    seen = set()
    unique_queries = []
    for q in queries:
        if q["query"] not in seen:
            seen.add(q["query"])
            unique_queries.append(q)
            if len(unique_queries) >= n:
                break

    return unique_queries


def evaluate_retrieval(queries, retrieval_fn, top_k=5):
    """
    评测检索效果

    Args:
        queries: 测试query列表
        retrieval_fn: 检索函数，接收query返回结果列表
        top_k: 评测的Top-K

    Returns:
        recall@k, mrr@10
    """
    recall_hits = 0
    mrr_sum = 0.0
    total = len(queries)

    for q in queries:
        try:
            results = retrieval_fn(q["query"])
        except Exception:
            total -= 1
            continue

        # 检查相关文档是否在Top-K中
        relevant_source = q["relevant_source"]
        relevant_chunk_id = q["chunk_id"]

        for rank, doc in enumerate(results[:top_k]):
            doc_source = doc.get("source", "")
            doc_id = doc.get("id", doc.get("chunk_id", ""))

            # 匹配条件：同source文件或同chunk_id
            if doc_source == relevant_source or doc_id == relevant_chunk_id:
                recall_hits += 1
                mrr_sum += 1.0 / (rank + 1)
                break

    recall = recall_hits / total if total > 0 else 0
    mrr = mrr_sum / total if total > 0 else 0
    return recall, mrr


def main():
    print("=" * 60)
    print("LycheeAI 召回率评测")
    print("=" * 60)
    print()

    # 1. 加载分块
    print("[1/5] 加载知识库分块...")
    chunks = load_chunks()
    print(f"  加载 {len(chunks)} 个分块")

    # 2. 生成测试query
    print("[2/5] 生成测试query...")
    queries = generate_test_queries(chunks, n=120)
    print(f"  生成 {len(queries)} 条测试query")

    # 3. 初始化检索器
    print("[3/5] 初始化检索器...")
    from retrieval.vector_searcher import VectorSearcher
    from data_pipeline.bm25_indexer import BM25Indexer
    from retrieval.fusion import RRFFusion, DynamicWeightAdjuster
    from retrieval.domain_expander import DomainExpander

    vector_searcher = VectorSearcher()
    bm25_indexer = BM25Indexer()
    bm25_indexer.load()
    fusion = RRFFusion(k=60)
    domain_expander = DomainExpander()

    # 4. 定义4种检索配置
    def bm25_only(query):
        return bm25_indexer.search(query, top_k=10)

    def vector_only(query):
        return vector_searcher.search(query, top_k=10)

    def rrf_fusion(query):
        vec_results = vector_searcher.search(query, top_k=10)
        bm25_results = bm25_indexer.search(query, top_k=10)
        all_results = {"vector": vec_results, "bm25": bm25_results}
        return fusion.fuse(all_results, top_k=10)

    def rrf_with_dict(query):
        # 词典扩展
        variants = domain_expander.expand_query(query)
        has_domain = domain_expander.has_domain_terms(query)

        vec_results = vector_searcher.search(query, top_k=10,
                                             expansion_queries=variants[1:] if len(variants) > 1 else None)
        bm25_results = bm25_indexer.search(query, top_k=10)

        # 动态权重
        weights = {"vector": 1.0, "bm25": 0.8}
        if has_domain:
            weights["bm25"] *= 1.3
            weights["vector"] *= 0.9

        all_results = {"vector": vec_results, "bm25": bm25_results}
        return fusion.fuse(all_results, top_k=10, weights=weights)

    # 5. 评测
    print("[4/5] 评测中...")
    print()

    configs = [
        ("纯BM25", bm25_only),
        ("纯向量检索", vector_only),
        ("RRF融合（向量+BM25）", rrf_fusion),
        ("RRF+词典扩展+动态权重", rrf_with_dict),
    ]

    results = []
    for name, fn in configs:
        start = time.time()
        recall5, mrr10 = evaluate_retrieval(queries, fn, top_k=5)
        elapsed = time.time() - start
        results.append((name, recall5, mrr10, elapsed))
        print(f"  {name:<25} Recall@5: {recall5:.1%}  MRR@10: {mrr10:.1%}  耗时: {elapsed:.1f}s")

    # 6. 输出汇总表
    print()
    print("[5/5] 评测结果汇总")
    print()
    print(f"{'配置':<30} {'Recall@5':>10} {'MRR@10':>10} {'耗时':>8}")
    print("-" * 60)
    for name, recall5, mrr10, elapsed in results:
        print(f"{name:<30} {recall5:>9.1%} {mrr10:>9.1%} {elapsed:>7.1f}s")
    print("-" * 60)
    print(f"测试集: {len(queries)} 条query, 知识库: {len(chunks)} 个分块")
    print()

    # 词典统计
    stats = domain_expander.get_stats()
    print(f"词典统计: 同义词 {stats['synonyms']}条, "
          f"口语映射 {stats['colloquial']}条, "
          f"已学习 {stats['learned']}条, "
          f"总术语 {stats['total_terms']}个")


if __name__ == "__main__":
    main()
