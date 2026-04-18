"""从项目字幕或镜头数据组装洗稿用的纯文本字幕（不含时间轴，顺序仍为时间顺序）。"""

from __future__ import annotations

from typing import Any, Dict

from services.script_generation.scene_utils import scenes_to_timeline_items
from services.script_generation.subtitle_utils import _parse_srt_subtitles


def build_subs_text_from_subtitle_file_content(subtitle_content: str) -> str:
    subtitles = _parse_srt_subtitles(subtitle_content)
    if not subtitles:
        return ""
    lines = []
    for s in subtitles:
        t = str(s.get("text") or "").strip()
        if t:
            lines.append(t)
    return "\n".join(lines)


def build_subs_text_from_scenes_data(scenes_data: Dict[str, Any]) -> str:
    scenes_raw = scenes_data.get("scenes") if isinstance(scenes_data, dict) else None
    if not isinstance(scenes_raw, list) or not scenes_raw:
        return ""
    scene_items = scenes_to_timeline_items(scenes_raw)
    if not scene_items:
        return ""
    lines = []
    for item in scene_items:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append(text)
    return "\n".join(lines)
