#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目存储模块（文件型）
使用JSON文件进行轻量级持久化，提供项目的增删改查接口。

适用于无数据库环境的本地开发与桌面运行。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from threading import RLock

import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    narration_type: str = Field(default="短剧解说")
    status: str = Field(default="draft")  # draft | processing | completed | failed
    video_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    output_video_path: Optional[str] = None
    script: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str


class ProjectsStore:
    """基于JSON文件的项目存储管理器"""

    def __init__(self, db_path: Optional[Path] = None):
        backend_dir = Path(__file__).resolve().parents[1]
        data_dir = backend_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path or (data_dir / "projects.json")
        self._lock = RLock()
        self._projects: Dict[str, Project] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.db_path.exists():
                try:
                    data = json.loads(self.db_path.read_text(encoding="utf-8"))
                    for pid, p in data.items():
                        try:
                            self._projects[pid] = Project(**p)
                        except Exception as e:
                            logger.warning(f"项目数据解析失败（跳过）: {pid} - {e}")
                except Exception as e:
                    logger.error(f"加载项目数据失败: {e}")
            else:
                # 初始化空文件
                self._persist()

    def _persist(self) -> None:
        with self._lock:
            try:
                serializable = {pid: p.model_dump() for pid, p in self._projects.items()}
                self.db_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.error(f"保存项目数据失败: {e}")

    def list_projects(self) -> List[Project]:
        with self._lock:
            return list(self._projects.values())

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._lock:
            return self._projects.get(project_id)

    def create_project(self, name: str, description: Optional[str] = None, narration_type: str = "短剧解说") -> Project:
        now = datetime.now().isoformat()
        new_id = str(uuid.uuid4())
        project = Project(
            id=new_id,
            name=name,
            description=description,
            narration_type=narration_type or "短剧解说",
            status="draft",
            video_path=None,
            subtitle_path=None,
            output_video_path=None,
            script=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._projects[new_id] = project
            self._persist()
        return project

    def update_project(self, project_id: str, updates: Dict[str, Any]) -> Optional[Project]:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            data = project.model_dump()
            # 允许更新的字段
            for key in [
                "name",
                "description",
                "narration_type",
                "status",
                "video_path",
                "subtitle_path",
                "output_video_path",
                "script",
            ]:
                if key in updates and updates[key] is not None:
                    data[key] = updates[key]
            data["updated_at"] = datetime.now().isoformat()
            try:
                project = Project(**data)
            except Exception as e:
                raise ValueError(f"更新数据格式无效: {e}")
            self._projects[project_id] = project
            self._persist()
            return project

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            if project_id in self._projects:
                del self._projects[project_id]
                self._persist()
                return True
            return False

    def save_script(self, project_id: str, script: Dict[str, Any]) -> Optional[Project]:
        return self.update_project(project_id, {"script": script})

    def clear_video_path(self, project_id: str) -> Optional[Project]:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            data = project.model_dump()
            data["video_path"] = None
            data["updated_at"] = datetime.now().isoformat()
            try:
                project = Project(**data)
            except Exception as e:
                raise ValueError(f"更新数据格式无效: {e}")
            self._projects[project_id] = project
            self._persist()
            return project

    def clear_subtitle_path(self, project_id: str) -> Optional[Project]:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            data = project.model_dump()
            data["subtitle_path"] = None
            data["updated_at"] = datetime.now().isoformat()
            try:
                project = Project(**data)
            except Exception as e:
                raise ValueError(f"更新数据格式无效: {e}")
            self._projects[project_id] = project
            self._persist()
            return project


# 单例实例供路由使用
projects_store = ProjectsStore()