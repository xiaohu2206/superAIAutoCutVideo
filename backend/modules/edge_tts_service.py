#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
SERVICE_DATA_DIR = BASE_DIR / "serviceData" / "tts"
PREVIEWS_DIR = SERVICE_DATA_DIR / "previews"
VOICES_CACHE_PATH = SERVICE_DATA_DIR / "edge_voices_cache.json"


async def _ensure_parent_dir(path: Path) -> None:
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


def _speed_ratio_to_rate(speed_ratio: Optional[float]) -> str:
    try:
        if speed_ratio is None:
            return "+0%"
        pct = int(round((float(speed_ratio) - 1.0) * 100))
        if pct > 100:
            pct = 100
        if pct < -80:
            pct = -80
        return f"{pct:+d}%"
    except Exception:
        return "+0%"


def _resolve_proxy_url() -> Optional[str]:
    try:
        # 优先使用配置中的代理，以便在运行时覆盖环境变量
        try:
            from modules.config.tts_config import tts_engine_config_manager
            cfg = tts_engine_config_manager.get_active_config()
            if cfg and (getattr(cfg, "provider", "") or "").lower() == "edge_tts":
                ep = getattr(cfg, "extra_params", None) or {}
                for key in ("ProxyUrl", "proxy_url", "proxy", "http_proxy", "https_proxy", "EDGE_TTS_PROXY"):
                    val = ep.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except Exception:
            pass

        # 其次读取环境变量
        env = (os.getenv("EDGE_TTS_PROXY") or "").strip()
        if env:
            if env.lower() in ("none", "disable", "disabled"):
                return None
            return env
        sys_https = (os.getenv("HTTPS_PROXY") or "").strip()
        if sys_https:
            return sys_https
        sys_http = (os.getenv("HTTP_PROXY") or "").strip()
        if sys_http:
            return sys_http
        return None
    except Exception:
        return None


def _normalize_proxy_url(url: Optional[str]) -> Optional[str]:
    try:
        if not url:
            return None
        u = url.strip()
        if not u:
            return None
        lu = u.lower()
        if lu in ("none", "disable", "disabled", "null"):
            return None
        if "://" in u:
            return u
        return f"http://{u}"
    except Exception:
        return url


