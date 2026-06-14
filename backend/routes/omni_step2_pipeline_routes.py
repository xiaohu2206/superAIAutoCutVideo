#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni Step2 管线参数配置 API（本地模型低并发模式）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from modules.config.omni_step2_pipeline_config import (
    OmniStep2LocalSettings,
    omni_step2_pipeline_config_manager,
)

router = APIRouter(prefix="/api/models", tags=["模型配置"])


def _now_ts() -> str:
    return datetime.now().isoformat()


class OmniStep2LocalPatch(BaseModel):
    vl_batch_size: Optional[int] = Field(default=None, ge=1, le=32)
    infer_wall_sec: Optional[int] = Field(default=None, ge=30, le=7200)
    vision_api_concurrency: Optional[int] = Field(default=None, ge=1, le=64)
    text_api_concurrency: Optional[int] = Field(default=None, ge=1, le=64)
    api_concurrency: Optional[int] = Field(default=None, ge=1, le=64, exclude=True)


class OmniStep2PipelineUpdateRequest(BaseModel):
    use_local_vision_model: Optional[bool] = None
    use_local_text_model: Optional[bool] = None
    use_local_model_pipeline: Optional[bool] = Field(default=None, exclude=True)
    local: Optional[OmniStep2LocalPatch] = None


@router.get("/omni-step2-pipeline")
async def get_omni_step2_pipeline_config() -> Dict[str, Any]:
    snap = omni_step2_pipeline_config_manager.snapshot()
    return {"success": True, "data": snap, "timestamp": _now_ts()}


@router.put("/omni-step2-pipeline")
async def update_omni_step2_pipeline_config(
    req: OmniStep2PipelineUpdateRequest = Body(...),
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if req.use_local_vision_model is not None:
        payload["use_local_vision_model"] = req.use_local_vision_model
    if req.use_local_text_model is not None:
        payload["use_local_text_model"] = req.use_local_text_model
    if req.use_local_model_pipeline is not None:
        payload["use_local_model_pipeline"] = req.use_local_model_pipeline
    if req.local is not None:
        cur_local = omni_step2_pipeline_config_manager.get_root().local
        local_patch = req.local.model_dump(exclude_none=True, exclude={"api_concurrency"})
        if req.local.api_concurrency is not None:
            local_patch.setdefault("vision_api_concurrency", req.local.api_concurrency)
            local_patch.setdefault("text_api_concurrency", req.local.api_concurrency)
        merged = {
            **cur_local.model_dump(),
            **local_patch,
        }
        payload["local"] = OmniStep2LocalSettings(**merged).model_dump()
    snap = omni_step2_pipeline_config_manager.update(payload)
    return {"success": True, "data": snap, "timestamp": _now_ts()}
