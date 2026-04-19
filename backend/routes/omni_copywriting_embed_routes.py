#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni：解说文案结构化 + 向量化 API（独立路由，与 visual / 多模态管线隔离）"""

import logging
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from modules.projects_store import projects_store
from modules.task_progress_store import task_progress_store
from services.omni_copywriting_struct_embed_service import omni_copywriting_struct_embed_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Omni 文案结构化与向量化"])


def _now_ts() -> str:
    return datetime.now().isoformat()


class OmniCopywritingEmbedRunRequest(BaseModel):
    force: bool = Field(default=False)
    task_id: Optional[str] = None
    chunk_target_chars: int = Field(default=500, ge=200, le=8000)
    chunk_lookback_chars: int = Field(default=100, ge=0, le=2000)
    structuring_concurrency: int = Field(default=3, ge=1, le=16)
    embedding_concurrency: int = Field(default=8, ge=1, le=32)
    prompt_language: str = Field(default="zh", description="zh 或 en，对应 prompt_zh / prompt_en")
    continue_on_embedding_error: bool = Field(default=True)


@router.post("/{project_id}/omni/copywriting-struct-embed/run")
async def omni_copywriting_struct_embed_run(
    project_id: str,
    req: OmniCopywritingEmbedRunRequest = Body(default=OmniCopywritingEmbedRunRequest()),
):
    try:
        pl = str(req.prompt_language or "zh").strip().lower()
        if pl not in ("zh", "en"):
            raise ValueError("prompt_language 仅支持 zh 或 en")
        data = await omni_copywriting_struct_embed_service.submit_run(
            project_id,
            force=bool(req.force),
            task_id=req.task_id,
            chunk_target_chars=int(req.chunk_target_chars),
            chunk_lookback_chars=int(req.chunk_lookback_chars),
            structuring_concurrency=int(req.structuring_concurrency),
            embedding_concurrency=int(req.embedding_concurrency),
            prompt_language=pl,
            continue_on_embedding_error=bool(req.continue_on_embedding_error),
        )
        return {"message": "任务已提交", "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("omni copywriting struct-embed submit failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/omni/copywriting-struct-embed/status/{task_id}")
async def omni_copywriting_struct_embed_status(project_id: str, task_id: str):
    st = task_progress_store.get_state(omni_copywriting_struct_embed_service.SCOPE, project_id, task_id)
    if not st:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "获取进度成功", "data": st, "timestamp": _now_ts()}


@router.get("/{project_id}/omni/copywriting-struct-embed/paths")
async def omni_copywriting_struct_embed_paths(project_id: str) -> Dict[str, object]:
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "获取路径成功",
        "data": {
            "omni_copywriting_structured_path": getattr(p, "omni_copywriting_structured_path", None),
            "omni_copywriting_embeddings_path": getattr(p, "omni_copywriting_embeddings_path", None),
            "omni_copywriting_embed_updated_at": getattr(p, "omni_copywriting_embed_updated_at", None),
        },
        "timestamp": _now_ts(),
    }
