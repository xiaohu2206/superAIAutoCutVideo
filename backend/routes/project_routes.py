#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目管理、文件上传与脚本相关API路由

实现API文档中的以下接口：
- GET /api/projects                 获取项目列表
- GET /api/projects/{project_id}    获取项目详情
- POST /api/projects                创建项目
- POST /api/projects/{project_id}   更新项目
- POST /api/projects/{project_id}/delete  删除项目
- POST /api/projects/{project_id}/upload/video    上传视频
- POST /api/projects/generate-script               生成解说脚本（简化实现）
- POST /api/projects/{project_id}/script          保存脚本
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio
import logging
import re
import cv2
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
import json
import uuid

from modules.projects_store import projects_store, Project
from modules.video_processor import video_processor
from services.script_generation_service import ScriptGenerationService
from services.video_generation_service import video_generation_service
from services.generate_script_service import generate_script_service
from services.jianying_draft_manager import jianying_draft_manager, JianyingDraftManager
from services.asr_bcut import BcutASR
from services.asr_utils import utterances_to_srt
from modules.config.content_model_config import content_model_config_manager
from modules.config.tts_config import tts_engine_config_manager
from modules.config.video_model_config import video_model_config_manager
from modules.ws_manager import manager


router = APIRouter(prefix="/api/projects", tags=["项目管理"])


def now_ts() -> str:
    return datetime.now().isoformat()


def project_root_dir() -> Path:
    # backend/routes/... -> backend -> project root
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def uploads_dir() -> Path:
    root = project_root_dir()
    up = root / "uploads"
    (up / "videos").mkdir(parents=True, exist_ok=True)
    (up / "subtitles").mkdir(parents=True, exist_ok=True)
    (up / "audios").mkdir(parents=True, exist_ok=True)
    (up / "analyses").mkdir(parents=True, exist_ok=True)
    return up


def to_web_path(p: Path) -> str:
    # 返回以 /uploads/... 开头的路径
    root = project_root_dir()
    rel = p.relative_to(root)
    return "/" + str(rel).replace("\\", "/")

class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None
    narration_type: Optional[str] = Field(default="短剧解说")


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    narration_type: Optional[str] = None
    script_length: Optional[str] = None
    status: Optional[str] = None
    video_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    audio_path: Optional[str] = None
    plot_analysis_path: Optional[str] = None
    script: Optional[Dict[str, Any]] = None


class DeleteVideoRequest(BaseModel):
    file_path: Optional[str] = None

class MergeTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str
    file_path: Optional[str] = None

MERGE_TASKS: Dict[str, MergeTaskStatus] = {}

DRAFT_TASKS: Dict[str, MergeTaskStatus] = {}


class UpdateVideoOrderRequest(BaseModel):
    ordered_paths: List[str]


class GenerateScriptRequest(BaseModel):
    project_id: str
    video_path: str
    subtitle_path: Optional[str] = None
    narration_type: str


def parse_srt(srt_path: Path) -> List[Dict[str, Any]]:
    """简易SRT解析，返回包含 start/end/text 的列表"""
    def _parse_ts(ts: str) -> float:
        # format: HH:MM:SS,mmm
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    segments: List[Dict[str, Any]] = []
    try:
        content = srt_path.read_text(encoding="utf-8", errors="ignore")
        norm = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        lines = [ln.strip() for ln in norm.splitlines() if ln.strip()]
        # 优先检测压缩后的行格式：[HH:MM:SS,mmm-HH:MM:SS,mmm] text
        bracket_pattern = re.compile(r"^\[(\d{2}:\d{2}:\d{2},\d{3})-(\d{2}:\d{2}:\d{2},\d{3})\]\s*(.+)$")
        bracket_matches = [bracket_pattern.match(ln) for ln in lines]
        if any(bracket_matches):
            idx = 1
            for m in bracket_matches:
                if not m:
                    continue
                start_str, end_str, text = m.groups()
                start_t = _parse_ts(start_str)
                end_t = _parse_ts(end_str)
                segments.append({
                    "id": str(idx),
                    "start_time": float(start_t),
                    "end_time": float(end_t),
                    "text": text,
                    "subtitle": text,
                })
                idx += 1
        else:
            # 兼容标准SRT解析
            blocks = [b.strip() for b in norm.split("\n\n") if b.strip()]
            for idx, block in enumerate(blocks, start=1):
                ls = [l for l in block.splitlines() if l.strip()]
                if len(ls) < 2:
                    continue
                timing_line = ls[1] if "-->" in ls[1] else ls[0]
                if "-->" not in timing_line:
                    continue
                start_str, end_str = [t.strip() for t in timing_line.split("-->")]
                start_t = _parse_ts(start_str)
                end_t = _parse_ts(end_str)
                text_lines = ls[2:] if timing_line == ls[1] else ls[1:]
                text = " ".join([ln.strip() for ln in text_lines if ln.strip()])
                if not text:
                    text = f"字幕段{idx}"
                segments.append({
                    "id": str(idx),
                    "start_time": float(start_t),
                    "end_time": float(end_t),
                    "text": text,
                    "subtitle": text,
                })
    except Exception:
        # 解析失败返回空
        pass
    return segments

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


