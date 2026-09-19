"""
文档加载器 - 支持 PDF, Markdown, TXT, DOCX, XLSX

支持的命名格式：
    hash_领域_英文标题.pdf（自动提取领域标签）

文件类型：
    - PDF：PyMuPDF 提取文本，坐标感知页眉页脚过滤，可选 OCR
    - Markdown/Text：直接读取
    - DOCX：python-docx 读取
    - XLSX：openpyxl 读取，每 sheet 一个 Document
"""
import re
from pathlib import Path
from typing import List, Optional, Callable

from loguru import logger

from .models import Document


def _extract_domain(filename: str) -> str:
    """从文件名提取领域标签"""
    # 格式: hash_领域_英文标题.pdf
    match = re.match(r'[a-f0-9]+_(.+?)_', filename)
    if match:
        domain_map = {
            '分子生物学': 'molecular_biology',
            '分子育种': 'molecular_breeding',
            '基因组学': 'genomics',
            '生理生态': 'physiology_ecology',
            '栽培技术': 'cultivation',
            '病虫害防治': 'disease_pest',
            '采后保鲜': 'postharvest',
            '裂果机理': 'fruit_cracking',
            '营养药理': 'nutrition_pharmacology',
            '产业经济': 'industry_economics',
        }
        cn_domain = match.group(1)
        return domain_map.get(cn_domain, cn_domain)
    return 'general'


