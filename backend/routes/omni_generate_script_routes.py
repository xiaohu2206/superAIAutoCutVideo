#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni：解说脚本生成（独立路由，与 /generate-script 隔离）。"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from modules.projects_store import projects_store
from modules.task_progress_store import task_progress_store
from services.omni_generate_script_service import omni_generate_script_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Omni 解说脚本生成"])


def _now_ts() -> str:
    return datetime.now().isoformat()


class OmniGenerateScriptRunRequest(BaseModel):
    force: bool = Field(default=False)
    task_id: Optional[str] = None
    input_global_path_web_path: Optional[str] = Field(
        default=None,
        description="覆盖项目上的 omni_global_path_search_path；默认使用已保存的 global_path.json",
    )
    input_multimodal_web_path: Optional[str] = Field(
        default=None,
        description="覆盖项目上的 omni_multimodal_json_path；默认使用多模态 shots JSON",
    )
    generation_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="分块/时间窗等参数，语义对齐 Step4.9（chunk_target_size、timeline_window_mode 等）",
    )
    temperature: Optional[float] = Field(default=None, description="覆盖当前文案模型温度")
    chunk_llm_concurrency: int = Field(default=4, ge=1, le=16, description="分块 LLM 并发数")


@router.post("/{project_id}/omni/generate-script/run")
async def omni_generate_script_run(
    project_id: str,
    req: OmniGenerateScriptRunRequest = Body(default=OmniGenerateScriptRunRequest()),
):
    try:
        data = await omni_generate_script_service.submit_run(
            project_id,
            force=bool(req.force),
            task_id=req.task_id,
            input_global_path_web_path=req.input_global_path_web_path,
            input_multimodal_web_path=req.input_multimodal_web_path,
            generation_params=req.generation_params,
            temperature=req.temperature,
            chunk_llm_concurrency=req.chunk_llm_concurrency,
        )
        return {"message": "任务已提交", "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("omni generate-script submit failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/omni/generate-script/status/{task_id}")
async def omni_generate_script_status(project_id: str, task_id: str):
    st = task_progress_store.get_state(omni_generate_script_service.SCOPE, project_id, task_id)
    if not st:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "获取进度成功", "data": st, "timestamp": _now_ts()}


@router.get("/{project_id}/omni/generate-script/paths")
async def omni_generate_script_paths(project_id: str) -> Dict[str, Any]:
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "获取路径成功",
        "data": {
            "omni_generate_script_path": getattr(p, "omni_generate_script_path", None),
            "omni_generate_script_updated_at": getattr(p, "omni_generate_script_updated_at", None),
            "omni_global_path_search_path": getattr(p, "omni_global_path_search_path", None),
            "omni_multimodal_json_path": getattr(p, "omni_multimodal_json_path", None),
        },
        "timestamp": _now_ts(),
    }
