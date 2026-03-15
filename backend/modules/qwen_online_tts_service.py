import asyncio
import base64
import logging
import os
import random
import string
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)
WIN_NO_WINDOW: int = (
    int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
)

_QWEN_ONLINE_DEFAULT_MAX_CONCURRENCY = 2
_QWEN_ONLINE_DEFAULT_MIN_INTERVAL_MS = 0
_QWEN_ONLINE_DEFAULT_MAX_RETRIES = 4

_qwen_online_sem: Optional[asyncio.Semaphore] = None
_qwen_online_sem_concurrency: int = 0
_qwen_online_sem_lock = asyncio.Lock()

_qwen_online_turn_lock = asyncio.Lock()
_qwen_online_last_started_at: float = 0.0
_qwen_online_min_interval_sec: float = 0.0
_qwen_online_cooldown_until: float = 0.0


def _parse_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    try:
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _parse_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _env_int(name: str) -> Optional[int]:
    return _parse_int(os.environ.get(name))


def _resolve_max_concurrency(v: Optional[int]) -> int:
    env = _env_int("SACV_QWEN_ONLINE_TTS_MAX_CONCURRENCY")
    n = v if isinstance(v, int) else (env if isinstance(env, int) else _QWEN_ONLINE_DEFAULT_MAX_CONCURRENCY)
    return max(1, int(n or 1))


def _resolve_min_interval_sec(v: Optional[float]) -> float:
    env_ms = _env_int("SACV_QWEN_ONLINE_TTS_MIN_INTERVAL_MS")
    ms = None
    if isinstance(v, (int, float)):
        ms = float(v) * 1000.0
    elif isinstance(env_ms, int):
        ms = float(env_ms)
    else:
        ms = float(_QWEN_ONLINE_DEFAULT_MIN_INTERVAL_MS)
    return max(0.0, float(ms or 0.0) / 1000.0)


def _resolve_max_retries(v: Optional[int]) -> int:
    env = _env_int("SACV_QWEN_ONLINE_TTS_MAX_RETRIES")
    n = v if isinstance(v, int) else (env if isinstance(env, int) else _QWEN_ONLINE_DEFAULT_MAX_RETRIES)
    return max(0, int(n or 0))


async def _get_qwen_online_semaphore(concurrency: int) -> asyncio.Semaphore:
    global _qwen_online_sem, _qwen_online_sem_concurrency
    target = max(1, int(concurrency or 1))
    if _qwen_online_sem is not None and _qwen_online_sem_concurrency == target:
        return _qwen_online_sem
    async with _qwen_online_sem_lock:
        if _qwen_online_sem is None or _qwen_online_sem_concurrency != target:
            _qwen_online_sem = asyncio.Semaphore(target)
            _qwen_online_sem_concurrency = target
        return _qwen_online_sem


async def _wait_qwen_online_turn(min_interval_sec: float) -> None:
    global _qwen_online_last_started_at, _qwen_online_min_interval_sec, _qwen_online_cooldown_until
    mi = max(0.0, float(min_interval_sec or 0.0))
    if mi > _qwen_online_min_interval_sec:
        _qwen_online_min_interval_sec = mi
    if _qwen_online_min_interval_sec <= 0.0 and _qwen_online_cooldown_until <= 0.0:
        return
    loop = asyncio.get_running_loop()
    while True:
        wait_sec = 0.0
        async with _qwen_online_turn_lock:
            now = loop.time()
            if _qwen_online_cooldown_until > now:
                wait_sec = max(wait_sec, _qwen_online_cooldown_until - now)
            if _qwen_online_min_interval_sec > 0.0:
                delta = now - _qwen_online_last_started_at
                if delta < _qwen_online_min_interval_sec:
                    wait_sec = max(wait_sec, _qwen_online_min_interval_sec - delta)
            if wait_sec <= 0.0:
                _qwen_online_last_started_at = now
                return
        await asyncio.sleep(wait_sec)


