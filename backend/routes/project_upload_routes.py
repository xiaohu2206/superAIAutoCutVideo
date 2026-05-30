
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目文件上传、媒体播放与资源删除相关API路由
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio
import uuid
import subprocess
from threading import RLock
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body, Request, Query
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel

from .project_routes import (
    now_ts,
    to_web_path,
    resolve_abs_path,
    remove_path,
    _stream_file_range,
    compress_srt,
    MergeTaskStatus,
    DeleteVideoRequest,
    PrepareVideoRequest,
    UpdateVideoOrderRequest,
    _enrich_project_status,
)
from modules.projects_store import projects_store
from modules.ffmpeg_utils import resolve_ffmpeg_bin


def _content_disposition(disposition: str, filename: str) -> str:
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "output.mp4"
    ascii_fallback = ascii_fallback.replace("\\", "_").replace('"', "_")
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


router = APIRouter(prefix="/api/projects", tags=["项目管理"])

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}
FASTSTART_EXTS = {".mp4", ".mov"}
VIDEO_UPLOAD_SESSIONS: Dict[str, Dict[str, Any]] = {}
VIDEO_UPLOAD_SESSIONS_LOCK = RLock()


def _register_uploaded_video(project_id: str, out_path: Path, file_name: str, size: int) -> Dict[str, Any]:
    web_path = to_web_path(out_path)
    projects_store.append_video_path(project_id, web_path, file_name)
    upload_time = now_ts()
    return {
        "message": "视频上传成功",
        "data": {
            "file_path": web_path,
            "file_name": file_name,
            "file_size": size,
            "upload_time": upload_time,
        },
        "timestamp": upload_time,
    }


def _build_video_upload_path(project_id: str, suffix: str) -> Path:
    from .project_routes import uploads_dir as _uploads_dir
    up_dir = _uploads_dir() / "videos"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique = uuid.uuid4().hex[:8]
    out_name = f"{project_id}_video_{ts}_{unique}{suffix}"
    return up_dir / out_name


async def remux_faststart(path: Path) -> bool:
    try:
        ffmpeg_bin = resolve_ffmpeg_bin()
        if not ffmpeg_bin:
            return False
        WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else None
        if path.suffix.lower() not in FASTSTART_EXTS:
            return False
        tmp_path = path.with_name(f".{path.stem}.faststart{path.suffix}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(path),
            "-c", "copy",
            "-movflags", "+faststart",
            "-y",
            str(tmp_path),
        ]
        kwargs = {"creationflags": WIN_NO_WINDOW} if os.name == "nt" else {}
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs
        )
        await process.communicate()
        if process.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
            os.replace(str(tmp_path), str(path))
            return True
    except Exception:
        pass
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass
    return False


class FinalizeVideoUploadRequest(BaseModel):
    upload_id: str
    file_name: str
    file_size: int
    total_chunks: int


