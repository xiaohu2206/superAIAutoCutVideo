#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS引擎与音色配置API路由
提供TTS引擎元数据、音色列表、配置管理、激活与测试接口。
"""

from typing import Dict, Optional, Any
import asyncio
import time
import tempfile
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
import logging

from modules.config.tts_config import (
    TtsEngineConfig,
    tts_engine_config_manager,
)

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/tts", tags=["TTS配置"])

_preview_cache_lock = asyncio.Lock()
_preview_cache: Dict[str, Dict[str, Any]] = {}
_preview_cache_ttl_sec = 180
_preview_cache_max_items = 128
_preview_cache_max_bytes = 15 * 1024 * 1024
_preview_eviction_tasks: Dict[str, asyncio.Task] = {}


def _guess_audio_media_type(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".mp3"):
        return "audio/mpeg"
    if name.endswith(".wav"):
        return "audio/wav"
    if name.endswith(".ogg"):
        return "audio/ogg"
    if name.endswith(".m4a") or name.endswith(".mp4"):
        return "audio/mp4"
    if name.endswith(".aac"):
        return "audio/aac"
    if name.endswith(".flac"):
        return "audio/flac"
    return "application/octet-stream"


def _get_preview_tmp_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "sacv_tts_previews"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


async def _preview_cache_cleanup(now_ts: Optional[float] = None) -> None:
    now = float(now_ts if now_ts is not None else time.time())
    expired = []
    for k, v in list(_preview_cache.items()):
        try:
            created_at = float(v.get("created_at") or 0)
        except Exception:
            created_at = 0.0
        try:
            delete_at = float(v.get("delete_at") or 0)
        except Exception:
            delete_at = 0.0
        if (delete_at and now >= delete_at) or created_at <= 0 or now - created_at > _preview_cache_ttl_sec:
            expired.append(k)
    for k in expired:
        _preview_cache.pop(k, None)
        t = _preview_eviction_tasks.pop(k, None)
        if t:
            try:
                t.cancel()
            except Exception:
                pass

    if len(_preview_cache) <= _preview_cache_max_items:
        return

    items = []
    for k, v in _preview_cache.items():
        try:
            items.append((k, float(v.get("created_at") or 0)))
        except Exception:
            items.append((k, 0.0))
    items.sort(key=lambda x: x[1])
    for k, _ in items[: max(0, len(_preview_cache) - _preview_cache_max_items)]:
        _preview_cache.pop(k, None)
        t = _preview_eviction_tasks.pop(k, None)
        if t:
            try:
                t.cancel()
            except Exception:
                pass


def _schedule_preview_eviction(preview_id: str, delay_sec: float) -> None:
    pid = str(preview_id)
    delay = max(0.0, float(delay_sec))
    old = _preview_eviction_tasks.get(pid)
    if old:
        try:
            old.cancel()
        except Exception:
            pass

    async def _job() -> None:
        try:
            await asyncio.sleep(delay)
            async with _preview_cache_lock:
                _preview_cache.pop(pid, None)
                _preview_eviction_tasks.pop(pid, None)
        except asyncio.CancelledError:
            return
        except Exception:
            async with _preview_cache_lock:
                _preview_eviction_tasks.pop(pid, None)

    try:
        _preview_eviction_tasks[pid] = asyncio.create_task(_job())
    except Exception:
        pass


async def _preview_cache_put(content: bytes, filename: str, meta: Optional[Dict[str, Any]] = None) -> str:
    data = bytes(content)
    if len(data) > _preview_cache_max_bytes:
        raise HTTPException(status_code=413, detail="试听音频过大")

    preview_id = uuid.uuid4().hex
    entry = {
        "content": data,
        "filename": filename,
        "media_type": _guess_audio_media_type(filename),
        "created_at": time.time(),
        "delete_at": None,
        "meta": meta or {},
    }
    async with _preview_cache_lock:
        await _preview_cache_cleanup(float(entry["created_at"]))
        _preview_cache[preview_id] = entry
        _schedule_preview_eviction(preview_id, _preview_cache_ttl_sec)
    return preview_id


@router.get("/voices/preview/{preview_id}", summary="获取试听音频（一次性）")
async def get_voice_preview(preview_id: str, request: Request):
    pid = str(preview_id)
    async with _preview_cache_lock:
        await _preview_cache_cleanup()
        entry = _preview_cache.get(pid)
        if entry and not entry.get("delete_at"):
            entry["delete_at"] = time.time() + 30
            _schedule_preview_eviction(pid, 30)
    if not entry:
        raise HTTPException(status_code=404, detail="试听音频不存在或已过期")
    content: bytes = entry.get("content") or b""
    total = len(content)
    filename = str(entry.get("filename") or "preview.audio")
    media_type = str(entry.get("media_type") or "application/octet-stream")
    headers: Dict[str, str] = {
        "Content-Disposition": f'inline; filename="{filename}"',
        "Accept-Ranges": "bytes",
    }

    rng = request.headers.get("range") or request.headers.get("Range")
    if rng and rng.strip().lower().startswith("bytes="):
        spec = rng.strip()[6:]
        if "," in spec:
            spec = spec.split(",", 1)[0]
        start_s, end_s = (spec.split("-", 1) + [""])[:2]
        try:
            start = int(start_s) if start_s.strip() else None
            end = int(end_s) if end_s.strip() else None
        except Exception:
            start = None
            end = None

        if start is None and end is not None:
            start = max(0, total - end)
            end = total - 1
        if start is None:
            start = 0
        if end is None or end >= total:
            end = total - 1
        if start < 0:
            start = 0
        if end < start or total <= 0:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})

        chunk = content[start:end + 1]
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        headers["Content-Length"] = str(len(chunk))
        return Response(content=chunk, status_code=206, media_type=media_type, headers=headers)

    headers["Content-Length"] = str(total)
    return Response(content=content, media_type=media_type, headers=headers)


@router.delete("/voices/preview/{preview_id}", summary="删除试听音频缓存")
async def delete_voice_preview(preview_id: str):
    async with _preview_cache_lock:
        removed = _preview_cache.pop(str(preview_id), None)
    return {"success": bool(removed)}


def safe_tts_config_dict_hide_secret(config: TtsEngineConfig) -> Dict[str, Any]:
    """将配置转换为字典并隐藏敏感字段"""
    d = config.dict()
    if 'secret_id' in d and d['secret_id']:
        d['secret_id'] = "***"
    if 'secret_key' in d and d['secret_key']:
        d['secret_key'] = "***"
    return d


class TtsConfigUpdateRequest(BaseModel):
    """TTS配置局部更新请求"""
    provider: Optional[str] = Field(None, description="提供商标识")
    secret_id: Optional[str] = Field(None, description="SecretId")
    secret_key: Optional[str] = Field(None, description="SecretKey")
    region: Optional[str] = Field(None, description="区域")
    description: Optional[str] = Field(None, description="配置说明")
    enabled: Optional[bool] = Field(None, description="是否启用")
    active_voice_id: Optional[str] = Field(None, description="激活音色ID")
    speed_ratio: Optional[float] = Field(None, description="语速倍率")
    extra_params: Optional[Dict[str, Any]] = Field(None, description="扩展参数")


@router.get("/engines", summary="获取TTS引擎列表")
async def get_tts_engines():
    try:
        engines = tts_engine_config_manager.get_engines_meta()
        return {"success": True, "data": engines, "message": f"获取到 {len(engines)} 个TTS引擎"}
    except Exception as e:
        logger.error(f"获取TTS引擎列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voices", summary="获取音色列表")
async def get_tts_voices(provider: str = Query(..., description="提供商标识，如tencent_tts")):
    try:
        voices = await tts_engine_config_manager.get_voices_async(provider)
        data = []
        for v in voices:
            d = v.dict()
            d.update({
                "VoiceName": v.name,
                "VoiceDesc": v.description,
                "VoiceQuality": v.voice_quality,
                "VoiceTypeTag": v.voice_type_tag,
                "VoiceHumanStyle": v.voice_human_style,
                "VoiceGender": v.gender,
            })
            data.append(d)
        return {
            "success": True,
            "data": data,
            "message": f"获取到 {len(voices)} 个音色"
        }
    except Exception as e:
        logger.error(f"获取音色列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs", summary="获取TTS配置与激活状态")
async def get_tts_configs():
    try:
        configs = tts_engine_config_manager.get_all_configs()
        active_config_id = tts_engine_config_manager.get_active_config_id()
        config_data = {cid: safe_tts_config_dict_hide_secret(cfg) for cid, cfg in configs.items()}
        return {
            "success": True,
            "data": {
                "configs": config_data,
                "active_config_id": active_config_id
            },
            "message": f"获取到 {len(configs)} 个TTS配置"
        }
    except Exception as e:
        logger.error(f"获取TTS配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/configs/{config_id}", summary="更新TTS配置（实时保存）")
async def patch_tts_config(config_id: str, req: TtsConfigUpdateRequest):
    try:
        current = tts_engine_config_manager.get_config(config_id)
        if not current:
            # 若不存在则创建（提供商缺省为tencent_tts）
            provider = (req.provider or 'tencent_tts')
            vt_val = None
            if isinstance(req.extra_params, dict) and 'VoiceType' in req.extra_params:
                try:
                    vt_val = int(req.extra_params['VoiceType'])
                except Exception:
                    vt_val = None
            if vt_val is None and req.active_voice_id is not None:
                aid = str(req.active_voice_id)
                if aid.isdigit():
                    vt_val = int(aid)
                else:
                    voices = tts_engine_config_manager.get_voices(provider)
                    m = next((v for v in voices if v.id == aid or v.name == aid), None)
                    if m and isinstance(m.voice_type, int):
                        vt_val = m.voice_type
            extra_params = (req.extra_params or {})
            if vt_val is not None:
                extra_params = dict(extra_params)
                extra_params['VoiceType'] = vt_val
                voices = tts_engine_config_manager.get_voices(provider)
                mv = next((v for v in voices if isinstance(v.voice_type, int) and v.voice_type == vt_val), None)
                if mv:
                    extra_params['VoiceName'] = mv.name
                    extra_params['VoiceDesc'] = mv.description
                    extra_params['VoiceQuality'] = mv.voice_quality
                    extra_params['VoiceTypeTag'] = mv.voice_type_tag
                    extra_params['VoiceHumanStyle'] = mv.voice_human_style
                    extra_params['VoiceGender'] = mv.gender
            base = TtsEngineConfig(
                provider=provider,
                secret_id=(req.secret_id.strip() if isinstance(req.secret_id, str) else req.secret_id),
                secret_key=(req.secret_key.strip() if isinstance(req.secret_key, str) else req.secret_key),
                region=req.region or 'ap-guangzhou',
                description=req.description,
                enabled=bool(req.enabled),
                active_voice_id=req.active_voice_id,
                speed_ratio=req.speed_ratio or 1.0,
                extra_params=extra_params
            )
            ok = tts_engine_config_manager.update_config(config_id, base)
        else:
            # 局部更新
            update_data: Dict[str, Any] = {}
            for field in req.__fields__:
                val = getattr(req, field)
                if val is not None:
                    if field in ['secret_id', 'secret_key'] and isinstance(val, str):
                        update_data[field] = val.strip()
                    else:
                        update_data[field] = val
            provider = (update_data.get('provider') or (current.provider if current else 'tencent_tts'))
            vt_val = None
            ep_in = update_data.get('extra_params') if isinstance(update_data.get('extra_params'), dict) else None
            if ep_in and 'VoiceType' in ep_in:
                try:
                    vt_val = int(ep_in['VoiceType'])
                except Exception:
                    vt_val = None
            if vt_val is None:
                aid_val = update_data.get('active_voice_id') if update_data.get('active_voice_id') is not None else current.active_voice_id
                if aid_val is not None:
                    aid_s = str(aid_val)
                    if aid_s.isdigit():
                        vt_val = int(aid_s)
                    else:
                        voices = await tts_engine_config_manager.get_voices_async(provider)
                        m = next((v for v in voices if v.id == aid_s or v.name == aid_s), None)
                        if m and isinstance(m.voice_type, int):
                            vt_val = m.voice_type
            if vt_val is not None:
                merged_ep = dict(current.extra_params or {})
                if isinstance(update_data.get('extra_params'), dict):
                    merged_ep.update(update_data['extra_params'])
                merged_ep['VoiceType'] = vt_val
                voices = await tts_engine_config_manager.get_voices_async(provider)
                mv = next((v for v in voices if isinstance(v.voice_type, int) and v.voice_type == vt_val), None)
                if mv:
                    merged_ep['VoiceName'] = mv.name
                    merged_ep['VoiceDesc'] = mv.description
                    merged_ep['VoiceQuality'] = mv.voice_quality
                    merged_ep['VoiceTypeTag'] = mv.voice_type_tag
                    merged_ep['VoiceHumanStyle'] = mv.voice_human_style
                    merged_ep['VoiceGender'] = mv.gender
                update_data['extra_params'] = merged_ep
            new_config = current.copy(update=update_data)
            ok = tts_engine_config_manager.update_config(config_id, new_config)

        if not ok:
            return {"success": False, "message": "更新失败"}

        updated = tts_engine_config_manager.get_config(config_id)
        if not updated:
            raise HTTPException(status_code=404, detail="配置不存在")
        return {
            "success": True,
            "data": safe_tts_config_dict_hide_secret(updated),
            "message": "更新成功"
        }
    except Exception as e:
        logger.error(f"更新TTS配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/{config_id}/activate", summary="激活指定TTS配置")
async def activate_tts_config(config_id: str):
    try:
        current = tts_engine_config_manager.get_config(config_id)
        if not current:
            raise HTTPException(status_code=404, detail=f"配置 '{config_id}' 不存在")
        new_config = current.copy(update={"enabled": True})
        ok = tts_engine_config_manager.update_config(config_id, new_config)
        if not ok:
            return {"success": False, "message": "激活失败"}
        return {"success": True, "message": f"已激活配置 {config_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"激活TTS配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TtsTestRequest(BaseModel):
    config_id: str = Field(..., description="配置ID")


@router.post("/configs/{config_id}/test", summary="测试TTS引擎连通性")
async def test_tts_connection(config_id: str, proxy_url: Optional[str] = Query(None, description="可选代理URL，覆盖EDGE_TTS_PROXY")):
    try:
        result = await tts_engine_config_manager.test_connection(config_id, proxy_url)
        return {"success": result.get('success', False), "data": result}
    except Exception as e:
        logger.error(f"测试TTS连接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class VoicePreviewRequest(BaseModel):
    text: Optional[str] = Field(None, description="试听文本")
    language: Optional[str] = Field(None, description="语言代码（如 chinese, english 或 zh, en）")
    provider: Optional[str] = Field(None, description="提供商标识，默认使用激活配置")
    config_id: Optional[str] = Field(None, description="使用指定配置")


@router.post("/voices/{voice_id}/preview", summary="音色试听（返回示例wav链接）")
async def preview_voice(voice_id: str, req: VoicePreviewRequest):
    try:
        cfg_by_id = None
        if isinstance(req.config_id, str) and req.config_id.strip():
            cfg_by_id = tts_engine_config_manager.get_config(req.config_id.strip())

        active_cfg = tts_engine_config_manager.get_active_config()

        if cfg_by_id:
            provider = cfg_by_id.provider
        else:
            provider = (req.provider or (active_cfg.provider if active_cfg else "tencent_tts"))

        cfg = (
            cfg_by_id
            if (cfg_by_id and cfg_by_id.provider == provider)
            else (
                active_cfg
                if (active_cfg and active_cfg.provider == provider)
                else (cfg_by_id or active_cfg)
            )
        )
        voices = await tts_engine_config_manager.get_voices_async(provider)
        match = next((v for v in voices if v.id == voice_id), None)
        # Edge TTS：若缓存列表未包含该音色，仍允许尝试合成（避免误报不存在）
        if provider == 'edge_tts':
            try:
                from modules.edge_tts_service import edge_tts_service
                vid = (match.id if match else voice_id)
                raw_voices = await edge_tts_service.list_voices()
                wanted = str(vid).lower()

                def _raw_voice_match(v: Any, wanted_id: str) -> bool:
                    if not isinstance(v, dict):
                        return False
                    v_id = v.get("id")
                    v_name = v.get("name")
                    if isinstance(v_id, str) and v_id.lower() == wanted_id:
                        return True
                    if isinstance(v_name, str) and v_name.lower() == wanted_id:
                        return True
                    return False

                found_raw = next((v for v in raw_voices if _raw_voice_match(v, wanted)), None)
                if found_raw:
                    vid = found_raw.get("id", vid)
                ts = int(time.time() * 1000)
                safe_vid = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in str(vid))[:64]
                filename = f"edge_{safe_vid}_preview_{ts}.mp3"
                out_path = _get_preview_tmp_dir() / filename

                # 文本使用请求或默认（前端写死即可，这里保持回退）
                lang = (match.language if match else (found_raw.get("language") if isinstance(found_raw, dict) else None)) or ""
                prefix = (lang.lower().split("-")[0] if isinstance(lang, str) else "")
                default_map = {
                    "zh": "您好，欢迎使用智能配音。",
                    "en": "Hello, welcome to smart voiceover.",
                    "ja": "こんにちは、スマート音声合成へようこそ。",
                    "ko": "안녕하세요, 스마트 보이스오버에 오신 것을 환영합니다.",
                    "es": "Hola, bienvenido al doblaje inteligente.",
                    "fr": "Bonjour, bienvenue sur la voix off intelligente.",
                    "de": "Hallo, willkommen bei der intelligenten Sprachsynthese.",
                    "ru": "Здравствуйте, добро пожаловать в интеллектуальное озвучивание.",
                    "it": "Ciao, benvenuto nel doppiaggio intelligente.",
                    "pt": "Olá, bem-vindo à locução inteligente.",
                    "hi": "नमस्ते, स्मार्ट वॉयसओवर में आपका स्वागत है.",
                    "ar": "مرحبًا، مرحبًا بك في التعليق الصوتي الذكي.",
                    "tr": "Merhaba, akıllı seslendirmeye hoş geldiniz.",
                    "vi": "Xin chào, chào mừng đến với thuyết minh thông minh.",
                    "th": "สวัสดี ยินดีต้อนรับสู่เสียงพากย์อัจฉริยะ",
                    "id": "Halo, selamat datang di sulih suara pintar.",
                }
                text = req.text or default_map.get(prefix, "Hello, welcome to smart voiceover.")
                speed_ratio = (cfg.speed_ratio if cfg else 1.0)
                try:
                    res = await edge_tts_service.synthesize(text=text, voice_id=vid, speed_ratio=speed_ratio, out_path=out_path)
                    if not res.get("success"):
                        raise HTTPException(status_code=500, detail=res.get("error") or "合成失败")
                    audio_bytes = out_path.read_bytes()
                finally:
                    try:
                        if out_path.exists():
                            out_path.unlink()
                    except Exception:
                        pass

                preview_id = await _preview_cache_put(
                    content=audio_bytes,
                    filename=filename,
                    meta={"provider": "edge_tts", "voice_id": str(vid)},
                )
                audio_url = f"/api/tts/voices/preview/{preview_id}"
                return {
                    "success": True,
                    "data": {
                        "voice_id": vid,
                        "name": (match.name if match else (found_raw.get("name") if isinstance(found_raw, dict) else vid)),
                        "audio_url": audio_url,
                        "description": (match.description if match else ((found_raw.get("description") if isinstance(found_raw, dict) else None))),
                        "duration": res.get("duration")
                    },
                    "message": "已生成 Edge TTS 试听音频"
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Edge TTS 试听失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        if provider == 'qwen3_tts':
            try:
                from modules.qwen3_tts_service import qwen3_tts_service
                from modules.qwen3_tts_voice_store import qwen3_tts_voice_store
                from modules.qwen3_tts_model_manager import Qwen3TTSPathManager, validate_model_dir

                vid = str(voice_id).strip()
                v = qwen3_tts_voice_store.get(vid)
                if not v:
                    raise HTTPException(status_code=404, detail="voice_not_found")

                model_key = (getattr(v, "model_key", None) or "base_0_6b").strip() or "base_0_6b"
                try:
                    pm = Qwen3TTSPathManager()
                    model_dir = pm.model_path(model_key)
                except KeyError:
                    raise RuntimeError(f"unknown_model_key:{model_key}")
                ok, missing = validate_model_dir(model_key, model_dir)
                if not ok:
                    raise RuntimeError(f"model_invalid:{model_key}:{','.join(missing)}|path={model_dir}")

                ts = int(time.time() * 1000)
                safe_vid = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in vid)[:64]
                filename = f"qwen3_{safe_vid}_preview_{ts}.wav"
                out_path = _get_preview_tmp_dir() / filename

                text = req.text
                if not text:
                    # Determine language: explicit req > voice config > auto
                    lang = (req.language or (v.language if v else None) or "auto").lower().strip()
                    
                    # Default text map (supports both full names and codes)
                    default_texts = {
                        "auto": "您好，欢迎使用智能配音。",
                        "chinese": "您好，欢迎使用智能配音。",
                        "zh": "您好，欢迎使用智能配音。",
                        "english": "Hello, welcome to smart voiceover.",
                        "en": "Hello, welcome to smart voiceover.",
                        "japanese": "こんにちは、スマート音声合成へようこそ。",
                        "ja": "こんにちは、スマート音声合成へようこそ。",
                        "korean": "안녕하세요, 스마트 보이스오버에 오신 것을 환영합니다.",
                        "ko": "안녕하세요, 스마트 보이스오버에 오신 것을 환영합니다.",
                        "german": "Hallo, willkommen bei der intelligenten Sprachsynthese.",
                        "de": "Hallo, willkommen bei der intelligenten Sprachsynthese.",
                        "french": "Bonjour, bienvenue sur la voix off intelligente.",
                        "fr": "Bonjour, bienvenue sur la voix off intelligente.",
                        "spanish": "Hola, bienvenido al doblaje inteligente.",
                        "es": "Hola, bienvenido al doblaje inteligente.",
                        "italian": "Ciao, benvenuto nel doppiaggio intelligente.",
                        "it": "Ciao, benvenuto nel doppiaggio intelligente.",
                        "portuguese": "Olá, bem-vindo à locução inteligente.",
                        "pt": "Olá, bem-vindo à locução inteligente.",
                        "russian": "Здравствуйте, добро пожаловать в интеллектуальное озвучивание.",
                        "ru": "Здравствуйте, добро пожаловать в интеллектуальное озвучивание.",
                    }
                    
                    if lang in default_texts:
                        text = default_texts[lang]
                    else:
                        # Fallback for codes like "zh-CN" -> "zh"
                        short_lang = lang.split('-')[0]
                        text = default_texts.get(short_lang, "您好，欢迎使用智能配音。")

                device_s = None
                if cfg:
                    extra = cfg.extra_params or {}
                    device = extra.get("Device")
                    device_s = str(device).strip() if isinstance(device, str) else None

                try:
                    res = await qwen3_tts_service.synthesize_by_voice_asset(
                        text=text,
                        out_path=out_path,
                        voice_asset=v,
                        device=device_s
                    )

                    if not res.get("success"):
                        raise HTTPException(status_code=500, detail=res.get("error") or "合成失败")

                    audio_bytes = out_path.read_bytes()
                finally:
                    try:
                        if out_path.exists():
                            out_path.unlink()
                    except Exception:
                        pass

                preview_id = await _preview_cache_put(
                    content=audio_bytes,
                    filename=filename,
                    meta={"provider": "qwen3_tts", "voice_id": vid},
                )
                audio_url = f"/api/tts/voices/preview/{preview_id}"
                return {
                    "success": True,
                    "data": {
                        "voice_id": vid,
                        "name": v.name if v else vid,
                        "audio_url": audio_url,
                        "description": None,
                        "duration": res.get("duration"),
                    },
                    "message": "已生成 Qwen3-TTS 试听音频"
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Qwen3-TTS 试听失败: {e}")
                msg = str(e)
                if (
                    "qwen_tts_not_installed" in msg
                    or "qwen_tts_bad_install" in msg
                    or "qwen_tts_import_failed" in msg
                    or "model_invalid:" in msg
                    or "unknown_model_key:" in msg
                    or "missing_dependency:" in msg
                ):
                    if "model_invalid:" in msg:
                        msg = f"{msg}。请先下载/放置对应模型文件，或在设置里配置 QWEN_TTS_MODELS_DIR/SACV_UPLOADS_DIR。"
                    raise HTTPException(status_code=503, detail=msg)
                raise HTTPException(status_code=500, detail=msg)

        # 非 Edge：严格校验音色存在
        if not match:
            raise HTTPException(status_code=404, detail=f"音色 '{voice_id}' 不存在")

        # 腾讯云：直接调用合成，并清理旧的本地预览音频
        if provider == 'tencent_tts':
            try:
                from modules.tts_service import tts_service
                vid = match.id
                text = (req.text or "您好，欢迎使用智能配音。")
                codec = "mp3"
                try:
                    extra = (cfg.extra_params if cfg else {}) or {}
                    codec = str(extra.get("Codec", codec))
                except Exception:
                    pass
                codec_s = "".join(ch for ch in codec.lower() if ch.isalnum()) or "mp3"
                ts = int(time.time() * 1000)
                safe_vid = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in str(vid))[:64]
                filename = f"tencent_{safe_vid}_preview_{ts}.{codec_s}"
                out_path = _get_preview_tmp_dir() / filename
                try:
                    res = await tts_service.synthesize(text=text, out_path=str(out_path), voice_id=vid)
                    if not res.get("success"):
                        raise HTTPException(status_code=500, detail=res.get("error") or "合成失败")
                    audio_bytes = out_path.read_bytes()
                finally:
                    try:
                        if out_path.exists():
                            out_path.unlink()
                    except Exception:
                        pass

                preview_id = await _preview_cache_put(
                    content=audio_bytes,
                    filename=filename,
                    meta={"provider": "tencent_tts", "voice_id": str(vid)},
                )
                audio_url = f"/api/tts/voices/preview/{preview_id}"
                return {
                    "success": True,
                    "data": {
                        "voice_id": vid,
                        "name": match.name,
                        "audio_url": audio_url,
                        "description": match.description,
                        "duration": res.get("duration")
                    },
                    "message": "已生成 腾讯云 TTS 试听音频"
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"腾讯云 TTS 试听失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # 其他提供商：返回示例音频链接
        return {
            "success": True,
            "data": {
                "voice_id": match.id,
                "name": match.name,
                "sample_wav_url": match.sample_wav_url,
                "description": match.description
            },
            "message": "返回示例试听链接"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"音色试听失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