async def _bump_qwen_online_cooldown(delay_sec: float) -> None:
    global _qwen_online_cooldown_until
    d = max(0.0, float(delay_sec or 0.0))
    if d <= 0.0:
        return
    loop = asyncio.get_running_loop()
    until = loop.time() + d
    async with _qwen_online_turn_lock:
        if until > _qwen_online_cooldown_until:
            _qwen_online_cooldown_until = until


def _is_retryable_dashscope_error(status_code: Optional[int], code: Optional[str], message: Optional[str]) -> bool:
    sc = int(status_code) if isinstance(status_code, int) else 0
    c = (code or "").strip()
    m = (message or "").strip().lower()
    if sc in {429, 500, 502, 503, 504}:
        return True
    if "throttling" in c.lower() or "ratequota" in c.lower() or "rate limit" in m or "requests rate" in m:
        return True
    return False


def _compute_backoff_delay_sec(attempt: int, retry_after_sec: Optional[float]) -> float:
    ra = float(retry_after_sec) if isinstance(retry_after_sec, (int, float)) else 0.0
    base = 0.8 * (2 ** max(0, int(attempt)))
    delay = max(ra, base)
    delay = min(30.0, max(0.2, delay))
    jitter = random.uniform(0.75, 1.25)
    return min(30.0, delay * jitter)



def _base_url_from_region(
    region: Optional[str],
    override: Optional[str],
 ) -> str:
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


def _strip_url_query(url: str) -> str:
    try:
        sp = urlsplit(url)
        if not sp.scheme or not sp.netloc:
            return url
        return urlunsplit((sp.scheme, sp.netloc, sp.path, "", ""))
    except Exception:
        return url


def _safe_resp_snapshot(resp: Any) -> Dict[str, Any]:
    try:
        data = (
            resp
            if isinstance(resp, dict)
            else {"repr": repr(resp), "type": type(resp).__name__}
        )
        is_dict = isinstance(data, dict)
        out = data.get("output") if is_dict else None
        status_code = data.get("status_code") if is_dict else None
        request_id = data.get("request_id") if is_dict else None
        code = data.get("code") if is_dict else None
        message = data.get("message") if is_dict else None
        snap: Dict[str, Any] = {
            "status_code": status_code,
            "request_id": request_id,
            "code": code,
            "message": message,
        }
        if isinstance(out, dict):
            audio = out.get("audio")
            if isinstance(audio, dict):
                audio2 = dict(audio)
                if isinstance(audio2.get("data"), str) and audio2["data"]:
                    audio2["data"] = f"<base64:{len(audio2['data'])}>"
                if isinstance(audio2.get("url"), str) and audio2["url"]:
                    audio2["url"] = _strip_url_query(str(audio2["url"]))
                snap["output_audio"] = audio2
            elif audio is not None:
                snap["output_audio"] = str(audio)
            if "choices" in out:
                try:
                    choices = out.get("choices")
                    if isinstance(choices, list) and choices:
                        c0 = choices[0]
                        if isinstance(c0, dict):
                            snap["output_choice0_keys"] = list(c0.keys())
                except Exception:
                    pass
            snap["output_keys"] = list(out.keys())
        elif out is not None:
            snap["output_type"] = type(out).__name__
        return snap
    except Exception:
        return {"repr": repr(resp), "type": type(resp).__name__}


def _extract_dashscope_error(resp: Any) -> Optional[str]:
    try:
        if not isinstance(resp, dict):
            return None
        status_code = resp.get("status_code")
        code = str(resp.get("code") or "").strip()
        message = str(resp.get("message") or "").strip()
        if isinstance(status_code, int) and status_code and status_code != 200:
            parts = [f"dashscope_http_error:{status_code}"]
            if code:
                parts.append(code)
            if message:
                parts.append(message)
            return ":".join(parts)
        if code or message:
            parts = ["dashscope_error"]
            if code:
                parts.append(code)
            if message:
                parts.append(message)
            return ":".join(parts)
        return None
    except Exception:
        return None