@router.get("/{project_id}/video/stream")
async def stream_project_video(project_id: str, request: Request):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    video_path = p.video_path
    if not video_path:
        raise HTTPException(status_code=404, detail="视频未上传")

    abs_path = resolve_abs_path(video_path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")

    return _stream_file_range(abs_path, request)


@router.get("/{project_id}/merged-video")
async def stream_project_merged_video(project_id: str, request: Request):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    video_path = p.merged_video_path
    if not video_path:
        raise HTTPException(status_code=404, detail="合并视频不存在")

    abs_path = resolve_abs_path(video_path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")

    return _stream_file_range(abs_path, request)


@router.post("/{project_id}/upload/video")
async def upload_video(project_id: str, file: UploadFile = File(...)):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="文件格式不支持")

    out_path = _build_video_upload_path(project_id, suffix)

    size = 0
    try:
        with open(out_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                buffer.write(chunk)
    finally:
        await file.close()

    return _register_uploaded_video(project_id, out_path, file.filename, size)


@router.post("/{project_id}/upload/video/chunk")
async def upload_video_chunk(
    project_id: str,
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    file_name: str = Form(...),
    file_size: int = Form(...),
    chunk: UploadFile = File(...),
):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    if total_chunks <= 0:
        raise HTTPException(status_code=400, detail="total_chunks 无效")
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="chunk_index 无效")

    suffix = Path(file_name or chunk.filename or "").suffix.lower()
    if suffix not in VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="文件格式不支持")

    from .project_routes import uploads_dir as _uploads_dir
    tmp_dir = _uploads_dir() / "videos" / "chunks" / project_id / upload_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = tmp_dir / f"{chunk_index:06d}.part"

    chunk_size = 0
    try:
        with open(chunk_path, "wb") as buffer:
            while True:
                piece = await chunk.read(1024 * 1024)
                if not piece:
                    break
                chunk_size += len(piece)
                buffer.write(piece)
    finally:
        await chunk.close()

    with VIDEO_UPLOAD_SESSIONS_LOCK:
        session = VIDEO_UPLOAD_SESSIONS.get(upload_id)
        if not session:
            session = {
                "project_id": project_id,
                "upload_id": upload_id,
                "file_name": file_name,
                "file_size": file_size,
                "total_chunks": total_chunks,
                "suffix": suffix,
            }
            VIDEO_UPLOAD_SESSIONS[upload_id] = session
        elif session.get("project_id") != project_id:
            raise HTTPException(status_code=400, detail="upload_id 与项目不匹配")

    return {
        "message": "分片上传成功",
        "data": {
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "chunk_size": chunk_size,
            "uploaded_chunks": len(list(tmp_dir.glob("*.part"))),
            "total_chunks": total_chunks,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/upload/video/complete")
async def complete_video_upload(project_id: str, req: FinalizeVideoUploadRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    with VIDEO_UPLOAD_SESSIONS_LOCK:
        session = VIDEO_UPLOAD_SESSIONS.get(req.upload_id)

    if not session:
        raise HTTPException(status_code=404, detail="上传会话不存在")
    if session.get("project_id") != project_id:
        raise HTTPException(status_code=400, detail="upload_id 与项目不匹配")

    total_chunks = int(session.get("total_chunks") or req.total_chunks)
    file_name = str(session.get("file_name") or req.file_name)
    file_size = int(session.get("file_size") or req.file_size or 0)
    suffix = str(session.get("suffix") or Path(file_name).suffix.lower())
    if suffix not in VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="文件格式不支持")

    from .project_routes import uploads_dir as _uploads_dir
    tmp_dir = _uploads_dir() / "videos" / "chunks" / project_id / req.upload_id
    if not tmp_dir.exists():
        raise HTTPException(status_code=404, detail="上传分片不存在")

    missing_chunks = [index for index in range(total_chunks) if not (tmp_dir / f"{index:06d}.part").exists()]
    if missing_chunks:
        raise HTTPException(status_code=400, detail=f"缺少分片: {missing_chunks[0]}")

    out_path = _build_video_upload_path(project_id, suffix)
    merged_size = 0
    try:
        with open(out_path, "wb") as output:
            for index in range(total_chunks):
                chunk_path = tmp_dir / f"{index:06d}.part"
                with open(chunk_path, "rb") as chunk_file:
                    shutil.copyfileobj(chunk_file, output)
                merged_size += chunk_path.stat().st_size
    except Exception as e:
        try:
            if out_path.exists():
                out_path.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"合并上传分片失败: {str(e)}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        with VIDEO_UPLOAD_SESSIONS_LOCK:
            VIDEO_UPLOAD_SESSIONS.pop(req.upload_id, None)

    actual_size = merged_size or file_size
    return _register_uploaded_video(project_id, out_path, file_name, actual_size)


@router.post("/{project_id}/video/prepare")
async def prepare_video_preview(project_id: str, req: PrepareVideoRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    file_path = (req.file_path or "").strip()
    if not file_path:
        raise HTTPException(status_code=400, detail="缺少 file_path")

    abs_path = resolve_abs_path(file_path)
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="视频文件不存在")

    prepared = await remux_faststart(abs_path)
    return {
        "message": "视频预处理完成",
        "data": {
            "file_path": to_web_path(abs_path),
            "prepared": prepared,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/upload/subtitle")
async def upload_subtitle(project_id: str, file: UploadFile = File(...)):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".srt"}:
        raise HTTPException(status_code=400, detail="仅支持上传SRT文件")

    from .project_routes import uploads_dir as _uploads_dir
    up_dir = _uploads_dir() / "subtitles"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique = uuid.uuid4().hex[:8]
    out_name = f"{project_id}_subtitle_{ts}_{unique}{suffix}"
    out_path = up_dir / out_name
    up_dir.mkdir(parents=True, exist_ok=True)

    size = 0
    try:
        buf = bytearray()
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            buf.extend(chunk)
        content = buf.decode("utf-8", errors="ignore")
        compressed = compress_srt(content)
        with out_path.open("w", encoding="utf-8") as f:
            f.write(compressed)
        size = len(compressed.encode("utf-8"))
    finally:
        await file.close()

    web_path = to_web_path(out_path)
    projects_store.update_project(project_id, {
        "subtitle_path": web_path,
        "subtitle_source": "user",
        "subtitle_status": "ready",
        "subtitle_updated_by_user": False,
        "subtitle_updated_at": now_ts(),
        "subtitle_format": "compressed_srt_v1",
    })

    return {
        "message": "字幕上传成功",
        "data": {
            "file_path": web_path,
            "file_name": file.filename,
            "file_size": size,
            "upload_time": now_ts(),
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/delete/video")
async def delete_video_file(project_id: str, request: Request, req: Optional[DeleteVideoRequest] = Body(None), file_path_form: Optional[str] = Form(None)):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    removed = False
    removed_path = None
    target_path = None
    if req and req.file_path:
        target_path = req.file_path.strip()
    else:
        json_candidate = None
        try:
            body_json = await request.json()
            if isinstance(body_json, dict):
                json_candidate = (body_json.get("file_path") or "").strip() or None
        except Exception:
            pass

        form_candidate = None
        try:
            form = await request.form()
            form_candidate = (form.get("file_path") or form.get("file_path_form") or "").strip() or None
        except Exception:
            pass

        if json_candidate:
            target_path = json_candidate
        elif file_path_form:
            target_path = (file_path_form or "").strip() or None
        elif form_candidate:
            target_path = form_candidate
        else:
            target_path = (p.video_path or "").strip() if p.video_path else None

    if target_path:
        path_str = target_path
        abs_path = resolve_abs_path(path_str)
        try:
            if abs_path.exists() and abs_path.is_file():
                removed_path = str(abs_path)
                abs_path.unlink()
                removed = True
        except Exception:
            pass

    if target_path:
        p2 = projects_store.remove_video_path(project_id, target_path)
        try:
            abs_path2 = resolve_abs_path(target_path)
            web_norm = to_web_path(abs_path2)
            if web_norm != target_path:
                p2 = projects_store.remove_video_path(project_id, web_norm) or p2
        except Exception:
            pass
    else:
        p2 = projects_store.clear_video_path(project_id)
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    return {
        "message": "视频删除成功",
        "data": {
            "removed": removed,
            "removed_path": to_web_path(Path(removed_path)) if removed_path else None,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/videos/order")
async def update_video_order(project_id: str, req: UpdateVideoOrderRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    existing = list(p.video_paths or [])
    new_order = list(req.ordered_paths or [])
    if len(existing) != len(new_order) or set(existing) != set(new_order):
        raise HTTPException(status_code=400, detail="排序列表与现有视频不匹配")
    try:
        updated = projects_store.update_project(project_id, {"video_paths": new_order})
        if not updated:
            raise HTTPException(status_code=500, detail="更新排序失败")
        return {
            "message": "更新排序成功",
            "data": _enrich_project_status(updated.model_dump(), project_id),
            "timestamp": now_ts(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"更新数据格式无效: {e}")


@router.post("/{project_id}/delete/subtitle")
async def delete_subtitle_file(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    removed = False
    removed_path = None
    if p.subtitle_path:
        path_str = p.subtitle_path.strip()
        abs_path = resolve_abs_path(path_str)
        try:
            if abs_path.exists() and abs_path.is_file():
                removed_path = str(abs_path)
                abs_path.unlink()
                removed = True
        except Exception:
            pass

    p2 = projects_store.clear_subtitle_path(project_id)
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    return {
        "message": "字幕删除成功",
        "data": {
            "removed": removed,
            "removed_path": to_web_path(Path(removed_path)) if removed_path else None,
        },
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/output-video")
async def get_output_video(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.output_video_path:
        raise HTTPException(status_code=404, detail="尚未生成输出视频")

    path_str = p.output_video_path.strip()
    abs_path = resolve_abs_path(path_str)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="输出视频文件不存在")

    filename = abs_path.name
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Disposition": _content_disposition("inline", filename),
    }
    return FileResponse(
        path=str(abs_path),
        filename=filename,
        media_type="video/mp4",
        headers=headers,
    )


@router.get("/{project_id}/output-video/download")
async def download_output_video_attachment(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.output_video_path:
        raise HTTPException(status_code=404, detail="尚未生成输出视频")

    path_str = p.output_video_path.strip()
    abs_path = resolve_abs_path(path_str)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="输出视频文件不存在")

    filename = abs_path.name
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Disposition": _content_disposition("attachment", filename),
    }
    return FileResponse(
        path=str(abs_path),
        filename=filename,
        media_type="video/mp4",
        headers=headers,
    )



