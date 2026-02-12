from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from modules.config.generate_concurrency_config import generate_concurrency_config_manager
from modules.task_scheduler import task_scheduler


router = APIRouter(prefix="/api/generate", tags=["生成设置"])


def now_ts() -> str:
    return datetime.now().isoformat()


class ScopeConcurrencyPatch(BaseModel):
    max_workers: Optional[int] = Field(default=None, ge=1)
    override: Optional[bool] = None


class UpdateGenerateConcurrencyRequest(BaseModel):
    generate_video: Optional[ScopeConcurrencyPatch] = None
    generate_jianying_draft: Optional[ScopeConcurrencyPatch] = None
    allow_same_project_parallel: Optional[bool] = None


@router.get("/concurrency")
async def get_generate_concurrency() -> Dict[str, Any]:
    snap = generate_concurrency_config_manager.snapshot()
    return {"message": "ok", "data": snap, "timestamp": now_ts()}


@router.put("/concurrency")
async def update_generate_concurrency(req: UpdateGenerateConcurrencyRequest = Body(...)) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if req.generate_video is not None:
        payload["generate_video"] = {
            **(generate_concurrency_config_manager.config.generate_video.model_dump()),
            **{k: v for k, v in req.generate_video.model_dump().items() if v is not None},
        }
    if req.generate_jianying_draft is not None:
        payload["generate_jianying_draft"] = {
            **(generate_concurrency_config_manager.config.generate_jianying_draft.model_dump()),
            **{k: v for k, v in req.generate_jianying_draft.model_dump().items() if v is not None},
        }
    if req.allow_same_project_parallel is not None:
        payload["allow_same_project_parallel"] = bool(req.allow_same_project_parallel)

    snap = generate_concurrency_config_manager.update(payload)
    return {"message": "updated", "data": snap, "timestamp": now_ts()}


class ResizeRequest(BaseModel):
    scopes: Optional[List[str]] = None


@router.post("/concurrency/resize")
async def resize_generate_concurrency(req: ResizeRequest = Body(default=ResizeRequest())) -> Dict[str, Any]:
    scopes = req.scopes or ["generate_video", "generate_jianying_draft"]
    allowed = {"generate_video", "generate_jianying_draft"}
    for s in scopes:
        if s not in allowed:
            raise HTTPException(status_code=400, detail=f"不支持的 scope: {s}")
    for s in scopes:
        max_workers, _src = generate_concurrency_config_manager.get_effective(s)  # type: ignore[arg-type]
        await task_scheduler.resize(s if s != "generate_jianying_draft" else "generate_jianying_draft", int(max_workers or 1))
    return {"message": "resized", "data": {"scopes": scopes}, "timestamp": now_ts()}