def _extract_url_or_b64_audio(x: Any) -> Tuple[Optional[str], Optional[bytes]]:
    if x is None:
        return None, None
    if isinstance(x, str) and x.strip():
        s = x.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s, None
        if s.startswith("data:") and "base64," in s:
            try:
                b64 = s.split("base64,", 1)[1]
                return None, base64.b64decode(b64)
            except Exception:
                return None, None
    if isinstance(x, dict):
        url = x.get("url") or x.get("audio_url") or x.get("audioUrl")
        if isinstance(url, str) and url.strip():
            return url.strip(), None
        data = x.get("data") or x.get("audio_data") or x.get("audioData")
        if isinstance(data, str) and data.strip():
            s = data.strip()
            if s.startswith("data:") and "base64," in s:
                try:
                    b64 = s.split("base64,", 1)[1]
                    return None, base64.b64decode(b64)
                except Exception:
                    return None, None
            try:
                return None, base64.b64decode(s)
            except Exception:
                return None, None
    return None, None


def _extract_audio_payload(
    resp: Any,
) -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
    request_id = _get_any(resp, ("request_id",))
    rid_s = str(request_id).strip() if request_id is not None else None

    audio = _get_any(resp, ("output", "audio"))
    if isinstance(audio, dict):
        url, audio_bytes = _extract_url_or_b64_audio(audio)
        if url or audio_bytes:
            return url, audio_bytes, rid_s

    url2 = _get_any(resp, ("output", "url"))
    if isinstance(url2, str) and url2.strip():
        return url2.strip(), None, rid_s

    out = _get_any(resp, ("output",))
    if isinstance(out, dict):
        url3, audio_bytes3 = _extract_url_or_b64_audio(out)
        if url3 or audio_bytes3:
            return url3, audio_bytes3, rid_s
        choices = out.get("choices")
        if isinstance(choices, list):
            for ch in choices:
                if not isinstance(ch, dict):
                    continue
                msg = ch.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if "audio" in item:
                                url4, audio_bytes4 = _extract_url_or_b64_audio(
                                    item.get("audio")
                                )
                                if url4 or audio_bytes4:
                                    return url4, audio_bytes4, rid_s
                            url5, audio_bytes5 = _extract_url_or_b64_audio(
                                item
                            )
                            if url5 or audio_bytes5:
                                return url5, audio_bytes5, rid_s
                url6, audio_bytes6 = _extract_url_or_b64_audio(msg)
                if url6 or audio_bytes6:
                    return url6, audio_bytes6, rid_s

    return None, None, rid_s


