from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

from modules.projects_store import projects_store, Project
from modules.ws_manager import manager
from modules.task_progress_store import task_progress_store
from services.script_generation_service import ScriptGenerationService
from modules.app_paths import uploads_dir as app_uploads_dir, resolve_uploads_path, to_uploads_web_path


logger = logging.getLogger(__name__)


def _now_ts() -> str:
    return datetime.now().isoformat()


def _uploads_dir() -> Path:
    return app_uploads_dir()


def _to_web_path(p: Path) -> str:
    return to_uploads_web_path(p)


def _resolve_path(path_str: str) -> Path:
    return resolve_uploads_path(path_str)


def _load_subtitle_text(p: Project, subtitle_path: Optional[str]) -> str:
    sub_abs: Optional[Path] = None
    if p.subtitle_path:
        cand = _resolve_path(p.subtitle_path)
        if cand.exists():
            sub_abs = cand
    if not sub_abs and subtitle_path:
        cand = _resolve_path(subtitle_path)
        if cand.exists():
            sub_abs = cand
            if not getattr(p, "subtitle_path", None):
                projects_store.update_project(
                    p.id,
                    {
                        "subtitle_path": subtitle_path,
                        "subtitle_status": "ready",
                        "subtitle_updated_at": _now_ts(),
                    },
                )
    if not sub_abs:
        raise HTTPException(status_code=400, detail="请先提取字幕或上传字幕")
    return sub_abs.read_text(encoding="utf-8", errors="ignore")


def _movie_narration_film_context(p: Project, narration_type: str) -> Optional[str]:
    t = (narration_type or "").strip()
    if "电影解说" not in t:
        return None
    raw = getattr(p, "narration_film_context", None)
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def _movie_narration_reference_copywriting(p: Project, narration_type: str) -> Optional[str]:
    t = (narration_type or "").strip()
    if "电影解说" not in t:
        return None
    raw = getattr(p, "narration_reference_copywriting", None)
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def _load_scenes_data(p: Project, project_id: str) -> Dict[str, Any]:
    scenes_abs: Optional[Path] = None
    if getattr(p, "scenes_path", None):
        cand = _resolve_path(str(getattr(p, "scenes_path", None) or ""))
        if cand.exists():
            scenes_abs = cand
    if not scenes_abs:
        cand = _uploads_dir() / "analyses" / f"{project_id}_scenes.json"
        if cand.exists():
            scenes_abs = cand
    if not scenes_abs:
        raise HTTPException(status_code=400, detail="镜头数据不存在，请先提取镜头")

    try:
        raw = scenes_abs.read_text(encoding="utf-8", errors="ignore")
        scenes_data = json.loads(raw) if raw.strip() else {}
    except Exception:
        scenes_data = {}
    if not isinstance(scenes_data, dict) or not isinstance(scenes_data.get("scenes"), list) or not scenes_data.get("scenes"):
        raise HTTPException(status_code=400, detail="镜头数据无效，请重新提取镜头")
    return scenes_data


