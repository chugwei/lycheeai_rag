"""
语言检测工具 — 识别文档/查询文本的语言

提供两级检测：
  1. 快速启发式：基于 Unicode 字符范围（零外部依赖，适合批量文档）
  2. 精确检测：基于 langdetect 库（适合查询/短文本）

输出: "zh" | "en" | "mixed" | "unknown"
"""
import re
from typing import Optional
from loguru import logger

# ─── Unicode 范围检测 ───────────────────────────────────

# 基本 CJK 统一汉字 (U+4E00–U+9FFF) + 扩展A (U+3400–U+4DBF)
CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')

# ASCII 英文字母
ASCII_LETTER_RE = re.compile(r'[a-zA-Z]')


def contains_chinese(text: str, threshold: float = 0.01) -> bool:
    """检测文本是否包含中文（按字符比例阈值）"""
    if not text:
        return False
    cjk_chars = len(CJK_RE.findall(text))
    return (cjk_chars / max(len(text), 1)) >= threshold


def contains_english(text: str, threshold: float = 0.01) -> bool:
    """检测文本是否包含英文（按字符比例阈值）"""
    if not text:
        return False
    en_chars = len(ASCII_LETTER_RE.findall(text))
    return (en_chars / max(len(text), 1)) >= threshold


def detect_heuristic(text: str, min_cjk_ratio: float = 0.05) -> str:
    """
    基于字符范围的快速语言检测

    参数:
        text: 输入文本
        min_cjk_ratio: 判定为中文的最小 CJK 字符比例

    返回:
        "zh" | "en" | "mixed" | "unknown"
    """
    if not text or not text.strip():
        return "unknown"

    total = len(text.strip())
    cjk = len(CJK_RE.findall(text))
    en = len(ASCII_LETTER_RE.findall(text))

    cjk_ratio = cjk / total if total > 0 else 0
    en_ratio = en / total if total > 0 else 0

    if cjk_ratio >= min_cjk_ratio and en_ratio >= min_cjk_ratio:
        return "mixed"
    elif cjk_ratio >= min_cjk_ratio:
        return "zh"
    elif en_ratio >= min_cjk_ratio:
        return "en"
    return "unknown"


# ─── 基于 langdetect 的精确检测 ─────────────────────────

# 缓存 detector 实例避免重复加载
_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        try:
            from langdetect import DetectorFactory
            # 设置种子确保结果可复现
            DetectorFactory.seed = 42
            from langdetect import detect_langs
            _detector = detect_langs
        except ImportError:
            logger.warning("langdetect 未安装，回退到启发式检测")
            return None
    return _detector


def detect_precise(text: str, min_len: int = 20) -> str:
    """
    基于 langdetect 的精确语言检测（推荐用于查询/短文本）

    参数:
        text: 输入文本（建议至少 20 字符以获得可靠结果）
        min_len: 启用 langdetect 的最小字符数

    返回:
        "zh" | "en" | "mixed" | "unknown"
    """
    if not text or not text.strip():
        return "unknown"

    detect = _get_detector()
    if detect is None:
        return detect_heuristic(text)

    if len(text.strip()) < min_len:
        # 短文本：启发式更可靠
        return detect_heuristic(text)

    try:
        langs = detect(text)
        if not langs:
            return detect_heuristic(text)

        # 取置信度最高的语言
        top = langs[0]
        lang = top.lang
        prob = top.prob

        # 如果第二语言也有一定置信度，可能为混合
        if len(langs) > 1 and langs[1].prob > 0.3:
            lang2 = langs[1].lang
            if {lang, lang2} in [{"zh-cn", "en"}, {"zh-tw", "en"}, {"en", "zh-cn"}, {"en", "zh-tw"}]:
                return "mixed"

        if lang in ("zh-cn", "zh-tw", "zh"):
            return "zh" if prob >= 0.5 else detect_heuristic(text)
        elif lang == "en":
            return "en" if prob >= 0.5 else detect_heuristic(text)
        else:
            return detect_heuristic(text)
    except Exception as e:
        logger.debug(f"langdetect 检测失败: {e}，回退到启发式")
        return detect_heuristic(text)


# ─── 统一入口 ──────────────────────────────────────────

def detect_language(text: str, method: str = "auto") -> str:
    """
    统一语言检测入口

    参数:
        text: 输入文本
        method: "auto" — 长文本用启发式，短文本用精确检测
                "heuristic" — 仅用启发式
                "precise" — 仅用 langdetect

    返回:
        "zh" | "en" | "mixed" | "unknown"
    """
    if not text or not text.strip():
        return "unknown"

    if method == "heuristic":
        return detect_heuristic(text)
    elif method == "precise":
        return detect_precise(text)

    # auto: 长文本（>500字符）用启发式（更快），短文本用精确检测
    if len(text) > 500:
        return detect_heuristic(text)
    return detect_precise(text)