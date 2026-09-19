"""
Milvus HTTP 客户端 — 通过 REST API 操作 Milvus，无需 gRPC / pymilvus

Milvus 2.4+ 原生支持 RESTful API（端口 19530），
避免 Windows 上 pymilvus 的 OpenSSL DLL 依赖问题。
"""
from typing import List, Optional
from loguru import logger


class MilvusHttpClient:
    """Milvus REST API 轻量封装"""

    def __init__(self, uri: str = "http://localhost:19530"):
        self.base = uri.rstrip("/")
        self._http = None

    def _get_http(self):
        if self._http is None:
            import httpx
            self._http = httpx.Client(timeout=30, base_url=self.base)
        return self._http

    def _post(self, path: str, json: dict):
        r = self._get_http().post(path, json=json)
        r.raise_for_status()
        data = r.json()
        code = data.get("code", 0)
        if code not in (0, 200):
            raise RuntimeError(f"Milvus error: {data.get('message', data)}")
        return data.get("data") or data

    def _get(self, path: str):
        r = self._get_http().get(path)
        r.raise_for_status()
        data = r.json()
        code = data.get("code", 0)
        if code not in (0, 200):
            raise RuntimeError(f"Milvus error: {data.get('message', data)}")
        return data.get("data") or data

    # ─── 集合管理 ───

    def has_collection(self, name: str) -> bool:
        """检查集合是否存在（通过 list_collections 判断）"""
        return name in self.list_collections()

    def drop_collection(self, name: str):
        """删除集合"""
        self._post("/v1/vector/collections/drop", {"collectionName": name})
        logger.info(f"Milvus 集合已删除: {name}")

    def create_collection(self, name: str, dim: int,
                          description: str = "",
                          metric_type: str = "COSINE"):
        """创建集合（autoId=true，chunk_id 作为普通标量字段）"""
        schema = {
            "collectionName": name,
            "dimension": dim,
            "description": description or "",
            "metricType": metric_type,
            "autoId": True,
            "primaryField": "id",
            "vectorField": "embedding",
            "fields": [
                {
                    "name": "id",
                    "dataType": "Int64",
                    "isPrimary": True,
                    "autoId": True,
                },
                {
                    "name": "chunk_id",
                    "dataType": "VarChar",
                    "elementTypeParams": {"max_length": 64},
                },
                {
                    "name": "knowledge_type",
                    "dataType": "VarChar",
                    "elementTypeParams": {"max_length": 32},
                },
                {
                    "name": "phenology_stages",
                    "dataType": "VarChar",
                    "elementTypeParams": {"max_length": 128},
                },
                {
                    "name": "risk_level",
                    "dataType": "VarChar",
                    "elementTypeParams": {"max_length": 8},
                },
                {
                    "name": "embedding",
                    "dataType": "FloatVector",
                    "elementTypeParams": {"dim": str(dim)},
                },
            ],
        }
        self._post("/v1/vector/collections/create", schema)
        logger.info(f"Milvus 集合已创建: {name} (dim={dim}, metric={metric_type})")

    def list_collections(self) -> list:
        """列出所有集合"""
        data = self._get("/v1/vector/collections")
        return data if isinstance(data, list) else []

    # ─── 数据操作 ───

    def insert(self, collection_name: str, data: List[dict]):
        """批量插入数据"""
        self._post(f"/v1/vector/insert", {
            "collectionName": collection_name,
            "data": data,
        })

    def flush(self, collection_name: str):
        """刷写数据到磁盘"""
        # REST API 自动刷写，无需显式调用
        pass

    def count(self, collection_name: str) -> int:
        """获取集合行数（用搜索空向量近似估算）"""
        try:
            dim = 512
            zero_vec = [0.0] * dim
            results = self.search(collection_name, zero_vec, top_k=1)
            # REST API 的 search 能返回结果就说明有数据
            return len(results) if results else 0
        except Exception:
            return 0

    # ─── 检索 ───

    def search(self, collection_name: str, query_vector: List[float],
               top_k: int = 20, output_fields: List[str] = None,
               expr: str = None) -> List[dict]:
        """向量检索"""
        payload = {
            "collectionName": collection_name,
            "vector": query_vector,
            "limit": top_k,
            "outputFields": output_fields or [],
        }
        if expr:
            payload["filter"] = expr

        result = self._post("/v1/vector/search", payload)
        if not result:
            return []

        # REST API 返回格式: [{"id": "xxx", "distance": 0.9, "chunk_id": "..."}, ...]
        if isinstance(result, dict):
            result = result.get("fields", []) or result.get("results", []) or [result]

        formatted = []
        for item in (result if isinstance(result, list) else [result]):
            formatted.append({
                "id": item.get("id", ""),
                "chunk_id": item.get("chunk_id", item.get("id", "")),
                "score": item.get("distance", 0),
                **{k: v for k, v in item.items()
                   if k not in ("id", "distance")},
            })
        return formatted

    def close(self):
        """关闭连接"""
        if self._http:
            self._http.close()
            self._http = None