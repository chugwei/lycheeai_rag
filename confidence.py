"""
置信度计算 - 与原系统完全一致的置信度公式
"""
from typing import List


def compute_confidence(docs: List[dict], intent: str) -> float:
    """
    计算回答置信度

    公式: (avg_rerank_score * 0.5 + path_coverage * 0.3 + 0.2) * intent_weight

    Args:
        docs: 检索到的文档列表（含 rerank_score 或 rrf_score）
        intent: 查询意图

    Returns:
        置信度 0.0-1.0
    """
    if not docs:
        return 0.1

    # 平均分数
    avg_score = sum(
        d.get("rerank_score", d.get("rrf_score", 0)) for d in docs
    ) / len(docs)

    # 检索路径覆盖率
    all_paths = set()
    for d in docs:
        all_paths.update(d.get("retrieval_paths", []))
    path_coverage = len(all_paths) / 4  # 最多4条路径

    # 意图权重
    intent_weight = {
        "knowledge_qa": 1.0,
        "agronomy_advice": 0.95,
        "relation_reasoning": 0.9,
        "pest_diagnosis": 0.85,
    }.get(intent, 0.9)

    confidence = (avg_score * 0.5 + path_coverage * 0.3 + 0.2) * intent_weight
    return min(max(confidence, 0.0), 1.0)
