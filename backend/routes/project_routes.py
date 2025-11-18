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
- POST /api/projects/{project_id}/upload/subtitle 上传字幕
- POST /api/projects/generate-script               生成解说脚本（简化实现）
- POST /api/projects/{project_id}/script          保存脚本
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio

import cv2
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

from modules.projects_store import projects_store, Project
from modules.video_processor import video_processor
from services.script_generation_service import ScriptGenerationService
from services.video_generation_service import video_generation_service


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
    status: Optional[str] = None
    video_path: Optional[str] = None
    subtitle_path: Optional[str] = None
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
        blocks = [b.strip() for b in content.strip().split("\n\n") if b.strip()]
        for idx, block in enumerate(blocks, start=1):
            lines = block.splitlines()
            if len(lines) < 2:
                continue
            # line 0 could be index, line 1 timing
            timing_line = lines[1] if "-->" in lines[1] else lines[0]
            if "-->" not in timing_line:
                continue
            start_str, end_str = [t.strip() for t in timing_line.split("-->")]
            start_t = _parse_ts(start_str)
            end_t = _parse_ts(end_str)
            text_lines = lines[2:] if timing_line == lines[1] else lines[1:]
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
    # 校验项目存在
    p = projects_store.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 解析视频与字幕路径（支持 /uploads/... 或绝对路径）
    root = project_root_dir()
    def resolve_path(path_str: str) -> Path:
        path_str = path_str.strip()
        if path_str.startswith("/"):
            return root / path_str[1:]
        return Path(path_str)

    video_abs = resolve_path(req.video_path)
    if not video_abs.exists():
        raise HTTPException(status_code=400, detail="视频文件不存在")

    total_duration = read_video_duration(video_abs)

    segments: List[Dict[str, Any]] = []
    if req.subtitle_path:
        sub_abs = resolve_path(req.subtitle_path)
        if sub_abs.exists():
            segments = parse_srt(sub_abs)
    # 读取原始字幕文本（用于提示词输入）
    subtitle_text: str = ""
    if req.subtitle_path:
        sub_abs = resolve_path(req.subtitle_path)
        if sub_abs.exists():
            try:
                subtitle_text = sub_abs.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                subtitle_text = ""

    # 状态变更为 processing
    projects_store.update_project(req.project_id, {"status": "processing"})

    try:
        drama_name = p.name or "剧名"
        # 1) 爆点分析
        plot_analysis = await ScriptGenerationService.generate_plot_analysis(subtitle_text)
        # 2) 格式化脚本（JSON）
        script_json = await ScriptGenerationService.generate_script_json(
            drama_name=drama_name,
            plot_analysis=plot_analysis,
            subtitle_content=subtitle_text,
        )
        # 3) 转为 VideoScript 结构
        script = ScriptGenerationService.to_video_script(script_json, total_duration)
        # 4) 保存到项目并返回
        p2 = projects_store.save_script(req.project_id, script)
        projects_store.update_project(req.project_id, {"status": "completed"})
        return {
            "message": "解说脚本生成成功",
            "data": {
                "script": script,
                "plot_analysis": plot_analysis,
            },
            "timestamp": now_ts(),
        }
    except Exception as e:
        # 失败时更新状态
        projects_store.update_project(req.project_id, {"status": "failed"})
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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{project_id}_video_{ts}{suffix}"
    out_path = up_dir / out_name

    size = 0
    try:
        with out_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                f.write(chunk)
    finally:
        await file.close()

    # 记录到项目的视频列表，并按规则更新生效路径
    web_path = to_web_path(out_path)
    projects_store.append_video_path(project_id, web_path)

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
async def upload_subtitle(project_id: str, file: UploadFile = File(...), project_id_form: str = Form(None)):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    suffix = Path(file.filename).suffix.lower()
    if suffix != ".srt":
        raise HTTPException(status_code=400, detail="文件格式不支持")

    up_dir = uploads_dir() / "subtitles"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{project_id}_subtitle_{ts}{suffix}"
    out_path = up_dir / out_name

    size = 0
    try:
        with out_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                f.write(chunk)
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
async def delete_video_file(project_id: str, req: Optional[DeleteVideoRequest] = None, file_path_form: str = Form(None)):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 选择目标删除路径：优先使用传入的 file_path，其次兼容旧逻辑（使用生效路径）
    removed = False
    removed_path = None
    target_path = None
    if req and req.file_path:
        target_path = req.file_path
    elif file_path_form:
        target_path = file_path_form
    else:
        target_path = p.video_path

    if target_path:
        root = project_root_dir()
        path_str = target_path.strip()
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
        p2 = projects_store.remove_video_path(project_id, target_path)
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

            ok = await video_processor.concat_videos([str(x) for x in inputs], str(out_path), on_progress)
            if not ok:
                MERGE_TASKS[task_id].status = "failed"
                MERGE_TASKS[task_id].message = "合并失败"
                return

            web_path = to_web_path(out_path)
            MERGE_TASKS[task_id].file_path = web_path
            MERGE_TASKS[task_id].progress = 100.0
            MERGE_TASKS[task_id].status = "completed"
            MERGE_TASKS[task_id].message = "合并完成"
            projects_store.set_merged_video_path(project_id, web_path)
        except Exception:
            MERGE_TASKS[task_id].status = "failed"
            MERGE_TASKS[task_id].message = "合并异常"

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
    return FileResponse(
        path=str(abs_path),
        filename=filename,
        media_type="video/mp4"
    )