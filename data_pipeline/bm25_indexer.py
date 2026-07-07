"""
BM25 关键词检索索引（支持中英文双语）

为什么需要 BM25：
- 向量检索擅长语义匹配，但对精确关键词匹配较弱
- 农业场景中很多专业术语（药剂名称"多菌灵"、具体数值"温度25°C"）
  需要精确匹配
- BM25 在处理专有名词和数值信息时补充向量检索的不足
- 英文内容使用正则分词，中文内容使用 jieba 分词
"""
import re
import pickle
from pathlib import Path
from typing import List, Optional
import numpy as np
import jieba
from rank_bm25 import BM25Okapi
from loguru import logger

from .models import Chunk
from config.settings import get_config


class BM25Indexer:
    """BM25 关键词检索索引（支持中英文双语分词）"""

    # 中文停用词（精简版）
    STOPWORDS = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它", "们"
    }

    # 英文停用词
    EN_STOPWORDS = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "must", "need",
        "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
        "us", "them", "my", "your", "his", "its", "our", "their",
        "this", "that", "these", "those", "what", "which", "who", "whom",
        "when", "where", "why", "how", "all", "each", "every", "both",
        "few", "more", "most", "some", "any", "no", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "also",
        "and", "but", "or", "if", "because", "as", "until", "while",
        "of", "at", "by", "for", "with", "about", "against", "between",
        "into", "through", "during", "before", "after", "above", "below",
        "from", "up", "down", "in", "out", "on", "off", "over", "under",
        "again", "further", "then", "once", "here", "there", "to",
    }

    def __init__(self):
        self.index_path = Path(get_config("bm25.index_path", "./indexes/bm25_index.pkl"))
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.bm25: Optional[BM25Okapi] = None
        self.corpus_meta: List[dict] = []
        self._tokenizer_mode = get_config("bilingual.bm25_tokenizer", "auto")

    # ─── 分词器 ───

    def _tokenize(self, text: str, language: str = "auto") -> List[str]:
        """
        语言感知分词

        参数:
            text: 输入文本
            language: "zh" | "en" | "auto" — auto 则自动检测

        返回:
            分词后的 token 列表
        """
        if language == "auto" or self._tokenizer_mode == "auto":
            from utils.lang_detector import detect_language
            lang = detect_language(text, method="heuristic")
        else:
            lang = language

        if self._tokenizer_mode == "en_only" or lang == "en":
            return self._tokenize_en(text)
        elif lang == "mixed":
            # 中英混合：同时使用两种分词器，合并 token
            zh_tokens = self._tokenize_zh(text)
            en_tokens = self._tokenize_en(text)
            # 合并去重（保持顺序，先中文后英文）
            seen = set(zh_tokens)
            for t in en_tokens:
                if t not in seen:
                    zh_tokens.append(t)
                    seen.add(t)
            return zh_tokens
        else:
            return self._tokenize_zh(text)

    def _tokenize_zh(self, text: str) -> List[str]:
        """中文分词 — jieba + 停用词过滤"""
        words = jieba.lcut(text)
        return [
            w.strip() for w in words
            if w.strip()
            and w.strip() not in self.STOPWORDS
            and len(w.strip()) > 1
        ]

    def _tokenize_en(self, text: str) -> List[str]:
        """英文分词 — 正则 + 小写 + 停用词过滤"""
        # 提取英文字母单词（包含连字符复合词）
        tokens = re.findall(r"\b[a-zA-Z]+(?:[-\'][a-zA-Z]+)*\b", text.lower())
        return [
            t for t in tokens
            if t not in self.EN_STOPWORDS
            and len(t) > 1
        ]

    def build(self, chunks: List[Chunk]):
        """构建 BM25 索引（支持中英文混合）"""
        logger.info(f"开始构建 BM25 索引，共 {len(chunks)} 个文档")

        corpus_tokens = []
        self.corpus_meta = []

        for chunk in chunks:
            lang = chunk.metadata.get("language", "auto")
            tokens = self._tokenize(chunk.content, language=lang)
            corpus_tokens.append(tokens)
            self.corpus_meta.append({
                "chunk_id": chunk.chunk_id,
                "source": chunk.metadata.get("source", ""),
                "text": chunk.content,
                "metadata": chunk.metadata
            })

        if not any(corpus_tokens):
            logger.warning("BM25 索引构建：所有文档分词结果为空，请检查语言检测配置")
            # 如果全空，提供一个空 BM25 避免后续崩溃
            self.bm25 = BM25Okapi([[]])
        else:
            self.bm25 = BM25Okapi(corpus_tokens)

        # 持久化
        with open(self.index_path, 'wb') as f:
            pickle.dump({
                "bm25": self.bm25,
                "corpus_meta": self.corpus_meta
            }, f)

        token_stats = sum(len(t) for t in corpus_tokens)
        logger.info(f"BM25 索引构建完成，持久化到 {self.index_path} （总 token 数: {token_stats}）")

    def load(self):
        """加载持久化的索引"""
        if not self.index_path.exists():
            logger.warning(f"BM25索引文件不存在: {self.index_path}")
            return False

        with open(self.index_path, 'rb') as f:
            data = pickle.load(f)
            self.bm25 = data["bm25"]
            self.corpus_meta = data["corpus_meta"]
        logger.info(f"BM25 索引加载完成，共 {len(self.corpus_meta)} 条文档")
        return True

    def search(self, query: str, top_k: int = 20,
               filters: dict = None, language: str = "auto") -> List[dict]:
        """BM25 检索（支持中英文查询，优化9: 接受language参数避免重复检测）"""
        if self.bm25 is None:
            if not self.load():
                return []

        # 优化9: 使用传入的语言，避免重复检测
        query_tokens = self._tokenize(query, language=language)
        if not query_tokens:
            logger.debug(f"BM25 查询分词结果为空: query='{query[:50]}...'")
            return []

        scores = self.bm25.get_scores(query_tokens)
        top_indices = np.argsort(scores)[::-1][:top_k * 2]  # 多取一些用于过滤

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue

            meta = self.corpus_meta[idx]

            # 应用元数据过滤
            if filters and not self._apply_filters(meta["metadata"], filters):
                continue

            results.append({
                "id": meta["chunk_id"],
                "text": meta["text"],
                "source": meta["source"],
                "score": float(scores[idx]),
                "metadata": meta["metadata"]
            })

            if len(results) >= top_k:
                break

        return results

    def _apply_filters(self, metadata: dict, filters: dict) -> bool:
        """元数据过滤"""
        for key, value in filters.items():
            if key == "phenology_stage":
                stages = metadata.get("phenology_stages", [])
                if isinstance(stages, str):
                    stages = stages.split(",")
                if value not in stages:
                    return False
            elif key == "knowledge_type":
                if metadata.get("knowledge_type") != value:
                    return False
            elif key == "entities":
                doc_entities = metadata.get("entities", [])
                if isinstance(doc_entities, str):
                    doc_entities = doc_entities.split(",")
                if not set(value).intersection(set(doc_entities)):
                    return False
        return True
