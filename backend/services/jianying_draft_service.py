from __future__ import annotations

import asyncio
import json
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
from typing import Any, Dict, List, Optional, Tuple

from modules.projects_store import Project, projects_store
from modules.video_processor import video_processor
from modules.ws_manager import manager
from modules.config.jianying_config import jianying_config_manager


def _now_ts() -> str:
    return datetime.now().isoformat()

async def _to_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _backend_root_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def _uploads_dir() -> Path:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    (up / "jianying_drafts").mkdir(parents=True, exist_ok=True)
    return up


def _to_web_path(p: Path) -> str:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    rel = p.relative_to(up)
    return "/uploads/" + str(rel).replace("\\", "/")


def _resolve_path(path_or_web: str) -> Path:
    root = _backend_root_dir()
    path_str = (path_or_web or "").strip()
    if not path_str:
        return Path("")
    if path_str.startswith("/"):
        return root / path_str[1:]
    return Path(path_str)


def _safe_file_stem(name: str, fallback: str) -> str:
    invalid = '<>:"/\\|?*'
    safe = "".join("_" if ch in invalid else ch for ch in (name or "").strip()).strip()
    safe = safe.replace(".", "_").strip()
    return safe or fallback


def _s_to_us(v: float) -> int:
    try:
        return int(round(float(v) * 1_000_000))
    except Exception:
        return 0


@dataclass
class DraftGenerateResult:
    task_id: str
    zip_abs: Path
    zip_web: str

@dataclass
class DraftGenerateFolderResult:
    task_id: str
    dir_abs: Path
    dir_web: str


