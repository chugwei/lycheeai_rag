"""
荔枝知识库文件管理 API

提供知识库文件的 CRUD、批量下载、预览等功能。
"""
import os
import zipfile
import io
from datetime import datetime
from pathlib import Path
from typing import List
from urllib.parse import quote, unquote

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from loguru import logger

from config.settings import get_config

router = APIRouter(prefix="/api/knowledge", tags=["荔枝知识库"])


def _get_knowledge_dir() -> Path:
    """获取知识库文件根目录（默认 data/raw）"""
    project_root = Path(__file__).parent.parent
    default_dir = project_root / "data" / "raw"
    custom_dir = get_config("knowledge_base.dir", None)
    if custom_dir:
        return Path(custom_dir)
    return default_dir


def _safe_filename(name: str) -> str:
    """防止路径遍历"""
    return os.path.basename(name)


def _file_info(path: Path) -> dict:
    stat = path.stat()
    return {
        "id": quote(path.name, safe=""),
        "name": path.name,
        "size": stat.st_size,
        "upload_time": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "update_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


class BatchFilesRequest(BaseModel):
    filenames: List[str] = Field(..., description="要操作的文件名列表")


class FileUploadResponse(BaseModel):
    id: str
    name: str
    size: int
    upload_time: str
    update_time: str


@router.get("/files", response_model=List[FileUploadResponse])
async def list_knowledge_files(search: str = Query("", description="按文件名搜索")):
    """列出知识库文件，支持按文件名搜索"""
    kb_dir = _get_knowledge_dir()
    if not kb_dir.exists():
        return []

    files = []
    for path in sorted(kb_dir.iterdir()):
        if path.is_file():
            if search and search.lower() not in path.name.lower():
                continue
            files.append(_file_info(path))
    return files


@router.post("/upload", response_model=FileUploadResponse)
async def upload_knowledge_file(file: UploadFile = File(...)):
    """上传知识库文件"""
    kb_dir = _get_knowledge_dir()
    kb_dir.mkdir(parents=True, exist_ok=True)

    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    safe_name = _safe_filename(file.filename)
    target_path = kb_dir / safe_name

    # 如果文件已存在，覆盖
    content = await file.read()
    target_path.write_bytes(content)

    logger.info(f"知识库文件上传成功: {target_path}")
    return _file_info(target_path)


@router.delete("/files/{filename}")
async def delete_knowledge_file(filename: str):
    """删除单个知识库文件"""
    kb_dir = _get_knowledge_dir()
    safe_name = _safe_filename(unquote(filename))
    target_path = kb_dir / safe_name

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(404, "文件不存在")

    target_path.unlink()
    logger.info(f"知识库文件已删除: {target_path}")
    return {"status": "deleted", "filename": safe_name}


@router.post("/files/batch-delete")
async def batch_delete_knowledge_files(request: BatchFilesRequest):
    """批量删除知识库文件"""
    kb_dir = _get_knowledge_dir()
    deleted = []
    failed = []

    for filename in request.filenames:
        safe_name = _safe_filename(unquote(filename))
        target_path = kb_dir / safe_name
        if target_path.exists() and target_path.is_file():
            target_path.unlink()
            deleted.append(safe_name)
        else:
            failed.append(safe_name)

    logger.info(f"批量删除知识库文件: 成功 {len(deleted)} 个，失败 {len(failed)} 个")
    return {"status": "ok", "deleted": deleted, "failed": failed}


@router.get("/files/{filename}/download")
async def download_knowledge_file(filename: str):
    """下载单个知识库文件"""
    kb_dir = _get_knowledge_dir()
    safe_name = _safe_filename(unquote(filename))
    target_path = kb_dir / safe_name

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(404, "文件不存在")

    return FileResponse(
        path=str(target_path),
        filename=safe_name,
        media_type="application/octet-stream"
    )


@router.post("/files/batch-download")
async def batch_download_knowledge_files(request: BatchFilesRequest):
    """批量下载知识库文件（打包为 zip）"""
    kb_dir = _get_knowledge_dir()
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in request.filenames:
            safe_name = _safe_filename(unquote(filename))
            target_path = kb_dir / safe_name
            if target_path.exists() and target_path.is_file():
                zf.write(target_path, arcname=safe_name)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=lychee-knowledge-files.zip"}
    )


@router.get("/files/{filename}/content")
async def get_knowledge_file_content(filename: str):
    """获取知识库文件文本内容（用于预览）"""
    kb_dir = _get_knowledge_dir()
    safe_name = _safe_filename(unquote(filename))
    target_path = kb_dir / safe_name

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(404, "文件不存在")

    try:
        text = target_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "该文件不是文本文件，无法预览")

    return JSONResponse({
        "filename": safe_name,
        "content": text
    })
