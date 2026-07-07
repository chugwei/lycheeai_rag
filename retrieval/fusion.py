"""
RRF (Reciprocal Rank Fusion) 多路检索结果融合

原理：
    score = Σ weight_i / (k + rank_i)
其中 rank_i 是文档在第 i 路检索中的排名，k 是平滑参数

为什么选择 RRF 而不是加权平均：
1. RRF 不需要归一化不同检索器的分数分布
   （BM25 分数范围 0-20+，向量检索 0-1）
2. RRF 对排名比分数更鲁棒
3. RRF 在多路融合场景中被广泛验证有效

k=60 是原始论文推荐值，在实践中表现稳定
"""
from collections import defaultdict
from typing import List, Dict, Optional
from loguru import logger


class RRFFusion:
    """RRF 多路检索结果融合"""

    def __init__(self, k: int = 60):
        self.k = k

    def fuse(self,
             all_results: Dict[str, List[dict]],
             top_k: int = 20,
             weights: Dict[str, float] = None) -> List[dict]:
        """
        多路结果融合

        参数：
        - all_results: 各路检索结果
          {"vector": [...], "bm25": [...], "kg": [...], "image": [...]}
        - top_k: 融合后返回数量
        - weights: 各路权重
        """
        if weights is None:
            weights = {"vector": 1.0, "kg": 1.2, "bm25": 0.8, "image": 1.0}

        # doc_id → {score, content, paths}
        doc_scores = defaultdict(
            lambda: {"score": 0.0, "content": None, "paths": []}
        )

        for path_name, results in all_results.items():
            if not results:
                continue

            weight = weights.get(path_name, 1.0)

            for rank, result in enumerate(results):
                doc_id = self._get_doc_id(result)
                rrf_score = weight * 1.0 / (self.k + rank + 1)

                doc_scores[doc_id]["score"] += rrf_score
                doc_scores[doc_id]["content"] = result
                doc_scores[doc_id]["paths"].append(path_name)

        # 按融合分数排序
        sorted_docs = sorted(
            doc_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True
        )

        results = []
        for doc_id, info in sorted_docs[:top_k]:
            content = info["content"].copy()
            content["rrf_score"] = info["score"]
            content["retrieval_paths"] = info["paths"]
            results.append(content)

        logger.info(f"RRF融合完成: {sum(len(v) for v in all_results.values())} "
                    f"→ {len(results)} 条结果")
        return results

    def _get_doc_id(self, result: dict) -> str:
        """生成文档唯一标识（基于内容去重）"""
        text = result.get("text", "")[:200]
        source = result.get("source", "")
        return f"{source}::{hash(text)}"


class DynamicWeightAdjuster:
    """
    动态权重调整器

    根据查询意图和物候期信息动态调整各检索路径权重
    """

    @staticmethod
    def adjust(intent: str,
               phenology_info: dict = None,
               language: str = "zh",
               has_domain_terms: bool = False) -> Dict[str, float]:
        """
        根据意图、物候期、查询语言和领域术语动态调整权重

        Args:
            intent: 查询意图
            phenology_info: 物候期信息
            language: 查询语言
            has_domain_terms: 查询是否含领域专有名词（词典匹配）
        """
        weights = {"vector": 1.0, "kg": 1.0, "bm25": 0.8, "image": 1.0}

        # 按意图调整
        if intent == "pest_diagnosis":
            weights["image"] = 1.3
            weights["kg"] = 1.2
        elif intent == "agronomy_advice":
            weights["bm25"] = 1.2
            weights["vector"] = 0.9
        elif intent == "relation_reasoning":
            weights["kg"] = 1.5
            weights["vector"] = 0.8
        elif intent == "knowledge_qa":
            weights["vector"] = 1.1
            weights["bm25"] = 0.9

        # 按查询语言调整（英文/混合查询时 BM25 不可靠，依赖向量语义检索）
        if language in ("en", "mixed"):
            weights["vector"] = weights.get("vector", 1.0) * 1.3
            weights["bm25"] = weights.get("bm25", 0.8) * 0.5

        # 按物候期调整
        if phenology_info:
            stage_name = phenology_info.get("name", "")
            if "花" in stage_name:
                weights["kg"] += 0.2
            if "果实" in stage_name:
                weights["vector"] += 0.1

        # 按领域术语调整：查询含专有名词时，BM25精确匹配更有优势
        if has_domain_terms:
            weights["bm25"] *= 1.3
            weights["vector"] *= 0.9

        # 归一化
        total = sum(weights.values())
        weights = {k: v / total * 4 for k, v in weights.items()}

        return weights