class JianyingDraftService:
    SCOPE = "generate_jianying_draft"

    @staticmethod
    async def _broadcast(payload: Dict[str, Any]) -> None:
        try:
            await manager.broadcast(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    @staticmethod
    async def generate_draft_zip(project_id: str, task_id: str) -> DraftGenerateResult:
        p: Optional[Project] = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")

        tmp_dir: Optional[Path] = None

        try:
            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "start",
                "message": "开始生成剪映草稿",
                "progress": 1,
                "timestamp": _now_ts(),
            })

            input_abs = _resolve_path(p.video_path or "")
            if not input_abs.exists():
                raise ValueError("原始视频文件不存在")

            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "prepare",
                "message": "读取素材信息",
                "progress": 8,
                "timestamp": _now_ts(),
            })

            video_dur = await video_processor._ffprobe_duration(str(input_abs), "format") or 0.0

            segments = JianyingDraftService._normalize_segments(p, video_dur)
            if not segments:
                raise ValueError("没有可用片段生成草稿")

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            uploads_root = _uploads_dir()
            tmp_dir = uploads_root / "jianying_drafts" / "tmp" / f"{project_id}_{ts}_{task_id[:8]}"
            target_dir_cfg = jianying_config_manager.get_draft_path()
            if target_dir_cfg and target_dir_cfg.exists():
                out_base = target_dir_cfg
            else:
                out_base = uploads_root / "jianying_drafts" / "outputs" / project_id
            tmp_dir.mkdir(parents=True, exist_ok=True)
            out_base.mkdir(parents=True, exist_ok=True)

            zip_abs = out_dir / f"{project_id}_jianying_draft_{ts}.zip"
            folder_name = f"JianyingDraft_{_safe_file_stem(p.name or '', project_id)}_{ts}"

            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "copy_materials",
                "message": "复制素材文件",
                "progress": 20,
                "timestamp": _now_ts(),
            })

            draft_root = tmp_dir / folder_name
            materials_videos = draft_root / "materials" / "videos"
            materials_videos.mkdir(parents=True, exist_ok=True)
            video_dest = materials_videos / input_abs.name
            await _to_thread(shutil.copy2, input_abs, video_dest)

            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "write_json",
                "message": "生成草稿 JSON",
                "progress": 65,
                "timestamp": _now_ts(),
            })

            draft_content, draft_meta = JianyingDraftService._build_draft_json(
                project=p,
                segments=segments,
                video_rel_path=str(Path("materials") / "videos" / input_abs.name).replace("\\", "/"),
                video_duration_s=float(video_dur or 0.0),
            )

            (draft_root / "draft_content.json").write_text(
                json.dumps(draft_content, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            (draft_root / "draft_meta_info.json").write_text(
                json.dumps(draft_meta, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "zip",
                "message": "打包草稿文件",
                "progress": 90,
                "timestamp": _now_ts(),
            })

            await _to_thread(JianyingDraftService._zip_dir, tmp_dir, zip_abs)

            copied_to: Optional[str] = None
            try:
                target_dir = jianying_config_manager.get_draft_path()
                if target_dir and target_dir.exists():
                    dst = target_dir / zip_abs.name
                    await _to_thread(shutil.copy2, zip_abs, dst)
                    copied_to = str(dst)
            except Exception:
                copied_to = None

            zip_web = _to_web_path(zip_abs)
            await JianyingDraftService._broadcast({
                "type": "completed",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "completed",
                "message": "剪映草稿生成完成",
                "progress": 100,
                "file_path": zip_web,
                "copied_to": copied_to,
                "timestamp": _now_ts(),
            })

            return DraftGenerateResult(task_id=task_id, zip_abs=zip_abs, zip_web=zip_web)
        except Exception as e:
            await JianyingDraftService._broadcast({
                "type": "error",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "failed",
                "message": f"剪映草稿生成失败: {str(e)}",
                "progress": 0,
                "timestamp": _now_ts(),
            })
            raise
        finally:
            try:
                if tmp_dir and tmp_dir.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    @staticmethod
    async def generate_draft_folder(project_id: str, task_id: str) -> DraftGenerateFolderResult:
        p: Optional[Project] = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")

        tmp_dir: Optional[Path] = None

        try:
            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "start",
                "message": "开始生成剪映草稿",
                "progress": 1,
                "timestamp": _now_ts(),
            })

            input_abs = _resolve_path(p.video_path or "")
            if not input_abs.exists():
                raise ValueError("原始视频文件不存在")

            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "prepare",
                "message": "读取素材信息",
                "progress": 8,
                "timestamp": _now_ts(),
            })

            video_dur = await video_processor._ffprobe_duration(str(input_abs), "format") or 0.0

            segments = JianyingDraftService._normalize_segments(p, video_dur)
            if not segments:
                raise ValueError("没有可用片段生成草稿")

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            uploads_root = _uploads_dir()
            tmp_dir = uploads_root / "jianying_drafts" / "tmp" / f"{project_id}_{ts}_{task_id[:8]}"
            out_dir = uploads_root / "jianying_drafts" / "outputs" / project_id
            tmp_dir.mkdir(parents=True, exist_ok=True)
            out_dir.mkdir(parents=True, exist_ok=True)

            folder_name = f"JianyingDraft_{_safe_file_stem(p.name or '', project_id)}_{ts}"

            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "copy_materials",
                "message": "复制素材文件",
                "progress": 20,
                "timestamp": _now_ts(),
            })

            draft_root = tmp_dir / folder_name
            materials_videos = draft_root / "materials" / "videos"
            materials_videos.mkdir(parents=True, exist_ok=True)
            video_dest = materials_videos / input_abs.name
            await _to_thread(shutil.copy2, input_abs, video_dest)

            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "write_json",
                "message": "生成草稿 JSON",
                "progress": 65,
                "timestamp": _now_ts(),
            })

            draft_content, draft_meta = JianyingDraftService._build_draft_json(
                project=p,
                segments=segments,
                video_rel_path=str(Path("materials") / "videos" / input_abs.name).replace("\\", "/"),
                video_duration_s=float(video_dur or 0.0),
            )

            (draft_root / "draft_content.json").write_text(
                json.dumps(draft_content, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            (draft_root / "draft_meta_info.json").write_text(
                json.dumps(draft_meta, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

            await JianyingDraftService._broadcast({
                "type": "progress",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "output",
                "message": "生成草稿目录",
                "progress": 90,
                "timestamp": _now_ts(),
            })

            dest_dir = out_base / folder_name
            if dest_dir.exists():
                try:
                    shutil.rmtree(dest_dir, ignore_errors=True)
                except Exception:
                    pass
            await _to_thread(shutil.copytree, draft_root, dest_dir)

            copied_to: Optional[str] = None

            try:
                dir_web = _to_web_path(dest_dir)
            except Exception:
                dir_web = str(dest_dir)
            await JianyingDraftService._broadcast({
                "type": "completed",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "completed",
                "message": "剪映草稿生成完成",
                "progress": 100,
                "file_path": dir_web,
                "copied_to": copied_to,
                "timestamp": _now_ts(),
            })

            return DraftGenerateFolderResult(task_id=task_id, dir_abs=dest_dir, dir_web=dir_web)
        except Exception as e:
            await JianyingDraftService._broadcast({
                "type": "error",
                "scope": JianyingDraftService.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "failed",
                "message": f"剪映草稿生成失败: {str(e)}",
                "progress": 0,
                "timestamp": _now_ts(),
            })
            raise
        finally:
            try:
                if tmp_dir and tmp_dir.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    @staticmethod
    def _zip_dir(src_dir: Path, zip_path: Path) -> None:
        if zip_path.exists():
            try:
                zip_path.unlink()
            except Exception:
                pass

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in src_dir.rglob("*"):
                if p.is_dir():
                    continue
                rel = p.relative_to(src_dir)
                zf.write(p, str(rel).replace("\\", "/"))

    @staticmethod
    def _normalize_segments(project: Project, video_dur: float) -> List[Dict[str, Any]]:
        segs: List[Dict[str, Any]] = []
        raw = (project.script or {}).get("segments") if isinstance(project.script, dict) else None
        if isinstance(raw, list) and raw:
            for seg in raw:
                if not isinstance(seg, dict):
                    continue
                st = float(seg.get("start_time") or 0.0)
                et = float(seg.get("end_time") or 0.0)
                if video_dur and et > video_dur:
                    et = float(video_dur)
                if st < 0:
                    st = 0.0
                if et <= st:
                    continue
                segs.append({
                    "start_time": st,
                    "end_time": et,
                    "text": str(seg.get("text") or ""),
                    "subtitle": str(seg.get("subtitle") or ""),
                })
        if segs:
            return segs

        if video_dur and video_dur > 0:
            return [{
                "start_time": 0.0,
                "end_time": float(video_dur),
                "text": "",
                "subtitle": "",
            }]
        return []

    @staticmethod
    def _build_draft_json(
        project: Project,
        segments: List[Dict[str, Any]],
        video_rel_path: str,
        video_duration_s: float,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        draft_id = uuid.uuid4().hex
        video_material_id = uuid.uuid4().hex

        total_tl_us = 0
        video_track_segments: List[Dict[str, Any]] = []
        text_track_segments: List[Dict[str, Any]] = []
        text_materials: List[Dict[str, Any]] = []

        for seg in segments:
            st = float(seg.get("start_time") or 0.0)
            et = float(seg.get("end_time") or 0.0)
            dur = max(0.0, et - st)
            if dur <= 0:
                continue

            dur_us = _s_to_us(dur)
            st_us = _s_to_us(st)
            vseg_id = uuid.uuid4().hex
            video_track_segments.append({
                "id": vseg_id,
                "material_id": video_material_id,
                "source_timerange": {"start": st_us, "duration": dur_us},
                "target_timerange": {"start": total_tl_us, "duration": dur_us},
                "clip": {
                    "transform": {"x": 0.0, "y": 0.0},
                    "scale": {"x": 1.0, "y": 1.0},
                    "rotation": 0.0,
                    "volume": 1.0,
                },
            })

            subtitle = str(seg.get("subtitle") or "").strip()
            if not subtitle:
                subtitle = str(seg.get("text") or "").strip()
            if subtitle:
                text_id = uuid.uuid4().hex
                text_materials.append({
                    "id": text_id,
                    "type": "text",
                    "content": subtitle,
                    "style": {
                        "font_size": 38,
                        "color": "#FFFFFF",
                        "stroke": {"color": "#000000", "width": 4},
                        "align": "center",
                    },
                })
                text_track_segments.append({
                    "id": uuid.uuid4().hex,
                    "material_id": text_id,
                    "target_timerange": {"start": total_tl_us, "duration": dur_us},
                    "clip": {"transform": {"x": 0.0, "y": 0.36}},
                })

            total_tl_us += dur_us

        draft_content: Dict[str, Any] = {
            "draft_id": draft_id,
            "platform": "desktop",
            "create_time": _now_ts(),
            "update_time": _now_ts(),
            "canvas_config": {
                "ratio": "16:9",
                "width": 1920,
                "height": 1080,
                "background_color": "#000000",
            },
            "materials": {
                "videos": [{
                    "id": video_material_id,
                    "type": "video",
                    "path": video_rel_path,
                    "duration": _s_to_us(video_duration_s) if video_duration_s else 0,
                }],
                "audios": [],
                "texts": text_materials,
                "images": [],
            },
            "tracks": [
                {"id": uuid.uuid4().hex, "type": "video", "segments": video_track_segments},
                {"id": uuid.uuid4().hex, "type": "text", "segments": text_track_segments},
            ],
            "timeline": {"duration": int(total_tl_us)},
        }

        draft_meta: Dict[str, Any] = {
            "draft_id": draft_id,
            "name": project.name,
            "created_at": _now_ts(),
            "updated_at": _now_ts(),
            "platform": "desktop",
        }

        return draft_content, draft_meta


jianying_draft_service = JianyingDraftService()
