"""
规则分块器 - 基于段落和字符数的分块策略（企业级增强版）

策略：
1. 递归分隔符分块：标题(##/###) → 段落(\\n\\n) → 句子(。！？) → 字符兜底
2. 语义主语注入：在 chunk 内容前注入主题标识（如【品种：桂味】），防止上下文丢失
3. 元数据自动填充：基于关键词规则填充 knowledge_type、phenology_stages、entities、risk_level
4. 语义相似度合并：只有语义相近的小块才合并，避免跨主题污染
"""
import hashlib
import re
from difflib import SequenceMatcher
from typing import List, Optional, Dict, Any, Tuple

from loguru import logger

from .models import Document, Chunk
from config.settings import get_config


# ===================================================================
# 元数据填充规则（纯规则匹配，无 LLM 依赖）
# ===================================================================

# 知识类型分类规则（关键词 → 类型映射）
_KNOWLEDGE_TYPE_RULES = [
    ("pest_disease", ["病害", "真菌", "细菌", "病毒", "虫", "蛀", "霉", "腐", "病", "害",
                       "霜疫", "炭疽", "灰霉", "疫霉", "白粉", "锈病", "褐斑", "黑斑",
                       "蒂蛀虫", "荔枝蝽", "黄蜂", "果核螟", "介壳虫", "潜叶蛾"]),
    ("agronomy", ["施肥", "灌溉", "修剪", "整枝", "疏果", "控梢", "环割", "断根",
                   "水分", "管理", "栽培", "种植", "育苗", "嫁接", "播种", "移栽",
                   "采收", "储藏", "保鲜", "运输"]),
    ("cultivar", ["品种", "选种", "良种", "杂交", "育种", "特性", "丰产", "抗逆",
                  "花期", "果期", "产量", "品质", "商品", "外观"]),
    ("phytopathology", ["病原", "寄主", "传播", "侵染", "循环", "越冬", "致病",
                        "症状", "识别", "诊断", "病理", "发病"]),
    ("environment", ["温度", "湿度", "光照", "降雨", "气候", "气象", "海拔", "土壤",
                     "物候", "生长周期"]),
]

# 风险等级关键词
_RISK_RULES = {
    "高": ["禁用", "中毒", "剧毒", "致癌", "残留超标", "急性", "致死", "严重"],
    "中": ["限量", "注意", "慎用", "副反应", "耐受", "药害", "灼伤", "烧苗"],
}


def _classify_knowledge_type(text: str) -> str:
    """基于关键词规则分类知识类型"""
    text_lower = text
    best_type = "general"
    best_score = 0
    for ktype, keywords in _KNOWLEDGE_TYPE_RULES:
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_type = ktype
    return best_type


def _extract_entities(text: str) -> List[str]:
    """从文本中提取实体（复用领域词典关键词）"""
    # 领域专名实体（品种名、病害名、农药名）
    entities = []
    known_entities = [
        # 品种名
        "桂味", "糯米糍", "怀枝", "妃子笑", "白糖罂", "仙进奉", "黑叶",
        # 病害名
        "霜疫霉病", "炭疽病", "灰霉病", "白粉病", "黄叶病", "枯萎病",
        # 害虫名
        "蒂蛀虫", "荔枝蝽", "黄蜂", "果核螟", "介壳虫", "潜叶蛾",
        # 农药名
        "多菌灵", "甲基托布津", "波尔多液", "石硫合剂", "吡虫啉",
    ]
    for entity in known_entities:
        if entity in text and entity not in entities:
            entities.append(entity)
    return entities


def _extract_phenology_stages(text: str) -> List[str]:
    """提取物候期阶段"""
    phenology_map = {
        "萌芽": "春梢萌芽", "抽梢": "春梢萌动", "长叶": "春梢萌动",
        "花芽": "花芽分化", "分化": "花芽分化", "花穗": "花穗生长期", "出花": "花穗生长期",
        "开花": "开花期", "花期": "开花期", "盛花": "开花期",
        "坐果": "幼果期", "幼果": "幼果期", "小果": "幼果期",
        "膨大": "果实膨大期", "膨果": "果实膨大期", "转色": "果实膨大期",
        "成熟": "成熟期", "采收": "成熟期", "上市": "成熟期",
        "休眠": "休眠期", "老熟": "秋梢老熟", "秋梢": "秋梢萌动",
    }
    stages = []
    for keyword, stage in phenology_map.items():
        if keyword in text and stage not in stages:
            stages.append(stage)
    return stages


