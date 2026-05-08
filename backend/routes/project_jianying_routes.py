#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
剪映草稿生成与文件管理相关API路由
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio
import uuid
import platform
import subprocess
import logging

from fastapi import APIRouter, HTTPException, Query

from .project_routes import (
    now_ts,
    resolve_abs_path,
    project_root_dir,
    MergeTaskStatus,
    DRAFT_TASKS,
    DRAFT_TASK_HANDLES,
)
from modules.projects_store import projects_store
from modules.config.jianying_config import jianying_config_manager
from services.jianying_draft_manager import jianying_draft_manager, JianyingDraftManager
from modules.config.generate_concurrency_config import generate_concurrency_config_manager
from modules.task_scheduler import task_scheduler
from modules.project_task_queue import project_task_queue

router = APIRouter(prefix="/api/projects", tags=["项目管理"])
logger = logging.getLogger(__name__)


@router.post("/{project_id}/generate-jianying-draft")
async def generate_jianying_draft(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.video_path:
        raise HTTPException(status_code=400, detail="请先上传原始视频文件")
    cfg_path = jianying_config_manager.get_draft_path()
    if not cfg_path or not cfg_path.exists():
        raise HTTPException(status_code=400, detail="未设置剪映草稿路径，无法生成")

    candidate_task_id = f"draft_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    max_workers, _src = generate_concurrency_config_manager.get_effective("generate_jianying_draft")
    logger.info(
        "生成剪映草稿入队请求: project_id=%s candidate_task_id=%s concurrency=%s",
        project_id,
        candidate_task_id,
        int(max_workers or 4),
    )

    def _local_update(task_id: str, status: str, progress: float, message: str, file_path: Optional[str]) -> None:
        t = DRAFT_TASKS.get(task_id)
        if not t:
            t = MergeTaskStatus(task_id=task_id, status=status, progress=progress, message=message)
            DRAFT_TASKS[task_id] = t
        t.status = status
        t.progress = progress
        if status == "queued":
            t.message = "进入队列"
        elif status == "processing":
            t.message = "生成中"
        elif status == "completed":
            t.message = "生成完成"
        elif status == "cancelled":
            t.message = "已停止"
        elif status == "failed":
            t.message = message or "生成失败"
        else:
            t.message = message
        if file_path:
            t.file_path = file_path

        if status == "processing":
            projects_store.update_project(project_id, {"status": "processing"})
        elif status == "completed":
            projects_store.update_project(project_id, {"status": "completed"})
        elif status == "cancelled":
            projects_store.update_project(project_id, {"status": "cancelled"})
        elif status == "failed":
            projects_store.update_project(project_id, {"status": "failed"})

    def _handle_update(task_id: str, task: Optional[asyncio.Task]) -> None:
        if task is None:
            DRAFT_TASK_HANDLES.pop(task_id, None)
        else:
            DRAFT_TASK_HANDLES[task_id] = task

    async def _run(project_id: str, task_id: str, cancel_event: asyncio.Event) -> Dict[str, Any]:
        await project_task_queue.acquire(project_id, JianyingDraftManager.SCOPE, task_id, cancel_event=cancel_event)
        try:
            r = await jianying_draft_manager.generate_draft_folder(project_id=project_id, task_id=task_id, cancel_event=cancel_event)
            try:
                projects_store.update_project(
                    project_id,
                    {
                        "jianying_draft_last_dir": str(r.dir_abs),
                        "jianying_draft_last_dir_web": r.dir_web,
                        "jianying_draft_dirs": list(
                            set((projects_store.get_project(project_id).model_dump().get("jianying_draft_dirs") or []) + [r.dir_web])
                        ),
                    },
                )
            except Exception:
                pass
            return {"file_path": r.dir_web}
        finally:
            await project_task_queue.release(project_id)

    task_id = await task_scheduler.enqueue(
        scope=JianyingDraftManager.SCOPE,
        project_id=project_id,
        run_fn=_run,
        task_id=candidate_task_id,
        concurrency=int(max_workers or 4),
        dedup=True,
        local_update=_local_update,
        handle_update=_handle_update,
    )
    logger.info(
        "生成剪映草稿入队结果: project_id=%s task_id=%s dedup_hit=%s",
        project_id,
        task_id,
        task_id != candidate_task_id,
    )

    return {
        "message": "开始生成剪映草稿" if task_id == candidate_task_id else "任务已存在",
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


@router.get("/{project_id}/open-in-explorer")
async def open_in_explorer(project_id: str, path: Optional[str] = None):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    target = path or (p.model_dump().get("jianying_draft_last_dir") or "")
    if not target:
        raise HTTPException(status_code=400, detail="未找到草稿目录路径")
    raw_target = str(target).strip()
    if raw_target.startswith("~"):
        raw_target = str(Path(raw_target).expanduser())

    abs_path = resolve_abs_path(raw_target)
    if abs_path and not abs_path.is_absolute():
        abs_path = (project_root_dir() / abs_path).resolve()
    try:
        if abs_path.exists():
            sysname = platform.system().lower()
            if abs_path.is_file():
                if "windows" in sysname:
                    subprocess.Popen(["explorer", "/select,", str(abs_path)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                elif "darwin" in sysname:
                    subprocess.Popen(["open", "-R", str(abs_path)])
                else:
                    subprocess.Popen(["xdg-open", str(abs_path.parent)])
            else:
                if "windows" in sysname:
                    subprocess.Popen(["explorer", str(abs_path)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                elif "darwin" in sysname:
                    subprocess.Popen(["open", str(abs_path)])
                else:
                    subprocess.Popen(["xdg-open", str(abs_path)])
            return {"message": "已打开文件管理器", "data": {"path": str(abs_path)}, "timestamp": now_ts()}
        else:
            raise HTTPException(status_code=404, detail="路径不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"打开文件管理器失败: {str(e)}")
