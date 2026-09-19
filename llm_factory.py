"""
LLM 工厂 - 创建 LangChain ChatOpenAI 实例

使用 SenseNova DeepSeek-v4-Flash（OpenAI 兼容 API）

支持多模型自由切换，extra_body 参数从配置读取，按模型灵活配置。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_openai import ChatOpenAI
from config.settings import get_config


def _parse_extra_body():
    """
    从配置读取 external.extra_body，解析为 dict

    支持格式：
    - YAML 中直接写行内 JSON：'{"enable_thinking": false}'
    - 空字符串或 null：返回 {}
    """
    raw = get_config("llm.external.extra_body", "")
    if not raw:
        return {}
    # 如果已经是 dict（YAML 解析后可能直接是 dict）
    if isinstance(raw, dict):
        return raw
    # 尝试解析 JSON 字符串
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def create_llm(
    temperature: float = None,
    max_tokens: int = None,
    timeout: int = None,
) -> ChatOpenAI:
    """
    创建 LangChain ChatOpenAI 实例

    Args:
        temperature: 生成温度（默认从配置读取）
        max_tokens: 最大生成 token 数
        timeout: 请求超时（秒）

    Returns:
        ChatOpenAI 实例
    """
    model = get_config("llm.external.model", "deepseek-v4-flash")

    kwargs = dict(
        base_url=get_config("llm.external.base_url", "https://token.sensenova.cn/v1"),
        api_key=get_config("llm.external.api_key", ""),
        model=model,
        temperature=temperature or get_config("llm.temperature", 0.3),
        max_tokens=max_tokens or get_config("llm.max_tokens", 512),
        timeout=timeout or get_config("llm.request_timeout", 30),
        top_p=get_config("llm.top_p", 0.9),
    )

    # 从配置读取 extra_body，按模型灵活配置
    # 例如 deepseek-v4-flash 支持 {"enable_thinking": false} 关闭 CoT 推理加速
    extra_body = _parse_extra_body()
    if extra_body:
        kwargs["extra_body"] = extra_body

    return ChatOpenAI(**kwargs)


def create_llm_for_analysis() -> ChatOpenAI:
    """创建用于图像分析的 LLM（低温度、高 token）"""
    return create_llm(temperature=0.1, max_tokens=1024)


def create_llm_for_expansion() -> ChatOpenAI:
    """创建用于查询扩展的 LLM（高温度、低 token）"""
    return create_llm(temperature=0.7, max_tokens=200)