# ========================= 项目管理 =========================

@router.get("")
async def list_projects():
    items = [p.model_dump() for p in projects_store.list_projects()]
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
        "data": p.model_dump(),
        "timestamp": now_ts(),
    }


@router.post("")
async def create_project(req: CreateProjectRequest):
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="项目名称无效")
    p = projects_store.create_project(req.name.strip(), req.description, req.narration_type or "短剧解说")
    return JSONResponse(status_code=201, content={
        "message": "项目创建成功",
        "data": p.model_dump(),
        "timestamp": now_ts(),
    })


# ========================= 脚本生成 =========================

@router.post("/generate-script")
async def generate_script(req: GenerateScriptRequest):
    try:
        return await generate_script_service.generate_script(
            project_id=req.project_id,
            video_path=req.video_path,
            subtitle_path=req.subtitle_path,
            narration_type=req.narration_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        projects_store.update_project(req.project_id, {"status": "failed"})
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "failed",
                "message": f"脚本生成失败: {str(e)}",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"脚本生成失败: {str(e)}")


@router.post("/{project_id}")
async def update_project(project_id: str, req: UpdateProjectRequest):
    p = projects_store.update_project(project_id, req.model_dump(exclude_unset=True))
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "项目更新成功",
        "data": {
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "updated_at": p.updated_at,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/delete")
async def delete_project(project_id: str):
    ok = projects_store.delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "项目删除成功",
        "success": True,
        "timestamp": now_ts(),
    }


# ========================= 文件上传 =========================

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}


