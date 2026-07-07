"""
Prompt 模板管理 - 基于 LangChain ChatPromptTemplate

加载 5 种意图模板，根据意图动态选择。
"""
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from config.settings import get_config


# 意图 → 模板文件映射
INTENT_TEMPLATE_MAP = {
    "pest_diagnosis": "diagnosis.txt",
    "agronomy_advice": "agronomy.txt",
    "knowledge_qa": "knowledge_qa.txt",
    "relation_reasoning": "relation_reasoning.txt",
}

# 模板缓存
_template_cache: dict = {}


def _load_template(name: str) -> str:
    """加载模板文件（带缓存）"""
    if name in _template_cache:
        return _template_cache[name]

    prompts_dir = Path(get_config("paths.prompts_dir", "./config/prompts"))
    file_path = prompts_dir / name

    if file_path.exists():
        content = file_path.read_text(encoding="utf-8")
    else:
        content = ""
        import loguru
        loguru.logger.warning(f"模板文件不存在: {file_path}")

    _template_cache[name] = content
    return content


def _build_context(docs: List[dict]) -> str:
    """构建检索上下文"""
    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.get("source", "未知来源")
        text = doc.get("text", "")[:1000]
        paths = doc.get("retrieval_paths", [])
        path_str = "+".join(paths) if paths else "unknown"
        parts.append(f"[{i}] 来源：{source} | 检索路径：{path_str}\n{text}")
    return "\n\n".join(parts)


def _build_phenology_info(phenology: Optional[dict]) -> str:
    """构建物候期信息"""
    if not phenology:
        return "当前物候期信息未知。"

    name = phenology.get("name", "未知")
    solar_term = phenology.get("solar_term", "未知")
    date = phenology.get("date", "未知")

    return f"""- 物候期名称：{name}
- 对应节气：{solar_term}
- 当前日期：{date}
- 管理目标：根据该物候期特点进行针对性管理"""


def _build_image_context(image_analysis: Optional[dict]) -> str:
    """构建图像分析上下文"""
    if not image_analysis:
        return ""

    parts = ["【图像识别结果】"]

    if "error" in image_analysis:
        parts.append(f"图像识别失败：{image_analysis['error']}")
        return "\n".join(parts)

    data = image_analysis.get("detection_results") or image_analysis.get("results") or image_analysis

    # 根据不同 API 类型格式化
    if "male_count" in data:
        parts.append(f"雌雄花比例检测：雄花 {data.get('male_count', 0)} 朵，"
                     f"雌花 {data.get('female_count', 0)} 朵，"
                     f"雌花比例 {data.get('female_ratio', '0')}%")
    elif "count" in data and "msg" in data:
        parts.append(f"花穗检测：{data.get('msg', '')}，数量 {data.get('count', 0)}")
    elif "msg1" in data:
        parts.append(f"梢量分割：{data.get('msg1', '')}")
    elif "flower_rate" in data:
        parts.append(f"开花率：{data.get('flower_rate', '0')}%")
    elif "fruit_count" in data:
        parts.append(f"果实个数（坐果率）：{data.get('fruit_count', 0)} 个")
    elif "white_spots_count" in data:
        parts.append(f"白点检测：{data.get('message', '')}，数量 {data.get('white_spots_count', 0)}")
    elif "counts" in data:
        counts = data.get("counts", {})
        parts.append(f"果实成熟度检测：{counts}")
    elif "risk_level" in data and "nums" in data:
        parts.append(f"椿象预测：预测数量 {data.get('nums', 0)}，风险等级 {data.get('risk_level', '未知')}")
    elif "orchard_risk_level" in data:
        parts.append(f"霜疫霉病预测：果园风险等级 {data.get('orchard_risk_level', '未知')}，"
                     f"生存概率 {data.get('orchard_survival_prob', 0)}")
    elif "avg_length" in data:
        parts.append(f"新梢检测：平均长度 {data.get('avg_length', '0')} cm，"
                     f"平均粗度 {data.get('avg_thickness', '0')} cm")
    elif "pupation_rate" in data:
        parts.append(f"蒂蛀虫化蛹率：{data.get('pupation_rate', 0)}%，"
                     f"风险等级 {data.get('risk_level', '未知')}")
    elif "predicted_yield_kTons" in data:
        parts.append(f"产量预测：{data.get('predicted_yield_kTons', 0)} 万吨")
    else:
        parts.append(f"识别结果：{image_analysis}")

    return "\n".join(parts)


def _build_history(history: List[dict], max_turns: int = 3) -> str:
    """构建对话历史"""
    if not history:
        return ""

    recent = history[-max_turns:]
    parts = []
    for turn in recent:
        user_input = turn.get("user", "")[:200]
        assistant = turn.get("assistant", "")[:200]
        parts.append(f"用户：{user_input}\n助手：{assistant}")

    return "\n\n".join(parts)


def build_prompt(
    query: str,
    docs: List[dict],
    intent: str,
    phenology: Optional[dict] = None,
    image_analysis: Optional[dict] = None,
    history: Optional[List[dict]] = None,
) -> str:
    """
    组装完整的 RAG Prompt

    结构: 系统提示 + 对话历史 + 意图模板 + 用户问题

    Args:
        query: 用户查询
        docs: 检索到的文档
        intent: 查询意图
        phenology: 物候期信息
        image_analysis: 图像分析结果
        history: 对话历史

    Returns:
        组装好的 prompt 字符串
    """
    # 系统提示
    system_prompt = _load_template("system.txt")

    # 对话历史
    history_text = _build_history(history or [])

    # 意图模板
    template_file = INTENT_TEMPLATE_MAP.get(intent, "knowledge_qa.txt")
    template = _load_template(template_file)

    # 填充模板变量
    context = _build_context(docs)
    phenology_str = _build_phenology_info(phenology)
    image_str = _build_image_context(image_analysis)

    # 替换占位符
    filled_template = template.replace("{context}", context)
    filled_template = filled_template.replace("{phenology_info}", phenology_str)
    filled_template = filled_template.replace("{image_analysis}", image_str)

    # 组装完整 prompt
    parts = [system_prompt]
    if history_text:
        parts.append(f"\n## 对话历史\n{history_text}")
    parts.append(f"\n{filled_template}")
    parts.append(f"\n## 用户问题：\n{query}")

    return "\n".join(parts)


def build_chat_messages(
    query: str,
    docs: List[dict],
    intent: str,
    phenology: Optional[dict] = None,
    image_analysis: Optional[dict] = None,
    history: Optional[List[dict]] = None,
) -> List[dict]:
    """
    构建 LangChain ChatPromptTemplate 所需的消息列表

    Returns:
        [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
    """
    prompt_text = build_prompt(query, docs, intent, phenology, image_analysis, history)

    return [
        {"role": "system", "content": "你是一个专业的荔枝种植专家助手。请直接回答问题，不要输出任何思考过程、分析步骤或推理链。"},
        {"role": "user", "content": prompt_text},
    ]
