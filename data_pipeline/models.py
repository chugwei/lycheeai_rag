"""
标准文档数据模型
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Document:
    """文档对象 - 解析后的标准文档单元"""
    content: str
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        source = self.metadata.get("source", "unknown")
        page = self.metadata.get("page", 0)
        return f"Document(source={source}, page={page}, len={len(self.content)})"


@dataclass
class Chunk:
    """分块对象 - 经过分块策略处理后的检索单元"""
    content: str
    metadata: dict = field(default_factory=dict)
    chunk_id: str = ""

    def __repr__(self):
        return f"Chunk(id={self.chunk_id}, len={len(self.content)})"
