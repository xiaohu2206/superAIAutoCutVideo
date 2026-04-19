#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni：全局路径搜索（独立路由，与 shot-match 分离）。"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from modules.projects_store import projects_store
from modules.task_progress_store import task_progress_store
from services.omni_global_path_search_service import omni_global_path_search_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Omni 全局路径搜索"])


def _now_ts() -> str:
    return datetime.now().isoformat()


class OmniGlobalPathSearchRunRequest(BaseModel):
    force: bool = Field(default=False)
    task_id: Optional[str] = None
    input_rerank_web_path: Optional[str] = Field(
        default=None,
        description="覆盖项目上的 omni_shot_match_rerank_path；默认使用项目已保存的 rerank.json Web 路径",
    )
    search_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="与 aiSearchShot Step4.8 一致的可选参数（candidate_top_k、beam 宽度、开关等），未传字段用内置默认",
    )


@router.post("/{project_id}/omni/global-path-search/run")
async def omni_global_path_search_run(
    project_id: str,
    req: OmniGlobalPathSearchRunRequest = Body(default=OmniGlobalPathSearchRunRequest()),
):
    try:
        data = await omni_global_path_search_service.submit_run(
            project_id,
            force=bool(req.force),
            task_id=req.task_id,
            input_rerank_web_path=req.input_rerank_web_path,
            search_params=req.search_params,
        )
        return {"message": "任务已提交", "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("omni global-path-search submit failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/omni/global-path-search/status/{task_id}")
async def omni_global_path_search_status(project_id: str, task_id: str):
    st = task_progress_store.get_state(omni_global_path_search_service.SCOPE, project_id, task_id)
    if not st:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "获取进度成功", "data": st, "timestamp": _now_ts()}


@router.get("/{project_id}/omni/global-path-search/paths")
async def omni_global_path_search_paths(project_id: str) -> Dict[str, Any]:
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "获取路径成功",
        "data": {
            "omni_global_path_search_path": getattr(p, "omni_global_path_search_path", None),
            "omni_global_path_search_updated_at": getattr(p, "omni_global_path_search_updated_at", None),
            "omni_shot_match_rerank_path": getattr(p, "omni_shot_match_rerank_path", None),
        },
        "timestamp": _now_ts(),
    }
