#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目管理核心路由模块
- 公共工具函数、Pydantic 模型、共享全局状态
- 项目 CRUD：列表、详情、创建、更新、删除
- 项目日志：查看、清空、流式订阅
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
import asyncio
import logging
import cv2
import mimetypes
from threading import RLock

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from modules.app_paths import uploads_dir as app_uploads_dir, to_uploads_web_path, resolve_uploads_path
from modules.auth.omni_project_license import require_valid_license_for_omni
from modules.projects_store import projects_store
from modules.narration_types import DEFAULT_NARRATION_TYPE, is_valid_narration_type, normalize_narration_type
from modules.runtime_log_store import runtime_log_store
from modules.task_progress_store import task_progress_store
from modules.subtitle_utils import format_ts_srt
from services.extract_scene_service import extract_scene_service
from services.omni_multimodal_pipeline_service import omni_multimodal_pipeline_service
from services.omni_copywriting_struct_embed_service import omni_copywriting_struct_embed_service
from services.omni_shot_match_service import omni_shot_match_service
from services.omni_global_path_search_service import omni_global_path_search_service
from services.omni_generate_script_service import omni_generate_script_service
from omni_full_narration_pipeline import omni_full_narration_pipeline_service
from services.jianying_draft_manager import JianyingDraftManager
from services.script_generation_service import normalize_script_length_selection
from services.asr.extract_subtitle_service import EXTRACT_SUBTITLE_SCOPE

router = APIRouter(prefix="/api/projects", tags=["项目管理"])
logger = logging.getLogger(__name__)


# ========================= 基础工具函数 =========================

def now_ts() -> str:
    return datetime.now().isoformat()


def project_root_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def uploads_dir() -> Path:
    return app_uploads_dir()


def safe_dir_name(name: str, fallback: str) -> str:
    invalid = '<>:"/\\|?*'
    safe = "".join("_" if ch in invalid else ch for ch in (name or "").strip())
    safe = safe.strip()
    if not safe:
        safe = f"project_{fallback}"
    safe = safe.replace(".", "_").strip()
    return safe


def to_web_path(p: Path) -> str:
    return to_uploads_web_path(p)


def resolve_abs_path(path_str: str) -> Path:
    return resolve_uploads_path(path_str)


def resolve_any_path(path_str: str) -> Path:
    s = (path_str or "").strip()
    if not s:
        return Path("")
    try:
        p = Path(s)
        if p.is_absolute():
            return p
    except Exception:
        pass
    return resolve_abs_path(s)


def _guess_video_media_type(path: Path) -> str:
    mt, _ = mimetypes.guess_type(str(path))
    if mt:
        return mt
    suffix = path.suffix.lower()
    if suffix in {".mp4", ".m4v"}:
        return "video/mp4"
    if suffix in {".webm"}:
        return "video/webm"
    if suffix in {".mov"}:
        return "video/quicktime"
    if suffix in {".ogg", ".ogv"}:
        return "video/ogg"
    return "application/octet-stream"


