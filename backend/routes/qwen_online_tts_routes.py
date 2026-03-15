import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query

from modules.config.tts_config import tts_engine_config_manager
from modules.qwen_online_tts_service import qwen_online_tts_service
from modules.qwen_online_tts_voice_store import qwen_online_tts_voice_store

router = APIRouter(prefix="/api/tts/qwen-online", tags=["QwenOnlineTTS"])


def _resolve_active_qwen_online_config(config_id: Optional[str] = None):
    cfg = None
    if isinstance(config_id, str) and config_id.strip():
        cfg = tts_engine_config_manager.get_config(config_id.strip())
    if not cfg:
        cfg = tts_engine_config_manager.get_active_config()
    if not cfg or (cfg.provider or "").lower() != "qwen_online_tts":
        raise HTTPException(status_code=400, detail="active_provider_not_qwen_online_tts")
    return cfg


def _resolve_api_key(cfg) -> str:
    import os

    api_key = (os.getenv("DASHSCOPE_API_KEY") or (cfg.secret_key or "")).strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="missing_credentials")
    return api_key


def _resolve_base_url(cfg) -> str:
    ep = getattr(cfg, "extra_params", None) or {}
    base_url = str(ep.get("BaseUrl") or "").strip()
    region = (cfg.region or "cn").strip().lower()
    if base_url:
        return base_url.rstrip("/")
    return "https://dashscope-intl.aliyuncs.com/api/v1" if region in {"intl", "sg", "ap-singapore"} else "https://dashscope.aliyuncs.com/api/v1"


@router.get("/voices", summary="列出复刻音色")
async def list_clone_voices():
    data = [v.model_dump() for v in qwen_online_tts_voice_store.list()]
    return {"success": True, "data": data}


@router.get("/voices/{voice_id}", summary="获取复刻音色详情")
async def get_clone_voice(voice_id: str):
    v = qwen_online_tts_voice_store.get(str(voice_id))
    if not v:
        raise HTTPException(status_code=404, detail="voice_not_found")
    return {"success": True, "data": v.model_dump()}


@router.post("/voices/upload", summary="上传参考音频并创建复刻音色")
async def upload_clone_voice(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    ref_text: Optional[str] = Form(None),
    config_id: Optional[str] = Query(None),
):
    cfg = _resolve_active_qwen_online_config(config_id)
    api_key = _resolve_api_key(cfg)
    base_url = _resolve_base_url(cfg)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty_file")

    target_model = str(model or "").strip() or str((cfg.extra_params or {}).get("Model") or "qwen3-tts-vc-2026-01-22").strip() or "qwen3-tts-vc-2026-01-22"
    v = qwen_online_tts_voice_store.create_from_upload(
        upload_bytes=content,
        original_filename=file.filename or "voice",
        name=name,
        model=target_model,
        ref_text=ref_text,
    )
    qwen_online_tts_voice_store.set_progress(v.id, "cloning", 10, None)

    audio_mime = file.content_type or "audio/mpeg"
    preferred_name = str(v.name or "voice").strip() or "voice"
    enroll = await qwen_online_tts_service.create_clone_voice(
        upload_bytes=content,
        audio_mime_type=audio_mime,
        target_model=target_model,
        preferred_name=preferred_name,
        api_key=api_key,
        base_url=base_url,
        voice_prompt=ref_text,
    )
    if not enroll.get("success"):
        qwen_online_tts_voice_store.set_progress(v.id, "failed", 100, enroll.get("error") or "enroll_failed")
        v2 = qwen_online_tts_voice_store.get(v.id)
        return {"success": False, "data": v2.model_dump() if v2 else v.model_dump(), "error": enroll.get("error")}

    voice_token = str(enroll.get("voice") or "").strip()
    qwen_online_tts_voice_store.update(
        v.id,
        {
            "voice": voice_token,
            "status": "ready",
            "progress": 100,
            "last_error": None,
            "meta": {**(v.meta or {}), "enrolled_at": time.time()},
        },
    )
    v3 = qwen_online_tts_voice_store.get(v.id)
    return {"success": True, "data": v3.model_dump() if v3 else v.model_dump()}


@router.patch("/voices/{voice_id}", summary="更新复刻音色信息")
async def patch_clone_voice(
    voice_id: str,
    name: Optional[str] = Form(None),
    ref_text: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
):
    v = qwen_online_tts_voice_store.get(str(voice_id))
    if not v:
        raise HTTPException(status_code=404, detail="voice_not_found")
    updates: Dict[str, Any] = {}
    if isinstance(name, str) and name.strip():
        updates["name"] = name.strip()
    if isinstance(ref_text, str):
        updates["ref_text"] = ref_text.strip() or None
    if isinstance(model, str) and model.strip():
        if v.voice and (v.model or "").strip() != model.strip():
            raise HTTPException(status_code=400, detail="cannot_change_model_after_enroll")
        updates["model"] = model.strip()
    v2 = qwen_online_tts_voice_store.update(str(voice_id), updates) if updates else v
    return {"success": True, "data": v2.model_dump()}


@router.delete("/voices/{voice_id}", summary="删除复刻音色")
async def delete_clone_voice(voice_id: str, remove_files: bool = Query(False)):
    ok = qwen_online_tts_voice_store.delete(str(voice_id), remove_files=bool(remove_files))
    return {"success": bool(ok)}
