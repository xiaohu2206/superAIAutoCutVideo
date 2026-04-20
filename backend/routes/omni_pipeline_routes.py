#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni 项目多模态管线 API（与 extract_scene 路由隔离）"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from modules.app_paths import resolve_uploads_path
from modules.projects_store import projects_store
from modules.task_progress_store import task_progress_store
from services.omni_internal.multimodal_json_crypto import read_multimodal_json
from services.omni_multimodal_pipeline_service import omni_multimodal_pipeline_service

logger = logging.getLogger(__name__)


def _now_ts() -> str:
    return datetime.now().isoformat()

router = APIRouter(prefix="/api/projects", tags=["Omni 多模态管线"])


class OmniPipelineRunRequest(BaseModel):
    """请求体：multimodal_action 为 auto|continue|restart（与镜头提取 visionAction 用法对齐）。"""

    force: bool = Field(default=False)
    task_id: Optional[str] = None
    multimodal_action: str = Field(default="auto", description="auto / continue / restart")


@router.post("/{project_id}/omni/run-pipeline")
async def omni_run_pipeline(project_id: str, req: OmniPipelineRunRequest = Body(default=OmniPipelineRunRequest())):
    try:
        data = await omni_multimodal_pipeline_service.submit_pipeline(
            project_id=project_id,
            force=bool(req.force),
            task_id=req.task_id,
            multimodal_action=req.multimodal_action,
        )
        return {"message": "Omni 管线已提交", "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Omni run-pipeline failed")
        raise HTTPException(status_code=500, detail=f"Omni 管线提交失败: {e}")


@router.get("/{project_id}/omni/pipeline-status/{task_id}")
async def omni_pipeline_status(project_id: str, task_id: str):
    st = task_progress_store.get_state(omni_multimodal_pipeline_service.SCOPE, project_id, task_id)
    if not st:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "获取进度成功", "data": st, "timestamp": _now_ts()}


@router.get("/{project_id}/omni/multimodal-result")
async def omni_multimodal_result(project_id: str) -> Dict[str, Any]:
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    path = getattr(p, "omni_multimodal_json_path", None)
    if not path:
        raise HTTPException(status_code=404, detail="尚未生成 Omni 多模态结果")
    abs_path: Path = resolve_uploads_path(str(path).strip())
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")
    try:
        data = read_multimodal_json(abs_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取结果失败: {e}")
    return {"message": "获取成功", "data": data, "timestamp": _now_ts()}
