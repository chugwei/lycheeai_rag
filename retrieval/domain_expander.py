"""
荔枝领域专有词典扩展器

功能：
1. 口语/俗称 → 标准术语映射（如"叶子长白毛" → 霜疫霉病）
2. 专业同义词展开（如"蒂蛀虫" ↔ "荔枝蛀蒂虫"）
3. 农药/品种简称展开
4. 物候期别名展开
5. 自动沉淀新词（learned层）
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime
from loguru import logger


class DomainExpander:
    """荔枝领域专有词典扩展器"""

    def __init__(self, dict_path: str = None):
        if dict_path is None:
            dict_path = str(
                Path(__file__).parent.parent / "data" / "domain_dict.json"
            )
        self.dict_path = dict_path
        self._load()

    def _load(self):
        """加载词典"""
        with open(self.dict_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.synonyms: Dict[str, List[str]] = data.get("synonyms", {})
        self.colloquial: Dict[str, List[str]] = data.get("colloquial", {})
        self.abbreviations: Dict[str, List[str]] = data.get("abbreviations", {})
        self.stage_aliases: Dict[str, List[str]] = data.get("stage_aliases", {})
        self.learned: Dict[str, list] = data.get("learned", {})

        # 构建反向索引：别名→标准名
        self._reverse: Dict[str, str] = {}
        for standard, aliases in self.synonyms.items():
            for alias in aliases:
                self._reverse[alias] = standard
        # colloquial 反向：口语→标准名
        self._colloquial_reverse: Dict[str, str] = {}
        for standard, phrases in self.colloquial.items():
            for phrase in phrases:
                self._colloquial_reverse[phrase] = standard
        # learned 反向
        for standard, entries in self.learned.items():
            for entry in entries:
                if isinstance(entry, dict) and "term" in entry:
                    self._reverse[entry["term"]] = standard

        # 所有已知术语集合（用于判断查询是否含领域专名）
        self._all_terms: Set[str] = set()
        self._all_terms.update(self.synonyms.keys())
        self._all_terms.update(self.colloquial.keys())
        self._all_terms.update(self.abbreviations.keys())
        self._all_terms.update(self.stage_aliases.keys())
        for aliases in self.synonyms.values():
            self._all_terms.update(aliases)
        for phrases in self.colloquial.values():
            self._all_terms.update(phrases)
        for entries in self.learned.values():
            for entry in entries:
                if isinstance(entry, dict) and "term" in entry:
                    self._all_terms.add(entry["term"])

        logger.info(f"领域词典加载完成: {len(self.synonyms)} 同义词, "
                    f"{len(self.colloquial)} 口语映射, "
                    f"{len(self.learned)} 已学习词")

    def expand_query(self, query: str) -> List[str]:
        """
        将查询中的领域术语展开为多个变体

        策略：
        1. 农民口语→标准术语（如"叶子长白毛"→"霜疫霉病"）
        2. 专业术语→同义词展开（如"蒂蛀虫"→"荔枝蛀蒂虫"）
        3. 标准术语→口语反向（如用户说了"霜疫霉病"，也搜"叶子长白毛"）
        """
        variants = [query]
        seen = {query}

        # 1. 口语→标准术语
        for phrase, standard in self._colloquial_reverse.items():
            if phrase in query:
                new_q = query.replace(phrase, standard)
                if new_q not in seen:
                    variants.append(new_q)
                    seen.add(new_q)
                # 也搜同义词
                for syn in self.synonyms.get(standard, []):
                    syn_q = query.replace(phrase, syn)
                    if syn_q not in seen:
                        variants.append(syn_q)
                        seen.add(syn_q)

        # 2. 标准术语→同义词
        for term, aliases in self.synonyms.items():
            if term in query:
                for alias in aliases:
                    new_q = query.replace(term, alias)
                    if new_q not in seen:
                        variants.append(new_q)
                        seen.add(new_q)

        # 3. 反向：标准术语→口语（让BM25也能匹配口语描述的文档）
        for standard, phrases in self.colloquial.items():
            if standard in query:
                for phrase in phrases[:2]:  # 只取前2个口语变体，避免过多
                    new_q = query.replace(standard, phrase)
                    if new_q not in seen:
                        variants.append(new_q)
                        seen.add(new_q)

        # 4. learned层
        for standard, entries in self.learned.items():
            for entry in entries:
                if isinstance(entry, dict) and "term" in entry:
                    term = entry["term"]
                    if term in query:
                        new_q = query.replace(term, standard)
                        if new_q not in seen:
                            variants.append(new_q)
                            seen.add(new_q)

        return variants

    def has_domain_terms(self, query: str) -> bool:
        """判断查询是否包含领域专有名词"""
        return any(term in query for term in self._all_terms)

    def get_standard_term(self, term: str) -> str:
        """将任意别名/口语转为标准术语"""
        # 先查同义词反向
        if term in self._reverse:
            return self._reverse[term]
        # 再查口语反向
        if term in self._colloquial_reverse:
            return self._colloquial_reverse[term]
        return term

    def learn_term(self, source_query: str, term: str,
                   standard_term: str, confidence: float = 0.8):
        """
        自动沉淀：将新词写入learned层

        Args:
            source_query: 来源用户query
            term: 新发现的词
            standard_term: 对应的标准术语
            confidence: 置信度
        """
        if standard_term not in self.learned:
            self.learned[standard_term] = []

        # 去重
        existing_terms = {e.get("term") for e in self.learned[standard_term]
                          if isinstance(e, dict)}
        if term in existing_terms:
            return

        entry = {
            "term": term,
            "source_query": source_query,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
        }
        self.learned[standard_term].append(entry)

        # 更新反向索引
        self._reverse[term] = standard_term
        self._all_terms.add(term)

        # 持久化
        self._save()
        logger.info(f"词典沉淀: '{term}' → '{standard_term}' "
                    f"(来源: '{source_query}', 置信度: {confidence})")

    def _save(self):
        """持久化词典"""
        data = {
            "synonyms": self.synonyms,
            "colloquial": self.colloquial,
            "abbreviations": self.abbreviations,
            "stage_aliases": self.stage_aliases,
            "learned": self.learned,
        }
        with open(self.dict_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_stats(self) -> dict:
        """获取词典统计信息"""
        total_learned = sum(len(v) for v in self.learned.values())
        return {
            "synonyms": sum(len(v) for v in self.synonyms.values()),
            "colloquial": sum(len(v) for v in self.colloquial.values()),
            "abbreviations": sum(len(v) for v in self.abbreviations.values()),
            "stage_aliases": sum(len(v) for v in self.stage_aliases.values()),
            "learned": total_learned,
            "total_terms": len(self._all_terms),
        }
