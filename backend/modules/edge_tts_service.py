#!/usr/bin/env python3
import asyncio
import json
import logging
import os
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
        env = (os.getenv("EDGE_TTS_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or "").strip()
        if env:
            return env
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
        return None
    except Exception:
        return None


class EdgeTtsService:
    async def list_voices(self) -> List[Dict[str, Any]]:
        """
        获取 Edge TTS 音色列表，带简单缓存（24小时）。
        返回统一的字典结构，供配置层映射到 TtsVoice。
        """
        try:
            # 读取缓存
            if VOICES_CACHE_PATH.exists():
                try:
                    data = json.loads(VOICES_CACHE_PATH.read_text("utf-8"))
                    if isinstance(data, dict) and "voices" in data and isinstance(data["voices"], list):
                        return data["voices"]
                except Exception:
                    pass

            import edge_tts  # noqa: F401
        except Exception as e:
            logger.error(f"edge-tts 模块不可用: {e}")
            return []

        try:
            import edge_tts
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
                description = f"{display_name}（{locale}）"
                voices.append({
                    "id": short_name,
                    "name": display_name,
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

    async def synthesize(self, text: str, voice_id: str, speed_ratio: Optional[float], out_path: Path) -> Dict[str, Any]:
        """
        使用 Edge TTS 合成语音到指定文件。
        返回包含路径与时长信息的结果。
        """
        try:
            import edge_tts
        except Exception as e:
            return {"success": False, "error": f"edge_tts_import_failed: {e}"}

        rate = _speed_ratio_to_rate(speed_ratio)
        try:
            proxy = _resolve_proxy_url()
            communicate = edge_tts.Communicate(text=text, voice=voice_id, rate=rate, proxy=proxy)
            await _ensure_parent_dir(out_path)
            await communicate.save(str(out_path))
            dur = await _ffprobe_duration(str(out_path))
            return {"success": True, "path": str(out_path), "duration": dur, "codec": "mp3", "sample_rate": None}
        except Exception as e:
            msg = str(e)
            if ("403" in msg) and ("Invalid response status" in msg or "speech.platform.bing.com" in msg or "TrustedClientToken" in msg):
                return {"success": False, "error": "edge_tts_403", "message": msg, "requires_proxy": True}
            return {"success": False, "error": msg}


edge_tts_service = EdgeTtsService()
