"""
向量检索器 - 支持 ChromaDB + Milvus + Milvus+MySQL

性能优化：
- 查询Embedding缓存（LRU）
- 扩展查询批量编码
"""
import os
# 强制 HuggingFace 离线模式，避免联网超时阻塞加载
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from functools import lru_cache
from typing import List, Optional
from loguru import logger

from config.settings import get_config
from utils.device import get_device


class VectorSearcher:
    """向量检索器"""

    def __init__(self):
        self.db_type = get_config("vector_db.type", "chroma")
        self.collection_name = get_config("vector_db.collection_name",
                                          "lychee_knowledge")
        self.encoder = None
        self._client = None
        self._collection = None
        self._mysql_conn = None
        self._embedding_cache = {}  # 优化4: 查询Embedding缓存

    def _get_encoder(self):
        """懒加载 Embedding 模型（当前使用 BAAI/bge-base-zh-v1.5）"""
        if self.encoder is None:
            from sentence_transformers import SentenceTransformer
            model_name = get_config("embedding.model_name")
            cache_dir = get_config("embedding.cache_dir")
            _device = get_device()
            logger.info(f"加载查询编码器: {model_name} (device={_device})")
            try:
                self.encoder = SentenceTransformer(
                    model_name, cache_folder=cache_dir,
                    device=_device,
                    local_files_only=True,  # 仅用本地缓存，避免联网超时
                )
            except Exception:
                fallback = get_config("embedding.fallback_model")
                self.encoder = SentenceTransformer(
                    fallback, cache_folder=cache_dir,
                    device=_device,
                    local_files_only=True,
                )
                model_name = fallback
            self._active_model_name = model_name
        return self.encoder

    def _get_collection(self):
        """获取集合"""
        if self._collection is not None:
            return self._collection

        if self.db_type == "chroma":
            import chromadb
            db_path = get_config("vector_db.chroma_path")
            client = chromadb.PersistentClient(path=db_path)
            self._collection = client.get_or_create_collection(self.collection_name)

        elif self.db_type in ("milvus", "milvus_mysql"):
            from utils.milvus_http import MilvusHttpClient
            uri = get_config("vector_db.milvus.uri",
                             get_config("vector_db.milvus_uri", "http://localhost:19530"))
            self._client = MilvusHttpClient(uri=uri)
            self._collection = self._client

        return self._collection

    def _get_mysql_connection(self):
        """懒加载 MySQL 连接（milvus_mysql 模式）"""
        if self._mysql_conn is not None:
            return self._mysql_conn

        import pymysql
        host = get_config("vector_db.mysql.host", "localhost")
        port = get_config("vector_db.mysql.port", 3306)
        user = get_config("vector_db.mysql.user", "root")
        password = get_config("vector_db.mysql.password", "")
        database = get_config("vector_db.mysql.database", "lycheeai_rag")

        self._mysql_conn = pymysql.connect(
            host=host, port=int(port), user=user, password=password,
            database=database, charset="utf8mb4",
        )
        return self._mysql_conn

    def _get_cached_embedding(self, text: str, encoder):
        """优化4: 带缓存的Embedding编码"""
        cache_key = text[:200]  # 取前200字作为缓存key
        if cache_key not in self._embedding_cache:
            encoded = f"query: {text}" if "e5" in getattr(self, "_active_model_name", "").lower() else text
            self._embedding_cache[cache_key] = encoder.encode(
                [encoded], normalize_embeddings=True
            )[0]
            # 缓存上限1000条，防止内存溢出
            if len(self._embedding_cache) > 1000:
                # 删除前500条
                keys = list(self._embedding_cache.keys())
                for k in keys[:500]:
                    del self._embedding_cache[k]
        return self._embedding_cache[cache_key]

    def search(self, query: str, top_k: int = 20,
               filters: dict = None,
               expansion_queries: List[str] = None) -> List[dict]:
        """
        向量检索（仅用原始 query，语义泛化）

        向量检索的核心价值是语义泛化——"叶子长白毛"这种口语表达
        靠语义相似度找到"霜疫霉病"文档。扩展查询交给 BM25 做精确匹配。
        """
        encoder = self._get_encoder()
        embedding = self._get_cached_embedding(query, encoder)
        results = self._search_single(embedding, top_k, filters)
        return results[:top_k]

    def _search_single(self, embedding, top_k: int,
                       filters: dict) -> List[dict]:
        """单次向量检索"""
        if self.db_type == "chroma":
            return self._search_chroma(embedding, top_k, filters)
        elif self.db_type == "milvus":
            return self._search_milvus(embedding, top_k, filters)
        elif self.db_type == "milvus_mysql":
            return self._search_milvus_mysql(embedding, top_k, filters)
        return []

    # ──────────────── ChromaDB ────────────────

    def _search_chroma(self, embedding, top_k: int,
                       filters: dict) -> List[dict]:
        """ChromaDB 检索"""
        collection = self._get_collection()

        where = None
        if filters:
            where_conditions = []
            if "phenology_stage" in filters:
                where_conditions.append({
                    "phenology_stages": {"$contains": filters["phenology_stage"]}
                })
            if "knowledge_type" in filters:
                where_conditions.append({
                    "knowledge_type": {"$eq": filters["knowledge_type"]}
                })
            if len(where_conditions) == 1:
                where = where_conditions[0]
            elif len(where_conditions) > 1:
                where = {"$and": where_conditions}

        try:
            results = collection.query(
                query_embeddings=[embedding.tolist()],
                n_results=top_k,
                where=where
            )
        except Exception as e:
            logger.error(f"ChromaDB 检索失败: {e}")
            return []

        formatted = []
        if results and results["ids"]:
            ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0]

            for i, doc_id in enumerate(ids):
                score = 1 - distances[i] if distances[i] < 1 else 0
                metadata = metadatas[i]
                phenology = metadata.get("phenology_stages", "")
                if isinstance(phenology, str) and phenology:
                    metadata["phenology_stages"] = [s.strip() for s in phenology.split(",") if s.strip()]
                entities = metadata.get("entities", "")
                if isinstance(entities, str) and entities:
                    metadata["entities"] = [e.strip() for e in entities.split(",") if e.strip()]

                formatted.append({
                    "id": doc_id,
                    "text": documents[i],
                    "source": metadata.get("source", ""),
                    "page": metadata.get("page", 0),
                    "score": score,
                    "metadata": metadata
                })

        return formatted

    # ──────────────── Milvus ────────────────

    def _search_milvus(self, embedding, top_k: int,
                       filters: dict) -> List[dict]:
        """Milvus 独立检索"""
        client = self._get_collection()
        expr = self._build_milvus_filter(filters)

        results = client.search(
            collection_name=self.collection_name,
            query_vector=embedding.tolist(),
            top_k=top_k,
            output_fields=["chunk_id"],
            expr=expr
        )

        formatted = []
        for r in results:
            formatted.append({
                "id": r.get("id"),
                "chunk_id": r.get("chunk_id", ""),
                "score": r.get("score", 0),
                "metadata": {},
            })
        return formatted

    # ──────────────── Milvus + MySQL 混合检索 ────────────────

    def _search_milvus_mysql(self, embedding, top_k: int,
                             filters: dict) -> List[dict]:
        """Milvus 向量检索 + MySQL 元数据补全"""
        client = self._get_collection()
        expr = self._build_milvus_filter(filters)

        # 1. Milvus 向量检索（只返回 chunk_id + score）
        results = client.search(
            collection_name=self.collection_name,
            query_vector=embedding.tolist(),
            top_k=top_k,
            output_fields=["chunk_id"],
            expr=expr
        )

        if not results:
            return []

        # 2. 提取 chunk_id 列表
        chunk_ids = [r.get("chunk_id", "") for r in results]
        score_map = {r.get("chunk_id", ""): r.get("score", 0) for r in results}

        # 3. MySQL 批量查询元数据
        mysql_conn = self._get_mysql_connection()
        formatted = []
        try:
            with mysql_conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(chunk_ids))
                cur.execute(
                    f"""SELECT chunk_id, content, source, doc_type,
                               knowledge_type, phenology_stages, entities,
                               risk_level, page
                        FROM chunks
                        WHERE chunk_id IN ({placeholders})""",
                    chunk_ids
                )
                rows = cur.fetchall()
                # 用 dict 加速查找
                meta_map = {}
                for row in rows:
                    meta_map[row[0]] = {
                        "chunk_id": row[0],
                        "content": row[1],
                        "source": row[2],
                        "doc_type": row[3],
                        "knowledge_type": row[4],
                        "phenology_stages": (
                            [s.strip() for s in row[5].split(",") if s.strip()]
                            if row[5] else []
                        ),
                        "entities": (
                            [e.strip() for e in row[6].split(",") if e.strip()]
                            if row[6] else []
                        ),
                        "risk_level": row[7],
                        "page": row[8],
                    }

            # 4. 组装结果（保持 Milvus 返回的顺序）
            for cid in chunk_ids:
                meta = meta_map.get(cid, {})
                formatted.append({
                    "id": cid,
                    "text": meta.get("content", ""),
                    "source": meta.get("source", ""),
                    "page": meta.get("page", 0),
                    "score": score_map.get(cid, 0),
                    "metadata": {
                        "knowledge_type": meta.get("knowledge_type", ""),
                        "phenology_stages": meta.get("phenology_stages", []),
                        "entities": meta.get("entities", []),
                        "risk_level": meta.get("risk_level", "low"),
                        "doc_type": meta.get("doc_type", ""),
                    }
                })

        except Exception as e:
            logger.error(f"MySQL 元数据查询失败: {e}")
            # 降级：只返回 Milvus 结果（不带元数据）
            for r in results:
                formatted.append({
                    "id": r.get("chunk_id", ""),
                    "text": "",
                    "source": "",
                    "page": 0,
                    "score": r.get("distance", 0),
                    "metadata": {}
                })

        return formatted

    # ──────────────── 工具方法 ────────────────

    def _build_milvus_filter(self, filters: dict) -> Optional[str]:
        """构建 Milvus 过滤表达式"""
        if not filters:
            return None
        conditions = []
        if "knowledge_type" in filters:
            conditions.append(f'knowledge_type == "{filters["knowledge_type"]}"')
        if "phenology_stage" in filters:
            # phenology_stages 是逗号分隔字符串，如 "开花期,幼果期"
            # 用 like 做模糊匹配
            conditions.append(
                f'phenology_stages like "%{filters["phenology_stage"]}%"'
            )
        return " && ".join(conditions) if conditions else None
