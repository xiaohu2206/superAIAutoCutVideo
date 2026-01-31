from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Any, Dict, Optional, Tuple


class TaskProgressStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._states: Dict[str, Dict[str, Any]] = {}
        self._active: Dict[Tuple[str, str], str] = {}

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
                "type": msg_type if msg_type is not None else existing.get("type"),
                "timestamp": timestamp or existing.get("timestamp") or datetime.now().isoformat(),
            }
            self._states[key] = state
            self._active[(project_id, scope)] = task_id or ""

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


task_progress_store = TaskProgressStore()
