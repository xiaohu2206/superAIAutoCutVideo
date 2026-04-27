#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni 全链路解说脚本：单接口顺序触发四步（路由层与 visual 脚本接口隔离）。"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from modules.auth.omni_project_license import require_valid_license_for_omni
from modules.task_progress_store import task_progress_store
from omni_full_narration_pipeline import omni_full_narration_pipeline_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Omni 全链路解说脚本"])


def _now_ts() -> str:
    return datetime.now().isoformat()


class OmniFullNarrationPipelineRunRequest(BaseModel):
    force: bool = Field(default=False)
    task_id: Optional[str] = None
    skip_global_path_search: bool = Field(
        default=False,
        description="为 true 时不执行全局路径搜索；解说脚本步骤默认使用本链路镜头重排或项目已保存的候选 JSON，"
        "也可在 generate_script_options 中显式传入 input_global_path_web_path（若指定则须存在）",
    )
    copywriting_embed_options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="透传给文案结构化+向量 submit_run 的可选字段",
    )
    shot_match_options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="透传给镜头匹配 submit_run 的可选字段",
    )
    global_path_search_options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="透传给全局路径搜索 submit_run 的可选字段",
    )
    generate_script_options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="透传给解说脚本生成 submit_run 的可选字段",
    )


@router.post("/{project_id}/omni/full-narration-pipeline/run")
async def omni_full_narration_pipeline_run(
    project_id: str,
    request: Request,
    req: OmniFullNarrationPipelineRunRequest = Body(default=OmniFullNarrationPipelineRunRequest()),
):
    await require_valid_license_for_omni(request.headers.get("Authorization"))
    try:
        data = await omni_full_narration_pipeline_service.submit_run(
            project_id,
            force=bool(req.force),
            task_id=req.task_id,
            copywriting_embed_options=req.copywriting_embed_options,
            shot_match_options=req.shot_match_options,
            global_path_search_options=req.global_path_search_options,
            generate_script_options=req.generate_script_options,
            skip_global_path_search=True,
        )
        return {"message": "任务已提交", "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("omni full-narration-pipeline submit failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/omni/full-narration-pipeline/status/{task_id}")
async def omni_full_narration_pipeline_status(project_id: str, task_id: str):
    st = task_progress_store.get_state(omni_full_narration_pipeline_service.SCOPE, project_id, task_id)
    if not st:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "获取进度成功", "data": st, "timestamp": _now_ts()}
