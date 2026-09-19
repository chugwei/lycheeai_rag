"""
设备选择工具 - 统一管理 CPU/GPU 设备选择

所有推理模型（Embedding / Reranker）统一通过本模块选择设备，
避免散落在各处的硬编码 device="cpu" 导致 GPU 闲置。

也提供共享的 Embedding 模型单例，避免索引构建时重复加载模型。
"""
import functools
from typing import Optional

from loguru import logger


# 共享 Embedding 模型实例（避免 chunker 和 vector_indexer 重复加载）
_shared_embedding_model = None
_shared_embedding_model_name = None


def get_shared_embedding_model(model_name: str = None, cache_dir: str = None):
    """
    获取共享的 Embedding 模型实例（单例）

    如果已加载同名模型，直接返回；否则加载并缓存。
    """
    global _shared_embedding_model, _shared_embedding_model_name
    if _shared_embedding_model is not None and _shared_embedding_model_name == model_name:
        return _shared_embedding_model

    from sentence_transformers import SentenceTransformer
    _device = get_device()
    _shared_embedding_model = SentenceTransformer(
        model_name,
        cache_folder=str(cache_dir) if cache_dir else None,
        device=_device,
        local_files_only=True,
    )
    _shared_embedding_model_name = model_name
    logger.info(f"共享 Embedding 模型已加载: {model_name} (device={_device})")
    return _shared_embedding_model


@functools.lru_cache(maxsize=1)
def get_device() -> str:
    """
    返回最优推理设备字符串（供 SentenceTransformer 使用）。

    - CUDA 可用时返回 "cuda"
    - 否则返回 "cpu"

    结果缓存（进程内），并打印一次选择日志。
    """
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            logger.info(f"设备选择: cuda (GPU: {name})")
            return "cuda"
    except Exception as e:  # torch 未安装或异常
        logger.debug(f"无法检测 CUDA，回退 CPU: {e}")

    logger.info("设备选择: cpu (未检测到可用 GPU)")
    return "cpu"


def get_devices() -> list:
    """
    返回设备列表（供 FlagReranker 使用，其 devices 参数为 list）。

    - CUDA 可用时返回 ["cuda:0"]
    - 否则返回 ["cpu"]
    """
    return ["cuda:0"] if get_device() == "cuda" else ["cpu"]