def _classify_risk_level(text: str) -> str:
    """基于风险关键词分类风险等级"""
    for level, keywords in _RISK_RULES.items():
        if any(kw in text for kw in keywords):
            return level
    return "低"


def _detect_table_stats(text: str) -> Optional[dict]:
    """
    检测 chunk 文本中是否包含表格结构，返回统计信息

    检测管道表（连续 3 行以上 | 开头 | 结尾）
    检测 tab 分隔表（连续 3 行以上含 tab 且列数 ≥ 3）

    Returns:
        {has_table, table_type, table_rows, table_cols} 或 None
    """
    lines = text.split('\n')
    # 检测管道表 | ... |
    pipe_lines = [l for l in lines if l.strip().startswith('|') and l.strip().endswith('|')]
    if len(pipe_lines) >= 3:
        return {
            "has_table": True,
            "table_type": "markdown_pipe",
            "table_rows": len(pipe_lines),
            "table_cols": pipe_lines[0].count('|') - 1,
        }
    # 检测 tab 分隔表格
    tab_lines = [l for l in lines if '\t' in l and len(l.split('\t')) >= 3]
    if len(tab_lines) >= 3:
        return {
            "has_table": True,
            "table_type": "tsv",
            "table_rows": len(tab_lines),
            "table_cols": len(tab_lines[0].split('\t')),
        }
    return None


def _enrich_metadata(text: str, existing_meta: dict) -> dict:
    """
    对 chunk 文本做元数据自动填充（纯规则匹配）

    填充字段：knowledge_type, phenology_stages, entities, risk_level, has_table
    如果已有值则保留已有值（不覆盖）
    """
    meta = existing_meta.copy()

    # 只填充缺失的字段
    if "knowledge_type" not in meta:
        meta["knowledge_type"] = _classify_knowledge_type(text)

    if "phenology_stages" not in meta:
        stages = _extract_phenology_stages(text)
        meta["phenology_stages"] = ",".join(stages) if stages else ""

    if "entities" not in meta:
        ents = _extract_entities(text)
        meta["entities"] = ",".join(ents) if ents else ""

    if "risk_level" not in meta:
        meta["risk_level"] = _classify_risk_level(text)

    # 表格检测（如果还没被标记）
    if "has_table" not in meta:
        stats = _detect_table_stats(text)
        if stats:
            meta.update(stats)

    return meta


# ===================================================================
# 语义相似度计算（Embedding-based）
# ===================================================================

# 模块级单例，避免重复加载模型
_similarity_model = None
_similarity_model_failed = False


def _get_similarity_model():
    """懒加载 SentenceTransformer 用于语义相似度计算"""
    global _similarity_model, _similarity_model_failed
    if _similarity_model_failed:
        return None
    if _similarity_model is None:
        from utils.device import get_shared_embedding_model
        model_name = get_config("embedding.model_name", "intfloat/multilingual-e5-small")
        cache_dir = get_config("embedding.cache_dir", "./indexes/model_cache")
        logger.info(f"加载语义相似度模型: {model_name}")
        try:
            _similarity_model = get_shared_embedding_model(model_name, cache_dir)
        except Exception:
            _similarity_model_failed = True
            raise
    return _similarity_model


def _compute_similarity(text_a: str, text_b: str) -> float:
    """计算两个文本的余弦相似度（0-1）"""
    try:
        model = _get_similarity_model()
        if model is None:
            raise RuntimeError("语义模型已标记为不可用")
        emb_a = model.encode([text_a], normalize_embeddings=True)
        emb_b = model.encode([text_b], normalize_embeddings=True)
        similarity = float((emb_a[0] * emb_b[0]).sum())
        return max(0.0, min(1.0, similarity))  # 钳位到 [0, 1]
    except Exception as e:
        # 生产环境不能因为可选模型缺失而悄悄改变分块结果；使用确定性词法回退。
        logger.debug(f"语义模型不可用，使用词法相似度回退: {e}")
        return SequenceMatcher(None, text_a[:2000], text_b[:2000]).ratio()


