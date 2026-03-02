from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from modules.ws_manager import manager

RunFn = Callable[[str, str, asyncio.Event], Awaitable[Dict[str, Any]]]
LocalUpdateFn = Callable[[str, str, float, str, Optional[str]], None]
HandleUpdateFn = Callable[[str, Optional[asyncio.Task]], None]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskItem:
    task_id: str
    project_id: str
    run_fn: RunFn
    local_update: Optional[LocalUpdateFn] = None
    handle_update: Optional[HandleUpdateFn] = None


class ScopeState:
    def __init__(self, scope: str, concurrency: int) -> None:
        self.scope = scope
        self.concurrency = max(1, int(concurrency or 1))
        self.queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self.pending: Dict[str, TaskItem] = {}
        self.running: Dict[str, asyncio.Task] = {}
        self.dedup: Dict[str, str] = {}
        self.workers: list[asyncio.Task] = []
        self.lock = asyncio.Lock()


class TaskScheduler:
    def __init__(self) -> None:
        self._scopes: Dict[str, ScopeState] = {}
        self._lock = asyncio.Lock()

    async def get_scope_stats(self, scope: str) -> Dict[str, Any]:
        s = self._scopes.get(scope)
        if not s:
            return {
                "scope": scope,
                "concurrency": 0,
                "workers_alive": 0,
                "queue_size": 0,
                "pending": 0,
                "running": 0,
                "dedup": 0,
            }
        async with s.lock:
            self._cleanup_workers(s)
            return {
                "scope": s.scope,
                "concurrency": int(s.concurrency),
                "workers_alive": int(len([w for w in s.workers if not w.done()])),
                "queue_size": int(s.queue.qsize()),
                "pending": int(len(s.pending)),
                "running": int(len(s.running)),
                "dedup": int(len(s.dedup)),
            }

    async def ensure_scope(self, scope: str, concurrency: int) -> ScopeState:
        if not scope:
            raise ValueError("scope is required")
        async with self._lock:
            s = self._scopes.get(scope)
            if not s:
                s = ScopeState(scope=scope, concurrency=max(1, int(concurrency or 1)))
                self._scopes[scope] = s
                for _ in range(s.concurrency):
                    s.workers.append(asyncio.create_task(self._worker(s)))
                logger.info(
                    "任务调度器 scope 已创建: scope=%s concurrency=%s workers=%s",
                    scope,
                    s.concurrency,
                    len(s.workers),
                )
                return s
        await self.resize(scope, concurrency)
        return self._scopes[scope]

    async def enqueue(
        self,
        scope: str,
        project_id: str,
        run_fn: RunFn,
        *,
        task_id: Optional[str] = None,
        concurrency: int = 2,
        dedup: bool = True,
        local_update: Optional[LocalUpdateFn] = None,
        handle_update: Optional[HandleUpdateFn] = None,
    ) -> str:
        if not project_id:
            raise ValueError("project_id is required")
        if not callable(run_fn):
            raise ValueError("run_fn is required")

        s = await self.ensure_scope(scope, concurrency)
        async with s.lock:
            self._cleanup_workers(s)
            if dedup:
                existed = s.dedup.get(project_id)
                if existed and (existed in s.pending or existed in s.running):
                    logger.info(
                        "任务调度器入队去重命中: scope=%s project_id=%s existed_task_id=%s concurrency=%s workers_alive=%s queue_size=%s pending=%s running=%s",
                        s.scope,
                        project_id,
                        existed,
                        s.concurrency,
                        len([w for w in s.workers if not w.done()]),
                        s.queue.qsize(),
                        len(s.pending),
                        len(s.running),
                    )
                    return existed
            if not task_id:
                task_id = f"{scope}_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            item = TaskItem(
                task_id=task_id,
                project_id=project_id,
                run_fn=run_fn,
                local_update=local_update,
                handle_update=handle_update,
            )
            s.pending[task_id] = item
            if dedup:
                s.dedup[project_id] = task_id
            await s.queue.put(task_id)
            logger.info(
                "任务调度器已入队: scope=%s project_id=%s task_id=%s concurrency=%s workers_alive=%s queue_size=%s pending=%s running=%s",
                s.scope,
                project_id,
                task_id,
                s.concurrency,
                len([w for w in s.workers if not w.done()]),
                s.queue.qsize(),
                len(s.pending),
                len(s.running),
            )

        await self._emit(
            scope=scope,
            project_id=project_id,
            task_id=task_id,
            status="queued",
            msg_type="progress",
            phase="queued",
            progress=0.0,
            message="进入队列",
            local_update=local_update,
        )
        return task_id

    async def cancel(self, scope: str, project_id: str, task_id: str) -> bool:
        s = self._scopes.get(scope)
        if not s or not task_id:
            return False

        t = s.running.get(task_id)
        if t:
            try:
                t.cancel()
                logger.info(
                    "任务调度器取消运行中任务: scope=%s project_id=%s task_id=%s",
                    scope,
                    project_id,
                    task_id,
                )
                return True
            except Exception:
                logger.exception(
                    "任务调度器取消运行中任务失败: scope=%s project_id=%s task_id=%s",
                    scope,
                    project_id,
                    task_id,
                )
                return False

        async with s.lock:
            item = s.pending.pop(task_id, None)
            if not item:
                return False
            if s.dedup.get(project_id) == task_id:
                s.dedup.pop(project_id, None)
            logger.info(
                "任务调度器取消排队中任务: scope=%s project_id=%s task_id=%s concurrency=%s workers_alive=%s queue_size=%s pending=%s running=%s",
                s.scope,
                project_id,
                task_id,
                s.concurrency,
                len([w for w in s.workers if not w.done()]),
                s.queue.qsize(),
                len(s.pending),
                len(s.running),
            )

        await self._emit(
            scope=scope,
            project_id=project_id,
            task_id=task_id,
            status="cancelled",
            msg_type="cancelled",
            phase="cancelled",
            progress=0.0,
            message="已停止",
            local_update=item.local_update if item else None,
        )
        return True

    async def resize(self, scope: str, concurrency: int) -> None:
        concurrency = max(1, int(concurrency or 1))
        s = self._scopes.get(scope)
        if not s:
            await self.ensure_scope(scope, concurrency)
            return

        async with s.lock:
            self._cleanup_workers(s)
            if concurrency == s.concurrency:
                return
            before = {
                "concurrency": int(s.concurrency),
                "workers_alive": int(len([w for w in s.workers if not w.done()])),
                "queue_size": int(s.queue.qsize()),
                "pending": int(len(s.pending)),
                "running": int(len(s.running)),
            }
            s.concurrency = concurrency
            alive = [w for w in s.workers if not w.done()]
            s.workers = alive
            if len(alive) < concurrency:
                for _ in range(concurrency - len(alive)):
                    s.workers.append(asyncio.create_task(self._worker(s)))
            elif len(alive) > concurrency:
                for _ in range(len(alive) - concurrency):
                    await s.queue.put(None)
            after = {
                "concurrency": int(s.concurrency),
                "workers_alive": int(len([w for w in s.workers if not w.done()])),
                "queue_size": int(s.queue.qsize()),
                "pending": int(len(s.pending)),
                "running": int(len(s.running)),
            }
            logger.info("任务调度器并发已调整: scope=%s before=%s after=%s", s.scope, before, after)

    async def shutdown(self) -> None:
        async with self._lock:
            scopes = list(self._scopes.values())
        for s in scopes:
            async with s.lock:
                self._cleanup_workers(s)
                for _ in range(len(s.workers)):
                    await s.queue.put(None)

    def _cleanup_workers(self, s: ScopeState) -> None:
        s.workers = [w for w in s.workers if not w.done()]

    async def _worker(self, s: ScopeState) -> None:
        while True:
            item_id = await s.queue.get()
            item: Optional[TaskItem] = None
            started_at: Optional[datetime] = None
            try:
                if item_id is None:
                    logger.info(
                        "任务调度器 worker 退出: scope=%s concurrency=%s workers_alive=%s queue_size=%s pending=%s running=%s",
                        s.scope,
                        s.concurrency,
                        len([w for w in s.workers if not w.done()]),
                        s.queue.qsize(),
                        len(s.pending),
                        len(s.running),
                    )
                    return

                item = s.pending.pop(item_id, None)
                if not item:
                    continue
                started_at = datetime.now()
                logger.info(
                    "任务调度器已出队开始执行: scope=%s project_id=%s task_id=%s concurrency=%s workers_alive=%s queue_size=%s pending=%s running=%s",
                    s.scope,
                    item.project_id,
                    item.task_id,
                    s.concurrency,
                    len([w for w in s.workers if not w.done()]),
                    s.queue.qsize(),
                    len(s.pending),
                    len(s.running),
                )

                cancel_event = task_cancel_store.get_event(s.scope, item.project_id, item.task_id)
                if cancel_event.is_set():
                    await self._emit(
                        scope=s.scope,
                        project_id=item.project_id,
                        task_id=item.task_id,
                        status="cancelled",
                        msg_type="cancelled",
                        phase="cancelled",
                        progress=0.0,
                        message="已停止",
                        local_update=item.local_update,
                    )
                    continue

                await self._emit(
                    scope=s.scope,
                    project_id=item.project_id,
                    task_id=item.task_id,
                    status="processing",
                    msg_type="progress",
                    phase="start",
                    progress=1.0,
                    message="开始执行",
                    local_update=item.local_update,
                )

                exec_task = asyncio.create_task(item.run_fn(item.project_id, item.task_id, cancel_event))
                s.running[item.task_id] = exec_task
                if item.handle_update:
                    try:
                        item.handle_update(item.task_id, exec_task)
                    except Exception:
                        pass

                try:
                    result = await exec_task
                except asyncio.CancelledError:
                    await self._emit(
                        scope=s.scope,
                        project_id=item.project_id,
                        task_id=item.task_id,
                        status="cancelled",
                        msg_type="cancelled",
                        phase="cancelled",
                        progress=0.0,
                        message="已停止",
                        local_update=item.local_update,
                    )
                except Exception as e:
                    logger.exception(
                        "任务调度器任务执行异常: scope=%s project_id=%s task_id=%s",
                        s.scope,
                        item.project_id,
                        item.task_id,
                    )
                    await self._emit(
                        scope=s.scope,
                        project_id=item.project_id,
                        task_id=item.task_id,
                        status="failed",
                        msg_type="error",
                        phase="failed",
                        progress=0.0,
                        message=str(e) or "执行失败",
                        local_update=item.local_update,
                    )
                else:
                    file_path = None
                    if isinstance(result, dict):
                        fp = result.get("file_path")
                        if fp is None:
                            fp = result.get("output_path")
                        if isinstance(fp, str) and fp.strip():
                            file_path = fp.strip()
                    await self._emit(
                        scope=s.scope,
                        project_id=item.project_id,
                        task_id=item.task_id,
                        status="completed",
                        msg_type="completed",
                        phase="completed",
                        progress=100.0,
                        message="执行完成",
                        file_path=file_path,
                        local_update=item.local_update,
                    )
            finally:
                if item:
                    if item.handle_update:
                        try:
                            item.handle_update(item.task_id, None)
                        except Exception:
                            pass
                    try:
                        s.running.pop(item.task_id, None)
                    except Exception:
                        pass
                    try:
                        async with s.lock:
                            if s.dedup.get(item.project_id) == item.task_id:
                                s.dedup.pop(item.project_id, None)
                    except Exception:
                        pass
                    try:
                        ended_at = datetime.now()
                        duration_ms = None
                        if started_at:
                            duration_ms = int((ended_at - started_at).total_seconds() * 1000)
                        logger.info(
                            "任务调度器任务结束: scope=%s project_id=%s task_id=%s duration_ms=%s concurrency=%s workers_alive=%s queue_size=%s pending=%s running=%s",
                            s.scope,
                            item.project_id,
                            item.task_id,
                            duration_ms,
                            s.concurrency,
                            len([w for w in s.workers if not w.done()]),
                            s.queue.qsize(),
                            len(s.pending),
                            len(s.running),
                        )
                    except Exception:
                        pass
                s.queue.task_done()

    async def _emit(
        self,
        *,
        scope: str,
        project_id: str,
        task_id: str,
        status: str,
        msg_type: str,
        phase: str,
        progress: float,
        message: str,
        file_path: Optional[str] = None,
        local_update: Optional[LocalUpdateFn] = None,
    ) -> None:
        ts = datetime.now().isoformat()
        try:
            task_progress_store.set_state(
                scope=scope,
                project_id=project_id,
                task_id=task_id,
                status=status,
                progress=float(progress),
                message=message,
                phase=phase,
                msg_type=msg_type,
                timestamp=ts,
            )
        except Exception:
            pass

        if local_update:
            try:
                local_update(task_id, status, float(progress), message, file_path)
            except Exception:
                pass

        payload: Dict[str, Any] = {
            "type": msg_type,
            "scope": scope,
            "project_id": project_id,
            "task_id": task_id,
            "status": status,
            "phase": phase,
            "message": message,
            "progress": float(progress),
            "timestamp": ts,
        }
        if file_path:
            payload["file_path"] = file_path
        try:
            await manager.broadcast(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass


task_scheduler = TaskScheduler()