class GenerateCopywritingService:
    @staticmethod
    async def generate_copywriting(
        project_id: str,
        video_path: str,
        subtitle_path: Optional[str],
        narration_type: str,
        *,
        task_id: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise HTTPException(status_code=404, detail="项目不存在")

        video_abs = _resolve_path(video_path)
        if not video_abs.exists():
            raise HTTPException(status_code=400, detail="视频文件不存在")

        project_type = str(getattr(p, "project_type", None) or "subtitle").strip().lower()
        use_visual = project_type == "visual"

        if not use_visual:
            subtitle_status = getattr(p, "subtitle_status", None)
            if subtitle_status and subtitle_status != "ready":
                raise HTTPException(status_code=400, detail="字幕尚未就绪，请先提取字幕或上传字幕")

        try:
            if task_id:
                try:
                    task_progress_store.set_state(
                        scope="generate_copywriting",
                        project_id=project_id,
                        task_id=task_id,
                        status="processing",
                        progress=1.0,
                        message="开始生成解说文案",
                        phase="start",
                        msg_type="progress",
                        timestamp=_now_ts(),
                    )
                except Exception:
                    pass
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "progress",
                        "scope": "generate_copywriting",
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "start",
                        "message": "开始生成解说文案",
                        "progress": 1,
                        "timestamp": _now_ts(),
                    }
                )
            )
        except Exception:
            pass

        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        subtitle_text = _load_subtitle_text(p, subtitle_path) if not use_visual else ""
        scenes_data = _load_scenes_data(p, project_id) if use_visual else None
        drama_name = p.name or "剧名"

        script_language = getattr(p, "script_language", None)
        script_length = getattr(p, "script_length", None)
        copywriting_word_count = getattr(p, "copywriting_word_count", None)

        try:
            if task_id:
                try:
                    task_progress_store.set_state(
                        scope="generate_copywriting",
                        project_id=project_id,
                        task_id=task_id,
                        status="processing",
                        progress=70.0,
                        message="大模型生成解说文案",
                        phase="llm_generate_copywriting",
                        msg_type="progress",
                        timestamp=_now_ts(),
                    )
                except Exception:
                    pass
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "progress",
                        "scope": "generate_copywriting",
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "llm_generate_copywriting",
                        "message": "大模型生成解说文案",
                        "progress": 70,
                        "timestamp": _now_ts(),
                    }
                )
            )
        except Exception:
            pass

        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        film_ctx = _movie_narration_film_context(p, narration_type)
        reference_cw = _movie_narration_reference_copywriting(p, narration_type)

        if use_visual and scenes_data is not None:
            copywriting_text = await ScriptGenerationService.generate_copywriting_pipeline_from_scenes(
                scenes_data=scenes_data,
                drama_name=drama_name,
                project_id=project_id,
                script_language=str(script_language) if script_language else None,
                script_length=str(script_length) if script_length else None,
                copywriting_word_count=int(copywriting_word_count) if copywriting_word_count else None,
                film_context=film_ctx,
                reference_copywriting=reference_cw,
                cancel_event=cancel_event,
            )
        else:
            copywriting_text = await ScriptGenerationService.generate_copywriting_pipeline(
                subtitle_content=subtitle_text,
                drama_name=drama_name,
                project_id=project_id,
                script_language=str(script_language) if script_language else None,
                script_length=str(script_length) if script_length else None,
                copywriting_word_count=int(copywriting_word_count) if copywriting_word_count else None,
                film_context=film_ctx,
                reference_copywriting=reference_cw,
                cancel_event=cancel_event,
            )
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()
        copywriting = {
            "version": "1.0",
            "title": drama_name,
            "narration_type": narration_type,
            "content": copywriting_text,
            "generated_at": _now_ts(),
            "metadata": {
                "source": "scene" if use_visual else "subtitle",
                "script_language": str(script_language) if script_language else "zh",
                "script_length": str(script_length) if script_length else "",
                "copywriting_word_count": int(copywriting_word_count) if copywriting_word_count else None,
                "film_context_included": bool(film_ctx),
                "reference_copywriting_included": bool(reference_cw),
            },
        }

        out_dir = _uploads_dir() / "analyses"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"{project_id}_copywriting_{ts}.json"
        out_path.write_text(json.dumps(copywriting, ensure_ascii=False, indent=2), encoding="utf-8")
        web_path = _to_web_path(out_path)
        projects_store.update_project(
            project_id,
            {
                "narration_copywriting": copywriting,
                "narration_copywriting_path": web_path,
            },
        )

        try:
            if task_id:
                try:
                    task_progress_store.set_state(
                        scope="generate_copywriting",
                        project_id=project_id,
                        task_id=task_id,
                        status="completed",
                        progress=100.0,
                        message="解说文案生成成功",
                        phase="done",
                        msg_type="completed",
                        timestamp=_now_ts(),
                    )
                except Exception:
                    pass
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "completed",
                        "scope": "generate_copywriting",
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "done",
                        "message": "解说文案生成成功",
                        "progress": 100,
                        "timestamp": _now_ts(),
                    }
                )
            )
        except Exception:
            pass

        return {
            "message": "解说文案生成成功",
            "data": {
                "copywriting": copywriting,
            },
            "timestamp": _now_ts(),
        }


generate_copywriting_service = GenerateCopywritingService()
