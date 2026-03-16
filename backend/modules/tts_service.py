#!/usr/bin/env python3
import base64
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Any
import subprocess

from modules.config.generate_concurrency_config import generate_concurrency_config_manager
from modules.config.tts_config import tts_engine_config_manager
from modules.audio_speed_processor import apply_audio_speed

logger = logging.getLogger(__name__)
WIN_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

_tts_semaphore: Optional[asyncio.Semaphore] = None
_tts_semaphore_concurrency: int = 0
_tts_semaphore_lock = asyncio.Lock()
_voxcpm_tts_semaphore: Optional[asyncio.Semaphore] = None
_voxcpm_tts_semaphore_concurrency: int = 0
_voxcpm_tts_semaphore_lock = asyncio.Lock()


async def _get_tts_semaphore() -> asyncio.Semaphore:
    global _tts_semaphore, _tts_semaphore_concurrency
    max_workers, _src = generate_concurrency_config_manager.get_effective("tts")
    target = max(1, int(max_workers or 1))
    if _tts_semaphore is not None and _tts_semaphore_concurrency == target:
        return _tts_semaphore
    async with _tts_semaphore_lock:
        max_workers2, _src2 = generate_concurrency_config_manager.get_effective("tts")
        target2 = max(1, int(max_workers2 or 1))
        if _tts_semaphore is None or _tts_semaphore_concurrency != target2:
            _tts_semaphore = asyncio.Semaphore(target2)
            _tts_semaphore_concurrency = target2
        return _tts_semaphore


async def _get_voxcpm_tts_semaphore(cfg) -> asyncio.Semaphore:
    global _voxcpm_tts_semaphore, _voxcpm_tts_semaphore_concurrency
    max_workers, _src = generate_concurrency_config_manager.get_effective("tts")
    tts_target = max(1, int(max_workers or 1))

    ep = (getattr(cfg, "extra_params", None) or {}) if cfg else {}
    raw = ep.get("MaxConcurrency", None)
    target = None
    try:
        if raw is not None and not isinstance(raw, bool):
            target = int(str(raw).strip())
    except Exception:
        target = None
    if target is None:
        target = 2 if tts_target >= 2 else 1
    target = max(1, min(int(target), int(tts_target)))

    if _voxcpm_tts_semaphore is not None and _voxcpm_tts_semaphore_concurrency == target:
        return _voxcpm_tts_semaphore

    async with _voxcpm_tts_semaphore_lock:
        max_workers2, _src2 = generate_concurrency_config_manager.get_effective("tts")
        tts_target2 = max(1, int(max_workers2 or 1))

        ep2 = (getattr(cfg, "extra_params", None) or {}) if cfg else {}
        raw2 = ep2.get("MaxConcurrency", None)
        target2 = None
        try:
            if raw2 is not None and not isinstance(raw2, bool):
                target2 = int(str(raw2).strip())
        except Exception:
            target2 = None
        if target2 is None:
            target2 = 2 if tts_target2 >= 2 else 1
        target2 = max(1, min(int(target2), int(tts_target2)))

        if _voxcpm_tts_semaphore is None or _voxcpm_tts_semaphore_concurrency != target2:
            _voxcpm_tts_semaphore = asyncio.Semaphore(target2)
            _voxcpm_tts_semaphore_concurrency = target2
        return _voxcpm_tts_semaphore


@asynccontextmanager
async def _tts_slot():
    sem = await _get_tts_semaphore()
    await sem.acquire()
    try:
        yield
    finally:
        try:
            sem.release()
        except Exception:
            pass


