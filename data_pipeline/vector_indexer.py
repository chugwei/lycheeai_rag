"""
向量索引器 - 将文档分块向量化并存储到 ChromaDB

使用 BAAI/bge-base-zh-v1.5 生成嵌入向量（768维）
专为中文优化，在农业术语上精度更高。
"""
import json
import time
import uuid
from pathlib import Path
from typing import List, Optional

from loguru import logger
from sentence_transformers import SentenceTransformer

from config.settings import get_config
from utils.device import get_device
from .models import Chunk


class VectorIndexer:
    """向量索引器"""

    def __init__(self):
        # 嵌入模型配置
        self.model_name = get_config("embedding.model_name", "intfloat/multilingual-e5-small")
        self.fallback_model = get_config("embedding.fallback_model", self.model_name)
        self.cache_dir = Path(get_config("embedding.cache_dir", "./indexes/model_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.dim = get_config("embedding.dim", 384)
        self.batch_size = get_config("embedding.batch_size", 32)
        self.normalize = get_config("embedding.normalize", True)

        # ChromaDB 配置
        self.chroma_path = str(Path(get_config("vector_db.chroma_path", "./indexes/chroma_db")).resolve())
        self.collection_name = get_config("vector_db.collection_name", "lychee_knowledge")

        # 模型懒加载
        self._model: Optional[SentenceTransformer] = None
        self.active_model_name = self.model_name

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            _device = get_device()
            logger.info(f"加载 Embedding 模型: {self.model_name} (device={_device})")
            t0 = time.time()
            try:
                self._model = SentenceTransformer(
                    self.model_name, cache_folder=str(self.cache_dir), device=_device,
                    local_files_only=True,
                )
            except Exception as exc:
                if self.fallback_model == self.model_name:
                    raise
                logger.warning(f"主 Embedding 模型不可用，切换灾备模型 {self.fallback_model}: {exc}")
                self.active_model_name = self.fallback_model
                self._model = SentenceTransformer(
                    self.fallback_model, cache_folder=str(self.cache_dir), device=_device,
                    local_files_only=True,
                )
            logger.info(f"Embedding 模型加载完成: {time.time()-t0:.1f}s")
        return self._model

    def build_index(self, chunks: List[Chunk]):
        """构建向量索引并存入 ChromaDB"""
        if not chunks:
            logger.warning("没有要索引的分块")
            return

        import chromadb
        from chromadb.config import Settings

        t0 = time.time()

        # 先完成向量计算，再触碰线上集合，避免模型失败导致旧索引被删除。
        texts = [c.content for c in chunks]
        logger.info(f"生成嵌入向量: {len(texts)} 条, 模型={self.model_name}")
        model = self.model
        encoded_texts = [f"passage: {t}" for t in texts] if "e5" in self.active_model_name.lower() else texts
        embeddings = model.encode(
            encoded_texts,
            batch_size=self.batch_size,
            show_progress_bar=True,
            normalize_embeddings=self.normalize,
        )

        # 连接 ChromaDB
        client = chromadb.PersistentClient(
            path=self.chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )

        staging_name = f"{self.collection_name}_staging_{uuid.uuid4().hex[:8]}"
        try:
            client.delete_collection(staging_name)
        except Exception:
            pass

        collection = client.create_collection(
            name=staging_name,
            metadata={"hnsw:space": "cosine", "embedding_model": self.active_model_name,
                      "chunker_version": "rule-v3"},
        )

        # 准备 ChromaDB 数据
        ids = [c.chunk_id for c in chunks]
        metadatas = []
        for c in chunks:
            meta = {
                "source": c.metadata.get("source", ""),
                "page": c.metadata.get("page", 0),
                "domain": c.metadata.get("domain", "general"),
                "chunk_id": c.chunk_id,
            }
            # 可选字段
            for key in ("knowledge_type", "phenology_stages", "entities", "risk_level"):
                if key in c.metadata:
                    val = c.metadata[key]
                    if isinstance(val, (list, tuple)):
                        val = ",".join(str(v) for v in val)
                    meta[key] = val
            metadatas.append(meta)

        # 批量添加
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            end = min(i + batch_size, len(chunks))
            collection.add(
                embeddings=embeddings[i:end].tolist(),
                documents=texts[i:end],
                metadatas=metadatas[i:end],
                ids=ids[i:end],
            )

        count = collection.count()
        if count != len(chunks):
            client.delete_collection(staging_name)
            raise RuntimeError(f"向量索引条数不一致: expected={len(chunks)}, actual={count}")

        # staging 完整后才切换集合；切换窗口只包含元数据操作。
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        collection.modify(name=self.collection_name)
        logger.info(f"向量索引构建完成: {count} 条, 耗时 {time.time()-t0:.1f}s")

    def delete_chunks(self, chunk_ids: List[str]):
        """从 ChromaDB 中删除指定 chunk_id 的分块（增量重建用）"""
        if not chunk_ids:
            return

        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=self.chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )

        try:
            collection = client.get_collection(self.collection_name)
            # ChromaDB 的 delete 一次最多处理 1000 条，分批次
            batch_size = 1000
            for i in range(0, len(chunk_ids), batch_size):
                batch = chunk_ids[i:i + batch_size]
                collection.delete(ids=batch)
            logger.info(f"已从 ChromaDB 删除 {len(chunk_ids)} 个分块")
        except Exception as e:
            logger.warning(f"ChromaDB 删除分块失败: {e}")

    def get_collection(self):
        """获取现有集合（用于查询）"""
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=self.chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )

        try:
            return client.get_collection(self.collection_name)
        except Exception:
            return None
