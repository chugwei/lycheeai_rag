"""
查询扩展模块

策略1：领域词典扩展（无LLM开销，毫秒级）
- 口语/俗称 → 标准术语
- 同义词展开

策略2：LLM Query改写
- 将用户查询改写为多个语义变体
- 每个变体独立检索，合并Top-K

策略3：HyDE（Hypothetical Document Embeddings）
- 先让LLM生成假设性回答文档
- 用假设回答的向量去做检索
"""
import json
from typing import List, Optional
from loguru import logger


class QueryExpander:
    """查询扩展模块"""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self._domain_expander = None

    @property
    def domain_expander(self):
        if self._domain_expander is None:
            from retrieval.domain_expander import DomainExpander
            self._domain_expander = DomainExpander()
        return self._domain_expander

    def expand(self, query: str, strategy: str = "rewrite") -> List[str]:
        """
        查询扩展

        strategy:
        - "rewrite": 领域词典 + LLM改写策略
        - "hyde": 领域词典 + HyDE策略
        - "both": 领域词典 + 两种策略结合
        - "dict_only": 仅领域词典扩展
        - "none": 不扩展
        """
        if strategy == "none":
            return [query]

        results = [query]

        try:
            # 领域词典扩展（无LLM开销，始终执行）
            if strategy != "none":
                dict_variants = self.domain_expander.expand_query(query)
                for v in dict_variants:
                    if v not in results:
                        results.append(v)

            # LLM改写
            if self.llm and strategy in ("rewrite", "both"):
                rewrites = self._rewrite_query(query)
                results.extend(rewrites)

            # HyDE
            if self.llm and strategy in ("hyde", "both"):
                hyde_doc = self._generate_hyde(query)
                if hyde_doc:
                    results.append(hyde_doc)
        except Exception as e:
            logger.warning(f"查询扩展失败: {e}")

        return results

    def has_domain_terms(self, query: str) -> bool:
        """判断查询是否含领域专名"""
        return self.domain_expander.has_domain_terms(query)

    def _rewrite_query(self, query: str, num_rewrites: int = 3) -> List[str]:
        """LLM Query改写"""
        prompt = f"""请将以下荔枝种植相关问题改写为{num_rewrites}个语义相同但表述不同的问题。
改写时请注意：
1. 保持专业术语的准确性
2. 可以替换同义词、调整语序、改变提问方式
3. 保留问题的核心意图

原始问题：{query}

请用JSON格式输出：
{{"rewrites": ["改写1", "改写2", "改写3"]}}"""

        response = self.llm.generate(prompt, temperature=0.7, max_tokens=200)

        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("rewrites", [])
        except Exception:
            pass

        return []

    def _generate_hyde(self, query: str) -> Optional[str]:
        """HyDE：生成假设性回答文档"""
        prompt = f"""假设你是一个荔枝种植专家，请用一段话（约100字）简要回答以下问题。
不需要完全准确，只需要包含相关的关键词和概念即可。

问题：{query}

请直接输出回答，不要加前缀："""

        response = self.llm.generate(prompt, temperature=0.8, max_tokens=150)
        return response.strip() if response else None
