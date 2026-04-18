#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局运行日志路由
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from modules.runtime_log_store import runtime_log_store

router = APIRouter(tags=["运行日志"])


@router.get("/api/logs")
async def list_global_logs(
    after_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
):
    items = runtime_log_store.list(project_id=None, after_id=after_id, limit=limit)
    next_after_id = None
    try:
        next_after_id = int(items[-1]["id"]) if items else after_id
    except Exception:
        next_after_id = after_id
    return {
        "message": "获取日志成功",
        "data": {
            "items": items,
            "next_after_id": next_after_id,
        },
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/api/logs/clear")
async def clear_global_logs():
    runtime_log_store.clear(project_id=None)
    return {"message": "清空日志成功", "success": True, "timestamp": datetime.now().isoformat()}


@router.get("/api/logs/stream")
async def stream_global_logs(after_id: Optional[int] = Query(default=None)):
    async def _gen():
        items = runtime_log_store.list(project_id=None, after_id=after_id, limit=2000)
        for it in items:
            yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
        handle = runtime_log_store.subscribe(project_id=None)
        try:
            while True:
                try:
                    it = await asyncio.wait_for(handle.queue.get(), timeout=15)
                    yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ":keep-alive\n\n"
        finally:
            runtime_log_store.unsubscribe(handle)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    return StreamingResponse(_gen(), media_type="text/event-stream", headers=headers)