class EdgeTtsService:
    async def list_voices(self) -> List[Dict[str, Any]]:
        """
        获取 Edge TTS 音色列表，带简单缓存（24小时）。
        返回统一的字典结构，供配置层映射到 TtsVoice。
        """
        try:
            if VOICES_CACHE_PATH.exists():
                try:
                    data = json.loads(VOICES_CACHE_PATH.read_text("utf-8"))
                    if isinstance(data, dict) and "voices" in data and isinstance(data["voices"], list):
                        return data["voices"]
                except Exception:
                    pass

            import edge_tts
        except Exception as e:
            logger.error(f"edge-tts 模块不可用: {e}")
            return []

        try:
            voices_raw = await edge_tts.list_voices()
            voices: List[Dict[str, Any]] = []
            for v in voices_raw:
                short_name = v.get("ShortName") or v.get("Name") or ""
                display_name = v.get("FriendlyName") or v.get("DisplayName") or short_name
                locale = v.get("Locale") or ""
                gender = (v.get("Gender") or "").title()
                tags = []
                voice_tag = v.get("VoiceTag") or {}
                styles = voice_tag.get("StyleList") or []
                if isinstance(styles, list):
                    tags.extend([str(s) for s in styles if s])
                # 精简展示名称：优先从 ShortName 提取人名部分（去掉语言与 Neural 后缀），否则从 FriendlyName 取第二个词（去掉前缀 Microsoft）
                simple_name = short_name
                try:
                    parts = short_name.split("-")
                    simple_name = parts[-1] if parts else short_name
                    simple_name = simple_name.replace("Neural", "-Neural")
                except Exception:
                    simple_name = short_name
                if not simple_name or simple_name == short_name:
                    try:
                        toks = display_name.split()
                        if len(toks) >= 2 and toks[0].lower() == "microsoft":
                            simple_name = toks[1]
                    except Exception:
                        pass
                description = f"{display_name}（{locale}）"
                voices.append({
                    "id": short_name,
                    "name": simple_name,
                    "description": description,
                    "language": locale,
                    "gender": gender,
                    "voice_quality": "Neural",
                    "voice_type_tag": "edge",
                    "voice_human_style": ", ".join(tags) if tags else None,
                    "tags": tags,
                    "sample_wav_url": None,
                })

            # 写入缓存
            await _ensure_parent_dir(VOICES_CACHE_PATH)
            VOICES_CACHE_PATH.write_text(json.dumps({"voices": voices}, ensure_ascii=False), "utf-8")

            return voices
        except Exception as e:
            logger.error(f"获取 Edge TTS 音色失败: {e}")
            return []

    async def synthesize(self, text: str, voice_id: str, speed_ratio: Optional[float], out_path: Path, proxy_override: Optional[str] = None, delete_after: bool = False) -> Dict[str, Any]:
        """
        使用 Edge TTS 合成语音到指定文件。
        返回包含路径与时长信息的结果。
        """
        try:
            import edge_tts
        except Exception as e:
            return {"success": False, "error": f"edge_tts_import_failed: {e}"}

        cfg_voice: Optional[str] = None
        cfg_speed: Optional[float] = None
        try:
            from modules.config.tts_config import tts_engine_config_manager
            cfg = tts_engine_config_manager.get_active_config()
            if cfg and (getattr(cfg, "provider", "") or "").lower() == "edge_tts":
                cfg_voice = getattr(cfg, "active_voice_id", None)
                cfg_speed = getattr(cfg, "speed_ratio", None)
        except Exception:
            pass

        vid = voice_id if isinstance(voice_id, str) and voice_id.strip() else (cfg_voice or "zh-CN-XiaoxiaoNeural")
        sr = speed_ratio if speed_ratio is not None else cfg_speed
        rate = _speed_ratio_to_rate(sr)
        pitch = _ratio_to_pitch(sr)
        try:
            candidates: List[Optional[str]] = []
            if proxy_override is not None:
                ov = _normalize_proxy_url(proxy_override)
                candidates.append(ov)
                candidates.append(None)
            else:
                candidates.append(_normalize_proxy_url(_resolve_proxy_url()))
                candidates.append(None)

            errs: List[Dict[str, Any]] = []
            for proxy in candidates:
                prev_env: Dict[str, Optional[str]] = {}
                need_disable_env = proxy is None
                try:
                    try:
                        logger.info(f"edge_tts proxy attempt: {proxy}")
                    except Exception:
                        pass
                    if need_disable_env:
                        for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "EDGE_TTS_PROXY"):
                            prev_env[k] = os.environ.get(k)
                            os.environ.pop(k, None)
                        prev_env["NO_PROXY"] = os.environ.get("NO_PROXY")
                        os.environ["NO_PROXY"] = "*"
                    await _ensure_parent_dir(out_path)
                    try:
                        communicate = edge_tts.Communicate(text=text, voice=vid, rate=rate, pitch=pitch, proxy=proxy)
                        await communicate.save(str(out_path))
                    except Exception:
                        audio_data = bytes()
                        cm2 = edge_tts.Communicate(text=text, voice=vid, rate=rate, pitch=pitch, proxy=proxy)
                        async for chunk in cm2.stream():
                            if chunk.get("type") == "audio":
                                audio_data += chunk.get("data", b"")
                        if not audio_data:
                            raise
                        with open(str(out_path), "wb") as f:
                            f.write(audio_data)
                    dur = await _ffprobe_duration(str(out_path))
                    if delete_after:
                        try:
                            if out_path.exists():
                                out_path.unlink()
                        except Exception:
                            pass
                    return {"success": True, "path": str(out_path), "duration": dur, "codec": "mp3", "sample_rate": None}
                except Exception as e:
                    msg = str(e)
                    requires_proxy = False
                    if ("403" in msg) and ("Invalid response status" in msg or "speech.platform.bing.com" in msg or "TrustedClientToken" in msg):
                        requires_proxy = True
                    if ("Cannot connect to host" in msg) or ("Connect call failed" in msg) or ("proxy" in msg.lower()):
                        requires_proxy = True
                    errs.append({"message": msg, "requires_proxy": requires_proxy})
                finally:
                    if need_disable_env:
                        for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "EDGE_TTS_PROXY"):
                            v = prev_env.get(k, None)
                            if v is None:
                                os.environ.pop(k, None)
                            else:
                                os.environ[k] = v
                        vnp = prev_env.get("NO_PROXY", None)
                        if vnp is None:
                            os.environ.pop("NO_PROXY", None)
                        else:
                            os.environ["NO_PROXY"] = vnp

            if errs:
                last = errs[-1]
                logger.error(f"Edge TTS failed (all proxies tried). Last error: {last['message']}")
                # if (platform.system().lower() == "darwin"):
                #     mac_voice = _map_edge_to_mac_voice(voice_id)
                #     ok = await _mac_say_to_mp3(text, mac_voice, out_path)
                #     if ok:
                #         dur = await _ffprobe_duration(str(out_path))
                #         return {"success": True, "path": str(out_path), "duration": dur, "codec": "mp3", "sample_rate": None}
                return {"success": False, "error": last["message"], "message": last["message"], "requires_proxy": bool(last.get("requires_proxy", False))}
            return {"success": False, "error": "edge_tts_unknown_error"}
        except Exception as e:
            return {"success": False, "error": f"edge_tts_outer_exception: {e}"}


edge_tts_service = EdgeTtsService()


def _ratio_to_pitch(speed_ratio: Optional[float]) -> str:
    try:
        return "+0Hz"
    except Exception:
        return "+0Hz"


async def _mac_say_to_mp3(text: str, voice: Optional[str], mp3_path: Path) -> bool:
    try:
        await _ensure_parent_dir(mp3_path)
        tmp_aiff = mp3_path.with_suffix(".aiff")
        args = ["say"]
        if isinstance(voice, str) and voice.strip():
            args += ["-v", voice.strip()]
        args += ["-o", str(tmp_aiff), text]
        p1 = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, _ = await p1.communicate()
        if p1.returncode != 0:
            try:
                if tmp_aiff.exists():
                    tmp_aiff.unlink()
            except Exception:
                pass
            return False
        p2 = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            str(tmp_aiff),
            str(mp3_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, _ = await p2.communicate()
        try:
            if tmp_aiff.exists():
                tmp_aiff.unlink()
        except Exception:
            pass
        return p2.returncode == 0
    except Exception:
        return False


def _map_edge_to_mac_voice(voice_id: str) -> Optional[str]:
    try:
        v = (voice_id or "").lower()
        if v.startswith("zh-"):
            return "Ting-Ting"
        if v.startswith("en-"):
            return "Samantha"
        return None
    except Exception:
        return None
