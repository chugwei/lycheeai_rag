"""
词典自动沉淀引擎

两阶段机制：
- 阶段1 粗筛：用户query中有词典没有的词，且检索结果命中了某个病害/虫害
- 阶段2 LLM确认：将候选映射发给LLM确认，确认后写入learned层

触发时机：RAG管线后处理阶段（Step 12之后）
"""
import re
from typing import List, Optional, Dict
from loguru import logger


class DomainLearner:
    """词典自动沉淀引擎"""

    # 病虫害实体标签
    PEST_DISEASE_LABELS = {"Disease", "Pest"}

    def __init__(self, domain_expander, llm_client=None):
        """
        Args:
            domain_expander: DomainExpander 实例
            llm_client: LLM客户端（用于确认候选映射）
        """
        self.expander = domain_expander
        self.llm = llm_client

    def maybe_learn(self, query: str, entities: List[dict],
                    answer: str = ""):
        """
        查询后触发学习（异步安全，失败不影响主流程）

        Args:
            query: 用户原始query
            entities: QueryParser提取的实体列表 [{"label": "Disease", "name": "霜疫霉病"}, ...]
            answer: LLM生成的回答（可选，用于辅助判断）
        """
        try:
            self._do_learn(query, entities, answer)
        except Exception as e:
            logger.debug(f"词典沉淀失败（不影响主流程）: {e}")

    def _do_learn(self, query: str, entities: List[dict], answer: str):
        """实际学习逻辑"""
        # 1. 提取query中的关键词（简单分词：2-6字的中文片段）
        query_terms = self._extract_terms(query)
        if not query_terms:
            return

        # 2. 过滤掉已在词典中的词
        unknown_terms = [
            t for t in query_terms
            if not self.expander.has_domain_terms(t)
            and len(t) >= 2
        ]
        if not unknown_terms:
            return

        # 3. 从实体中提取命中的病虫害
        hit_diseases = [
            e["name"] for e in entities
            if e.get("label") in self.PEST_DISEASE_LABELS
        ]
        if not hit_diseases:
            return

        # 4. 对每个未知词，检查是否可能是某个病虫害的口语描述
        for term in unknown_terms[:3]:  # 最多处理3个
            self._confirm_and_learn(query, term, hit_diseases, answer)

    def _confirm_and_learn(self, query: str, term: str,
                           candidates: List[str], answer: str):
        """LLM确认后写入词典"""
        if self.llm is None:
            # 无LLM时，用简单启发式：如果query和病虫害相关度高，直接学习
            if self._heuristic_confirm(query, term, candidates):
                standard = candidates[0]
                self.expander.learn_term(query, term, standard, confidence=0.6)
            return

        # LLM确认
        prompt = f"""你是一个荔枝种植领域专家。请判断以下用户描述是否指代某个已知的荔枝病虫害。

用户原始问题："{query}"
用户可能的口语表达："{term}"
可能对应的病虫害：{', '.join(candidates)}

请回答：
- 如果这个口语表达确实指代某个病虫害，回答格式：{{"match": true, "standard": "病虫害名", "confidence": 0.9}}
- 如果无法确定或不匹配，回答：{{"match": false}}

只输出JSON，不要其他内容。"""

        try:
            response = self.llm.generate(prompt, temperature=0.1, max_tokens=100)
            import json
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                if result.get("match") and result.get("standard"):
                    standard = result["standard"]
                    confidence = min(result.get("confidence", 0.8), 0.95)
                    self.expander.learn_term(query, term, standard, confidence)
        except Exception as e:
            logger.debug(f"LLM确认失败: {e}")

    def _heuristic_confirm(self, query: str, term: str,
                           candidates: List[str]) -> bool:
        """
        启发式确认（无LLM时的降级方案）

        规则：如果query中同时包含未知词和至少一个病虫害相关的
        上下文词（如"怎么治""防治""什么病"），则认为可能匹配
        """
        context_keywords = [
            "怎么治", "怎么防", "什么病", "什么虫", "得了", "感染",
            "症状", "用药", "打药", "喷药", "治", "防", "病", "虫",
            "how to treat", "disease", "pest"
        ]
        has_context = any(kw in query.lower() for kw in context_keywords)
        # 未知词不是纯数字或纯标点
        has_content = bool(re.search(r'[\u4e00-\u9fff]{2,}', term))
        return has_context and has_content and len(candidates) > 0

    @staticmethod
    def _extract_terms(text: str) -> List[str]:
        """简单分词：提取2-6字的中文片段"""
        # 匹配连续中文字符（2-6字）
        segments = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
        return list(set(segments))
