# -*- coding: utf-8 -*-
"""OmniVoice 局域网连接与转发 API（与 TTS 合成逻辑解耦，仅负责连接与音色管理）"""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
import logging

from modules.omnivoice_tts.client import (
    discover_omnivoice,
    post_clone_voice_delete,
    post_clone_voice_rename,
    post_clone_voice_select,
    probe_omnivoice,
    upload_clone_voice,
)
from modules.omnivoice_tts.connection_store import omnivoice_tts_connection_store
from modules.config.tts_config import tts_engine_config_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/omnivoice-tts", tags=["OmniVoice TTS"])


class OmniVoiceConnectRequest(BaseModel):
    host: str = Field(..., description="局域网 IP 或主机名，如 192.168.1.10")
    port: int = Field(8970, description="起始端口，默认 8970（与 omnivoice-api 一致）")
    api_prefix: str = Field("/api", description="API 前缀，默认 /api")
    scan_back: int = Field(10, description="若起始端口不可用，向前（端口号递减）扫描的额外端口数")


@router.post("/connect", summary="连接 OmniVoice 服务")
async def omnivoice_connect(req: OmniVoiceConnectRequest) -> Dict[str, Any]:
    host = (req.host or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="host 不能为空")

    api_p = (req.api_prefix or "/api").strip()
    if not api_p.startswith("/"):
        api_p = "/" + api_p

    discovered = await discover_omnivoice(
        host,
        start_port=int(req.port),
        scan_back=max(0, int(req.scan_back)),
        api_prefix=api_p,
    )
    if not discovered:
        omnivoice_tts_connection_store.set_failed("无法发现 OmniVoice 服务（请检查局域网与防火墙）")
        return {
            "success": False,
            "message": "连接失败：未在指定端口范围内发现 OmniVoice API",
            "data": {"host": host, "start_port": req.port, "scan_back": req.scan_back},
        }

    base_url, port = discovered
    ok, err = await probe_omnivoice(base_url, api_p)
    if not ok:
        omnivoice_tts_connection_store.set_failed(err or "probe_failed")
        return {
            "success": False,
            "message": f"连接失败：{err or '接口无响应'}",
            "data": {"base_url": base_url},
        }

    omnivoice_tts_connection_store.set_connected(
        base_url=base_url,
        api_prefix=api_p,
        host=host,
        port=port,
    )
    try:
        tts_engine_config_manager._voices_cache.pop("omnivoice_tts", None)
    except Exception:
        pass

    logger.info("OmniVoice 已连接: base_url=%s port=%s", base_url, port)
    return {
        "success": True,
        "message": "已连接 OmniVoice 服务",
        "data": {
            "base_url": base_url,
            "port": port,
            "api_prefix": api_p,
            "host": host,
        },
    }


@router.get("/status", summary="OmniVoice 连接状态")
async def omnivoice_status() -> Dict[str, Any]:
    st = omnivoice_tts_connection_store.get_state()
    alive: Optional[bool] = None
    err: Optional[str] = None
    if st.connected and st.base_url:
        ok, e = await probe_omnivoice(st.base_url, st.api_prefix)
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


@router.post("/disconnect", summary="断开 OmniVoice 连接状态")
async def omnivoice_disconnect() -> Dict[str, Any]:
    omnivoice_tts_connection_store.disconnect()
    try:
        tts_engine_config_manager._voices_cache.pop("omnivoice_tts", None)
    except Exception:
        pass
    return {"success": True, "message": "已断开"}


@router.get("/probe", summary="探测指定 URL 是否为 OmniVoice（调试用）")
async def omnivoice_probe(
    base_url: str = Query(..., description="完整 Base URL，如 http://192.168.1.5:8970"),
    api_prefix: str = Query("/api"),
) -> Dict[str, Any]:
    ok, err = await probe_omnivoice(base_url, api_prefix)
    return {"success": ok, "error": err}


class OmniVoiceCloneSelectRequest(BaseModel):
    voice_id: str = Field(..., description="克隆音色 ID")


class OmniVoiceCloneRenameRequest(BaseModel):
    voice_id: str = Field(..., description="克隆音色 ID")
    new_name: str = Field(..., description="新名称")