class DocumentLoader:
    """文档加载器"""

    def __init__(self, raw_dir: str = None):
        self.raw_dir = Path(raw_dir) if raw_dir else Path(__file__).parent.parent / "data" / "raw"
        self.supported_extensions = {'.pdf', '.md', '.txt', '.docx', '.xlsx'}
        self.load_report = {"candidate_files": 0, "loaded_files": 0, "empty_files": [], "failed_files": []}

    # ─── 目录加载 ───

    def load_directory(self, directory: str = None) -> List[Document]:
        """递归加载目录下所有支持的文件"""
        target_dir = Path(directory) if directory else self.raw_dir
        if not target_dir.exists():
            raise FileNotFoundError(f"目录不存在: {target_dir}")

        docs = []
        self.load_report = {"candidate_files": 0, "loaded_files": 0, "empty_files": [], "failed_files": []}

        # 递归遍历所有子目录
        for fpath in sorted(target_dir.rglob('*')):
            if fpath.is_dir() or fpath.name.startswith('.'):
                continue
            if fpath.suffix.lower() not in self.supported_extensions:
                continue

            self.load_report["candidate_files"] += 1
            try:
                file_docs = self.load_file(str(fpath))
                docs.extend(file_docs)
                if file_docs:
                    self.load_report["loaded_files"] += 1
                    logger.info(f"  ✓ {fpath.name} → {len(file_docs)} 页")
                else:
                    self.load_report["empty_files"].append(fpath.name)
                    logger.warning(f"  ⚠ {fpath.name} → 未提取到可索引文本")
            except Exception as e:
                self.load_report["failed_files"].append({"source": fpath.name, "error": str(e)})
                logger.warning(f"  ✗ {fpath.name}: {e}")

        logger.info(f"文档加载完成: {len(docs)} 个文档片段, 来自 {target_dir}")
        return docs

    # ─── 单文件加载 ───

    def load_file(self, file_path: str) -> List[Document]:
        """加载单个文件，返回 Document 列表"""
        fpath = Path(file_path)
        domain = _extract_domain(fpath.name)
        source = fpath.name

        suffix = fpath.suffix.lower()
        if suffix == '.pdf':
            return self._load_pdf(fpath, source, domain)
        elif suffix in ('.md', '.txt'):
            return self._load_text(fpath, source, domain)
        elif suffix == '.docx':
            return self._load_docx(fpath, source, domain)
        elif suffix == '.xlsx':
            return self._load_xlsx(fpath, source, domain)
        else:
            raise ValueError(f"不支持的文件类型: {fpath.suffix}")

    # ─── PDF ───

    def _load_pdf(self, fpath: Path, source: str, domain: str) -> List[Document]:
        """用 PyMuPDF 提取 PDF 文本（坐标感知页眉页脚过滤）"""
        import fitz
        docs = []
        try:
            pdf = fitz.open(str(fpath))
        except Exception as e:
            raise RuntimeError(f"无法打开 PDF: {e}")

        header_threshold = 80  # 顶部过滤 y 坐标阈值 (px)
        footer_threshold = None  # 将在第一页确定

        for page_num in range(len(pdf)):
            page = pdf[page_num]
            text = page.get_text().strip()

            # 扫描页检测
            if not text or len(text) < 50:
                # 尝试 OCR
                ocr_text = self._ocr_page(page, source, page_num)
                if ocr_text:
                    text = ocr_text
                else:
                    continue

            # 用 text blocks 做坐标感知过滤
            try:
                blocks = page.get_text("blocks")
                page_height = page.rect.height
                # 动态计算底部阈值（页脚区域）
                if footer_threshold is None:
                    footer_threshold = page_height - header_threshold

                filtered_blocks = []
                for block in blocks:
                    # blocks: (x0, y0, x1, y1, text, block_no, block_type)
                    y0, y1 = block[1], block[3]
                    block_text = block[4].strip()

                    # 过滤页眉区域（顶部）和页脚区域（底部）
                    if y0 < header_threshold:
                        continue
                    if y1 > footer_threshold:
                        continue

                    # 过滤纯页码行
                    if block_text.isdigit():
                        continue

                    filtered_blocks.append(block_text)

                text = '\n'.join(filtered_blocks).strip()
            except Exception:
                # 坐标方法失败，回退到简单过滤
                lines = text.split('\n')
                filtered_lines = []
                for line in lines:
                    stripped = line.strip()
                    if re.match(r'^\d+$', stripped):
                        continue
                    filtered_lines.append(stripped)
                text = '\n'.join(filtered_lines).strip()

            if text:
                # 尝试提取 PDF 中的结构化表格
                metadata = {
                    "source": source,
                    "page": page_num + 1,
                    "domain": domain,
                    "file_path": str(fpath),
                }
                try:
                    pdf_tables = page.find_tables()
                    if pdf_tables and len(pdf_tables.tables) > 0:
                        table_sections = []
                        for ti, tbl in enumerate(pdf_tables.tables):
                            data = tbl.extract()
                            if data and len(data) >= 2:
                                # 转为管道表格式："| col1 | col2 | ... |"
                                md_rows = []
                                for row in data:
                                    md_rows.append("| " + " | ".join(str(c) if c else "" for c in row) + " |")
                                # 加分隔行（第二行加 ---）
                                if len(md_rows) >= 2:
                                    sep = "| " + " | ".join("---" for _ in data[0]) + " |"
                                    md_rows.insert(1, sep)
                                table_sections.append("\n".join(md_rows))
                        if table_sections:
                            metadata["has_table"] = True
                            metadata["table_type"] = "pdf_table"
                            # 表格内容追加到文本末尾（保留结构）
                            text += "\n\n" + "\n\n".join(table_sections)
                except Exception:
                    # find_tables() 可能失败，不影响主流程
                    pass

                docs.append(Document(
                    content=text,
                    metadata=metadata,
                ))

        pdf.close()
        return docs

    def _ocr_page(self, page, source: str, page_num: int) -> Optional[str]:
        """
        对扫描页尝试 OCR

        需要安装 rapidocr-onnxruntime:
            pip install rapidocr-onnxruntime

        返回识别文本，或 None（OCR 不可用/失败）
        """
        try:
            # 尝试导入 OCR 引擎
            from rapidocr_onnxruntime import RapidOCR
            # 缓存引擎实例
            if not hasattr(self, '_ocr_engine'):
                self._ocr_engine = RapidOCR()
        except ImportError:
            logger.debug(f"  OCR 引擎未安装，跳过扫描页: {source} p{page_num + 1}")
            return None

        try:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            result, elapse = self._ocr_engine(img_bytes)
            if result is None:
                return None
            # result: [[(box, text, score), ...]]
            texts = [item[1] for item in result if item[1] and item[1].strip()]
            ocr_text = '\n'.join(texts) if texts else None
            if ocr_text:
                logger.info(f"  📷 OCR 识别: {source} p{page_num + 1} → {len(texts)} 个文本块")
            return ocr_text
        except Exception as e:
            logger.debug(f"  OCR 识别失败: {source} p{page_num + 1}: {e}")
            return None

    # ─── Docx ───

    def _load_docx(self, fpath: Path, source: str, domain: str) -> List[Document]:
        """用 python-docx 加载 DOCX 文件"""
        try:
            from docx import Document as DocxDocument
        except ImportError:
            raise RuntimeError("需要安装 python-docx: pip install python-docx")

        doc = DocxDocument(str(fpath))

        # 按段落提取文本
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        if not paragraphs:
            return []

        full_text = '\n'.join(paragraphs)

        # 如果内容较短，作为一个 Document 返回
        if len(full_text) < 3000:
            return [Document(
                content=full_text,
                metadata={
                    "source": source,
                    "page": 1,
                    "domain": domain,
                    "file_path": str(fpath),
                }
            )]

        # 长文档按每 ~3000 字分割
        docs = []
        chunk_size = 3000
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i:i + chunk_size]
            docs.append(Document(
                content=chunk,
                metadata={
                    "source": source,
                    "page": i // chunk_size + 1,
                    "domain": domain,
                    "file_path": str(fpath),
                }
            ))
        return docs

    # ─── Xlsx ───

    def _load_xlsx(self, fpath: Path, source: str, domain: str) -> List[Document]:
        """用 openpyxl 加载 XLSX 文件，每 sheet 一个 Document"""
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("需要安装 openpyxl: pip install openpyxl")

        wb = openpyxl.load_workbook(str(fpath), read_only=True, data_only=True)
        docs = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                # 过滤全空行
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    rows.append(' | '.join(cells))

            if rows:
                content = f"## Sheet: {sheet_name}\n" + '\n'.join(rows)
                docs.append(Document(
                    content=content,
                    metadata={
                        "source": source,
                        "page": len(docs) + 1,
                        "domain": domain,
                        "file_path": str(fpath),
                        "sheet": sheet_name,
                        "has_table": True,
                        "table_type": "xlsx",
                    }
                ))

        wb.close()

        if not docs:
            logger.warning(f"XLSX 文件无有效数据: {source}")
        return docs

    # ─── 文本文件 ───

    def _load_text(self, fpath: Path, source: str, domain: str) -> List[Document]:
        """加载文本文件，检测管道表"""
        text = fpath.read_text(encoding="utf-8").strip()
        if not text:
            return []

        metadata = {
            "source": source,
            "page": 0,
            "domain": domain,
            "file_path": str(fpath),
        }

        # 检测 MD/TXT 中的管道表（连续 3 行以上 | 开头 | 结尾）
        lines = text.split('\n')
        pipe_count = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') and stripped.endswith('|'):
                pipe_count += 1
                if pipe_count >= 3:
                    metadata["has_table"] = True
                    metadata["table_type"] = "markdown_pipe"
                    break
            else:
                pipe_count = 0  # 重置计数器

        return [Document(
            content=text,
            metadata=metadata,
        )]