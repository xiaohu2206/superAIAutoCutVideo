import asyncio
import base64
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)
WIN_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

_dashscope_lock = asyncio.Lock()


def _base_url_from_region(region: Optional[str], override: Optional[str]) -> str:
    if isinstance(override, str) and override.strip():
        return override.strip().rstrip("/")
    r = (region or "").strip().lower()
    if r in {"intl", "sg", "ap-singapore", "singapore"}:
        return "https://dashscope-intl.aliyuncs.com/api/v1"
    return "https://dashscope.aliyuncs.com/api/v1"


def _resolve_api_key(secret_key: Optional[str]) -> Optional[str]:
    env = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
    if env:
        return env
    sk = (secret_key or "").strip()
    return sk or None


async def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


async def _ffprobe_duration(path: str) -> Optional[float]:
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=duration",
            "-of",
            "default=nk=1:nw=1",
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
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
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


def _get_any(d: Any, keys: Tuple[str, ...], default: Any = None) -> Any:
    cur = d
    for k in keys:
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(k)
            continue
        try:
            cur = getattr(cur, k)
        except Exception:
            return default
    return cur if cur is not None else default


def _extract_audio_payload(resp: Any) -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
    audio = _get_any(resp, ("output", "audio"))
    if isinstance(audio, dict):
        url = audio.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip(), None, None
        data = audio.get("data")
        if isinstance(data, str) and data.strip():
            try:
                return None, base64.b64decode(data.strip()), None
            except Exception:
                pass

    url2 = _get_any(resp, ("output", "url"))
    if isinstance(url2, str) and url2.strip():
        return url2.strip(), None, None

    request_id = _get_any(resp, ("request_id",))
    rid_s = str(request_id).strip() if request_id is not None else None
    return None, None, rid_s


async def _download_to(url: str, out: Path, timeout_sec: float = 90.0) -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec), follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        await _ensure_dir(out)
        out.write_bytes(resp.content)


class QwenOnlineTTSService:
    async def create_clone_voice(
        self,
        upload_bytes: bytes,
        audio_mime_type: str,
        target_model: str,
        preferred_name: str,
        api_key: str,
        base_url: str,
    ) -> Dict[str, Any]:
        mime = (audio_mime_type or "audio/mpeg").strip() or "audio/mpeg"
        b64 = base64.b64encode(upload_bytes).decode()
        data_uri = f"data:{mime};base64,{b64}"
        url = base_url.rstrip("/") + "/services/audio/tts/customization"
        payload = {
            "model": "qwen-voice-enrollment",
            "input": {
                "action": "create",
                "target_model": str(target_model or "").strip(),
                "preferred_name": str(preferred_name or "").strip() or "voice",
                "audio": {"data": data_uri},
            },
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0), follow_redirects=True) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code != 200:
                    return {"success": False, "error": f"enroll_failed:{r.status_code}:{r.text}"}
                data = r.json()
                voice = _get_any(data, ("output", "voice"))
                if not isinstance(voice, str) or not voice.strip():
                    return {"success": False, "error": "enroll_parse_failed:missing_voice"}
                return {"success": True, "voice": voice.strip(), "raw": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def synthesize(
        self,
        text: str,
        out_path: str,
        api_key: str,
        base_url: str,
        model: str,
        voice: str,
        language_type: Optional[str] = None,
        instructions: Optional[str] = None,
        optimize_instructions: Optional[bool] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        out = Path(out_path)
        t = str(text or "")
        if not t.strip():
            return {"success": False, "error": "empty_text"}
        m = str(model or "").strip()
        if not m:
            return {"success": False, "error": "missing_model"}
        v = str(voice or "").strip()
        if not v:
            return {"success": False, "error": "missing_voice"}

        try:
            async with _dashscope_lock:
                import dashscope

                dashscope.base_http_api_url = base_url.rstrip("/")

                kwargs: Dict[str, Any] = {
                    "model": m,
                    "api_key": api_key,
                    "text": t,
                    "voice": v,
                    "stream": bool(stream),
                }
                if isinstance(language_type, str) and language_type.strip():
                    kwargs["language_type"] = language_type.strip()
                if isinstance(instructions, str) and instructions.strip():
                    kwargs["instructions"] = instructions.strip()
                if optimize_instructions is not None:
                    kwargs["optimize_instructions"] = bool(optimize_instructions)

                resp = await asyncio.to_thread(lambda: dashscope.MultiModalConversation.call(**kwargs))

            url, audio_bytes, req_id = _extract_audio_payload(resp)
            if audio_bytes:
                await _ensure_dir(out)
                out.write_bytes(audio_bytes)
            elif url:
                await _download_to(url, out)
            else:
                return {"success": False, "error": "tts_no_audio_url", "request_id": req_id, "raw": resp}

            dur = await _ffprobe_duration(str(out))
            return {
                "success": True,
                "path": str(out),
                "duration": dur,
                "model": m,
                "voice": v,
                "request_id": req_id,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


qwen_online_tts_service = QwenOnlineTTSService()

