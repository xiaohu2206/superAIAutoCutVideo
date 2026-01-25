#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS引擎与音色配置API路由
提供TTS引擎元数据、音色列表、配置管理、激活与测试接口。
"""

from typing import Dict, Optional, Any
import time
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import logging

from modules.config.tts_config import (
    TtsEngineConfig,
    tts_engine_config_manager,
)

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/tts", tags=["TTS配置"])


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
                aid = update_data.get('active_voice_id') if update_data.get('active_voice_id') is not None else current.active_voice_id
                if aid is not None:
                    aid_s = str(aid)
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
    provider: Optional[str] = Field(None, description="提供商标识，默认使用激活配置")
    config_id: Optional[str] = Field(None, description="使用指定配置")


@router.post("/voices/{voice_id}/preview", summary="音色试听（返回示例wav链接）")
async def preview_voice(voice_id: str, req: VoicePreviewRequest):
    try:
        provider = (req.provider or (tts_engine_config_manager.get_active_config() or TtsEngineConfig(provider='tencent_tts')).provider)
        voices = await tts_engine_config_manager.get_voices_async(provider)
        match = next((v for v in voices if v.id == voice_id), None)
        # Edge TTS：若缓存列表未包含该音色，仍允许尝试合成（避免误报不存在）
        if provider == 'edge_tts':
            try:
                from modules.edge_tts_service import edge_tts_service, PREVIEWS_DIR
                vid = (match.id if match else voice_id)
                raw_voices = await edge_tts_service.list_voices()
                found_raw = next((v for v in raw_voices if (isinstance(v.get("id"), str) and v.get("id", "").lower() == str(vid).lower()) or (isinstance(v.get("name"), str) and v.get("name", "").lower() == str(vid).lower())), None)
                if found_raw:
                    vid = found_raw.get("id", vid)
                ts = int(time.time() * 1000)
                filename = f"edge_{vid}_preview_{ts}.mp3"
                out_path = PREVIEWS_DIR / filename

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
                cfg = tts_engine_config_manager.get_active_config()
                speed_ratio = (cfg.speed_ratio if cfg else 1.0)
                res = await edge_tts_service.synthesize(text=text, voice_id=vid, speed_ratio=speed_ratio, out_path=out_path)
                if not res.get("success"):
                    raise HTTPException(status_code=500, detail=res.get("error") or "合成失败")
                audio_url = f"/backend/serviceData/tts/previews/{filename}"
                return {
                    "success": True,
                    "data": {
                        "voice_id": vid,
                        "name": (match.name if match else (found_raw.get("name") if isinstance(found_raw, dict) else vid)),
                        "audio_url": audio_url,
                        "description": (match.description if match else ((found_raw.get("description") if isinstance(found_raw, dict) else None))),
                        "duration": res.get("duration")
                    },
                    "message": "已生成并保存 Edge TTS 试听音频"
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Edge TTS 试听失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # 非 Edge：严格校验音色存在
        if not match:
            raise HTTPException(status_code=404, detail=f"音色 '{voice_id}' 不存在")

        # 腾讯云：直接调用合成，并清理旧的本地预览音频
        if provider == 'tencent_tts':
            try:
                from modules.tts_service import tts_service
                from modules.edge_tts_service import PREVIEWS_DIR
                vid = match.id
                base_name = f"tencent_{vid}_preview"
                try:
                    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                try:
                    if PREVIEWS_DIR.exists():
                        for p in PREVIEWS_DIR.iterdir():
                            if p.is_file() and (p.name.startswith(base_name + "_") or p.stem.startswith(base_name + "_") or p.stem == base_name):
                                try:
                                    p.unlink()
                                except Exception:
                                    pass
                except Exception:
                    pass
                text = (req.text or "您好，欢迎使用智能配音。")
                cfg = tts_engine_config_manager.get_active_config()
                codec = "mp3"
                try:
                    extra = (cfg.extra_params if cfg else {}) or {}
                    codec = str(extra.get("Codec", codec))
                except Exception:
                    pass
                ts = int(time.time() * 1000)
                out_path = PREVIEWS_DIR / f"{base_name}_{ts}.{codec}"
                res = await tts_service.synthesize(text=text, out_path=str(out_path), voice_id=vid)
                if not res.get("success"):
                    raise HTTPException(status_code=500, detail=res.get("error") or "合成失败")
                audio_url = f"/backend/serviceData/tts/previews/{out_path.name}"
                return {
                    "success": True,
                    "data": {
                        "voice_id": vid,
                        "name": match.name,
                        "audio_url": audio_url,
                        "description": match.description,
                        "duration": res.get("duration")
                    },
                    "message": "已生成并保存 腾讯云 TTS 试听音频"
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
