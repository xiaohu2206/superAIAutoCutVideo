#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni 脚本段落配音：文本 hash、有效性判断、路径解析。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from modules.app_paths import resolve_uploads_path, to_uploads_web_path, uploads_dir
from modules.ffmpeg_utils import ffprobe_get_duration

def tts_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def is_original_segment(seg: Dict[str, Any]) -> bool:
    ost = seg.get("OST")
    text = str(seg.get("text") or "").strip()
    if ost == 1 or ost is True or str(ost or "").strip() == "1":
        return True
    return text.startswith("播放原片")


def segment_tts_abs_path(segment: Dict[str, Any]) -> Optional[Path]:
    path_str = str(segment.get("tts_audio_path") or "").strip()
    if not path_str:
        return None
    try:
        p = resolve_uploads_path(path_str)
        return p if p.exists() else None
    except Exception:
        return None


def is_valid_segment_tts(segment: Dict[str, Any], *, probe_duration: bool = False) -> bool:
    text = str(segment.get("text") or "").strip()
    stored_hash = str(segment.get("tts_text_hash") or "").strip()
    if not stored_hash or stored_hash != tts_text_hash(text):
        return False
    p = segment_tts_abs_path(segment)
    if not p:
        return False
    dur = segment.get("tts_audio_duration")
    if isinstance(dur, (int, float)) and float(dur) > 0:
        return True
    if not probe_duration:
        return True
    try:
        import asyncio

        loop = asyncio.get_event_loop()
        if loop.is_running():
            return True
    except Exception:
        pass
    return False


async def probe_segment_tts_duration(segment: Dict[str, Any]) -> float:
    dur = segment.get("tts_audio_duration")
    if isinstance(dur, (int, float)) and float(dur) > 0:
        return float(dur)
    p = segment_tts_abs_path(segment)
    if not p:
        return 0.0
    try:
        d = await ffprobe_get_duration(str(p))
        return float(d or 0.0)
    except Exception:
        return 0.0


def find_segment_index(script: Dict[str, Any], segment_id: str) -> Optional[int]:
    segments = script.get("segments") if isinstance(script.get("segments"), list) else []
    sid = str(segment_id or "").strip()
    if not sid:
        return None
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        seg_id = seg.get("id")
        if str(seg_id).strip() == sid:
            return i
        if str(i + 1) == sid:
            return i
    return None


def omni_tts_dir(project_id: str, source: str) -> Path:
    sub = "manual" if source == "manual" else "bulk"
    return uploads_dir() / "omni_script_tts" / project_id / sub


def build_tts_out_path(project_id: str, segment_id: str, text: str, source: str) -> Path:
    h = tts_text_hash(text)[:12]
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(segment_id))[:64] or "seg"
    return omni_tts_dir(project_id, source) / f"seg_{safe_id}_{h}.mp3"


def to_web_path(path: Path) -> str:
    return to_uploads_web_path(path)


def apply_tts_fields_to_segment(
    segment: Dict[str, Any],
    *,
    web_path: str,
    duration: float,
    source: str,
    text: str,
) -> Dict[str, Any]:
    from datetime import datetime

    out = dict(segment)
    out["tts_audio_path"] = web_path
    out["tts_audio_duration"] = float(duration or 0.0)
    out["tts_source"] = source
    out["tts_text_hash"] = tts_text_hash(text)
    out["tts_updated_at"] = datetime.now().isoformat()
    return out


def should_skip_bulk_tts(segment: Dict[str, Any]) -> bool:
    """批量配音跳过：原片段、或已有有效 manual 配音。"""
    if is_original_segment(segment):
        return True
    if str(segment.get("tts_source") or "").strip() == "manual" and is_valid_segment_tts(segment):
        return True
    return False


def needs_bulk_tts(segment: Dict[str, Any], *, force: bool = False) -> bool:
    if is_original_segment(segment):
        return False
    text = str(segment.get("text") or "").strip()
    if not text:
        return False
    if force:
        return not should_skip_bulk_tts(segment)
    if should_skip_bulk_tts(segment):
        return False
    return not is_valid_segment_tts(segment)
