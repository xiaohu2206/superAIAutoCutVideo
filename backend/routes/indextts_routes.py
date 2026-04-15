# -*- coding: utf-8 -*-
"""IndexTTS 局域网连接与状态 API（与 TTS 合成逻辑解耦，仅负责连接握手）"""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
import logging

from modules.indextts.client import (
    discover_indextts,
    post_clone_voice_delete,
    post_clone_voice_select,
    probe_indextts,
    upload_clone_voice,
)
from modules.indextts.connection_store import indextts_connection_store
from modules.config.tts_config import tts_engine_config_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/indextts", tags=["IndexTTS"])


class IndexTTSConnectRequest(BaseModel):
    host: str = Field(..., description="局域网 IP 或主机名，如 192.168.1.10")
    port: int = Field(7860, description="起始端口，默认 7860")
    api_prefix: str = Field("/api", description="API 前缀，默认 /api")
    scan_back: int = Field(10, description="若起始端口不可用，向前（端口号递减）扫描的额外端口数")


@router.post("/connect", summary="连接 IndexTTS 服务")
async def indextts_connect(req: IndexTTSConnectRequest) -> Dict[str, Any]:
    host = (req.host or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="host 不能为空")

    api_p = (req.api_prefix or "/api").strip()
    if not api_p.startswith("/"):
        api_p = "/" + api_p

    discovered = await discover_indextts(
        host,
        start_port=int(req.port),
        scan_back=max(0, int(req.scan_back)),
        api_prefix=api_p,
    )
    if not discovered:
        indextts_connection_store.set_failed("无法发现 IndexTTS 服务（请检查局域网与防火墙）")
        return {
            "success": False,
            "message": "连接失败：未在指定端口范围内发现 IndexTTS API",
            "data": {"host": host, "start_port": req.port, "scan_back": req.scan_back},
        }

    base_url, port = discovered
    ok, err = await probe_indextts(base_url, api_p)
    if not ok:
        indextts_connection_store.set_failed(err or "probe_failed")
        return {
            "success": False,
            "message": f"连接失败：{err or '接口无响应'}",
            "data": {"base_url": base_url},
        }

    indextts_connection_store.set_connected(
        base_url=base_url,
        api_prefix=api_p,
        host=host,
        port=port,
    )
    try:
        tts_engine_config_manager._voices_cache.pop("indextts", None)
    except Exception:
        pass

    logger.info("IndexTTS 已连接: base_url=%s port=%s", base_url, port)
    return {
        "success": True,
        "message": "已连接 IndexTTS 服务",
        "data": {
            "base_url": base_url,
            "port": port,
            "api_prefix": api_p,
            "host": host,
        },
    }


@router.get("/status", summary="IndexTTS 连接状态")
async def indextts_status() -> Dict[str, Any]:
    st = indextts_connection_store.get_state()
    alive: Optional[bool] = None
    err: Optional[str] = None
    if st.connected and st.base_url:
        ok, e = await probe_indextts(st.base_url, st.api_prefix)
        alive = ok
        err = e
    return {
        "success": True,
        "data": {
            "connected": bool(st.connected),
            "base_url": st.base_url,
            "api_prefix": st.api_prefix,
            "host": st.host,
            "port": st.port,
            "last_error": st.last_error,
            "reachable": alive,
            "probe_error": err,
        },
    }


@router.post("/disconnect", summary="断开 IndexTTS 连接状态")
async def indextts_disconnect() -> Dict[str, Any]:
    indextts_connection_store.disconnect()
    try:
        tts_engine_config_manager._voices_cache.pop("indextts", None)
    except Exception:
        pass
    return {"success": True, "message": "已断开"}


@router.get("/probe", summary="探测指定 URL 是否为 IndexTTS（调试用）")
async def indextts_probe(
    base_url: str = Query(..., description="完整 Base URL，如 http://192.168.1.5:7860"),
    api_prefix: str = Query("/api"),
) -> Dict[str, Any]:
    ok, err = await probe_indextts(base_url, api_prefix)
    return {"success": ok, "error": err}


class IndexTTSCloneSelectRequest(BaseModel):
    voice_id: str = Field(..., description="克隆音色 ID")


@router.post("/clone-voices/upload", summary="上传克隆音色（转发至 IndexTTS）")
async def indextts_clone_upload(
    file: UploadFile = File(..., description="音频文件"),
    name: Optional[str] = Form(None, description="显示名称；缺省使用上传文件名"),
) -> Dict[str, Any]:
    if not indextts_connection_store.is_connected():
        raise HTTPException(status_code=400, detail="indextts_not_connected")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty_file")
    fn = Path(file.filename or "upload.wav").name
    display_name = (name or "").strip() or fn
    try:
        payload = await upload_clone_voice(
            indextts_connection_store.base_url(),
            indextts_connection_store.api_prefix(),
            file_content=raw,
            filename=fn,
            display_name=display_name,
        )
    except Exception as e:
        logger.exception("IndexTTS 上传克隆音色失败")
        raise HTTPException(status_code=502, detail=str(e)) from e
    try:
        tts_engine_config_manager._voices_cache.pop("indextts", None)
    except Exception:
        pass
    return {"success": True, "data": payload}


@router.post("/clone-voices/select", summary="选择默认克隆音色（转发至 IndexTTS）")
async def indextts_clone_select(req: IndexTTSCloneSelectRequest) -> Dict[str, Any]:
    if not indextts_connection_store.is_connected():
        raise HTTPException(status_code=400, detail="indextts_not_connected")
    vid = (req.voice_id or "").strip()
    if not vid:
        raise HTTPException(status_code=400, detail="voice_id_required")
    try:
        payload = await post_clone_voice_select(
            indextts_connection_store.base_url(),
            indextts_connection_store.api_prefix(),
            vid,
        )
    except Exception as e:
        logger.exception("IndexTTS 选择音色失败")
        raise HTTPException(status_code=502, detail=str(e)) from e
    try:
        tts_engine_config_manager._voices_cache.pop("indextts", None)
    except Exception:
        pass
    return {"success": True, "data": payload}


@router.post("/clone-voices/delete", summary="删除克隆音色（转发至 IndexTTS）")
async def indextts_clone_delete(req: IndexTTSCloneSelectRequest) -> Dict[str, Any]:
    if not indextts_connection_store.is_connected():
        raise HTTPException(status_code=400, detail="indextts_not_connected")
    vid = (req.voice_id or "").strip()
    if not vid:
        raise HTTPException(status_code=400, detail="voice_id_required")
    try:
        payload = await post_clone_voice_delete(
            indextts_connection_store.base_url(),
            indextts_connection_store.api_prefix(),
            vid,
        )
    except Exception as e:
        logger.exception("IndexTTS 删除音色失败")
        raise HTTPException(status_code=502, detail=str(e)) from e
    try:
        tts_engine_config_manager._voices_cache.pop("indextts", None)
    except Exception:
        pass
    return {"success": True, "data": payload}
