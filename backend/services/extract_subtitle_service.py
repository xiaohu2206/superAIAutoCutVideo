from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from modules.projects_store import projects_store, Project
from modules.video_processor import video_processor
from modules.ws_manager import manager
from services.asr_bcut import BcutASR
from services.asr_utils import utterances_to_srt


logger = logging.getLogger(__name__)


def _now_ts() -> str:
    return datetime.now().isoformat()


def _backend_root_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def _uploads_dir() -> Path:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    (up / "videos").mkdir(parents=True, exist_ok=True)
    (up / "subtitles").mkdir(parents=True, exist_ok=True)
    (up / "audios").mkdir(parents=True, exist_ok=True)
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
        candidates: List[Path] = []
        try:
            if env:
                candidates.append(Path(env) / rel)
        except Exception:
            pass
        try:
            candidates.append((_backend_root_dir() / "uploads") / rel)
        except Exception:
            pass
        for c in candidates:
            try:
                if c.exists():
                    return c
            except Exception:
                pass
        return candidates[0] if candidates else Path(rel)
    try:
        p = Path(s)
        if p.is_absolute():
            return p
    except Exception:
        pass
    root = _backend_root_dir()
    if s_norm.startswith("/"):
        return root / s_norm[1:]
    return Path(s)


def _compress_srt(content: str) -> str:
    text = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = [b for b in text.split("\n\n") if b.strip()]
    out_lines: List[str] = []
    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if not lines:
            continue
        timing_i = None
        for i, ln in enumerate(lines[:3]):
            if "-->" in ln:
                timing_i = i
                break
        if timing_i is None:
            continue
        parts = lines[timing_i].split("-->")
        if len(parts) < 2:
            continue
        start = parts[0].strip()
        end = parts[1].strip()
        text_lines = lines[timing_i + 1:]
        t = " ".join(text_lines)
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"<[^>]+>", "", t)
        if not t:
            continue
        out_lines.append(f"[{start}-{end}] {t}")
    return ("\n".join(out_lines) + ("\n" if out_lines else ""))