@router.post("/{project_id}/upload/video")
async def upload_video(project_id: str, file: UploadFile = File(...), project_id_form: str = Form(None)):
    # 校验项目存在
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 校验扩展名
    suffix = Path(file.filename).suffix.lower()
    if suffix not in VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="文件格式不支持")

    # 保存文件
    up_dir = uploads_dir() / "videos"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique = uuid.uuid4().hex[:8]
    out_name = f"{project_id}_video_{ts}_{unique}{suffix}"
    out_path = up_dir / out_name

    size = 0
    try:
        # 以二进制模式保存视频文件
        with open(out_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                size += len(chunk)
                buffer.write(chunk)
    finally:
        await file.close()

    # 记录到项目的视频列表，并按规则更新生效路径
    web_path = to_web_path(out_path)
    # 记录路径与原始文件名
    projects_store.append_video_path(project_id, web_path, file.filename)

    return {
        "message": "视频上传成功",
        "data": {
            "file_path": web_path,
            "file_name": file.filename,
            "file_size": size,
            "upload_time": now_ts(),
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

    up_dir = uploads_dir() / "subtitles"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique = uuid.uuid4().hex[:8]
    out_name = f"{project_id}_subtitle_{ts}_{unique}{suffix}"
    out_path = up_dir / out_name

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
    projects_store.update_project(project_id, {"subtitle_path": web_path})

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

# ========================= 文件删除 =========================

@router.post("/{project_id}/delete/video")
async def delete_video_file(project_id: str, request: Request, req: Optional[DeleteVideoRequest] = Body(None), file_path_form: Optional[str] = Form(None)):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 选择目标删除路径：优先使用传入的 file_path，其次兼容旧逻辑（使用生效路径）
    removed = False
    removed_path = None
    target_path = None
    # 同时兼容 JSON Body 与 Form 提交
    if req and req.file_path:
        target_path = req.file_path.strip()
    else:
        # 尝试直接解析原始请求体（JSON 或 Form），以覆盖混合场景
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
        root = project_root_dir()
        path_str = target_path
        abs_path = root / path_str[1:] if path_str.startswith("/") else Path(path_str)
        try:
            if abs_path.exists() and abs_path.is_file():
                removed_path = str(abs_path)
                abs_path.unlink()
                removed = True
        except Exception:
            pass

    # 从列表移除对应项；若未传入路径且是旧逻辑，清空生效路径
    if target_path:
        # 传入已修剪的路径，确保与存储层中的字符串一致
        p2 = projects_store.remove_video_path(project_id, target_path)
        # 若传入的是绝对路径或不同规范，尝试按统一web规范再次移除
        try:
            root = project_root_dir()
            abs_path2 = root / target_path[1:] if target_path.startswith("/") else Path(target_path)
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


@router.post("/{project_id}/merge/videos")
async def merge_videos(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.video_paths or len(p.video_paths) < 2:
        raise HTTPException(status_code=400, detail="需要至少两个视频进行合并")

    task_id = f"merge_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    MERGE_TASKS[task_id] = MergeTaskStatus(task_id=task_id, status="pending", progress=0.0, message="准备合并")

    async def _run():
        try:
            MERGE_TASKS[task_id].status = "processing"
            MERGE_TASKS[task_id].message = "正在合并"
            try:
                # 广播任务开始
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "merge_videos",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "开始合并视频",
                    "progress": 0,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass

            root = project_root_dir()
            inputs: List[Path] = []
            for path_str in p.video_paths:
                s = path_str.strip()
                abs_path = root / s[1:] if s.startswith("/") else Path(s)
                if not abs_path.exists():
                    MERGE_TASKS[task_id].status = "failed"
                    MERGE_TASKS[task_id].message = f"源视频不存在: {s}"
                    return
                inputs.append(abs_path)

            out_dir = uploads_dir() / "videos" / "outputs" / p.name
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_name = f"{p.id}_merged_{ts}.mp4"
            out_path = out_dir / out_name

            async def on_progress(pct: float):
                MERGE_TASKS[task_id].progress = float(f"{pct:.2f}")
                try:
                    await manager.broadcast(json.dumps({
                        "type": "progress",
                        "scope": "merge_videos",
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": "正在合并",
                        "progress": MERGE_TASKS[task_id].progress,
                        "timestamp": now_ts(),
                    }))
                except Exception:
                    pass

            ok = await video_processor.concat_videos([str(x) for x in inputs], str(out_path), on_progress)
            if not ok:
                MERGE_TASKS[task_id].status = "failed"
                MERGE_TASKS[task_id].message = "合并失败"
                try:
                    await manager.broadcast(json.dumps({
                        "type": "error",
                        "scope": "merge_videos",
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": "合并失败",
                        "progress": MERGE_TASKS[task_id].progress,
                        "timestamp": now_ts(),
                    }))
                except Exception:
                    pass
                return

            web_path = to_web_path(out_path)
            MERGE_TASKS[task_id].file_path = web_path
            MERGE_TASKS[task_id].progress = 100.0
            MERGE_TASKS[task_id].status = "completed"
            MERGE_TASKS[task_id].message = "合并完成"
            # 设置合并后路径并同步当前文件名（使用输出文件名）
            projects_store.set_merged_video_path(project_id, web_path, out_name)
            try:
                await manager.broadcast(json.dumps({
                    "type": "completed",
                    "scope": "merge_videos",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "合并完成",
                    "progress": 100,
                    "file_path": web_path,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
        except Exception:
            MERGE_TASKS[task_id].status = "failed"
            MERGE_TASKS[task_id].message = "合并异常"
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "merge_videos",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "合并异常",
                    "progress": MERGE_TASKS[task_id].progress,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass

    asyncio.create_task(_run())

    return {
        "message": "开始合并",
        "data": {
            "task_id": task_id,
        },
        "timestamp": now_ts(),
    }

@router.get("/{project_id}/merge/videos/status/{task_id}")
async def merge_videos_status(project_id: str, task_id: str):
    t = MERGE_TASKS.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "message": "获取合并进度",
        "data": t.model_dump(),
        "timestamp": now_ts(),
    }


# 更新项目的视频排序（按用户顺序）
@router.post("/{project_id}/videos/order")
async def update_video_order(project_id: str, req: UpdateVideoOrderRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    existing = list(p.video_paths or [])
    new_order = list(req.ordered_paths or [])
    # 校验：必须与现有视频集合一致
    if len(existing) != len(new_order) or set(existing) != set(new_order):
        raise HTTPException(status_code=400, detail="排序列表与现有视频不匹配")
    try:
        updated = projects_store.update_project(project_id, {"video_paths": new_order})
        if not updated:
            raise HTTPException(status_code=500, detail="更新排序失败")
        return {
            "message": "更新排序成功",
            "data": updated.model_dump(),
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
        root = project_root_dir()
        path_str = p.subtitle_path.strip()
        abs_path = root / path_str[1:] if path_str.startswith("/") else Path(path_str)
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


# ========================= 脚本保存 =========================


class SaveScriptRequest(BaseModel):
    script: Dict[str, Any]


@router.post("/{project_id}/script")
async def save_script(project_id: str, req: SaveScriptRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    script = req.script
    if not isinstance(script, dict) or "segments" not in script:
        raise HTTPException(status_code=400, detail="脚本格式错误")

    p2 = projects_store.save_script(project_id, script)
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    return {
        "message": "脚本保存成功",
        "data": script,
        "timestamp": now_ts(),
    }


# ========================= 视频生成与下载 =========================

@router.post("/{project_id}/generate-video")
async def generate_video(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not p.script or not isinstance(p.script, dict):
        raise HTTPException(status_code=400, detail="请先生成并保存脚本")
    if not p.video_path:
        raise HTTPException(status_code=400, detail="请先上传原始视频文件")

    # 状态置为 processing
    projects_store.update_project(project_id, {"status": "processing"})

    try:
        result = await video_generation_service.generate_from_script(project_id)
        return {
            "message": "视频生成成功",
            "data": result,
            "timestamp": now_ts(),
        }
    except Exception as e:
        projects_store.update_project(project_id, {"status": "failed"})
        # 广播错误事件
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": "generate_video",
                "project_id": project_id,
                "phase": "failed",
                "message": f"生成视频失败: {str(e)}",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"生成视频失败: {str(e)}")


@router.get("/{project_id}/output-video")
async def download_output_video(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.output_video_path:
        raise HTTPException(status_code=404, detail="尚未生成输出视频")

    root = project_root_dir()
    path_str = p.output_video_path.strip()
    abs_path = root / path_str[1:] if path_str.startswith("/") else Path(path_str)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="输出视频文件不存在")

    filename = abs_path.name
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Disposition": f"inline; filename=\"{filename}\"",
    }
    return FileResponse(
        path=str(abs_path),
        filename=filename,
        media_type="video/mp4",
        headers=headers,
    )

# ========================= 合并视频播放 =========================

@router.get("/{project_id}/merged-video")
async def get_merged_video(project_id: str):
    """获取已合并视频文件用于播放。如果不存在则返回404。"""
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.merged_video_path:
        raise HTTPException(status_code=404, detail="尚未存在合并后的视频")

    root = project_root_dir()
    path_str = p.merged_video_path.strip()
    abs_path = root / path_str[1:] if path_str.startswith("/") else Path(path_str)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="合并视频文件不存在")

    filename = abs_path.name
    # 合并输出目前固定为 mp4
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Disposition": f"inline; filename=\"{filename}\"",
    }
    return FileResponse(
        path=str(abs_path),
        filename=filename,
        media_type="video/mp4",
        headers=headers,
    )


# ========================= 剪映草稿生成与下载 =========================

@router.post("/{project_id}/generate-jianying-draft")
async def generate_jianying_draft(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.video_path:
        raise HTTPException(status_code=400, detail="请先上传原始视频文件")

    task_id = f"draft_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    DRAFT_TASKS[task_id] = MergeTaskStatus(task_id=task_id, status="pending", progress=0.0, message="准备生成")

    async def _run():
        try:
            DRAFT_TASKS[task_id].status = "processing"
            DRAFT_TASKS[task_id].message = "生成中"
            DRAFT_TASKS[task_id].progress = 1.0
            r = await jianying_draft_manager.generate_draft_folder(project_id=project_id, task_id=task_id)
            DRAFT_TASKS[task_id].file_path = r.dir_web
            DRAFT_TASKS[task_id].status = "completed"
            DRAFT_TASKS[task_id].message = "生成完成"
            DRAFT_TASKS[task_id].progress = 100.0
        except Exception as e:
            DRAFT_TASKS[task_id].status = "failed"
            DRAFT_TASKS[task_id].message = str(e) or "生成失败"
            DRAFT_TASKS[task_id].progress = 0.0
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": JianyingDraftManager.SCOPE,
                    "project_id": project_id,
                    "task_id": task_id,
                    "phase": "failed",
                    "message": f"剪映草稿生成失败: {str(e)}",
                    "progress": DRAFT_TASKS[task_id].progress,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass

    asyncio.create_task(_run())

    return {
        "message": "开始生成剪映草稿",
        "data": {
            "task_id": task_id,
            "scope": JianyingDraftManager.SCOPE,
        },
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/jianying-draft/status/{task_id}")
async def get_jianying_draft_status(project_id: str, task_id: str):
    _ = project_id
    t = DRAFT_TASKS.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "message": "获取剪映草稿生成进度",
        "data": t.model_dump(),
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/jianying-draft")
async def download_jianying_draft(project_id: str, f: Optional[str] = None):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    root = project_root_dir()
    drafts_dir = root / "uploads" / "jianying_drafts" / "outputs" / project_id
    drafts_dir.mkdir(parents=True, exist_ok=True)

    target: Optional[Path] = None
    if f:
        name = Path(str(f)).name
        candidate = drafts_dir / name
        if candidate.exists() and candidate.is_file():
            target = candidate
    else:
        candidates = sorted(
            [x for x in drafts_dir.glob("*.zip") if x.is_file()],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            target = candidates[0]

    if not target or not target.exists():
        raise HTTPException(status_code=404, detail="尚未生成剪映草稿")

    filename = target.name
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Disposition": f"attachment; filename=\"{filename}\"",
    }
    return FileResponse(
        path=str(target),
        filename=filename,
        media_type="application/zip",
        headers=headers,
    )
async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
