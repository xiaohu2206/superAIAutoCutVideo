#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

from modules.config.jianying_config import jianying_config_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jianying", tags=["剪映配置"])


class DraftPathUpdateRequest(BaseModel):
    path: str = Field(..., description="剪映草稿存放目录")


@router.get("/draft-path", summary="获取剪映草稿路径配置")
async def get_draft_path():
    try:
        p = jianying_config_manager.get_draft_path()
        return {
            "success": True,
            "data": {
                "path": (str(p) if p else None),
                "exists": (bool(p and p.exists()))
            },
            "message": "获取剪映草稿路径成功"
        }
    except Exception as e:
        logger.error(f"获取剪映草稿路径失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/draft-path", summary="更新剪映草稿路径（实时保存）")
async def update_draft_path(req: DraftPathUpdateRequest):
    try:
        ok = jianying_config_manager.set_draft_path(req.path)
        if not ok:
            return {"success": False, "message": "保存失败"}
        p = jianying_config_manager.get_draft_path()
        return {
            "success": True,
            "data": {
                "path": (str(p) if p else None),
                "exists": (bool(p and p.exists()))
            },
            "message": "保存成功"
        }
    except Exception as e:
        logger.error(f"更新剪映草稿路径失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect-draft-path", summary="自动查找剪映草稿路径")
async def detect_draft_path():
    try:
        candidates = jianying_config_manager.auto_detect_draft_paths()
        selected = candidates[0] if candidates else None
        return {
            "success": True,
            "data": {
                "candidates": candidates,
                "selected": selected
            },
            "message": f"找到 {len(candidates)} 个候选路径" if candidates else "未找到候选路径"
        }
    except Exception as e:
        logger.error(f"自动查找剪映草稿路径失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