@asynccontextmanager
async def _voxcpm_tts_slot(cfg):
    sem = await _get_voxcpm_tts_semaphore(cfg)
    await sem.acquire()
    try:
        yield
    finally:
        try:
            sem.release()
        except Exception:
            pass


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
        if os.name == "nt":
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
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
        if os.name == "nt":
            proc2 = await asyncio.create_subprocess_exec(
                *cmd2,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW,
            )
        else:
            proc2 = await asyncio.create_subprocess_exec(
                *cmd2,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
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
    async def _postprocess_qwen_audio(self, res: Dict[str, Any], out: Path, cfg) -> Dict[str, Any]:
        speed_ratio = getattr(cfg, "speed_ratio", None) if cfg else None
        if speed_ratio is None:
            return res
        try:
            sr = float(speed_ratio)
        except Exception:
            return res
        if abs(sr - 1.0) < 0.0001:
            return res
        sp = await apply_audio_speed(str(out), sr)
        if not sp.get("success"):
            return {"success": False, "error": sp.get("error") or "speed_process_failed"}
        dur = await _ffprobe_duration(str(out))
        if dur:
            res["duration"] = dur
        return res

    async def synthesize(self, text: str, out_path: str, voice_id: Optional[str] = None) -> Dict[str, Any]:
        cfg = tts_engine_config_manager.get_active_config()
        provider = (getattr(cfg, "provider", None) or "tencent_tts").lower()

        if provider == "voxcpm_tts":
            async with _voxcpm_tts_slot(cfg):
                async with _tts_slot():
                    return await self._synthesize_with_provider(
                        text=text,
                        out_path=out_path,
                        voice_id=voice_id,
                        cfg=cfg,
                        provider=provider,
                    )

        async with _tts_slot():
            return await self._synthesize_with_provider(
                text=text,
                out_path=out_path,
                voice_id=voice_id,
                cfg=cfg,
                provider=provider,
            )

    async def _synthesize_with_provider(
        self,
        text: str,
        out_path: str,
        voice_id: Optional[str],
        cfg,
        provider: str,
    ) -> Dict[str, Any]:
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

            qwen_voice_id: Optional[str] = str(voice_id or (cfg.active_voice_id if cfg else "") or "").strip() or None

            if qwen_voice_id:
                try:
                    from modules.qwen3_tts_voice_store import qwen3_tts_voice_store

                    vv = qwen3_tts_voice_store.get(qwen_voice_id)
                    if vv:
                        try:
                            res = await qwen3_tts_service.synthesize_by_voice_asset(
                                text=text,
                                out_path=out,
                                voice_asset=vv,
                                device=device_s,
                            )
                            if res and res.get("success"):
                                return await self._postprocess_qwen_audio(res, out, cfg)
                            return res
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
                    speaker = str(ep.get("Speaker") or (qwen_voice_id or "")).strip() or None
                    if not speaker:
                        try:
                            supported = await qwen3_tts_service.list_supported_speakers(model_key=model_key, device=device_s)
                            if supported:
                                speaker = str(supported[0]).strip() or speaker
                        except Exception:
                            pass
                    if not speaker:
                        return {"success": False, "error": "speaker_required_for_custom_voice"}

                    res = await qwen3_tts_service.synthesize_custom_voice_to_wav(
                        text=text,
                        out_path=out,
                        model_key=model_key,
                        language=language,
                        speaker=speaker,
                        instruct=instruct,
                        device=device_s,
                    )
                    if res and res.get("success"):
                        return await self._postprocess_qwen_audio(res, out, cfg)
                    return res
                else:
                    ref_audio = str(ep.get("RefAudio") or "").strip() or None
                    ref_text = str(ep.get("RefText") or "").strip() or None
                    xvec_in = ep.get("XVectorOnly", None)
                    x_vector_only_mode = bool(xvec_in) if xvec_in is not None else True

                    if not ref_audio:
                        return {"success": False, "error": "ref_audio_required_for_voice_clone"}

                    res = await qwen3_tts_service.synthesize_voice_clone_to_wav(
                        text=text,
                        out_path=out,
                        model_key=model_key,
                        language=language,
                        ref_audio=ref_audio,
                        ref_text=ref_text,
                        x_vector_only_mode=x_vector_only_mode,
                        device=device_s,
                    )
                    if res and res.get("success"):
                        return await self._postprocess_qwen_audio(res, out, cfg)
                    return res
            except Exception as e:
                return {"success": False, "error": str(e)}

        if provider == "qwen_online_tts":
            api_key = (os.getenv("DASHSCOPE_API_KEY") or ((cfg.secret_key or "").strip() if cfg else "")).strip()
            if not api_key:
                return {"success": False, "error": "missing_credentials"}
            try:
                from modules.qwen_online_tts_service import qwen_online_tts_service
                from modules.qwen_online_tts_voice_store import qwen_online_tts_voice_store
            except Exception as e:
                return {"success": False, "error": f"qwen_online_import_failed:{e}"}

            out = Path(out_path)
            ep = (getattr(cfg, "extra_params", None) or {}) if cfg else {}
            base_url = str(ep.get("BaseUrl") or "").strip()
            region = ((cfg.region or "").strip().lower() if cfg else "")
            if not base_url:
                base_url = "https://dashscope-intl.aliyuncs.com/api/v1" if region in {"intl", "sg", "ap-singapore"} else "https://dashscope.aliyuncs.com/api/v1"

            model = str(ep.get("Model") or "qwen3-tts-flash").strip() or "qwen3-tts-flash"
            language_type = str(ep.get("LanguageType") or "").strip() or None
            instructions = str(ep.get("Instructions") or "").strip() or None
            optimize = ep.get("OptimizeInstructions", None)
            optimize_b = bool(optimize) if optimize is not None else None
            max_concurrency_i = None
            try:
                mc = ep.get("MaxConcurrency", None)
                if mc is not None and not isinstance(mc, bool):
                    max_concurrency_i = int(str(mc).strip())
            except Exception:
                max_concurrency_i = None
            min_interval_sec = None
            try:
                mi = ep.get("MinIntervalMs", None)
                if mi is not None and not isinstance(mi, bool):
                    min_interval_sec = float(str(mi).strip()) / 1000.0
            except Exception:
                min_interval_sec = None
            max_retries_i = None
            try:
                mr = ep.get("MaxRetries", None)
                if mr is not None and not isinstance(mr, bool):
                    max_retries_i = int(str(mr).strip())
            except Exception:
                max_retries_i = None

            qwen_voice_id: Optional[str] = str(voice_id or (cfg.active_voice_id if cfg else "") or "").strip() or None
            voice = str(ep.get("Voice") or "Cherry").strip() or "Cherry"
            if qwen_voice_id:
                vrec = qwen_online_tts_voice_store.get(qwen_voice_id)
                if vrec:
                    if not getattr(vrec, "voice", None):
                        return {"success": False, "error": "voice_not_ready"}
                    voice = str(vrec.voice).strip()
                    model = str(getattr(vrec, "model", model) or model).strip() or model
            if not qwen_voice_id:
                qwen_voice_id = None

            try:
                res = await qwen_online_tts_service.synthesize(
                    text=text,
                    out_path=str(out),
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    voice=voice,
                    language_type=language_type,
                    instructions=instructions,
                    optimize_instructions=optimize_b,
                    stream=False,
                    max_concurrency=max_concurrency_i,
                    min_interval_sec=min_interval_sec,
                    max_retries=max_retries_i,
                )
                if res and res.get("success"):
                    return await self._postprocess_qwen_audio(res, out, cfg)
                return res
            except Exception as e:
                return {"success": False, "error": str(e)}

        if provider == "voxcpm_tts":
            try:
                from modules.voxcpm_tts_service import voxcpm_tts_service
            except Exception as e:
                return {"success": False, "error": f"voxcpm_tts_import_failed:{e}"}

            out = Path(out_path)
            ep = (getattr(cfg, "extra_params", None) or {}) if cfg else {}
            device = ep.get("Device")
            device_s = str(device).strip() if isinstance(device, str) else None

            voxcpm_voice_id: Optional[str] = str(voice_id or (cfg.active_voice_id if cfg else "") or "").strip() or None

            if voxcpm_voice_id:
                try:
                    from modules.voxcpm_tts_voice_store import voxcpm_tts_voice_store

                    vv = voxcpm_tts_voice_store.get(voxcpm_voice_id)
                    if vv:
                        try:
                            res = await voxcpm_tts_service.synthesize_by_voice_asset(
                                text=text,
                                out_path=out,
                                voice_asset=vv,
                                device=device_s,
                            )
                            if res and res.get("success"):
                                return await self._postprocess_qwen_audio(res, out, cfg)
                            return res
                        except Exception as e:
                            return {"success": False, "error": str(e)}
                except Exception:
                    pass

            # Legacy / Config-only Fallback
            model_key = str(ep.get("ModelKey") or "voxcpm_0_5b")
            language = str(ep.get("Language") or "Auto")
            ref_audio = str(ep.get("RefAudio") or "").strip() or None
            ref_text = str(ep.get("RefText") or "").strip() or None

            if not ref_audio:
                return {"success": False, "error": "ref_audio_required_for_voice_clone"}

            try:
                res = await voxcpm_tts_service.synthesize_voice_clone_to_wav(
                    text=text,
                    out_path=out,
                    model_key=model_key,
                    language=language,
                    ref_audio=ref_audio,
                    ref_text=ref_text,
                    device=device_s,
                )
                if res and res.get("success"):
                    return await self._postprocess_qwen_audio(res, out, cfg)
                return res
            except Exception as e:
                return {"success": False, "error": str(e)}

        return await self._synthesize_tencent(text=text, out_path=out_path, cfg=cfg, voice_id=voice_id)

    async def _synthesize_tencent(self, text: str, out_path: str, cfg, voice_id: Optional[str]) -> Dict[str, Any]:
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
            tencent_voice_id = voice_id or (cfg.active_voice_id if cfg else None)
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
                if isinstance(tencent_voice_id, int) or (isinstance(tencent_voice_id, str) and str(tencent_voice_id).isdigit()):
                    vt_from_vid = int(tencent_voice_id)
                else:
                    try:
                        provider2 = (cfg.provider if cfg else "tencent_tts")
                        voices = tts_engine_config_manager.get_voices(provider2)
                        sid = str(tencent_voice_id) if tencent_voice_id is not None else ""
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
                logger.info(f"VoiceType mismatch resolved: voice_id={tencent_voice_id} extra={vt_from_extra} use={final_vt}")
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
