from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


_TERMINAL_STATUSES = {"completed", "failed", "error", "cancelled"}


def _status_to_message_type(status: str, fallback: Optional[str] = None) -> str:
    explicit = str(fallback or "").strip().lower()
    if explicit:
        return explicit
    st = str(status or "").strip().lower()
    if st == "completed":
        return "completed"
    if st in {"failed", "error"}:
        return "error"
    if st == "cancelled":
        return "cancelled"
    return "progress"


class TaskProgressStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._states: Dict[str, Dict[str, Any]] = {}
        self._active: Dict[Tuple[str, str], str] = {}
        self._last_broadcast: Dict[str, Tuple[float, str, float, str, str]] = {}
        self._broadcast_min_interval = self._read_float_env("TASK_PROGRESS_WS_MIN_INTERVAL_SEC", 0.5)
        self._broadcast_keepalive_interval = self._read_float_env("TASK_PROGRESS_WS_KEEPALIVE_SEC", 2.0)
        self._broadcast_progress_delta = self._read_float_env("TASK_PROGRESS_WS_PROGRESS_DELTA", 0.25)

    def _read_float_env(self, name: str, default: float) -> float:
        try:
            raw = str(os.environ.get(name) or "").strip()
            if not raw:
                return default
            value = float(raw)
            if value < 0:
                return default
            return value
        except Exception:
            return default

    def _key(self, scope: str, project_id: str, task_id: Optional[str]) -> str:
        return f"{scope}::{project_id}::{task_id or ''}"

    def _normalize_status(self, payload: Dict[str, Any], existing: Dict[str, Any]) -> str:
        status = str(payload.get("status") or "").strip().lower()
        if status:
            return status
        msg_type = str(payload.get("type") or "").strip().lower()
        if msg_type == "completed":
            return "completed"
        if msg_type == "error":
            return "failed"
        if msg_type == "cancelled":
            return "cancelled"
        if msg_type == "progress":
            return "running"
        return str(existing.get("status") or "running").strip().lower()

    def set_state(
        self,
        scope: str,
        project_id: str,
        task_id: Optional[str],
        status: Optional[str],
        progress: Optional[float] = None,
        message: Optional[str] = None,
        phase: Optional[str] = None,
        msg_type: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        if not scope or not project_id:
            return
        key = self._key(scope, project_id, task_id)
        should_broadcast = False
        state: Dict[str, Any]
        with self._lock:
            existing = self._states.get(key) or {}
            state = {
                "scope": scope,
                "project_id": project_id,
                "task_id": task_id,
                "status": (status or existing.get("status") or "running"),
                "progress": float(progress)
                if isinstance(progress, (int, float))
                else float(existing.get("progress", 0.0)),
                "message": message if message is not None else existing.get("message"),
                "phase": phase if phase is not None else existing.get("phase"),
                "timestamp": timestamp or datetime.now().isoformat(),
            }
            state["type"] = msg_type if msg_type is not None else _status_to_message_type(str(state.get("status") or ""))
            self._states[key] = state
            self._active[(project_id, scope)] = task_id or ""
            should_broadcast = self._should_broadcast_locked(key, state)
        if should_broadcast:
            self._schedule_ws_broadcast(dict(state))

    def _should_broadcast_locked(self, key: str, state: Dict[str, Any]) -> bool:
        status = str(state.get("status") or "").strip().lower()
        msg_type = _status_to_message_type(status, state.get("type"))
        progress = float(state.get("progress") or 0.0)
        message = str(state.get("message") or "")
        phase = str(state.get("phase") or "")
        now = time.monotonic()
        prev = self._last_broadcast.get(key)

        if status in _TERMINAL_STATUSES or msg_type in {"completed", "error", "cancelled"}:
            self._last_broadcast[key] = (now, status, progress, message, phase)
            return True
        if prev is None:
            self._last_broadcast[key] = (now, status, progress, message, phase)
            return True

        last_at, last_status, last_progress, last_message, last_phase = prev
        elapsed = now - last_at
        changed_text = status != last_status or message != last_message or phase != last_phase
        changed_progress = abs(progress - last_progress) >= self._broadcast_progress_delta
        if (changed_text or changed_progress) and elapsed >= self._broadcast_min_interval:
            self._last_broadcast[key] = (now, status, progress, message, phase)
            return True
        if elapsed >= self._broadcast_keepalive_interval:
            self._last_broadcast[key] = (now, status, progress, message, phase)
            return True
        return False

    def _schedule_ws_broadcast(self, state: Dict[str, Any]) -> None:
        try:
            from modules.ws_manager import manager

            if not getattr(manager, "active_connections", None):
                return
            status = str(state.get("status") or "").strip().lower()
            payload = {
                **state,
                "type": _status_to_message_type(status, state.get("type")),
                "timestamp": state.get("timestamp") or datetime.now().isoformat(),
            }
            message = json.dumps(payload, ensure_ascii=False)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(manager.broadcast(message))
        except Exception:
            logger.debug("task progress ws broadcast schedule failed", exc_info=True)

    def update_from_payload(self, payload: Dict[str, Any]) -> None:
        scope = payload.get("scope")
        project_id = payload.get("project_id")
        if not scope or not project_id:
            return
        task_id = payload.get("task_id")
        key = self._key(scope, project_id, task_id)
        with self._lock:
            existing = self._states.get(key) or {}
            status = self._normalize_status(payload, existing)
            existing_status = str(existing.get("status") or "").strip().lower()
            if existing_status in _TERMINAL_STATUSES and status not in _TERMINAL_STATUSES:
                # Progress callbacks and WS broadcasts can arrive out of order.
                # A late progress event must not revive an already finished task.
                return
            progress = payload.get("progress")
            if not isinstance(progress, (int, float)):
                progress = existing.get("progress", 0.0)
            message = payload.get("message")
            if message is None:
                message = existing.get("message")
            phase = payload.get("phase")
            if phase is None:
                phase = existing.get("phase")
            msg_type = payload.get("type")
            if msg_type is None:
                msg_type = existing.get("type")
            timestamp = payload.get("timestamp") or existing.get("timestamp") or datetime.now().isoformat()
            state = {
                "scope": scope,
                "project_id": project_id,
                "task_id": task_id,
                "status": status,
                "progress": float(progress) if isinstance(progress, (int, float)) else 0.0,
                "message": message,
                "phase": phase,
                "type": msg_type,
                "timestamp": timestamp,
            }
            self._states[key] = state
            self._active[(project_id, scope)] = task_id or ""

    def get_state(self, scope: str, project_id: str, task_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not scope or not project_id:
            return None
        with self._lock:
            if task_id is None:
                task_id = self._active.get((project_id, scope), "")
            key = self._key(scope, project_id, task_id)
            return self._states.get(key)

    def get_latest_running(self, scope: str, project_id: str) -> Optional[Dict[str, Any]]:
        state = self.get_state(scope, project_id)
        if not state:
            return None
        status = str(state.get("status") or "").strip().lower()
        msg_type = str(state.get("type") or "").strip().lower()
        if status in {"running", "processing", "pending"} or msg_type == "progress":
            return state
        return None

    def iter_states_for_scope(self, scope: str) -> List[Dict[str, Any]]:
        """遍历某 scope 下的全部快照（用于队列聚合等，调用方自行过滤终端状态）。"""
        if not scope:
            return []
        prefix = f"{scope}::"
        with self._lock:
            return [dict(v) for k, v in self._states.items() if k.startswith(prefix)]


task_progress_store = TaskProgressStore()