async def _download_to(url: str, out: Path, timeout_sec: float = 90.0) -> None:
    timeout = httpx.Timeout(timeout_sec)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
    ) as client:
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
        voice_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        mime = (audio_mime_type or "audio/mpeg").strip() or "audio/mpeg"
        b64 = base64.b64encode(upload_bytes).decode()
        data_uri = f"data:{mime};base64,{b64}"
        url = base_url.rstrip("/") + "/services/audio/tts/customization"
        preferred = "".join(random.choices(string.ascii_letters, k=10)) or str(preferred_name or "").strip() or "voice"
        payload = {
            "model": "qwen-voice-enrollment",
            "input": {
                "action": "create",
                "target_model": str(target_model or "").strip(),
                "preferred_name": preferred,
                "audio": {"data": data_uri},
                "voice_prompt": str(voice_prompt or "").strip(),
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            timeout = httpx.Timeout(120.0)
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
            ) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code != 200:
                    err = f"enroll_failed:{r.status_code}:{r.text}"
                    return {"success": False, "error": err}
                data = r.json()
                voice = _get_any(data, ("output", "voice"))
                if not isinstance(voice, str) or not voice.strip():
                    return {
                        "success": False,
                        "error": "enroll_parse_failed:missing_voice",
                    }
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
        max_concurrency: Optional[int] = None,
        min_interval_sec: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        if stream:
            return {"success": False, "error": "stream_not_supported"}
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

        gen_url = base_url.rstrip("/") + "/services/aigc/multimodal-generation/generation"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        inp: Dict[str, Any] = {"text": t, "voice": v}
        if isinstance(language_type, str) and language_type.strip():
            inp["language_type"] = language_type.strip()
        if isinstance(instructions, str) and instructions.strip():
            inp["instructions"] = instructions.strip()
        if optimize_instructions is not None:
            inp["optimize_instructions"] = bool(optimize_instructions)
        payload = {"model": m, "input": inp}

        eff_concurrency = _resolve_max_concurrency(max_concurrency if isinstance(max_concurrency, int) else None)
        eff_min_interval = _resolve_min_interval_sec(min_interval_sec if isinstance(min_interval_sec, (int, float)) else None)
        eff_retries = _resolve_max_retries(max_retries if isinstance(max_retries, int) else None)

        last_exc: Optional[Exception] = None
        for attempt in range(eff_retries + 1):
            sem = await _get_qwen_online_semaphore(eff_concurrency)
            await sem.acquire()
            try:
                await _wait_qwen_online_turn(eff_min_interval)
                timeout = httpx.Timeout(120.0)
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                ) as client:
                    r = await client.post(gen_url, json=payload, headers=headers)
                    try:
                        data = r.json()
                    except Exception:
                        data = {"message": r.text}
                    retry_after_sec = None
                    try:
                        ra = r.headers.get("Retry-After")
                        retry_after_sec = _parse_float(ra)
                        if retry_after_sec is not None and retry_after_sec < 0:
                            retry_after_sec = None
                    except Exception:
                        retry_after_sec = None
                    if isinstance(data, dict):
                        data.setdefault("status_code", r.status_code)
                        if retry_after_sec is not None:
                            data.setdefault("retry_after_sec", retry_after_sec)
                        if not data.get("request_id"):
                            rid = r.headers.get("X-DashScope-Request-Id") or r.headers.get("x-dashscope-request-id")
                            if isinstance(rid, str) and rid.strip():
                                data["request_id"] = rid.strip()
                    else:
                        data = {"status_code": r.status_code, "output": data}
                        if retry_after_sec is not None:
                            data["retry_after_sec"] = retry_after_sec
                    resp = data
            except Exception as e:
                last_exc = e
                if attempt < eff_retries:
                    delay = _compute_backoff_delay_sec(attempt, None)
                    await _bump_qwen_online_cooldown(delay)
                    await asyncio.sleep(delay)
                    continue
                return {"success": False, "error": str(e)}
            finally:
                try:
                    sem.release()
                except Exception:
                    pass

            err = _extract_dashscope_error(resp)
            if err:
                status_code = resp.get("status_code") if isinstance(resp, dict) else None
                code = resp.get("code") if isinstance(resp, dict) else None
                message = resp.get("message") if isinstance(resp, dict) else None
                retry_after_raw = resp.get("retry_after_sec") if isinstance(resp, dict) else None
                retry_after_sec2 = _parse_float(retry_after_raw)
                if _is_retryable_dashscope_error(status_code if isinstance(status_code, int) else None, str(code) if code is not None else None, str(message) if message is not None else None) and attempt < eff_retries:
                    delay = _compute_backoff_delay_sec(attempt, retry_after_sec2)
                    await _bump_qwen_online_cooldown(delay)
                    await asyncio.sleep(delay)
                    continue
                request_id_raw = _get_any(resp, ("request_id",))
                request_id = str(request_id_raw or "").strip() or None
                return {
                    "success": False,
                    "error": err,
                    "request_id": request_id,
                    "raw": _safe_resp_snapshot(resp),
                }

            url, audio_bytes, req_id = _extract_audio_payload(resp)
            if audio_bytes:
                await _ensure_dir(out)
                out.write_bytes(audio_bytes)
            elif url:
                await _download_to(url, out)
            else:
                return {
                    "success": False,
                    "error": "tts_no_audio_url",
                    "request_id": req_id,
                    "raw": _safe_resp_snapshot(resp),
                }

            dur = await _ffprobe_duration(str(out))
            return {
                "success": True,
                "path": str(out),
                "duration": dur,
                "model": m,
                "voice": v,
                "request_id": req_id,
            }

        if last_exc is not None:
            return {"success": False, "error": str(last_exc)}
        return {"success": False, "error": "unknown_error"}


qwen_online_tts_service = QwenOnlineTTSService()
