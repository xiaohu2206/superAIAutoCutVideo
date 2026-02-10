from __future__ import annotations

import asyncio
from threading import RLock
from typing import Dict, Optional, Set, Tuple


class TaskCancelStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._events: Dict[Tuple[str, str, str], asyncio.Event] = {}
        self._procs: Dict[Tuple[str, str, str], Set[asyncio.subprocess.Process]] = {}

    def _key(self, scope: str, project_id: str, task_id: str) -> Tuple[str, str, str]:
        return (str(scope or ""), str(project_id or ""), str(task_id or ""))

    def get_event(self, scope: str, project_id: str, task_id: str) -> asyncio.Event:
        k = self._key(scope, project_id, task_id)
        with self._lock:
            ev = self._events.get(k)
            if ev is None:
                ev = asyncio.Event()
                self._events[k] = ev
            return ev

    def register_process(self, scope: str, project_id: str, task_id: str, proc: asyncio.subprocess.Process) -> None:
        if not proc:
            return
        k = self._key(scope, project_id, task_id)
        with self._lock:
            s = self._procs.get(k)
            if s is None:
                s = set()
                self._procs[k] = s
            s.add(proc)

    def unregister_process(self, scope: str, project_id: str, task_id: str, proc: asyncio.subprocess.Process) -> None:
        k = self._key(scope, project_id, task_id)
        with self._lock:
            s = self._procs.get(k)
            if not s:
                return
            try:
                s.discard(proc)
            except Exception:
                return
            if not s:
                self._procs.pop(k, None)

    async def cancel(self, scope: str, project_id: str, task_id: str) -> int:
        k = self._key(scope, project_id, task_id)
        ev = self.get_event(scope, project_id, task_id)
        ev.set()

        with self._lock:
            procs = list(self._procs.get(k) or [])

        stopped = 0
        for proc in procs:
            try:
                if proc.returncode is not None:
                    continue
                try:
                    proc.terminate()
                except ProcessLookupError:
                    continue
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.5)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=1.5)
                    except Exception:
                        pass
                stopped += 1
            except Exception:
                continue
        return stopped


task_cancel_store = TaskCancelStore()

