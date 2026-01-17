#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Deque, Dict, Iterable, List, Optional, Set, Tuple

from .app_paths import user_data_dir


_REDACT_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,'\"\\]+)"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s,'\"\\]+)"),
    re.compile(r"(?i)(bearer\s+)([^\s,'\"\\]+)"),
    re.compile(r"(?i)(token\s*[:=]\s*)([^\s,'\"\\]+)"),
)


def _now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) + f".{int((time.time() % 1) * 1000):03d}"


def _sanitize_text(text: str) -> str:
    if not text:
        return text
    out = str(text)
    for pat in _REDACT_PATTERNS:
        out = pat.sub(lambda m: f"{m.group(1)}***", out)
    return out


def _channel_key(project_id: Optional[str]) -> str:
    if project_id:
        return f"project:{project_id}"
    return "global"


@dataclass(frozen=True)
class SubscribeHandle:
    channel: str
    queue: "asyncio.Queue[Dict[str, Any]]"


class RuntimeLogStore:
    def __init__(self, max_in_memory: int = 5000):
        self._dir = user_data_dir() / "runtime_logs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._max_in_memory = int(max_in_memory)
        self._buffers: Dict[str, Deque[Dict[str, Any]]] = {}
        self._loaded: Set[str] = set()
        self._subscribers: Dict[str, Set["asyncio.Queue[Dict[str, Any]]"]] = {}
        self._last_id: int = 0

    def _next_id(self) -> int:
        with self._lock:
            now_ms = int(time.time() * 1000)
            if now_ms <= self._last_id:
                now_ms = self._last_id + 1
            self._last_id = now_ms
            return now_ms

    def _file_path(self, channel: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9:_-]+", "_", channel)
        return self._dir / f"{safe}.jsonl"

    def _ensure_loaded(self, channel: str) -> None:
        with self._lock:
            if channel in self._loaded:
                return
            buf: Deque[Dict[str, Any]] = deque(maxlen=self._max_in_memory)
            fp = self._file_path(channel)
            if fp.exists():
                try:
                    with fp.open("r", encoding="utf-8") as f:
                        for line in f:
                            ln = line.strip()
                            if not ln:
                                continue
                            try:
                                obj = json.loads(ln)
                                if isinstance(obj, dict):
                                    buf.append(obj)
                            except Exception:
                                continue
                except Exception:
                    pass
            self._buffers[channel] = buf
            self._loaded.add(channel)

    def append(self, entry: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        channel = _channel_key(project_id or entry.get("project_id"))
        self._ensure_loaded(channel)

        data = dict(entry or {})
        if "id" not in data:
            data["id"] = self._next_id()
        if "timestamp" not in data:
            data["timestamp"] = _now_ts()
        if "message" in data:
            data["message"] = _sanitize_text(str(data.get("message") or ""))
        if "detail" in data:
            data["detail"] = _sanitize_text(str(data.get("detail") or ""))
        if "error" in data:
            data["error"] = _sanitize_text(str(data.get("error") or ""))
        data["channel"] = channel

        line = json.dumps(data, ensure_ascii=False)
        fp = self._file_path(channel)
        with self._lock:
            try:
                fp.parent.mkdir(parents=True, exist_ok=True)
                with fp.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
            buf = self._buffers.get(channel)
            if buf is None:
                buf = deque(maxlen=self._max_in_memory)
                self._buffers[channel] = buf
            buf.append(data)
            qs = list(self._subscribers.get(channel, set()))

        for q in qs:
            try:
                q.put_nowait(data)
            except Exception:
                continue
        return data

    def list(self, project_id: Optional[str] = None, after_id: Optional[int] = None, limit: int = 200) -> List[Dict[str, Any]]:
        channel = _channel_key(project_id)
        self._ensure_loaded(channel)
        lim = max(1, min(int(limit or 200), 2000))
        with self._lock:
            items = list(self._buffers.get(channel, deque()))
        if after_id is not None:
            try:
                aid = int(after_id)
                items = [it for it in items if int(it.get("id") or 0) > aid]
            except Exception:
                pass
        return items[-lim:]

    def clear(self, project_id: Optional[str] = None) -> None:
        channel = _channel_key(project_id)
        self._ensure_loaded(channel)
        fp = self._file_path(channel)
        with self._lock:
            try:
                if fp.exists():
                    fp.unlink()
            except Exception:
                pass
            self._buffers[channel] = deque(maxlen=self._max_in_memory)

    def subscribe(self, project_id: Optional[str] = None) -> SubscribeHandle:
        channel = _channel_key(project_id)
        self._ensure_loaded(channel)
        q: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=2000)
        with self._lock:
            s = self._subscribers.get(channel)
            if s is None:
                s = set()
                self._subscribers[channel] = s
            s.add(q)
        return SubscribeHandle(channel=channel, queue=q)

    def unsubscribe(self, handle: SubscribeHandle) -> None:
        with self._lock:
            s = self._subscribers.get(handle.channel)
            if not s:
                return
            s.discard(handle.queue)


runtime_log_store = RuntimeLogStore()