# ===================================================================
# 分块器主类
# ===================================================================

class RuleChunker:
    """企业级规则分块器

    特性：
    1. 递归分隔符（标题→段落→句子→字符）
    2. 语义主语注入（防止上下文丢失）
    3. 元数据自动填充（知识类型/物候期/实体/风险等级）
    4. 语义相似度合并（避免跨主题污染）
    """

    def __init__(
        self,
        chunk_size: int = None,
        overlap: int = None,
        merge_threshold: int = None,
        merge_similarity_threshold: float = None,
    ):
        self.chunk_size = chunk_size or get_config("chunker.chunk_size", 768)
        self.overlap = overlap or get_config("chunker.overlap", 96)
        self.merge_threshold = merge_threshold or get_config("chunker.merge_threshold", 300)
        self.merge_similarity_threshold = merge_similarity_threshold or \
            get_config("chunker.merge_similarity_threshold", 0.65)

        if self.chunk_size < 128:
            raise ValueError("chunk_size 不能小于 128")
        if not 0 <= self.overlap < self.chunk_size:
            raise ValueError("overlap 必须满足 0 <= overlap < chunk_size")

        # 递归分隔符层级：从粗到细。分隔符使用零宽匹配以保留标题/条款。
        self._separators = [
            # Markdown 标题、中文/英文编号标题（5.1、1. Introduction 等）
            re.compile(
                r'\n(?=(?:#{1,6}\s+|(?:第[一二三四五六七八九十百0-9]+[章节条]\s*)|'
                r'(?:\d+(?:\.\d+){0,3}[、.．]?\s+[A-Z\u4e00-\u9fff])))',
                re.MULTILINE,
            ),
            # Level 2: 段落（双换行）
            re.compile(r'\n\s*\n'),
            # Level 3: 列表项（保留每个列表项），表格已由占位符保护
            re.compile(r'\n(?=(?:[-*+]\s+|\d+[.)、]\s+))', re.MULTILINE),
            # Level 4: 中英文句子
            re.compile(r'(?<=[。！？!?])\s*\n?|(?<=[.!?])\s+(?=[A-Z0-9])'),
        ]

    # ─── 主入口 ───

    def chunk(self, documents: List[Document]) -> List[Chunk]:
        """将文档列表分块"""
        all_chunks = []
        source_sequences: Dict[str, int] = {}
        for doc in documents:
            doc_chunks = self._chunk_document(doc)
            source = doc.metadata.get("source", "")
            sequence = source_sequences.get(source, 0)
            for chunk in doc_chunks:
                chunk.metadata["chunk_index"] = sequence
                chunk.metadata["chunk_length"] = len(chunk.content)
                chunk.metadata["chunker_version"] = "rule-v3"
                sequence += 1
            source_sequences[source] = sequence
            all_chunks.extend(doc_chunks)
        logger.info(f"分块完成: {len(all_chunks)} 个分块, 来自 {len(documents)} 个文档片段")
        return all_chunks

    # ─── 单文档分块 ───

    def _chunk_document(self, doc: Document) -> List[Chunk]:
        """对单个文档进行分块"""
        # Step 0: 提取并保护表格（用占位符替换，避免被切碎）
        protected_content, tables = self._extract_tables(doc.content)

        # Step 1: 提取文档级主题（用于主语注入）
        doc_topic = self._extract_document_topic(doc)

        # Step 2: 递归分隔符切分（表格已被占位符保护，不会被切）
        blocks = self._recursive_split(protected_content)

        # Step 3: 按块拼接成 chunk（贪心积累）
        raw_chunks = self._accumulate_to_chunks(blocks, doc_topic, doc)

        # Step 4: 语义相似度合并
        merged_chunks = self._merge_small_chunks(raw_chunks)

        # Step 5: 还原表格占位符 + 标记表格 chunk + 检查超长
        final_chunks = []
        for chunk in merged_chunks:
            chunk.content = self._restore_tables(chunk.content, tables)
            for tbl in tables:
                if tbl["content"] in chunk.content:
                    chunk.metadata["has_table"] = True
                    chunk.metadata["table_type"] = tbl.get("format", "pipe")
                    chunk.metadata["table_rows"] = tbl["row_count"]
                    chunk.metadata["table_cols"] = tbl["col_count"]
                    break

            # 检查还原后是否超长（表格还原后可能超过 chunk_size 限制）
            if len(chunk.content) > self.chunk_size * 1.1:
                # 对超长 chunk 做字符级切分（去掉已有的 topic 前缀避免重复）
                existing_topic = ""
                for prefix in ("【品种：", "【主题："):
                    idx = chunk.content.find(prefix)
                    if idx != -1:
                        end = chunk.content.find("】", idx)
                        if end != -1:
                            existing_topic = chunk.content[idx:end + 1]
                            # 从 content 中移除已有前缀
                            chunk.content = chunk.content.replace(existing_topic, "", 1)
                            break
                split_chunks = self._split_long_text(chunk.content, doc_topic or existing_topic, doc)
                for sc in split_chunks:
                    # 保留表格标记到子分块
                    for key in ("has_table", "table_type", "table_rows", "table_cols"):
                        if key in chunk.metadata:
                            sc.metadata[key] = chunk.metadata[key]
                    final_chunks.append(sc)
            else:
                final_chunks.append(chunk)

        # Step 6: 元数据自动填充（含表格检测）
        for chunk in final_chunks:
            chunk.metadata = _enrich_metadata(chunk.content, chunk.metadata)

        return final_chunks

    # ─── 文档级主题提取 ───

    def _extract_tables(self, text: str):
        """
        检测并提取管道表，用占位符替换，保护表格不被切碎。

        检测逻辑：连续 3 行以上以 | 开头 → 视为表格。
        将表格替换为 <<TABLE_N>> 占位符，返回（替换后文本, 表格列表）。

        Returns:
            Tuple[str, list]: (替换后的文本, 表格信息列表)
            每个表格信息: {id, content, row_count, col_count, format}
        """
        tables = []
        lines = text.split('\n')
        result = []
        i = 0
        table_counter = 0

        while i < len(lines):
            line = lines[i]
            # 检测表格开始：连续 3 行以 | 开头
            if (line.strip().startswith('|') and
                    i + 2 < len(lines) and
                    all(l.strip().startswith('|') for l in lines[i:i + 3])):
                table_lines = []
                table_start = i
                while i < len(lines) and lines[i].strip().startswith('|'):
                    table_lines.append(lines[i])
                    i += 1
                placeholder = f"<<TABLE_{table_counter}>>"
                tables.append({
                    "id": table_counter,
                    "content": '\n'.join(table_lines),
                    "row_count": len(table_lines),
                    "col_count": table_lines[0].count('|') - 1 if table_lines else 0,
                    "format": "pipe",
                })
                result.append(placeholder)
                table_counter += 1
            else:
                result.append(line)
                i += 1

        return '\n'.join(result), tables

    def _restore_tables(self, text: str, tables: list) -> str:
        """将占位符 <<TABLE_N>> 还原为完整表格内容"""
        for tbl in tables:
            text = text.replace(f"<<TABLE_{tbl['id']}>>", tbl['content'])
        return text

    # ─── 文档级主题提取 ───

    def _extract_document_topic(self, doc: Document) -> str:
        """从文档元数据和内容中提取主题标识"""
        source = doc.metadata.get("source", "")

        # 策略 1: 文件名中提取品种名或主题词
        # 匹配模式：xxx_品种名_... 或 ...品种名...
        cultivar_pattern = re.search(
            r'(桂味|糯米糍|怀枝|妃子笑|白糖罂|仙进奉|黑叶|三月红|挂绿)', source
        )
        if cultivar_pattern:
            topic = cultivar_pattern.group(1)
            return f"品种：{topic}"

        # 策略 2: 从文件名中按 `_` 分割，取第二个部分
        parts = source.replace('.pdf', '').replace('.md', '').split('_')
        if len(parts) >= 2:
            return f"主题：{parts[1]}"

        # 策略 3: 从 doc 内容第一行提取标题
        first_line = doc.content.strip().split('\n')[0].strip('# ').strip()
        if first_line and len(first_line) < 50:
            return f"主题：{first_line}"

        return ""

    # ─── 递归分隔符切分 ───

    def _recursive_split(self, text: str) -> List[Tuple[str, int]]:
        """
        递归分隔符切分（Recursive Character Splitting）

        从最粗粒度到最细粒度逐层切分：
        1. 按章节标题切
        2. 按段落切
        3. 按句子切
        4. 字符兜底

        返回 [(块文本, 分隔符层级), ...]
        """
        separators = self._separators
        return self._recursive_split_impl(text, separators, 0)

    def _recursive_split_impl(
        self, text: str, separators: List[re.Pattern], level: int
    ) -> List[Tuple[str, int]]:
        """递归切分实现"""
        # 当前层级：用对应分隔符切
        if level < len(separators):
            pattern = separators[level]
            parts = pattern.split(text)
            # 过滤空字符串和纯空白
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) > 1:
                result: List[Tuple[str, int]] = []
                for part in parts:
                    # 真正递归：只有超长子块继续向更细粒度切分。
                    if len(part) > self._content_budget("") and level + 1 < len(separators):
                        result.extend(self._recursive_split_impl(part, separators, level + 1))
                    else:
                        result.append((part, level))
                return result
            # 如果切不出来（只有一个部分），进入下一层级

        # 下一层级：用更细的分隔符切
        if level + 1 < len(separators):
            return self._recursive_split_impl(text, separators, level + 1)

        # 兜底：字符级别（不再继续切，返回原文本）
        return [(text, level)]

    def _topic_prefix(self, doc_topic: str) -> str:
        return f"【{doc_topic}】" if doc_topic else ""

    def _content_budget(self, doc_topic: str) -> int:
        """主题前缀计入硬上限，保证最终 chunk 不超过 chunk_size。"""
        return max(1, self.chunk_size - len(self._topic_prefix(doc_topic)))

    # ─── 贪心积累成 Chunk ───

    def _accumulate_to_chunks(
        self, blocks: List[Tuple[str, int]], doc_topic: str, doc: Document
    ) -> List[Chunk]:
        """
        将切分后的 block 列表贪心积累成 chunk

        积累策略：
        - 将 block 逐个加入 buffer，直到 buffer 长度接近 chunk_size
        - 超过后生成 chunk，保留 overlap 尾部的 block 到下一轮
        - 每个 chunk 注入语义主语前缀，附带 doc metadata
        """
        chunks = []
        buffer = []
        buffer_len = 0

        for block_text, block_level in blocks:
            block_len = len(block_text)
            content_budget = self._content_budget(doc_topic)

            # 超 block 直接截断
            if block_len > content_budget:
                if buffer:
                    chunks.append(self._make_chunk_from_buffer(buffer, doc_topic, doc))
                    buffer = []
                    buffer_len = 0
                chunks.extend(self._split_long_text(block_text, doc_topic, doc))
                continue

            # 超过 chunk_size，先输出当前 buffer
            separator_cost = 2 if buffer else 0
            if buffer_len + separator_cost + block_len > content_budget and buffer:
                chunks.append(self._make_chunk_from_buffer(buffer, doc_topic, doc))
                # 保留 overlap 尾部 block
                buffer = self._get_overlap_tail(buffer)
                buffer_len = len('\n\n'.join(buffer))
                # overlap 加上当前原子块仍超预算时，优先保证硬上限。
                if buffer_len + (2 if buffer else 0) + block_len > content_budget:
                    buffer = []
                    buffer_len = 0

            buffer.append(block_text)
            buffer_len = len('\n\n'.join(buffer))

        # 剩余内容输出
        if buffer:
            chunks.append(self._make_chunk_from_buffer(buffer, doc_topic, doc))

        return chunks

    def _make_chunk_from_buffer(self, buffer: List[str], doc_topic: str, doc: Document) -> Chunk:
        """从 buffer 列表生成 Chunk，注入语义主语，附带 doc metadata"""
        content = '\n\n'.join(buffer).strip()

        # 注入主语前缀
        if doc_topic:
            content = self._topic_prefix(doc_topic) + content

        return self._make_chunk(content, doc)

    def _get_overlap_tail(self, buffer: List[str]) -> List[str]:
        """从 buffer 尾部取 overlap 长度的内容（block 粒度）"""
        if self.overlap == 0:
            return []
        tail = []
        tail_len = 0
        for block_text in reversed(buffer):
            block_len = len(block_text)
            if not tail and block_len > self.overlap:
                fragment = block_text[-self.overlap:]
                # 尽量从空白或句末后开始，且绝不让 overlap 超预算。
                boundary = re.search(r'(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z0-9])', fragment)
                start_at = boundary.end() if boundary else None
                if start_at is None:
                    word_boundary = re.search(r'(?<=\s)\S', fragment)
                    start_at = word_boundary.start() if word_boundary else 0
                tail.insert(0, fragment[start_at:])
                break
            if tail_len + block_len > self.overlap and tail:
                break
            tail.insert(0, block_text)
            tail_len += block_len
        return tail

    def _split_long_text(self, text: str, doc_topic: str, doc: Document) -> List[Chunk]:
        """边界感知地截断超长文本（带 overlap），字符切分仅作为最终兜底。"""
        chunks = []
        start = 0
        budget = self._content_budget(doc_topic)
        while start < len(text):
            end = min(start + budget, len(text))
            if end < len(text):
                # 在窗口后 35% 中优先寻找自然边界，避免截断英文单词和中文句子。
                floor = start + int(budget * 0.65)
                window = text[floor:end]
                candidates = [m.end() for m in re.finditer(r'[。！？!?；;]\s*|\.\s+(?=[A-Z0-9])|\n+', window)]
                if candidates:
                    end = floor + candidates[-1]
                else:
                    spaces = [m.start() for m in re.finditer(r'\s+', window)]
                    if spaces:
                        end = floor + spaces[-1]
            chunk_text = text[start:end]
            if doc_topic:
                chunk_text = self._topic_prefix(doc_topic) + chunk_text.strip()
            chunks.append(self._make_chunk(chunk_text, doc))
            if end >= len(text):
                break
            next_start = max(start + 1, end - self.overlap)
            # overlap 起点向后移到词边界，避免下一块从单词中间开始。
            overlap_window = text[next_start:end]
            boundary = re.search(r'(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z0-9])', overlap_window)
            if boundary:
                start = next_start + boundary.end()
            else:
                word_boundary = re.search(r'(?<=\s)\S', overlap_window)
                start = next_start + (word_boundary.start() if word_boundary else 0)
        return chunks

    # ─── 语义相似度合并 ───

    def _merge_small_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        语义相似度感知合并

        规则：
        1. 只合并长度 < merge_threshold 的 chunk
        2. 合并前计算 Embedding 语义相似度
        3. 只有相似度 > merge_similarity_threshold 才合并
        4. 合并后重新计算 chunk_id（修复碰撞 bug）
        5. 合并后的长度不超过 chunk_size * 1.5
        """
        if not chunks:
            return chunks

        merged = [chunks[0]]
        for chunk in chunks[1:]:
            last = merged[-1]
            last_len = len(last.content)
            chunk_len = len(chunk.content)

            # 只在至少一侧为小块时考虑合并，避免孤立的页尾/条款碎片。
            if last_len >= self.merge_threshold and chunk_len >= self.merge_threshold:
                merged.append(chunk)
                continue

            # 检查长度限制
            combined_len = last_len + chunk_len + 4  # +4 为 \n\n
            if combined_len > self.chunk_size:
                merged.append(chunk)
                continue

            # 语义相似度检查
            if len(last.content) > 10 and len(chunk.content) > 10:
                similarity = _compute_similarity(last.content, chunk.content)
                if similarity < self.merge_similarity_threshold:
                    # 语义不相似，不合并
                    merged.append(chunk)
                    continue
                logger.debug(
                    f"合并：相似度={similarity:.2f} (阈值={self.merge_similarity_threshold}), "
                    f"合并两个小块"
                )

            # 合并（chunk_id 已在 _make_chunk 中正确生成，合并后重新计算）
            merged[-1] = Chunk(
                content=last.content + '\n\n' + chunk.content,
                metadata=last.metadata.copy(),
                chunk_id="",  # 稍后重新计算
            )

        # 重新计算合并后 chunk 的 chunk_id（修复合并导致的碰撞 bug）
        for chunk in merged:
            if not chunk.chunk_id:
                # 合并后的 chunk 需要基于新内容重新生成 ID
                source = chunk.metadata.get("source", "")
                page = chunk.metadata.get("page", 0)
                unique_key = f"{source}:{page}:{chunk.content}"
                new_id = hashlib.sha256(unique_key.encode()).hexdigest()[:16]
                chunk.chunk_id = new_id
                chunk.metadata["chunk_id"] = new_id

        return merged

    # ─── Chunk 创建（含完整 metadata） ───

    def _make_chunk(self, content: str, doc: Document) -> Chunk:
        """创建 Chunk 对象（带完整 metadata）"""
        unique_key = f"{doc.metadata.get('source', '')}:{doc.metadata.get('page', 0)}:{content}"
        chunk_id = hashlib.sha256(unique_key.encode()).hexdigest()[:16]

        return Chunk(
            content=content.strip(),
            metadata={
                **doc.metadata,
                "chunk_id": chunk_id,
            },
            chunk_id=chunk_id,
        )


# ===================================================================
# 兼容旧接口（_chunk_document 旧实现，保留供回退）
# ===================================================================

class _LegacyChunker(RuleChunker):
    """
    旧版 RuleChunker 实现（保留供兼容性使用）

    旧版行为：
    1. 按段落分割（\\n\\n）
    2. 合并小段落直到达到 chunk_size
    3. 超长段落按字符数截断
    4. 相邻块间有 overlap 字符重叠
    5. 合并过小的连续分块（无语义检查）
    """

    def _chunk_document(self, doc: Document) -> List[Chunk]:
        """旧版单文档分块"""
        paragraphs = self._split_paragraphs(doc.content)
        chunks = []
        buffer = []
        buffer_len = 0

        for para in paragraphs:
            para_len = len(para)

            if para_len >= self.chunk_size:
                if buffer:
                    chunks.append(self._make_chunk('\n\n'.join(buffer), doc))
                    buffer = []
                    buffer_len = 0
                chunks.extend(self._split_long_paragraph(para, doc))
                continue

            if buffer_len + para_len > self.chunk_size and buffer:
                chunks.append(self._make_chunk('\n\n'.join(buffer), doc))
                buffer = self._get_overlap_tail(buffer, doc)
                buffer_len = sum(len(p) for p in buffer)

            buffer.append(para)
            buffer_len += para_len

        if buffer:
            chunks.append(self._make_chunk('\n\n'.join(buffer), doc))

        chunks = self._merge_small_chunks_legacy(chunks)

        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        parts = re.split(r'\n\s*\n|(?=^#{1,3}\s)', text.strip(), flags=re.MULTILINE)
        return [p.strip() for p in parts if p.strip()]

    def _split_long_paragraph(self, text: str, doc: Document) -> List[Chunk]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]
            chunks.append(self._make_chunk(chunk_text, doc))
            start = end - self.overlap
        return chunks

    def _get_overlap_tail(self, paragraphs: List[str], doc: Document) -> List[str]:
        tail = []
        tail_len = 0
        for para in reversed(paragraphs):
            para_len = len(para)
            if tail_len + para_len > self.overlap and tail:
                break
            tail.insert(0, para)
            tail_len += para_len
        return tail

    def _merge_small_chunks_legacy(self, chunks: List[Chunk]) -> List[Chunk]:
        """旧版合并（无语义检查）"""
        if not chunks:
            return chunks

        merged = [chunks[0]]
        for chunk in chunks[1:]:
            last = merged[-1]
            if (len(last.content) < self.merge_threshold and
                    len(last.content) + len(chunk.content) < self.chunk_size * 1.5):
                merged[-1] = Chunk(
                    content=last.content + '\n\n' + chunk.content,
                    metadata=last.metadata,
                    chunk_id=last.chunk_id,
                )
            else:
                merged.append(chunk)
        return merged