def _parse_srt_content(content: str) -> List[Dict[str, Any]]:
    def _parse_ts(ts: str) -> float:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    segments: List[Dict[str, Any]] = []
    norm = (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [ln.strip() for ln in norm.splitlines() if ln.strip()]
    bracket_pattern = re.compile(r"^\[(\d{2}:\d{2}:\d{2},\d{3})-(\d{2}:\d{2}:\d{2},\d{3})\]\s*(.+)$")
    idx = 1
    for ln in lines:
        m = bracket_pattern.match(ln)
        if not m:
            continue
        start_str, end_str, text = m.groups()
        start_t = _parse_ts(start_str)
        end_t = _parse_ts(end_str)
        segments.append({
            "id": str(idx),
            "start_time": float(start_t),
            "end_time": float(end_t),
            "text": text,
            "subtitle": text,
        })
        idx += 1
    return segments


async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def _ws(project_id: str, type_: str, phase: str, message: str, progress: Optional[int] = None) -> None:
    payload: Dict[str, Any] = {
        "type": type_,
        "scope": "extract_subtitle",
        "project_id": project_id,
        "phase": phase,
        "message": message,
        "timestamp": _now_ts(),
    }
    if type_ != "error" and progress is not None:
        payload["progress"] = progress
    elif type_ == "completed" and progress is not None:
        payload["progress"] = progress
    try:
        await manager.broadcast(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


def _subtitle_meta(p: Project) -> Dict[str, Any]:
    return {
        "file_path": getattr(p, "subtitle_path", None),
        "source": getattr(p, "subtitle_source", None),
        "status": getattr(p, "subtitle_status", None),
        "updated_by_user": bool(getattr(p, "subtitle_updated_by_user", False)),
        "updated_at": getattr(p, "subtitle_updated_at", None),
        "format": getattr(p, "subtitle_format", None),
    }


class ExtractSubtitleService:
    @staticmethod
    async def extract_subtitle(project_id: str, force: bool = False) -> Dict[str, Any]:
        p: Optional[Project] = projects_store.get_project(project_id)
        if not p:
            await _ws(project_id, "error", "project_not_found", "项目不存在")
            raise HTTPException(status_code=404, detail="项目不存在")

        subtitle_source = getattr(p, "subtitle_source", None)
        subtitle_status = getattr(p, "subtitle_status", None)
        subtitle_updated_by_user = bool(getattr(p, "subtitle_updated_by_user", False))
        if subtitle_source == "user" and getattr(p, "subtitle_path", None):
            raise HTTPException(status_code=409, detail="已上传字幕，无法提取；请先删除字幕")
        if subtitle_status == "extracting":
            raise HTTPException(status_code=409, detail="正在提取中")
        if subtitle_updated_by_user and not force:
            raise HTTPException(status_code=409, detail="字幕已被修改，若需覆盖请传 force=true")
        if subtitle_source == "extracted" and getattr(p, "subtitle_path", None) and not force and subtitle_status == "ready":
            raise HTTPException(status_code=409, detail="已存在提取字幕，若需重提请传 force=true")

        video_path = (getattr(p, "video_path", None) or "").strip()
        if not video_path:
            await _ws(project_id, "error", "video_missing", "未找到可用的视频文件")
            raise HTTPException(status_code=400, detail="未找到可用的视频文件")
        video_abs = _resolve_path(video_path)
        if not video_abs.exists():
            await _ws(project_id, "error", "video_missing", "视频文件不存在")
            raise HTTPException(status_code=400, detail="视频文件不存在")

        projects_store.update_project(project_id, {
            "subtitle_status": "extracting",
            "subtitle_source": "extracted" if subtitle_source != "user" else subtitle_source,
            "subtitle_updated_at": _now_ts(),
        })

        await _ws(project_id, "progress", "start", "开始提取字幕", 1)

        await _ws(project_id, "progress", "validating_asr", "验证 ASR 服务可用性", 10)
        asr_check = await _run_in_thread(BcutASR.test_connection)
        if not asr_check.get("success", False):
            projects_store.update_project(project_id, {"subtitle_status": "failed"})
            await _ws(project_id, "error", "asr_unavailable", asr_check.get("error") or asr_check.get("message") or "ASR服务不可用")
            raise HTTPException(status_code=400, detail=asr_check.get("error") or asr_check.get("message") or "ASR服务不可用")

        audio_abs: Optional[Path] = None
        audio_web: Optional[str] = None

        if not force and getattr(p, "audio_path", None):
            a_cand = _resolve_path(p.audio_path)
            if a_cand.exists():
                audio_abs = a_cand
                await _ws(project_id, "progress", "audio_exists", "复用已提取音频", 20)

        if not audio_abs:
            # 清理旧音频
            old_audio_path = getattr(p, "audio_path", None)
            if old_audio_path:
                try:
                    old_f = _resolve_path(old_audio_path)
                    if old_f.exists():
                        old_f.unlink()
                        await _ws(project_id, "progress", "cleanup_old_audio", "清理旧音频", 25)
                except Exception:
                    pass

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            audio_out = _uploads_dir() / "audios" / f"{project_id}_audio_{ts}.mp3"
            await _ws(project_id, "progress", "extract_audio", "提取音频中", 30)
            ok_audio = await video_processor.extract_audio_mp3(str(video_abs), str(audio_out))
            if not ok_audio:
                projects_store.update_project(project_id, {"subtitle_status": "failed"})
                await _ws(project_id, "error", "extract_audio_failed", "音频提取失败")
                raise HTTPException(status_code=500, detail="音频提取失败")
            audio_abs = audio_out
            audio_web = _to_web_path(audio_out)
            projects_store.update_project(project_id, {"audio_path": audio_web})
            await _ws(project_id, "progress", "audio_ready", "音频提取完成", 45)

        await _ws(project_id, "progress", "asr_start", "ASR 识别中", 55)
        asr = BcutASR(str(audio_abs))
        try:
            data = await _run_in_thread(asr.run)
        except Exception as e:
            projects_store.update_project(project_id, {"subtitle_status": "failed"})
            await _ws(project_id, "error", "asr_failed", f"语音识别服务异常：{str(e)}")
            raise HTTPException(status_code=500, detail="语音识别失败")

        utterances = data.get("utterances") if isinstance(data, dict) else None
        if not isinstance(utterances, list) or not utterances:
            projects_store.update_project(project_id, {"subtitle_status": "failed"})
            await _ws(project_id, "error", "asr_failed", "语音识别失败")
            raise HTTPException(status_code=500, detail="语音识别失败")

        await _ws(project_id, "progress", "subtitle_ready", "字幕生成完成", 75)
        srt_text = utterances_to_srt(utterances)
        compressed = _compress_srt(srt_text)

        ts2 = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        srt_out = _uploads_dir() / "subtitles" / f"{project_id}_subtitle_{ts2}.srt"
        try:
            srt_out.write_text(compressed, encoding="utf-8")
        except Exception:
            projects_store.update_project(project_id, {"subtitle_status": "failed"})
            await _ws(project_id, "error", "subtitle_saved_failed", "字幕写入失败")
            raise HTTPException(status_code=500, detail="字幕写入失败")

        web_path = _to_web_path(srt_out)
        projects_store.update_project(project_id, {
            "subtitle_path": web_path,
            "subtitle_source": "extracted",
            "subtitle_status": "ready",
            "subtitle_updated_by_user": False,
            "subtitle_updated_at": _now_ts(),
            "subtitle_format": "compressed_srt_v1",
        })
        await _ws(project_id, "progress", "subtitle_saved", "字幕落盘完成", 85)

        segments = _parse_srt_content(compressed)
        await _ws(project_id, "progress", "subtitle_parsed", "字幕解析完成", 95)
        await _ws(project_id, "completed", "done", "提取字幕成功", 100)

        p2 = projects_store.get_project(project_id) or p
        return {
            "segments": segments,
            "subtitle_meta": _subtitle_meta(p2),
        }


extract_subtitle_service = ExtractSubtitleService()