@router.post("/clone-voices/upload", summary="上传克隆音色（转发至 OmniVoice）")
async def omnivoice_clone_upload(
    file: UploadFile = File(..., description="音频文件"),
    name: Optional[str] = Form(None, description="显示名称；缺省使用上传文件名"),
) -> Dict[str, Any]:
    if not omnivoice_tts_connection_store.is_connected():
        raise HTTPException(status_code=400, detail="omnivoice_tts_not_connected")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty_file")
    fn = Path(file.filename or "upload.wav").name
    display_name = (name or "").strip() or fn
    try:
        payload = await upload_clone_voice(
            omnivoice_tts_connection_store.base_url(),
            omnivoice_tts_connection_store.api_prefix(),
            file_content=raw,
            filename=fn,
            display_name=display_name,
        )
    except Exception as e:
        logger.exception("OmniVoice 上传克隆音色失败")
        raise HTTPException(status_code=502, detail=str(e)) from e
    try:
        tts_engine_config_manager._voices_cache.pop("omnivoice_tts", None)
    except Exception:
        pass
    return {"success": True, "data": payload}


@router.post("/clone-voices/select", summary="选择默认克隆音色（转发至 OmniVoice）")
async def omnivoice_clone_select(req: OmniVoiceCloneSelectRequest) -> Dict[str, Any]:
    if not omnivoice_tts_connection_store.is_connected():
        raise HTTPException(status_code=400, detail="omnivoice_tts_not_connected")
    vid = (req.voice_id or "").strip()
    if not vid:
        raise HTTPException(status_code=400, detail="voice_id_required")
    try:
        payload = await post_clone_voice_select(
            omnivoice_tts_connection_store.base_url(),
            omnivoice_tts_connection_store.api_prefix(),
            vid,
        )
    except Exception as e:
        logger.exception("OmniVoice 选择音色失败")
        raise HTTPException(status_code=502, detail=str(e)) from e
    try:
        tts_engine_config_manager._voices_cache.pop("omnivoice_tts", None)
    except Exception:
        pass
    return {"success": True, "data": payload}


@router.post("/clone-voices/rename", summary="修改克隆音色名称（转发至 OmniVoice）")
async def omnivoice_clone_rename(req: OmniVoiceCloneRenameRequest) -> Dict[str, Any]:
    if not omnivoice_tts_connection_store.is_connected():
        raise HTTPException(status_code=400, detail="omnivoice_tts_not_connected")
    vid = (req.voice_id or "").strip()
    nn = (req.new_name or "").strip()
    if not vid or not nn:
        raise HTTPException(status_code=400, detail="voice_id_or_name_required")
    try:
        payload = await post_clone_voice_rename(
            omnivoice_tts_connection_store.base_url(),
            omnivoice_tts_connection_store.api_prefix(),
            vid,
            nn,
        )
    except Exception as e:
        logger.exception("OmniVoice 重命名音色失败")
        raise HTTPException(status_code=502, detail=str(e)) from e
    try:
        tts_engine_config_manager._voices_cache.pop("omnivoice_tts", None)
    except Exception:
        pass
    return {"success": True, "data": payload}


@router.post("/clone-voices/delete", summary="删除克隆音色（转发至 OmniVoice）")
async def omnivoice_clone_delete(req: OmniVoiceCloneSelectRequest) -> Dict[str, Any]:
    if not omnivoice_tts_connection_store.is_connected():
        raise HTTPException(status_code=400, detail="omnivoice_tts_not_connected")
    vid = (req.voice_id or "").strip()
    if not vid:
        raise HTTPException(status_code=400, detail="voice_id_required")
    try:
        payload = await post_clone_voice_delete(
            omnivoice_tts_connection_store.base_url(),
            omnivoice_tts_connection_store.api_prefix(),
            vid,
        )
    except Exception as e:
        logger.exception("OmniVoice 删除音色失败")
        raise HTTPException(status_code=502, detail=str(e)) from e
    try:
        tts_engine_config_manager._voices_cache.pop("omnivoice_tts", None)
    except Exception:
        pass
    return {"success": True, "data": payload}
