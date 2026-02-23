from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

from modules.projects_store import projects_store, Project
from modules.ws_manager import manager
from services.script_generation_service import ScriptGenerationService


logger = logging.getLogger(__name__)


def _now_ts() -> str:
    return datetime.now().isoformat()


def _backend_root_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def _uploads_dir() -> Path:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    (up / "analyses").mkdir(parents=True, exist_ok=True)
    return up


def _to_web_path(p: Path) -> str:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    rel = p.relative_to(up)
    return "/uploads/" + str(rel).replace("\\", "/")


def _resolve_path(path_str: str) -> Path:
    s = (path_str or "").strip()
    if not s:
        return Path("")
    s_norm = s.replace("\\", "/")
    if s_norm.startswith("/uploads/") or s_norm == "/uploads":
        env = os.environ.get("SACV_UPLOADS_DIR")
        rel = s_norm[len("/uploads/"):] if s_norm.startswith("/uploads/") else ""
        candidates = []
        if env:
            candidates.append(Path(env) / rel)
        candidates.append((_backend_root_dir() / "uploads") / rel)
        for c in candidates:
            try:
                if c.exists():
                    return c
            except Exception:
                pass
        return candidates[0] if candidates else Path(rel)
    p = Path(s)
    if p.is_absolute():
        return p
    if s_norm.startswith("/"):
        return _backend_root_dir() / s_norm[1:]
    return Path(s)


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


class GenerateCopywritingService:
    @staticmethod
    async def generate_copywriting(
        project_id: str,
        video_path: str,
        subtitle_path: Optional[str],
        narration_type: str,
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise HTTPException(status_code=404, detail="项目不存在")

        video_abs = _resolve_path(video_path)
        if not video_abs.exists():
            raise HTTPException(status_code=400, detail="视频文件不存在")

        subtitle_status = getattr(p, "subtitle_status", None)
        if subtitle_status and subtitle_status != "ready":
            raise HTTPException(status_code=400, detail="字幕尚未就绪，请先提取字幕或上传字幕")

        try:
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "progress",
                        "scope": "generate_copywriting",
                        "project_id": project_id,
                        "phase": "start",
                        "message": "开始生成解说文案",
                        "progress": 1,
                        "timestamp": _now_ts(),
                    }
                )
            )
        except Exception:
            pass

        subtitle_text = _load_subtitle_text(p, subtitle_path)
        drama_name = p.name or "剧名"

        script_language = getattr(p, "script_language", None)
        script_length = getattr(p, "script_length", None)
        copywriting_word_count = getattr(p, "copywriting_word_count", None)

        try:
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "progress",
                        "scope": "generate_copywriting",
                        "project_id": project_id,
                        "phase": "llm_generate_copywriting",
                        "message": "大模型生成解说文案",
                        "progress": 70,
                        "timestamp": _now_ts(),
                    }
                )
            )
        except Exception:
            pass

        copywriting_text = await ScriptGenerationService.generate_copywriting_pipeline(
            subtitle_content=subtitle_text,
            drama_name=drama_name,
            project_id=project_id,
            script_language=str(script_language) if script_language else None,
            script_length=str(script_length) if script_length else None,
            copywriting_word_count=int(copywriting_word_count) if copywriting_word_count else None,
        )
        copywriting = {
            "version": "1.0",
            "title": drama_name,
            "narration_type": narration_type,
            "content": copywriting_text,
            "generated_at": _now_ts(),
            "metadata": {
                "source": "subtitle",
                "script_language": str(script_language) if script_language else "zh",
                "script_length": str(script_length) if script_length else "",
                "copywriting_word_count": int(copywriting_word_count) if copywriting_word_count else None,
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
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "completed",
                        "scope": "generate_copywriting",
                        "project_id": project_id,
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
