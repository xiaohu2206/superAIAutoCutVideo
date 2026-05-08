#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目级串行任务队列：确保同一时间只有一个项目的任务在执行，其它项目的任务排队等待。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
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
            if project_id not in self._project_tasks:
                self._project_tasks[project_id] = []
            self._project_tasks[project_id].append(
                QueuedTaskInfo(project_id=project_id, scope=scope, task_id=task_id, status="waiting")
            )
            project_name = self._resolve_project_name(project_id)
            logger.info(
                "ProjectTaskQueue: 项目 %s（%s）排队等待 (当前活跃项目=%s 排队位置=%s)",
                project_name,
                project_id,
                self._active_project,
                self._project_queue.index(project_id) + 1,
            )

        event = self._ready_events[project_id]
        while not event.is_set():
            if cancel_event is not None and cancel_event.is_set():
                await self._cancel_queued(project_id, scope, task_id)
                project_name = self._resolve_project_name(project_id)
                raise asyncio.CancelledError(
                    f"项目 {project_name}（{project_id}）在排队等待期间被取消 (scope={scope} task_id={task_id})"
                )
            try:
                await asyncio.wait_for(event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

        async with self._lock:
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
        """推进到队列中的下一个项目。"""
        while self._project_queue:
            next_project = self._project_queue.pop(0)
            if next_project in self._ready_events:
                self._active_project = next_project
                self._active_task_count = 0
                if next_project in self._project_tasks:
                    for task_info in self._project_tasks[next_project]:
                        task_info.status = "ready"
                logger.info("ProjectTaskQueue: 推进到下一个排队项目 %s（%s）", self._resolve_project_name(next_project), next_project)
                self._ready_events[next_project].set()
                del self._ready_events[next_project]
                return

    async def _cancel_queued(self, project_id: str, scope: str, task_id: str) -> None:
        """清理被取消的排队项目记录。"""
        async with self._lock:
            if project_id in self._project_tasks:
                self._project_tasks[project_id] = [
                    t for t in self._project_tasks[project_id] if t.task_id != task_id
                ]
                if not self._project_tasks[project_id]:
                    del self._project_tasks[project_id]
            if project_id in self._project_queue:
                try:
                    self._project_queue.remove(project_id)
                except ValueError:
                    pass
            if project_id in self._ready_events:
                del self._ready_events[project_id]
            logger.info(
                "ProjectTaskQueue: 排队项目 %s（%s）已被取消 (scope=%s task_id=%s)",
                self._resolve_project_name(project_id),
                project_id,
                scope,
                task_id,
            )

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
