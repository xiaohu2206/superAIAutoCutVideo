#!/usr/bin/env python3
import base64
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

from modules.config.tts_config import tts_engine_config_manager

logger = logging.getLogger(__name__)


async def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


async def _ffprobe_duration(path: str) -> Optional[float]:
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=duration",
            "-of", "default=nk=1:nw=1",
            path,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        if proc.returncode == 0:
            try:
                return float(out.decode().strip())
            except Exception:
                pass
        cmd2 = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nk=1:nw=1",
            path,
        ]
        proc2 = await asyncio.create_subprocess_exec(*cmd2, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out2, _ = await proc2.communicate()
        if proc2.returncode == 0:
            try:
                return float(out2.decode().strip())
            except Exception:
                return None
        return None
    except Exception:
        return None


class TencentTtsService:
    async def synthesize(self, text: str, out_path: str, voice_id: Optional[str] = None) -> Dict[str, Any]:
        cfg = tts_engine_config_manager.get_active_config()
        provider = (getattr(cfg, "provider", None) or "tencent_tts").lower()

        # Edge TTS 合成路径（免凭据）
        if provider == "edge_tts":
            try:
                from modules.edge_tts_service import edge_tts_service
            except Exception as e:
                return {"success": False, "error": f"edge_service_import_failed: {e}"}

            vid = voice_id or (cfg.active_voice_id if cfg else None) or "zh-CN-XiaoxiaoNeural"
            speed_ratio = getattr(cfg, "speed_ratio", None) if cfg else None
            out = Path(out_path)
            ep = (getattr(cfg, "extra_params", None) or {}) if cfg else {}
            override = None
            try:
                pv = ep.get("ProxyUrl")
                if isinstance(pv, str) and pv.strip():
                    override = pv.strip()
            except Exception:
                override = None
            try:
                logger.info(f"配音角色： edge_tts_synthesize voice={vid} speed={speed_ratio} text_len={len(text)}")
                res = await edge_tts_service.synthesize(
                    text=text,
                    voice_id=vid,
                    speed_ratio=speed_ratio,
                    out_path=out,
                    proxy_override=override,
                )
                return res
            except Exception as e:
                return {"success": False, "error": str(e)}

        if provider == "qwen3_tts":
            try:
                from modules.qwen3_tts_service import qwen3_tts_service
            except Exception as e:
                return {"success": False, "error": f"qwen3_tts_import_failed:{e}"}

            out = Path(out_path)
            ep = (getattr(cfg, "extra_params", None) or {}) if cfg else {}
            device = ep.get("Device")
            device_s = str(device).strip() if isinstance(device, str) else None

            vid = str(voice_id or (cfg.active_voice_id if cfg else "") or "").strip() or None

            if vid:
                try:
                    from modules.qwen3_tts_voice_store import qwen3_tts_voice_store

                    vv = qwen3_tts_voice_store.get(vid)
                    if vv:
                        try:
                            return await qwen3_tts_service.synthesize_by_voice_asset(
                                text=text,
                                out_path=out,
                                voice_asset=vv,
                                device=device_s,
                            )
                        except Exception as e:
                            return {"success": False, "error": str(e)}
                except Exception:
                    pass

            # Legacy / Config-only Fallback
            model_key = str(ep.get("ModelKey") or "custom_0_6b")
            language = str(ep.get("Language") or "Auto")
            instruct = str(ep.get("Instruct") or "").strip() or None

            try:
                if model_key.startswith("custom_"):
                    speaker = str(ep.get("Speaker") or (vid or "")).strip() or None
                    if not speaker:
                        try:
                            supported = await qwen3_tts_service.list_supported_speakers(model_key=model_key, device=device_s)
                            if supported:
                                speaker = str(supported[0]).strip() or speaker
                        except Exception:
                            pass
                    if not speaker:
                        return {"success": False, "error": "speaker_required_for_custom_voice"}

                    return await qwen3_tts_service.synthesize_custom_voice_to_wav(
                        text=text,
                        out_path=out,
                        model_key=model_key,
                        language=language,
                        speaker=speaker,
                        instruct=instruct,
                        device=device_s,
                    )
                else:
                    ref_audio = str(ep.get("RefAudio") or "").strip() or None
                    ref_text = str(ep.get("RefText") or "").strip() or None
                    xvec_in = ep.get("XVectorOnly", None)
                    x_vector_only_mode = bool(xvec_in) if xvec_in is not None else True

                    if not ref_audio:
                        return {"success": False, "error": "ref_audio_required_for_voice_clone"}

                    return await qwen3_tts_service.synthesize_voice_clone_to_wav(
                        text=text,
                        out_path=out,
                        model_key=model_key,
                        language=language,
                        ref_audio=ref_audio,
                        ref_text=ref_text,
                        x_vector_only_mode=x_vector_only_mode,
                        device=device_s,
                    )
            except Exception as e:
                return {"success": False, "error": str(e)}

        # 腾讯云 TTS 合成路径（需凭据）
        env_sid = (os.getenv("TENCENTCLOUD_SECRET_ID") or "").strip()
        env_skey = (os.getenv("TENCENTCLOUD_SECRET_KEY") or "").strip()
        secret_id = env_sid or ((cfg.secret_id or "").strip() if cfg else "")
        secret_key = env_skey or ((cfg.secret_key or "").strip() if cfg else "")
        if not (secret_id and secret_key):
            return {"success": False, "error": "missing_credentials"}
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.tts.v20190823 import tts_client, models
        except Exception as e:
            return {"success": False, "error": f"sdk_import_failed: {e}"}

        try:
            cred = credential.Credential(secret_id, secret_key)
            http_profile = HttpProfile()
            http_profile.endpoint = "tts.tencentcloudapi.com"
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            region = (cfg.region if cfg else None) or "ap-beijing"
            client = tts_client.TtsClient(cred, region, client_profile)

            req = models.TextToVoiceRequest()
            import json
            import uuid
            vid = voice_id or (cfg.active_voice_id if cfg else None)
            params: Dict[str, Any] = {
                "Text": text,
                "SessionId": f"{uuid.uuid4()}",
            }
            extra = (cfg.extra_params if cfg else {}) or {}
            sample_rate = int(extra.get("SampleRate", 16000))
            codec = str(extra.get("Codec", "mp3"))
            params["SampleRate"] = sample_rate
            params["Codec"] = codec

            try:
                sr = getattr(cfg, "speed_ratio", None) if cfg else None
                speed = float(extra.get("Speed", sr if sr is not None else 1.0))
            except Exception:
                speed = 1.0
            params["Speed"] = speed

            try:
                volume = float(extra.get("Volume", 10))
            except Exception:
                volume = 10.0
            params["Volume"] = volume

            vt_from_vid = None
            try:
                if isinstance(vid, int) or (isinstance(vid, str) and str(vid).isdigit()):
                    vt_from_vid = int(vid)
                else:
                    try:
                        provider2 = (cfg.provider if cfg else "tencent_tts")
                        voices = tts_engine_config_manager.get_voices(provider2)
                        sid = str(vid) if vid is not None else ""
                        m = next((v for v in voices if v.id == sid or v.name == sid), None)
                        if m and isinstance(m.voice_type, int):
                            vt_from_vid = int(m.voice_type)
                    except Exception:
                        vt_from_vid = None
            except Exception:
                vt_from_vid = None

            vt_from_extra = None
            try:
                vt_val = extra.get("VoiceType", None)
                if vt_val is not None:
                    vt_from_extra = int(vt_val)
            except Exception:
                vt_from_extra = None

            final_vt = vt_from_vid if vt_from_vid is not None else vt_from_extra
            if vt_from_vid is not None and vt_from_extra is not None and vt_from_vid != vt_from_extra:
                logger.info(f"VoiceType mismatch resolved: voice_id={vid} extra={vt_from_extra} use={final_vt}")
            if final_vt is not None:
                params["VoiceType"] = final_vt

            req.from_json_string(json.dumps(params))

            resp = client.TextToVoice(req)
            audio_b64 = getattr(resp, "Audio", None)
            if not audio_b64:
                return {"success": False, "error": "empty_audio", "request_id": getattr(resp, "RequestId", None)}

            out = Path(out_path)
            await _ensure_dir(out)
            data = base64.b64decode(audio_b64)
            out.write_bytes(data)
            dur = await _ffprobe_duration(str(out))
            return {
                "success": True,
                "path": str(out),
                "duration": dur,
                "codec": codec,
                "sample_rate": sample_rate,
                "request_id": getattr(resp, "RequestId", None),
            }
        except Exception as e:
            try:
                from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
                if isinstance(e, TencentCloudSDKException):
                    return {"success": False, "error": getattr(e, "message", str(e))}
            except Exception:
                pass
            return {"success": False, "error": str(e)}


tts_service = TencentTtsService()
