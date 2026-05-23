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


class ScriptRevisionConflict(ValueError):
    """Raised when a script save is based on a stale revision."""

    def __init__(self, current_revision: int, expected_revision: Optional[int]):
        self.current_revision = int(current_revision or 0)
        self.expected_revision = expected_revision
        super().__init__(
            f"script revision conflict: current={self.current_revision}, expected={expected_revision}"
        )


class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    project_type: str = Field(default="subtitle") # subtitle | visual | omni
    # 全感知（omni）生成档位：low=低消耗/低效果，medium=中消耗，high=高消耗/高效果；非 omni 为 None
    omni_effect_tier: Optional[str] = Field(default=None)
    narration_type: str = Field(default="短剧解说")
    script_length: Optional[str] = None
    original_ratio: Optional[int] = None
    interleave_mode: Optional[str] = Field(default="smart_interleave")
    script_language: str = Field(default="zh")
    copywriting_word_count: Optional[int] = None
    status: str = Field(default="draft")
    video_path: Optional[str] = None
    video_paths: List[str] = Field(default_factory=list)
    merged_video_path: Optional[str] = None
    # 新增：原始文件名映射与当前生效视频的文件名
    # 不改变现有 video_paths 结构，仅补充元数据
    video_names: Dict[str, str] = Field(default_factory=dict)
    video_current_name: Optional[str] = None
    subtitle_path: Optional[str] = None
    subtitle_source: Optional[str] = None
    subtitle_status: Optional[str] = Field(default="none")
    subtitle_updated_by_user: bool = Field(default=False)
    subtitle_updated_at: Optional[str] = None
    subtitle_format: Optional[str] = None
    subtitle_extract_run_id: Optional[str] = None
    asr_provider: str = Field(default="bcut")
    asr_model_key: Optional[str] = None
    asr_language: Optional[str] = None
    audio_path: Optional[str] = None
    chunk_audio_paths: List[str] = Field(default_factory=list)
    chunk_results: List[Dict[str, Any]] = Field(default_factory=list)
    narration_copywriting: Optional[Dict[str, Any]] = None
    narration_copywriting_path: Optional[str] = None
    # 电影解说：用户从外部大模型整理的影片背景（脉络/人物等），生成文案时作为 system 上下文
    narration_film_context: Optional[str] = None
    # 电影解说：用户提供的参考解说全文，生成时作为最后一条 user 消息
    narration_reference_copywriting: Optional[str] = None
    output_video_path: Optional[str] = None
    scenes_path: Optional[str] = None
    scenes_updated_at: Optional[str] = None
    scenes_raw_path: Optional[str] = None
    scenes_raw_updated_at: Optional[str] = None
    # Omni 专用产出（与 visual 的 scenes_path 隔离）
    omni_step1_json_path: Optional[str] = None
    omni_multimodal_json_path: Optional[str] = None
    omni_pipeline_updated_at: Optional[str] = None
    # Omni：解说文案结构化 / 向量化产出（与 omni 多模态管线、visual 镜头数据隔离）
    omni_copywriting_structured_path: Optional[str] = None
    omni_copywriting_embeddings_path: Optional[str] = None
    omni_copywriting_embed_updated_at: Optional[str] = None
    # Omni：解说向量 ↔ 镜头 粗筛/重排产出（与 visual、copywriting_embed 目录隔离）
    omni_shot_match_topk_path: Optional[str] = None
    omni_shot_match_rerank_path: Optional[str] = None
    omni_shot_match_updated_at: Optional[str] = None
    # Omni：全局路径搜索产出（与 omni_shot_match 目录隔离）
    omni_global_path_search_path: Optional[str] = None
    omni_global_path_search_updated_at: Optional[str] = None
    # Omni：解说脚本生成产出（与 visual script、全局路径目录隔离）
    omni_generate_script_path: Optional[str] = None
    omni_generate_script_updated_at: Optional[str] = None
    # 剪映草稿相关字段
    jianying_draft_last_dir: Optional[str] = None
    jianying_draft_last_dir_web: Optional[str] = None
    jianying_draft_dirs: List[str] = Field(default_factory=list)
    script: Optional[Dict[str, Any]] = None
    prompt_selection: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ProjectsStore:
    """基于JSON文件的项目存储管理器"""

    def __init__(self, db_path: Optional[Path] = None):
        from .app_paths import user_data_dir
        data_dir = user_data_dir()
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
                            # 兼容旧数据：剪映草稿字段
                            if "jianying_draft_last_dir" not in p:
                                p["jianying_draft_last_dir"] = None
                            if "jianying_draft_last_dir_web" not in p:
                                p["jianying_draft_last_dir_web"] = None
                            if "jianying_draft_dirs" not in p:
                                p["jianying_draft_dirs"] = []
                            if "jianying_draft_last_zip" in p:
                                p.pop("jianying_draft_last_zip", None)
                            # 兼容旧数据：字幕元信息字段
                            if "subtitle_source" not in p:
                                p["subtitle_source"] = None
                            if "subtitle_status" not in p:
                                p["subtitle_status"] = "ready" if p.get("subtitle_path") else "none"
                            if "subtitle_updated_by_user" not in p:
                                p["subtitle_updated_by_user"] = False
                            if "subtitle_updated_at" not in p:
                                p["subtitle_updated_at"] = p.get("updated_at") or None
                            if "subtitle_format" not in p:
                                p["subtitle_format"] = "compressed_srt_v1" if p.get("subtitle_path") else None
                            if "subtitle_extract_run_id" not in p:
                                p["subtitle_extract_run_id"] = None
                            if "asr_provider" not in p:
                                p["asr_provider"] = "bcut"
                            if "asr_model_key" not in p:
                                p["asr_model_key"] = None
                            if "asr_language" not in p:
                                p["asr_language"] = None
                            if "original_ratio" not in p:
                                p["original_ratio"] = None
                            if "interleave_mode" not in p:
                                p["interleave_mode"] = "smart_interleave"
                            if "script_language" not in p:
                                p["script_language"] = "zh"
                            if "chunk_audio_paths" not in p:
                                p["chunk_audio_paths"] = []
                            if "chunk_results" not in p:
                                p["chunk_results"] = []
                            if "narration_copywriting" not in p:
                                p["narration_copywriting"] = None
                            if "narration_copywriting_path" not in p:
                                p["narration_copywriting_path"] = None
                            if "narration_film_context" not in p:
                                p["narration_film_context"] = None
                            if "narration_reference_copywriting" not in p:
                                p["narration_reference_copywriting"] = None
                            if "project_type" not in p:
                                p["project_type"] = "subtitle"
                            if "omni_effect_tier" not in p:
                                p["omni_effect_tier"] = (
                                    "high"
                                    if str(p.get("project_type") or "").strip().lower() == "omni"
                                    else None
                                )
                            if "scenes_path" not in p:
                                p["scenes_path"] = None
                            if "scenes_updated_at" not in p:
                                p["scenes_updated_at"] = None
                            if "scenes_raw_path" not in p:
                                p["scenes_raw_path"] = None
                            if "scenes_raw_updated_at" not in p:
                                p["scenes_raw_updated_at"] = None
                            if "omni_step1_json_path" not in p:
                                p["omni_step1_json_path"] = None
                            if "omni_multimodal_json_path" not in p:
                                p["omni_multimodal_json_path"] = None
                            if "omni_pipeline_updated_at" not in p:
                                p["omni_pipeline_updated_at"] = None
                            if "omni_copywriting_structured_path" not in p:
                                p["omni_copywriting_structured_path"] = None
                            if "omni_copywriting_embeddings_path" not in p:
                                p["omni_copywriting_embeddings_path"] = None
                            if "omni_copywriting_embed_updated_at" not in p:
                                p["omni_copywriting_embed_updated_at"] = None
                            if "omni_shot_match_topk_path" not in p:
                                p["omni_shot_match_topk_path"] = None
                            if "omni_shot_match_rerank_path" not in p:
                                p["omni_shot_match_rerank_path"] = None
                            if "omni_shot_match_updated_at" not in p:
                                p["omni_shot_match_updated_at"] = None
                            if "omni_global_path_search_path" not in p:
                                p["omni_global_path_search_path"] = None
                            if "omni_global_path_search_updated_at" not in p:
                                p["omni_global_path_search_updated_at"] = None
                            if "omni_generate_script_path" not in p:
                                p["omni_generate_script_path"] = None
                            if "omni_generate_script_updated_at" not in p:
                                p["omni_generate_script_updated_at"] = None
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

    def _get_default_script_length(self, narration_type: str) -> str:
        """根据解说类型获取默认脚本长度"""
        if "电影" in narration_type:
            return "60～80条"
        elif "短剧" in narration_type:
            return "30～40条"
        return "30～40条"

    def list_projects(self) -> List[Project]:
        with self._lock:
            return list(self._projects.values())

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._lock:
            return self._projects.get(project_id)

    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        narration_type: str = "短剧解说",
        project_type: str = "subtitle",
        omni_effect_tier: Optional[str] = None,
    ) -> Project:
        now = datetime.now().isoformat()
        new_id = str(uuid.uuid4())
        effective_narration_type = narration_type or "短剧解说"
        pt = str(project_type or "subtitle").strip().lower()
        tier_norm: Optional[str] = None
        if pt == "omni":
            t = str(omni_effect_tier or "high").strip().lower()
            tier_norm = t if t in ("low", "medium", "high") else "high"
        project = Project(
            id=new_id,
            name=name,
            description=description,
            project_type=project_type,
            omni_effect_tier=tier_norm,
            narration_type=effective_narration_type,
            script_length="auto",
            script_language="zh",
            interleave_mode="smart_interleave",
            status="draft",
            video_path=None,
            video_paths=[],
            merged_video_path=None,
            subtitle_path=None,
            subtitle_source=None,
            subtitle_status="none",
            subtitle_updated_by_user=False,
            subtitle_updated_at=None,
            subtitle_format=None,
            asr_provider="bcut",
            asr_model_key=None,
            asr_language=None,
            audio_path=None,
            chunk_audio_paths=[],
            chunk_results=[],
            narration_copywriting=None,
            narration_copywriting_path=None,
            narration_film_context=None,
            narration_reference_copywriting=None,
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
                "project_type",
                "omni_effect_tier",
                "narration_type",
                "script_length",
                "original_ratio",
                "interleave_mode",
                "script_language",
                "copywriting_word_count",
                "status",
                "video_path",
                "video_paths",
                "merged_video_path",
                "video_names",
                "video_current_name",
                "subtitle_path",
                "subtitle_source",
                "subtitle_status",
                "subtitle_updated_by_user",
                "subtitle_updated_at",
                "subtitle_format",
                "subtitle_extract_run_id",
                "asr_provider",
                "asr_model_key",
                "asr_language",
                "audio_path",
                "chunk_audio_paths",
                "chunk_results",
                "narration_copywriting",
                "narration_copywriting_path",
                "narration_film_context",
                "narration_reference_copywriting",
                "output_video_path",
                "scenes_path",
                "scenes_updated_at",
                "scenes_raw_path",
                "scenes_raw_updated_at",
                "omni_step1_json_path",
                "omni_multimodal_json_path",
                "omni_pipeline_updated_at",
                "omni_copywriting_structured_path",
                "omni_copywriting_embeddings_path",
                "omni_copywriting_embed_updated_at",
                "omni_shot_match_topk_path",
                "omni_shot_match_rerank_path",
                "omni_shot_match_updated_at",
                "omni_global_path_search_path",
                "omni_global_path_search_updated_at",
                "omni_generate_script_path",
                "omni_generate_script_updated_at",
                "jianying_draft_last_dir",
                "jianying_draft_last_dir_web",
                "jianying_draft_dirs",
                "script",
            ]:
                if key not in updates:
                    continue
                if key == "copywriting_word_count":
                    data[key] = updates[key]
                elif key in ("narration_film_context", "narration_reference_copywriting"):
                    v = updates.get(key)
                    data[key] = None if v is None else str(v)
                elif key == "omni_effect_tier":
                    v = updates.get(key)
                    if v is None or v == "":
                        data[key] = None
                    else:
                        s = str(v).strip().lower()
                        data[key] = s if s in ("low", "medium", "high") else None
                elif key == "interleave_mode":
                    v = updates.get(key)
                    if v is None or v == "":
                        data[key] = None
                    else:
                        s = str(v).strip().lower()
                        data[key] = s if s in ("smart_interleave", "original_interleave") else "smart_interleave"
                elif updates[key] is not None:
                    data[key] = updates[key]
                elif key in {"script_length", "original_ratio"}:
                    data[key] = updates[key]
            pt = str(data.get("project_type") or "").strip().lower()
            if pt != "omni":
                data["omni_effect_tier"] = None
            else:
                t = str(data.get("omni_effect_tier") or "high").strip().lower()
                data["omni_effect_tier"] = t if t in ("low", "medium", "high") else "high"
            im = str(data.get("interleave_mode") or "").strip().lower()
            data["interleave_mode"] = im if im in ("smart_interleave", "original_interleave") else "smart_interleave"
            data["updated_at"] = datetime.now().isoformat()
            try:
                project = Project(**data)
            except Exception as e:
                raise ValueError(f"更新数据格式无效: {e}")
            project = self._refresh_effective_video_path(project)
            self._projects[project_id] = project
            self._persist()
            return project

    def _script_revision(self, script: Optional[Dict[str, Any]]) -> int:
        if not isinstance(script, dict):
            return 0
        meta = script.get("metadata") if isinstance(script.get("metadata"), dict) else {}
        try:
            return int(meta.get("omni_revision") or 0)
        except Exception:
            return 0

    def _with_next_script_revision(self, script: Dict[str, Any], current_revision: int) -> Dict[str, Any]:
        next_script = dict(script or {})
        meta = dict(next_script.get("metadata") or {})
        meta["updated_at"] = datetime.now().isoformat()
        meta["omni_revision"] = int(current_revision or 0) + 1
        next_script["metadata"] = meta
        return next_script

    def get_script_revision(self, project_id: str) -> int:
        with self._lock:
            p = self._projects.get(project_id)
            return self._script_revision(p.script if p else None)

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            if project_id in self._projects:
                del self._projects[project_id]
                self._persist()
                return True
            return False

    def save_script(
        self,
        project_id: str,
        script: Dict[str, Any],
        *,
        expected_revision: Optional[int] = None,
    ) -> Optional[Project]:
        with self._lock:
            p = self._projects.get(project_id)
            if not p:
                return None
            current_revision = self._script_revision(p.script)
            if expected_revision is not None and int(expected_revision) != current_revision:
                raise ScriptRevisionConflict(current_revision, expected_revision)
            data = p.model_dump()
            data["script"] = self._with_next_script_revision(script, current_revision)
            data["updated_at"] = datetime.now().isoformat()
            project = Project(**data)
            project = self._refresh_effective_video_path(project)
            self._projects[project_id] = project
            self._persist()
            return project

    def update_script_atomic(
        self,
        project_id: str,
        updater,
        *,
        expected_revision: Optional[int] = None,
    ) -> Optional[Project]:
        with self._lock:
            p = self._projects.get(project_id)
            if not p:
                return None
            current_revision = self._script_revision(p.script)
            if expected_revision is not None and int(expected_revision) != current_revision:
                raise ScriptRevisionConflict(current_revision, expected_revision)
            next_script = updater(dict(p.script or {}), current_revision)
            if next_script is None:
                return p
            data = p.model_dump()
            data["script"] = self._with_next_script_revision(next_script, current_revision)
            data["updated_at"] = datetime.now().isoformat()
            project = Project(**data)
            project = self._refresh_effective_video_path(project)
            self._projects[project_id] = project
            self._persist()
            return project

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
            data["subtitle_source"] = None
            data["subtitle_status"] = "none"
            data["subtitle_updated_by_user"] = False
            data["subtitle_updated_at"] = datetime.now().isoformat()
            data["subtitle_format"] = None
            data["subtitle_extract_run_id"] = None
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
