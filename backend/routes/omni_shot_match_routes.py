#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni：本地 BGE 向量粗筛 + LLM 精排 + 连续性融合（独立路由）。"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from modules.projects_store import projects_store
from modules.task_progress_store import task_progress_store
from services.omni_shot_match_service import omni_shot_match_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Omni 镜头匹配与重排"])


def _now_ts() -> str:
    return datetime.now().isoformat()


class OmniShotMatchWeights(BaseModel):
    rerank_score: float = Field(default=0.55, ge=0.0, le=1.0)
    embedding_score: float = Field(default=0.30, ge=0.0, le=1.0)
    continuity_score: float = Field(default=0.15, ge=0.0, le=1.0)


class OmniShotMatchRunRequest(BaseModel):
    force: bool = Field(default=False)
    task_id: Optional[str] = None
    top_k: int = Field(default=20, ge=1, le=200)
    stage1_top_n: int = Field(default=10, ge=1, le=100)
    stage2_top_n: int = Field(default=3, ge=1, le=50)
    stage2_return_n: int = Field(default=3, ge=1, le=20)
    output_top_k: int = Field(default=0, ge=0, le=100, description="0 表示不截断；>0 时每条解说仅保留前 N 个镜头")
    concurrency: int = Field(default=32, ge=1, le=32)
    rerank_instruct: Optional[str] = Field(
        default=None,
        description="已废弃：粗排固定为本地向量分数，该字段将被忽略",
    )
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    weights: Optional[OmniShotMatchWeights] = None


@router.post("/{project_id}/omni/shot-match/run")
async def omni_shot_match_run(
    project_id: str,
    req: OmniShotMatchRunRequest = Body(default=OmniShotMatchRunRequest()),
):
    try:
        w = req.weights.model_dump() if req.weights else None
        data = await omni_shot_match_service.submit_run(
            project_id,
            force=bool(req.force),
            task_id=req.task_id,
            top_k=int(req.top_k),
            stage1_top_n=int(req.stage1_top_n),
            stage2_top_n=int(req.stage2_top_n),
            stage2_return_n=int(req.stage2_return_n),
            output_top_k=int(req.output_top_k),
            concurrency=int(req.concurrency),
            rerank_instruct=req.rerank_instruct,
            temperature=float(req.temperature),
            weights=w,
        )
        return {"message": "任务已提交", "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("omni shot-match submit failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/omni/shot-match/status/{task_id}")
async def omni_shot_match_status(project_id: str, task_id: str):
    st = task_progress_store.get_state(omni_shot_match_service.SCOPE, project_id, task_id)
    if not st:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "获取进度成功", "data": st, "timestamp": _now_ts()}


@router.get("/{project_id}/omni/shot-match/paths")
async def omni_shot_match_paths(project_id: str) -> Dict[str, Any]:
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "获取路径成功",
        "data": {
            "omni_shot_match_topk_path": getattr(p, "omni_shot_match_topk_path", None),
            "omni_shot_match_rerank_path": getattr(p, "omni_shot_match_rerank_path", None),
            "omni_shot_match_updated_at": getattr(p, "omni_shot_match_updated_at", None),
        },
        "timestamp": _now_ts(),
    }