def _stream_file_range(abs_path: Path, request: Request) -> StreamingResponse:
    file_size = abs_path.stat().st_size
    media_type = _guess_video_media_type(abs_path)
    headers: Dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{abs_path.name}"',
    }

    range_header = request.headers.get("range") or request.headers.get("Range")
    if range_header and range_header.strip().lower().startswith("bytes="):
        spec = range_header.strip()[6:]
        if "," in spec:
            spec = spec.split(",", 1)[0]
        start_s, end_s = (spec.split("-", 1) + [""])[:2]
        try:
            start = int(start_s) if start_s.strip() else None
            end = int(end_s) if end_s.strip() else None
        except Exception:
            start = None
            end = None

        if start is None and end is not None:
            start = max(0, file_size - end)
            end = file_size - 1
        if start is None:
            start = 0
        if end is None or end >= file_size:
            end = file_size - 1
        if start < 0:
            start = 0
        if end < start or file_size <= 0:
            return StreamingResponse(
                content=iter(()),
                status_code=416,
                headers={"Content-Range": f"bytes */{file_size}"},
                media_type=media_type,
            )

        chunk_size = end - start + 1

        def file_iter(path: Path, start_pos: int, count: int, block: int = 1024 * 1024):
            with open(path, "rb") as f:
                f.seek(start_pos)
                remaining = count
                while remaining > 0:
                    read_size = min(block, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers.update({
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(chunk_size),
        })
        return StreamingResponse(
            file_iter(abs_path, start, chunk_size),
            status_code=206,
            media_type=media_type,
            headers=headers,
        )

    def full_file_iter(path: Path, block: int = 1024 * 1024):
        with open(path, "rb") as f:
            while True:
                data = f.read(block)
                if not data:
                    break
                yield data

    headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        full_file_iter(abs_path),
        media_type=media_type,
        headers=headers,
    )


def remove_path(target: Path) -> bool:
    try:
        if not target:
            return False
        if target.exists():
            if target.is_file() or target.is_symlink():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            return True
    except Exception:
        return False
    return False


def remove_prefix_entries(dir_path: Path, prefix: str) -> int:
    removed = 0
    try:
        if dir_path.exists() and dir_path.is_dir():
            for item in dir_path.iterdir():
                if item.name.startswith(prefix):
                    if remove_path(item):
                        removed += 1
    except Exception:
        pass
    return removed


def remove_matching_glob(dir_path: Path, pattern: str) -> int:
    removed = 0
    try:
        if dir_path.exists() and dir_path.is_dir():
            for item in dir_path.glob(pattern):
                if remove_path(item):
                    removed += 1
    except Exception:
        pass
    return removed


def cleanup_project_assets(p) -> None:
    paths: List[str] = []

    def _add(v):
        if v is None:
            return
        s = str(v).strip()
        if s:
            paths.append(s)

    _add(getattr(p, "video_path", None))
    for v in (getattr(p, "video_paths", None) or []):
        _add(v)
    _add(getattr(p, "merged_video_path", None))
    _add(getattr(p, "subtitle_path", None))
    _add(getattr(p, "audio_path", None))
    _add(getattr(p, "narration_copywriting_path", None))
    _add(getattr(p, "output_video_path", None))
    _add(getattr(p, "jianying_draft_last_dir", None))
    _add(getattr(p, "jianying_draft_last_dir_web", None))
    for v in (getattr(p, "jianying_draft_dirs", None) or []):
        _add(v)

    seen = set()
    for s in paths:
        if s in seen:
            continue
        seen.add(s)
        abs_path = resolve_any_path(s)
        remove_path(abs_path)

    up = uploads_dir()
    project_dir_name = safe_dir_name(getattr(p, "name", None) or getattr(p, "id", ""), getattr(p, "id", ""))
    remove_path(up / "videos" / "outputs" / project_dir_name)
    remove_path(up / "videos" / "merged" / project_dir_name)
    remove_path(up / "jianying_drafts" / "outputs" / str(getattr(p, "id", "")))

    prefix = f"{getattr(p, 'id', '')}_"
    remove_prefix_entries(up / "videos" / "tmp", prefix)
    remove_prefix_entries(up / "audios" / "tmp", prefix)
    remove_prefix_entries(up / "jianying_drafts" / "tmp", prefix)
    remove_matching_glob(up / "videos", f"{getattr(p, 'id', '')}_video_*")
    remove_matching_glob(up / "subtitles", f"{getattr(p, 'id', '')}_subtitle_*")
    remove_matching_glob(up / "audios", f"{getattr(p, 'id', '')}_audio_*")
    remove_matching_glob(up / "analyses", f"{getattr(p, 'id', '')}_copywriting_*")
    remove_matching_glob(up / "analyses", f"{getattr(p, 'id', '')}_analysis_*")


