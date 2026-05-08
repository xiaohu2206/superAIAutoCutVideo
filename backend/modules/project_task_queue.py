#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目级串行任务队列：确保同一时间只有一个项目的任务在执行，其它项目的任务排队等待。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from modules.projects_store import projects_store

logger = logging.getLogger(__name__)


@dataclass
class QueuedTaskInfo:
    project_id: str
    scope: str
    task_id: str
    status: str = "waiting"


class ProjectTaskQueue:
    """全局项目级串行任务队列。

    规则：
    - 同一时间只有一个项目的任务可以执行
    - 其它项目的任务按 FIFO 顺序排队
    - 当前项目的所有活跃任务都完成后，自动推进到下一个排队项目
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_project: Optional[str] = None
        self._active_task_count: int = 0
        self._project_queue: List[str] = []
        self._ready_events: Dict[str, asyncio.Event] = {}
        self._project_tasks: Dict[str, List[QueuedTaskInfo]] = {}

    async def acquire(
        self,
        project_id: str,
        scope: str,
        task_id: str,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> None:
        """获取项目执行权限。如果其他项目正在执行，则排队等待。

        Args:
            project_id: 项目ID
            scope: 任务 scope
            task_id: 任务ID
            cancel_event: 可选的取消事件，等待期间会周期性检查
        """
        event: Optional[asyncio.Event] = None
        async with self._lock:
            if self._active_project is None:
                self._active_project = project_id
                self._active_task_count = 1
                project_name = self._resolve_project_name(project_id)
                logger.info(
                    "ProjectTaskQueue: 项目 %s（%s）获得执行权 (task_count=1 scope=%s task_id=%s)",
                    project_name,
                    project_id,
                    scope,
                    task_id,
                )
                return

            if self._active_project == project_id:
                self._active_task_count += 1
                project_name = self._resolve_project_name(project_id)
                logger.info(
                    "ProjectTaskQueue: 项目 %s（%s）增加任务 (task_count=%s scope=%s task_id=%s)",
                    project_name,
                    project_id,
                    self._active_task_count,
                    scope,
                    task_id,
                )
                return

            if project_id not in self._project_queue:
                self._project_queue.append(project_id)
                self._ready_events[project_id] = asyncio.Event()
            elif project_id not in self._ready_events:
                self._ready_events[project_id] = asyncio.Event()
            if project_id not in self._project_tasks:
                self._project_tasks[project_id] = []
            self._project_tasks[project_id].append(
                QueuedTaskInfo(project_id=project_id, scope=scope, task_id=task_id, status="waiting")
            )
            event = self._ready_events[project_id]
            project_name = self._resolve_project_name(project_id)
            logger.info(
                "ProjectTaskQueue: 项目 %s（%s）排队等待 (当前活跃项目=%s 排队位置=%s)",
                project_name,
                project_id,
                self._active_project,
                self._project_queue.index(project_id) + 1,
            )

        try:
            while event is not None and not event.is_set():
                if cancel_event is not None and cancel_event.is_set():
                    project_name = self._resolve_project_name(project_id)
                    raise asyncio.CancelledError(
                        f"项目 {project_name}（{project_id}）在排队等待期间被取消 (scope={scope} task_id={task_id})"
                    )
                try:
                    await asyncio.wait_for(event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            # HTTP 请求断开、前端重复提交作废等普通 coroutine cancellation 也必须清理等待记录；
            # 否则当前任务 release 后可能推进到一个已经没有真实任务的项目，队列会卡在 active_project/count=0。
            await self._cancel_queued(project_id, scope, task_id)
            raise

        async with self._lock:
            if not self._has_queued_task_locked(project_id, scope, task_id):
                project_name = self._resolve_project_name(project_id)
                if self._active_project == project_id and self._active_task_count <= 0:
                    self._active_project = None
                    self._active_task_count = 0
                    await self._advance_queue()
                raise asyncio.CancelledError(
                    f"项目 {project_name}（{project_id}）的排队记录已被清理 (scope={scope} task_id={task_id})"
                )
            self._remove_queued_task_locked(project_id, scope, task_id)
            if self._active_project is None:
                self._active_project = project_id
            elif self._active_project != project_id:
                raise RuntimeError(
                    f"ProjectTaskQueue 状态异常：准备执行项目 {project_id}，但当前活跃项目为 {self._active_project}"
                )
            self._active_task_count += 1
            project_name = self._resolve_project_name(project_id)
            logger.info(
                "ProjectTaskQueue: 项目 %s（%s）从队列中取出开始执行 (task_count=%s scope=%s task_id=%s)",
                project_name,
                project_id,
                self._active_task_count,
                scope,
                task_id,
            )

    async def release(self, project_id: str) -> None:
        """释放项目的一个任务计数。当计数归零时推进到下一个排队项目。"""
        async with self._lock:
            if self._active_project != project_id:
                return
            self._active_task_count -= 1
            project_name = self._resolve_project_name(project_id)
            logger.info(
                "ProjectTaskQueue: 项目 %s（%s）释放任务 (task_count=%s)",
                project_name,
                project_id,
                self._active_task_count,
            )
            if self._active_task_count <= 0:
                self._active_project = None
                self._active_task_count = 0
                await self._advance_queue()

    async def _advance_queue(self) -> None:
        """推进到队列中的下一个项目。

        调用方必须已持有 self._lock。
        """
        while self._project_queue:
            next_project = self._project_queue.pop(0)
            event = self._ready_events.get(next_project)
            tasks = self._project_tasks.get(next_project) or []
            if event is None or not tasks:
                self._ready_events.pop(next_project, None)
                self._project_tasks.pop(next_project, None)
                logger.info(
                    "ProjectTaskQueue: 跳过空排队项目 %s（%s）",
                    self._resolve_project_name(next_project),
                    next_project,
                )
                continue
            if next_project in self._ready_events:
                self._active_project = next_project
                self._active_task_count = 0
                if next_project in self._project_tasks:
                    for task_info in self._project_tasks[next_project]:
                        task_info.status = "ready"
                logger.info("ProjectTaskQueue: 推进到下一个排队项目 %s（%s）", self._resolve_project_name(next_project), next_project)
                event.set()
                del self._ready_events[next_project]
                return

    async def _cancel_queued(self, project_id: str, scope: str, task_id: str) -> None:
        """清理被取消的排队项目记录。"""
        async with self._lock:
            self._remove_queued_task_locked(project_id, scope, task_id)
            has_project_tasks = bool(self._project_tasks.get(project_id))
            if not has_project_tasks and project_id in self._project_queue:
                try:
                    self._project_queue.remove(project_id)
                except ValueError:
                    pass
            if not has_project_tasks:
                event = self._ready_events.pop(project_id, None)
                if event is not None and not event.is_set():
                    event.set()
            if self._active_project == project_id and self._active_task_count <= 0 and not has_project_tasks:
                self._active_project = None
                self._active_task_count = 0
                await self._advance_queue()
            logger.info(
                "ProjectTaskQueue: 排队项目 %s（%s）已被取消 (scope=%s task_id=%s)",
                self._resolve_project_name(project_id),
                project_id,
                scope,
                task_id,
            )

    def _has_queued_task_locked(self, project_id: str, scope: str, task_id: str) -> bool:
        for task_info in self._project_tasks.get(project_id) or []:
            if task_info.scope == scope and task_info.task_id == task_id:
                return True
        return False

    def _remove_queued_task_locked(self, project_id: str, scope: str, task_id: str) -> None:
        tasks = self._project_tasks.get(project_id)
        if not tasks:
            return
        remaining = [
            t for t in tasks
            if not (t.scope == scope and t.task_id == task_id)
        ]
        if remaining:
            self._project_tasks[project_id] = remaining
        else:
            del self._project_tasks[project_id]

    def _resolve_project_name(self, project_id: str) -> str:
        """根据 project_id 解析项目名称，如果找不到则返回 project_id。"""
        p = projects_store.get_project(project_id)
        if p and p.name:
            return p.name
        return project_id

    def get_queue_status(self) -> dict:
        """获取当前任务队列状态。"""
        waiting_projects_info = []
        for pid in self._project_queue:
            tasks_info = []
            if pid in self._project_tasks:
                for t in self._project_tasks[pid]:
                    tasks_info.append({
                        "project_id": t.project_id,
                        "project_name": self._resolve_project_name(t.project_id),
                        "scope": t.scope,
                        "task_id": t.task_id,
                        "status": t.status,
                    })
            waiting_projects_info.append({
                "project_id": pid,
                "project_name": self._resolve_project_name(pid),
                "queue_position": self._project_queue.index(pid) + 1,
                "tasks": tasks_info,
            })

        return {
            "active_project": self._active_project,
            "active_project_name": self._resolve_project_name(self._active_project) if self._active_project else None,
            "active_task_count": self._active_task_count,
            "waiting_projects": waiting_projects_info,
            "total_waiting_projects": len(self._project_queue),
        }


project_task_queue = ProjectTaskQueue()
