"""
查询理解与解析（支持中英文）

功能：
1. 意图分类（基于规则的关键词匹配，中英文双语）
2. 实体抽取（基于词典，中英文双语）
3. 物候期匹配（日期→阶段）
4. 查询改写（LLM扩展变体，可选）
5. 语言检测（自动识别查询语言）
"""
import re
from datetime import datetime, date
from typing import List, Optional, Dict
from loguru import logger

from config.settings import get_config


class QueryParser:
    """查询理解与解析（支持中英文）"""

    # 中文意图关键词模式
    INTENT_PATTERNS = {
        "pest_diagnosis": [
            "诊断", "什么病", "什么虫", "得了", "感染", "症状",
            "怎么治", "怎么防治", "叶子", "果实", "图片"
        ],
        "agronomy_advice": [
            "怎么种", "怎么管理", "施肥", "修剪", "灌溉", "什么时候",
            "怎么操作", "农事", "管理", "种植"
        ],
        "relation_reasoning": [
            "为什么", "原因", "导致", "关系", "影响", "因为",
            "关联", "因果", "之间"
        ],
    }

    # 英文意图关键词模式（荔枝领域）
    EN_INTENT_PATTERNS = {
        "pest_diagnosis": [
            "diagnos", "disease", "pest", "infection", "symptom",
            "what disease", "what pest", "how to treat", "leaf", "fruit"
        ],
        "agronomy_advice": [
            "how to plant", "how to grow", "management", "fertiliz",
            "prun", "irrigat", "cultivat", "when to"
        ],
        "relation_reasoning": [
            "why", "cause", "lead to", "result in", "relationship",
            "effect", "impact", "because", "correlation"
        ],
    }

    def __init__(self):
        self.phenology_mapping = get_config("phenology.stage_month_mapping", {})
        self._bilingual_enabled = get_config("bilingual.enabled", True)

    def _detect_query_language(self, query: str) -> str:
        """检测查询语言"""
        if not self._bilingual_enabled:
            return "zh"
        from utils.lang_detector import detect_language
        return detect_language(query, method="precise")

    def parse(self, query: str, has_image: bool = False,
              phenology_date: str = None) -> dict:
        """查询解析主入口"""
        query_lang = self._detect_query_language(query)
        intent = self.classify_intent(query, has_image, language=query_lang)
        entities = self.extract_entities(query, language=query_lang)
        phenology = self.match_phenology(phenology_date)

        result = {
            "query": query,
            "intent": intent,
            "entities": entities,
            "phenology": phenology,
            "has_image": has_image,
            "language": query_lang,
        }

        logger.debug(f"查询解析: [{query_lang}] {result}")
        return result

    def classify_intent(self, query: str, has_image: bool = False,
                        language: str = "zh") -> str:
        """意图分类（支持中英文）"""
        # 有图片默认为诊断意图
        if has_image:
            return "pest_diagnosis"

        # 根据语言选择意图词典
        if language == "en":
            patterns = self.EN_INTENT_PATTERNS
            query_lower = query.lower()
            scores = {}
            for intent, keywords in patterns.items():
                score = sum(1 for kw in keywords if kw in query_lower)
                if score > 0:
                    scores[intent] = score
        else:
            patterns = self.INTENT_PATTERNS
            scores = {}
            for intent, keywords in patterns.items():
                score = sum(1 for kw in keywords if kw in query)
                if score > 0:
                    scores[intent] = score

        if scores:
            return max(scores, key=scores.get)
        return "knowledge_qa"

    def extract_entities(self, query: str, language: str = "zh") -> List[dict]:
        """基于词典的实体识别（支持中英文）"""
        entity_patterns = {
            "Disease": ["霜疫霉病", "炭疽病", "酸腐病", "溃疡病", "鬼扫病",
                        "叶斑病", "煤烟病"],
            "Pest": ["蒂蛀虫", "蝽象", "荔枝蝽", "蓟马", "卷叶蛾", "天牛",
                     "金龟子", "红蜘蛛", "尺蠖", "椿象"],
            "Phenology": ["秋梢萌动", "秋梢老熟", "花芽分化", "花穗期",
                          "花穗生长期", "开花期", "幼果期", "果实膨大期",
                          "成熟期", "休眠期"],
            "Chemical": ["波尔多液", "多菌灵", "甲基托布津", "代森锰锌",
                         "氯氰菊酯", "吡虫啉", "阿维菌素"],
            "Variety": ["桂味", "糯米糍", "妃子笑", "白糖罂", "黑叶",
                        "白蜡", "槐枝", "怀枝", "增城挂绿"],
        }

        # 英文实体词典
        en_entity_patterns = {
            "Disease": ["downy blight", "anthracnose", "sour rot",
                        "canker", "witch's broom", "leaf spot", "sooty mold"],
            "Pest": ["litchi stink bug", "fruit borer", "leaf roller",
                     "longhorn beetle", "spider mite", "thrips"],
            "Phenology": ["shoot emergence", "flower bud differentiation",
                          "flowering", "fruit set", "fruit expansion",
                          "maturity", "dormancy", "harvest"],
            "Chemical": ["bordeaux mixture", "carbendazim",
                         "mancozeb", "cypermethrin", "imidacloprid", "abamectin"],
            "Variety": ["feizixiao", "guiwei", "nuomici", "heiye",
                        "baila", "huaizhi", "lychee"],
        }

        entities = []
        seen = set()

        if language == "en":
            patterns = en_entity_patterns
            query_lower = query.lower()
            for label, keywords in patterns.items():
                for keyword in keywords:
                    if keyword in query_lower and f"{label}:{keyword}" not in seen:
                        entities.append({"label": label, "name": keyword})
                        seen.add(f"{label}:{keyword}")
        else:
            patterns = entity_patterns
            for label, keywords in patterns.items():
                for keyword in keywords:
                    if keyword in query and f"{label}:{keyword}" not in seen:
                        entities.append({"label": label, "name": keyword})
                        seen.add(f"{label}:{keyword}")

        return entities

    def match_phenology(self, phenology_date: str = None) -> Optional[dict]:
        """物候期匹配 - 日期→阶段"""
        if phenology_date:
            try:
                d = datetime.strptime(phenology_date, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(f"日期格式错误: {phenology_date}，使用今天")
                d = date.today()
        else:
            d = date.today()

        month = d.month

        # 匹配物候期
        matched_stages = []
        for stage, months in self.phenology_mapping.items():
            if month in months:
                matched_stages.append(stage)

        if not matched_stages:
            return None

        # 取第一个匹配的阶段
        stage = matched_stages[0]
        return {
            "name": stage,
            "date": d.isoformat(),
            "month": month,
            "solar_term": self._get_solar_term(d),
            "all_candidates": matched_stages,
        }

    def _get_solar_term(self, d: date) -> str:
        """根据日期近似推断节气（简化版）"""
        # 24节气近似日期（基于公历）
        solar_terms = [
            (1, 6, "小寒"), (1, 20, "大寒"),
            (2, 4, "立春"), (2, 19, "雨水"),
            (3, 6, "惊蛰"), (3, 21, "春分"),
            (4, 5, "清明"), (4, 20, "谷雨"),
            (5, 6, "立夏"), (5, 21, "小满"),
            (6, 6, "芒种"), (6, 21, "夏至"),
            (7, 7, "小暑"), (7, 23, "大暑"),
            (8, 8, "立秋"), (8, 23, "处暑"),
            (9, 8, "白露"), (9, 23, "秋分"),
            (10, 8, "寒露"), (10, 24, "霜降"),
            (11, 7, "立冬"), (11, 22, "小雪"),
            (12, 7, "大雪"), (12, 22, "冬至"),
        ]

        for m, day, name in solar_terms:
            if m == d.month and day <= d.day:
                return name
            if m == d.month and day > d.day:
                # 找上一个节气
                idx = solar_terms.index((m, day, name))
                if idx > 0:
                    return solar_terms[idx - 1][2]
                return "冬至"
        return ""