# ========================= Pydantic 模型 =========================

class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = Field(default="subtitle")
    narration_type: Optional[str] = Field(default="短剧解说")
    omni_effect_tier: Optional[str] = Field(default=None)


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    omni_effect_tier: Optional[str] = None
    narration_type: Optional[str] = None
    script_length: Optional[str] = None
    original_ratio: Optional[int] = None
    interleave_mode: Optional[str] = None
    script_language: Optional[str] = None
    copywriting_word_count: Optional[int] = None
    status: Optional[str] = None
    video_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    audio_path: Optional[str] = None
    narration_copywriting: Optional[Dict[str, Any]] = None
    narration_copywriting_path: Optional[str] = None
    narration_film_context: Optional[str] = None
    narration_reference_copywriting: Optional[str] = None
    script: Optional[Dict[str, Any]] = None


class DeleteVideoRequest(BaseModel):
    file_path: Optional[str] = None


class PrepareVideoRequest(BaseModel):
    file_path: str


class MergeTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str
    file_path: Optional[str] = None


MERGE_TASKS: Dict[str, MergeTaskStatus] = {}
_merge_lock = RLock()
_active_merge_keys: Dict[str, str] = {}
DRAFT_TASKS: Dict[str, MergeTaskStatus] = {}
VIDEO_TASKS: Dict[str, MergeTaskStatus] = {}

DRAFT_TASK_HANDLES: Dict[str, asyncio.Task] = {}
VIDEO_TASK_HANDLES: Dict[str, asyncio.Task] = {}


class TrimTimeRange(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)


class TrimVideoRequest(BaseModel):
    file_path: str
    mode: Literal["keep", "delete"] = "keep"
    ranges: List[TrimTimeRange] = Field(default_factory=list)


class TrimTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str
    file_path: Optional[str] = None
    output_version: Optional[str] = None


TRIM_TASKS: Dict[str, TrimTaskStatus] = {}

_trim_lock = RLock()
_active_trim_keys: Dict[str, str] = {}


class UpdateVideoOrderRequest(BaseModel):
    ordered_paths: List[str]


class GenerateScriptRequest(BaseModel):
    project_id: str
    video_path: str
    subtitle_path: Optional[str] = None
    narration_type: str


class GenerateCopywritingRequest(BaseModel):
    project_id: str
    video_path: str
    subtitle_path: Optional[str] = None
    narration_type: str


class ExtractSubtitleRequest(BaseModel):
    force: bool = False
    task_id: Optional[str] = None
    asr_provider: Optional[str] = None
    asr_model_key: Optional[str] = None
    asr_language: Optional[str] = None
    itn: bool = True
    hotwords: Optional[List[str]] = None
    analyzeVision: bool = False
    visionMode: str = "all"
    visionKeyFrames: int = 1
    visionAction: str = "auto"


class SubtitleSegmentInput(BaseModel):
    id: Optional[str] = None
    start_time: float
    end_time: float
    text: str


class SaveSubtitleRequest(BaseModel):
    segments: Optional[List[SubtitleSegmentInput]] = None
    content: Optional[str] = None


# ========================= 字幕工具函数 =========================

def _segments_to_compressed_srt(segments: List[SubtitleSegmentInput]) -> str:
    items = list(segments or [])
    items.sort(key=lambda x: (float(x.start_time), float(x.end_time)))
    out_lines: List[str] = []
    for seg in items:
        start = float(seg.start_time)
        end = float(seg.end_time)
        if start < 0 or end < 0 or start >= end:
            raise HTTPException(status_code=400, detail="字幕时间戳无效")
        text = (seg.text or "").strip()
        if not text:
            continue
        normalized_text = re.sub(r"\s+", " ", text)
        out_lines.append(f"[{format_ts_srt(start)}-{format_ts_srt(end)}] {normalized_text}")
    return ("\n".join(out_lines) + ("\n" if out_lines else ""))


