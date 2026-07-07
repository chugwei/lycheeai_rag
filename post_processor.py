"""
后处理模块 - 引用提取 + 思考链清理

从 LLM 响应中提取 [N] 引用标记，并清理思考过程/推理链。
"""
import re
from typing import List, Tuple
from loguru import logger


def clean_response(text: str) -> str:
    """
    清理 LLM 响应，去除思考过程/推理链，仅保留最终答案

    4 层防御策略:
    1. 查找最后一个中文答案标记（【当前状况总结】【决策建议】等）
    2. 检测英文思考链，提取最后中文段落
    3. 检测中文思考链，从后往前找答案段落
    4. 返回原文
    """
    if not text:
        return text

    # ─── 第1层：rfind 最后一个答案标记 ───
    answer_markers = [
        '【当前状况总结】',
        '【决策建议】',
        '【综合答案】',
        '【回答】',
        '核心结论',
    ]

    last_pos = len(text)
    for marker in answer_markers:
        idx = text.rfind(marker)
        if idx != -1 and idx < last_pos:
            last_pos = idx

    if last_pos < len(text):
        result = text[last_pos:]
        result = re.sub(r'^[\s\*\#\:\-\n]+', '', result)
        if result.strip():
            return result.strip()

    # ─── 第2层：检测英文思考链 ───
    eng_patterns = [
        r'Thinking\s*Process',
        r'1\.\s*\*{0,2}(Analyze|Scan|Review|Identify|Understand|Break)',
        r'Step\s+\d+',
        r'Let\s+me\s+(analyze|think|break|consider)',
        r"Here'?s\s+(my|the|how)",
    ]

    is_thinking = any(re.search(p, text, re.IGNORECASE) for p in eng_patterns)

    if is_thinking:
        paragraphs = re.split(r'\n\s*\n', text)
        chinese_paras = []
        for p in paragraphs:
            cn_chars = len(re.findall(r'[\u4e00-\u9fff]', p))
            total = len(p.strip())
            if cn_chars > 20 and total > 0 and cn_chars / total > 0.4:
                chinese_paras.append(p.strip())

        if len(chinese_paras) >= 2:
            return '\n\n'.join(chinese_paras[-2:])
        elif chinese_paras:
            return chinese_paras[-1]

    # ─── 第3层：检测中文思考链 ───
    cn_patterns = [
        r'1\.\s*\*{0,2}拆解',
        r'1\.\s*\*{0,2}识别用户',
        r'1\.\s*\*{0,2}分析请求',
        r'1\.\s*\*{0,2}理解问题',
        r'1\.\s*\*{0,2}扫描',
        r'2\.\s*\*{0,2}扫描',
        r'2\.\s*\*{0,2}分析',
        r'3\.\s*\*{0,2}分析',
    ]

    is_cn_thinking = any(re.search(p, text, re.IGNORECASE) for p in cn_patterns)

    if is_cn_thinking:
        lines = text.split('\n')
        answer_start = -1
        thinking_header_re = re.compile(
            r'^\s*\d+\.\s*\*{0,2}.*\*{0,2}[:：]', re.IGNORECASE
        )

        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if not line:
                continue
            if thinking_header_re.match(line):
                break
            cn_count = len(re.findall(r'[\u4e00-\u9fff]', line))
            if cn_count >= 15:
                answer_start = i

        if answer_start > 0:
            result = '\n'.join(lines[answer_start:])
            if result.strip():
                return result.strip()

    # ─── 第4层：返回原文 ───
    return text


def extract_citations(
    llm_response: str, docs: List[dict]
) -> Tuple[str, List[dict]]:
    """
    从 LLM 响应中提取 [N] 引用标记，构建来源列表

    Args:
        llm_response: LLM 生成的回答文本
        docs: 检索到的文档列表

    Returns:
        (answer, sources) - 清理后的回答和来源列表
    """
    answer = clean_response(llm_response)
    if not answer:
        answer = "无法生成回答。"
    if len(answer) < 10:
        answer = "无法生成有效回答，请检查 LLM 配置。"

    # 提取 [N] 引用标记
    source_refs = re.findall(r'\[(\d+)\]', answer)

    sources = []
    seen = set()

    if source_refs:
        for ref_num in source_refs:
            idx = int(ref_num) - 1
            if 0 <= idx < len(docs) and ref_num not in seen:
                seen.add(ref_num)
                doc = docs[idx]
                sources.append({
                    "ref_id": int(ref_num),
                    "source": doc.get("source", ""),
                    "chunk_id": doc.get("id", doc.get("chunk_id", "")),
                    "text_preview": doc.get("text", "")[:200],
                    "retrieval_paths": doc.get("retrieval_paths", []),
                    "rerank_score": doc.get("rerank_score", 0),
                })
    else:
        # 无引用标记时，返回所有检索文档作为来源
        for idx, doc in enumerate(docs):
            ref_num = str(idx + 1)
            if ref_num not in seen:
                seen.add(ref_num)
                sources.append({
                    "ref_id": idx + 1,
                    "source": doc.get("source", ""),
                    "chunk_id": doc.get("id", doc.get("chunk_id", "")),
                    "text_preview": doc.get("text", "")[:200],
                    "retrieval_paths": doc.get("retrieval_paths", []),
                    "rerank_score": doc.get("rerank_score", 0),
                })

    return answer, sources
