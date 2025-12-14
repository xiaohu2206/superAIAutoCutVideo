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
    script_length: Optional[str] = None
    status: str = Field(default="draft")
    video_path: Optional[str] = None
    video_paths: List[str] = Field(default_factory=list)
    merged_video_path: Optional[str] = None
    # 新增：原始文件名映射与当前生效视频的文件名
    # 不改变现有 video_paths 结构，仅补充元数据
    video_names: Dict[str, str] = Field(default_factory=dict)
    video_current_name: Optional[str] = None
    subtitle_path: Optional[str] = None
    audio_path: Optional[str] = None
    plot_analysis_path: Optional[str] = None
    output_video_path: Optional[str] = None
    script: Optional[Dict[str, Any]] = None
    prompt_selection: Dict[str, Any] = Field(default_factory=dict)
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
                            # 兼容旧数据：填充缺失字段并将单视频并入列表
                            if "video_paths" not in p:
                                p["video_paths"] = []
                            if p.get("video_path") and not p.get("merged_video_path"):
                                vp = p.get("video_path")
                                if vp and vp not in p["video_paths"]:
                                    p["video_paths"].append(vp)
                            # 兼容旧数据：新增文件名元数据字段
                            if "video_names" not in p:
                                p["video_names"] = {}
                            if "video_current_name" not in p:
                                p["video_current_name"] = None
                            proj = Project(**p)
                            # 回填生效视频路径
                            proj = self._refresh_effective_video_path(proj)
                            self._projects[pid] = proj
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
            script_length=None,
            status="draft",
            video_path=None,
            video_paths=[],
            merged_video_path=None,
            subtitle_path=None,
            audio_path=None,
            plot_analysis_path=None,
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
                "script_length",
                "status",
                "video_path",
                "video_paths",
                "merged_video_path",
                "video_names",
                "video_current_name",
                "subtitle_path",
                "audio_path",
                "plot_analysis_path",
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
            project = self._refresh_effective_video_path(project)
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

    def update_prompt_selection(self, project_id: str, feature_key: str, selection: Dict[str, Any]) -> Optional[Project]:
        with self._lock:
            p = self._projects.get(project_id)
            if not p:
                return None
            sel = dict(p.prompt_selection or {})
            sel[str(feature_key)] = selection
            p.prompt_selection = sel
            p.updated_at = datetime.now().isoformat()
            self._persist()
            return p

    def clear_video_path(self, project_id: str) -> Optional[Project]:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            data = project.model_dump()
            data["video_path"] = None
            # 清空单视频兼容：不触动列表与合并路径
            data["updated_at"] = datetime.now().isoformat()
            try:
                project = Project(**data)
            except Exception as e:
                raise ValueError(f"更新数据格式无效: {e}")
            project = self._refresh_effective_video_path(project)
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

    def append_video_path(self, project_id: str, path: str, file_name: Optional[str] = None) -> Optional[Project]:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            data = project.model_dump()
            paths: List[str] = list(data.get("video_paths") or [])
            if path not in paths:
                paths.append(path)
            data["video_paths"] = paths
            # 记录原始文件名映射
            names: Dict[str, str] = dict(data.get("video_names") or {})
            if file_name:
                names[path] = file_name
            else:
                # 兜底使用存储文件名
                try:
                    names[path] = Path(path).name
                except Exception:
                    pass
            data["video_names"] = names
            # 如果没有合并视频且只有一个源视频，则设置生效路径
            if not data.get("merged_video_path") and len(paths) == 1:
                data["video_path"] = paths[0]
                # 同步当前文件名
                data["video_current_name"] = names.get(paths[0])
            data["updated_at"] = datetime.now().isoformat()
            project = Project(**data)
            project = self._refresh_effective_video_path(project)
            self._projects[project_id] = project
            self._persist()
            return project

    def remove_video_path(self, project_id: str, path: str) -> Optional[Project]:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            data = project.model_dump()
            paths: List[str] = list(data.get("video_paths") or [])
            paths = [p for p in paths if p != path]
            data["video_paths"] = paths
            # 移除文件名映射
            names: Dict[str, str] = dict(data.get("video_names") or {})
            if path in names:
                try:
                    del names[path]
                except Exception:
                    pass
            data["video_names"] = names
            # 若没有合并视频，按剩余数量调整生效路径
            if not data.get("merged_video_path"):
                if len(paths) == 1:
                    data["video_path"] = paths[0]
                    data["video_current_name"] = names.get(paths[0])
                elif len(paths) == 0:
                    data["video_path"] = None
                    data["video_current_name"] = None
            data["updated_at"] = datetime.now().isoformat()
            project = Project(**data)
            project = self._refresh_effective_video_path(project)
            self._projects[project_id] = project
            self._persist()
            return project

    def set_merged_video_path(self, project_id: str, path: Optional[str], current_name: Optional[str] = None) -> Optional[Project]:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            data = project.model_dump()
            data["merged_video_path"] = path
            names: Dict[str, str] = dict(data.get("video_names") or {})
            # 合并后使生效路径指向合并结果；清除时按规则回退
            if path:
                data["video_path"] = path
                # 记录合并结果文件名
                if current_name:
                    names[path] = current_name
                    data["video_current_name"] = current_name
                else:
                    try:
                        fallback_name = Path(path).name
                        names[path] = names.get(path, fallback_name)
                        data["video_current_name"] = names[path]
                    except Exception:
                        data["video_current_name"] = None
            else:
                # 回退到单源视频或空
                paths: List[str] = list(data.get("video_paths") or [])
                data["video_path"] = paths[0] if len(paths) == 1 else None
                data["video_current_name"] = names.get(data["video_path"]) if data["video_path"] else None
            data["video_names"] = names
            data["updated_at"] = datetime.now().isoformat()
            project = Project(**data)
            project = self._refresh_effective_video_path(project)
            self._projects[project_id] = project
            self._persist()
            return project

    def _refresh_effective_video_path(self, project: Project) -> Project:
        data = project.model_dump()
        merged = data.get("merged_video_path")
        paths: List[str] = list(data.get("video_paths") or [])
        if merged:
            data["video_path"] = merged
        else:
            data["video_path"] = paths[0] if len(paths) == 1 else None
        # 同步当前文件名
        current_path = data.get("video_path")
        names: Dict[str, str] = dict(data.get("video_names") or {})
        if current_path:
            data["video_current_name"] = names.get(current_path)
            if not data["video_current_name"]:
                try:
                    data["video_current_name"] = Path(current_path).name
                except Exception:
                    data["video_current_name"] = None
        else:
            data["video_current_name"] = None
        return Project(**data)


# 单例实例供路由使用
projects_store = ProjectsStore()