def compress_srt(content: str) -> str:
    text = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = [b for b in text.split("\n\n") if b.strip()]
    out_lines: List[str] = []
    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if not lines:
            continue
        timing_i = None
        for i, ln in enumerate(lines[:3]):
            if "-->" in ln:
                timing_i = i
                break
        if timing_i is None:
            continue
        parts = lines[timing_i].split("-->")
        if len(parts) < 2:
            continue
        start = parts[0].strip()
        end = parts[1].strip()
        text_lines = lines[timing_i + 1:]
        t = " ".join(text_lines)
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"<[^>]+>", "", t)
        if not t:
            continue
        out_lines.append(f"[{start}-{end}] {t}")
    return ("\n".join(out_lines) + ("\n" if out_lines else ""))


def read_video_duration(video_path: Path) -> float:
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return 0.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        cap.release()
        if fps <= 0:
            return 0.0
        return float(frame_count / fps)
    except Exception:
        return 0.0


# ========================= 项目状态辅助 =========================

_ALL_TASK_SCOPES = [
    "generate_copywriting",
    "generate_script",
    "generate_video",
    JianyingDraftManager.SCOPE,
    extract_scene_service.SCOPE,
    omni_multimodal_pipeline_service.SCOPE,
    omni_copywriting_struct_embed_service.SCOPE,
    omni_shot_match_service.SCOPE,
    omni_global_path_search_service.SCOPE,
    omni_generate_script_service.SCOPE,
    omni_full_narration_pipeline_service.SCOPE,
]


def _is_project_processing(project_id: str) -> bool:
    for scope in _ALL_TASK_SCOPES:
        if task_progress_store.get_latest_running(scope, project_id):
            return True
    return False


def _reconcile_stale_subtitle_extract_status(data: dict, project_id: str) -> dict:
    """若磁盘上仍是 extracting，但内存中无运行中的字幕任务（客户端崩溃、后端重启等），纠正 subtitle_status。"""
    st = str(data.get("subtitle_status") or "").strip().lower()
    if st != "extracting":
        return data
    if task_progress_store.get_latest_running(EXTRACT_SUBTITLE_SCOPE, project_id):
        return data
    sp = data.get("subtitle_path")
    path_ok = bool((str(sp).strip() if isinstance(sp, str) else sp))
    updates: Dict[str, Any] = {"subtitle_status": "ready" if path_ok else "failed"}
    try:
        projects_store.update_project(project_id, updates)
        merged = {**data, **updates}
        return merged
    except Exception:
        logger.warning("纠正陈旧字幕提取状态失败: project_id=%s", project_id, exc_info=True)
        return data


def _enrich_project_status(data: dict, project_id: str) -> dict:
    data = _reconcile_stale_subtitle_extract_status(data, project_id)
    if _is_project_processing(project_id):
        data["status"] = "processing"
    return data


# ========================= 核心 CRUD 路由 =========================

@router.get("")
async def list_projects():
    items = [_enrich_project_status(p.model_dump(), p.id) for p in projects_store.list_projects()]
    return {
        "message": "获取项目列表成功",
        "data": items,
        "timestamp": now_ts(),
    }


@router.get("/{project_id}")
async def get_project_detail(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "获取项目详情成功",
        "data": _enrich_project_status(p.model_dump(), project_id),
        "timestamp": now_ts(),
    }


