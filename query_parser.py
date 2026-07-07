"""
查询解析器 - 意图分类 + 物候期匹配 + 语言检测

直接复用原系统 QueryParser 的逻辑，保持完全一致。
"""
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from retrieval.query_parser import QueryParser
from config.settings import get_config
from utils.lang_detector import detect_language


@dataclass
class ParsedQuery:
    """查询解析结果"""
    query: str
    intent: str = "knowledge_qa"
    entities: list = field(default_factory=list)
    phenology: Optional[dict] = None
    has_image: bool = False
    language: str = "zh"


# 复用原系统的 QueryParser 实例
_parser = QueryParser()


def parse_query(
    query: str,
    has_image: bool = False,
    phenology_date: Optional[str] = None,
) -> ParsedQuery:
    """
    解析查询：意图分类 + 实体提取 + 物候期匹配 + 语言检测

    Args:
        query: 用户查询文本
        has_image: 是否包含图片
        phenology_date: 物候期日期（YYYY-MM-DD），默认今天

    Returns:
        ParsedQuery 对象
    """
    parsed = _parser.parse(
        query=query,
        has_image=has_image,
        phenology_date=phenology_date,
    )

    return ParsedQuery(
        query=query,
        intent=parsed.get("intent", "knowledge_qa"),
        entities=parsed.get("entities", []),
        phenology=parsed.get("phenology"),
        has_image=has_image,
        language=parsed.get("language", "zh"),
    )
