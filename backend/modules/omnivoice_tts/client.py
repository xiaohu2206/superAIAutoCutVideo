# -*- coding: utf-8 -*-
"""OmniVoice HTTP API 客户端（与业务配置解耦，仅负责请求与轮询）"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

WIN_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

_DEFAULT_TIMEOUT = httpx.Timeout(connect=60.0, read=600.0, write=120.0, pool=60.0)
_DEFAULT_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)

_POLL_STATUS_RETRIES = 8
_POLL_STATUS_RETRY_BASE_SEC = 0.5

_DOWNLOAD_RETRIES = 6
_DOWNLOAD_RETRY_BASE_SEC = 0.5


def _normalize_prefix(api_prefix: str) -> str:
    p = (api_prefix or "/api").strip()
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/api"


def _join(base: str, prefix: str, path: str) -> str:
    base = (base or "").rstrip("/") + "/"
    rel = _normalize_prefix(prefix) + (path if path.startswith("/") else "/" + path)
    return urljoin(base, rel.lstrip("/"))


def _is_transient_omnivoice_http_err(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.RemoteProtocolError):
        return True
    return False


async def _get_task_status_with_client(
    client: httpx.AsyncClient,
    base_url: str,
    api_prefix: str,
    task_id: str,
) -> Dict[str, Any]:
    url = _join(base_url, api_prefix, f"/tts/tasks/{task_id}")
    r = await client.get(url)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else {}


async def probe_omnivoice(base_url: str, api_prefix: str = "/api") -> Tuple[bool, Optional[str]]:
    """检测 OmniVoice 是否可用：请求 clone-voices。"""
    url = _join(base_url, api_prefix, "/clone-voices")
    try:
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            limits=_DEFAULT_LIMITS,
            follow_redirects=True,
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return False, f"http_{r.status_code}"
            try:
                r.json()
            except Exception:
                return False, "invalid_json"
            return True, None
    except Exception as e:
        return False, str(e)


def build_port_candidates(start_port: int, scan_back: int) -> List[int]:
    start = int(start_port)
    n = max(0, int(scan_back))
    return [start - i for i in range(n + 1)]


async def discover_omnivoice(
    host: str,
    start_port: int = 8970,
    scan_back: int = 10,
    api_prefix: str = "/api",
) -> Optional[Tuple[str, int]]:
    """在 host 上探测 OmniVoice API，返回 (base_url, port)。"""
    h = (host or "").strip()
    if not h:
        return None
    for port in build_port_candidates(start_port, scan_back):
        if port <= 0 or port > 65535:
            continue
        base = f"http://{h}:{port}"
        ok, _err = await probe_omnivoice(base, api_prefix)
        if ok:
            return base, port
    return None


async def fetch_clone_voices_json(base_url: str, api_prefix: str) -> Dict[str, Any]:
    url = _join(base_url, api_prefix, "/clone-voices")
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json() if r.content else {}


def _unwrap_data(payload: Dict[str, Any]) -> Any:
    if not isinstance(payload, dict):
        return None
    d = payload.get("data")
    return d if d is not None else payload


async def post_tts_generate(
    base_url: str,
    api_prefix: str,
    text: str,
    voice_id: Optional[str] = None,
    language: Optional[str] = None,
    ref_text: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    url = _join(base_url, api_prefix, "/tts/generate")
    body: Dict[str, Any] = {"text": text}
    if voice_id:
        body["voice_id"] = voice_id
    if language:
        body["language"] = language
    if ref_text is not None:
        body["ref_text"] = ref_text
    if params:
        body["params"] = params
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    tid = None
    if isinstance(data, dict):
        tid = data.get("task_id") or data.get("taskId")
        inner = data.get("data")
        if isinstance(inner, dict):
            tid = tid or inner.get("task_id") or inner.get("taskId")
    wrapped = _unwrap_data(data) if isinstance(data, dict) else data
    if not tid and isinstance(wrapped, dict):
        tid = wrapped.get("task_id") or wrapped.get("taskId")
    if not tid:
        raise RuntimeError("omnivoice_missing_task_id")
    return str(tid)


async def get_task_status(base_url: str, api_prefix: str, task_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        return await _get_task_status_with_client(client, base_url, api_prefix, task_id)


def _task_status_str(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    st = payload.get("status")
    if st:
        return str(st).lower()
    d = _unwrap_data(payload)
    if isinstance(d, dict):
        st2 = d.get("status")
        if st2:
            return str(st2).lower()
        t = d.get("task")
        if isinstance(t, dict) and t.get("status"):
            return str(t.get("status")).lower()
    t2 = payload.get("task")
    if isinstance(t2, dict) and t2.get("status"):
        return str(t2.get("status")).lower()
    return ""


async def poll_task_until_done(
    base_url: str,
    api_prefix: str,
    task_id: str,
    *,
    interval_sec: float = 1,
    timeout_sec: float = 3000.0,
) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(5.0, float(timeout_sec))
    last: Dict[str, Any] = {}
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        while loop.time() < deadline:
            for attempt in range(_POLL_STATUS_RETRIES):
                try:
                    last = await _get_task_status_with_client(client, base_url, api_prefix, task_id)
                    break
                except Exception as e:
                    if not _is_transient_omnivoice_http_err(e) or attempt >= _POLL_STATUS_RETRIES - 1:
                        raise
                    wait = _POLL_STATUS_RETRY_BASE_SEC * (2**attempt)
                    logger.warning(
                        "OmniVoice 轮询状态暂时失败（将重试）: %s (attempt %s/%s)",
                        e,
                        attempt + 1,
                        _POLL_STATUS_RETRIES,
                    )
                    await asyncio.sleep(wait)
            st = _task_status_str(last)
            if st in {"succeeded", "success", "completed", "done"}:
                return last
            if st in {"failed", "error"}:
                err = ""
                d = _unwrap_data(last)
                if isinstance(d, dict):
                    t = d.get("task")
                    if isinstance(t, dict) and t.get("error"):
                        err = str(t.get("error") or "")
                    if not err:
                        err = str(d.get("error") or "")
                if not err and isinstance(last.get("task"), dict):
                    err = str(last["task"].get("error") or "")
                raise RuntimeError(err or "omnivoice_task_failed")
            await asyncio.sleep(interval_sec)
    raise TimeoutError("omnivoice_task_timeout")


async def download_task_audio(
    base_url: str,
    api_prefix: str,
    task_id: str,
    dest_path: Path,
) -> None:
    url = _join(base_url, api_prefix, f"/tts/tasks/{task_id}/audio")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        for attempt in range(_DOWNLOAD_RETRIES):
            try:
                r = await client.get(url)
                r.raise_for_status()
                dest_path.write_bytes(r.content)
                return
            except Exception as e:
                if not _is_transient_omnivoice_http_err(e) or attempt >= _DOWNLOAD_RETRIES - 1:
                    raise
                wait = _DOWNLOAD_RETRY_BASE_SEC * (2**attempt)
                logger.warning(
                    "OmniVoice 下载音频暂时失败（将重试）: %s (attempt %s/%s)",
                    e,
                    attempt + 1,
                    _DOWNLOAD_RETRIES,
                )
                await asyncio.sleep(wait)


async def wav_to_mp3_with_ffmpeg(wav_path: Path, mp3_path: Path) -> bool:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "3",
        str(mp3_path),
    ]
    try:
        if os.name == "nt":
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=WIN_NO_WINDOW,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        rc = await proc.wait()
        return rc == 0 and mp3_path.exists()
    except Exception as e:
        logger.warning("ffmpeg wav->mp3 失败: %s", e)
        return False


async def upload_clone_voice(
    base_url: str,
    api_prefix: str,
    *,
    file_content: bytes,
    filename: str,
    display_name: str,
) -> Dict[str, Any]:
    url = _join(base_url, api_prefix, "/clone-voices/upload")
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        files = {"file": (filename, file_content, "application/octet-stream")}
        data = {"name": display_name}
        r = await client.post(url, files=files, data=data)
        r.raise_for_status()
        try:
            return r.json() if r.content else {}
        except Exception:
            return {}


async def post_clone_voice_select(base_url: str, api_prefix: str, voice_id: str) -> Dict[str, Any]:
    url = _join(base_url, api_prefix, "/clone-voices/select")
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        r = await client.post(url, json={"voice_id": voice_id})
        r.raise_for_status()
        try:
            return r.json() if r.content else {}
        except Exception:
            return {}


async def post_clone_voice_rename(
    base_url: str,
    api_prefix: str,
    voice_id: str,
    new_name: str,
) -> Dict[str, Any]:
    url = _join(base_url, api_prefix, "/clone-voices/rename")
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        r = await client.post(url, json={"voice_id": voice_id, "new_name": new_name})
        r.raise_for_status()
        try:
            return r.json() if r.content else {}
        except Exception:
            return {}


async def post_clone_voice_delete(base_url: str, api_prefix: str, voice_id: str) -> Dict[str, Any]:
    url = _join(base_url, api_prefix, "/clone-voices/delete")
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=_DEFAULT_LIMITS,
        follow_redirects=True,
    ) as client:
        r = await client.post(url, json={"voice_id": voice_id})
        r.raise_for_status()
        try:
            return r.json() if r.content else {}
        except Exception:
            return {}