@router.post("")
async def create_project(req: CreateProjectRequest, request: Request):
    if (req.project_type or "").strip().lower() == "omni":
        await require_valid_license_for_omni(request.headers.get("Authorization"))
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="项目名称无效")
    name_clean = req.name.strip()
    for existing in projects_store.list_projects():
        if (existing.name or "").strip() == name_clean:
            raise HTTPException(status_code=400, detail="项目名称已存在")
    narration_type = normalize_narration_type(req.narration_type)
    if req.narration_type and not is_valid_narration_type(req.narration_type):
        raise HTTPException(status_code=400, detail="解说类型无效")
    p = projects_store.create_project(
        name_clean,
        req.description,
        narration_type or DEFAULT_NARRATION_TYPE,
        req.project_type or "subtitle",
        omni_effect_tier=req.omni_effect_tier,
    )
    return JSONResponse(status_code=201, content={
        "message": "项目创建成功",
        "data": p.model_dump(),
        "timestamp": now_ts(),
    })


@router.post("/{project_id}")
async def update_project(project_id: str, req: UpdateProjectRequest):
    updates = req.model_dump(exclude_unset=True)
    if "narration_type" in updates:
        if updates.get("narration_type") and not is_valid_narration_type(updates.get("narration_type")):
            raise HTTPException(status_code=400, detail="解说类型无效")
        updates["narration_type"] = normalize_narration_type(updates.get("narration_type"))
    if "script_length" in updates:
        try:
            updates["script_length"] = normalize_script_length_selection(
                updates.get("script_length")
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if "original_ratio" in updates:
        ratio_raw = updates.get("original_ratio")
        if ratio_raw is None:
            updates["original_ratio"] = None
        else:
            try:
                ratio_val = int(ratio_raw)
            except Exception:
                raise HTTPException(status_code=400, detail="原片占比必须为整数")
            if ratio_val < 0 or ratio_val > 100:
                raise HTTPException(status_code=400, detail="原片占比范围为 0%~100%")
            updates["original_ratio"] = ratio_val
    if "script_language" in updates:
        try:
            lang_raw = (updates.get("script_language") or "").strip().lower()
        except Exception:
            lang_raw = ""
        if lang_raw in {"zh", "zh-cn", "中文", "cn", "chinese"}:
            updates["script_language"] = "zh"
        elif lang_raw in {"en", "en-us", "英文", "us", "english"}:
            updates["script_language"] = "en"
        else:
            raise HTTPException(status_code=400, detail="脚本语言仅支持 zh 或 en")
    p = projects_store.update_project(project_id, updates)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "项目更新成功",
        "data": {
            "id": p.id,
            "name": p.name,
            "status": "processing" if _is_project_processing(project_id) else p.status,
            "updated_at": p.updated_at,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/delete")
async def delete_project(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        cleanup_project_assets(p)
    except Exception:
        pass
    runtime_log_store.clear(project_id=project_id)
    ok = projects_store.delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "项目删除成功",
        "success": True,
        "timestamp": now_ts(),
    }


# ========================= 日志路由 =========================

@router.get("/{project_id}/logs")
async def list_project_logs(
    project_id: str,
    after_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    items = runtime_log_store.list(project_id=project_id, after_id=after_id, limit=limit)
    next_after_id = None
    try:
        next_after_id = int(items[-1]["id"]) if items else after_id
    except Exception:
        next_after_id = after_id
    return {
        "message": "获取日志成功",
        "data": {
            "items": items,
            "next_after_id": next_after_id,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/logs/clear")
async def clear_project_logs(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    runtime_log_store.clear(project_id=project_id)
    return {"message": "清空日志成功", "success": True, "timestamp": now_ts()}


@router.get("/{project_id}/logs/stream")
async def stream_project_logs(
    project_id: str,
    after_id: Optional[int] = Query(default=None),
):
    import json
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    async def _gen():
        items = runtime_log_store.list(project_id=project_id, after_id=after_id, limit=2000)
        for it in items:
            yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
        handle = runtime_log_store.subscribe(project_id=project_id)
        try:
            while True:
                try:
                    it = await asyncio.wait_for(handle.queue.get(), timeout=15)
                    yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ":keep-alive\n\n"
        finally:
            runtime_log_store.unsubscribe(handle)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    return StreamingResponse(_gen(), media_type="text/event-stream", headers=headers)


async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
