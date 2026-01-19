import math
import re
from typing import Any, Dict, List, Tuple


def _split_subtitles_if_oversize(
    subtitles: List[Dict[str, Any]],
    max_items: int,
    soft_factor: float,
) -> List[List[Dict[str, Any]]]:
    soft_max = int(math.ceil(float(max_items) * float(soft_factor)))
    if soft_max <= 0 or len(subtitles) <= soft_max:
        return [subtitles]
    mid = len(subtitles) // 2
    if mid <= 0:
        return [subtitles[:soft_max]]
    left = subtitles[:mid]
    right = subtitles[mid:]
    out: List[List[Dict[str, Any]]] = []
    out.extend(_split_subtitles_if_oversize(left, max_items, soft_factor))
    out.extend(_split_subtitles_if_oversize(right, max_items, soft_factor))
    return [c for c in out if c]


def compute_subtitle_chunks(
    subtitles: List[Dict[str, Any]],
    desired_calls: int,
    max_items: int,
    soft_factor: float,
) -> List[Dict[str, Any]]:
    n = len(subtitles)
    if n <= 0:
        return []
    soft_max = int(math.ceil(float(max_items) * float(soft_factor)))
    min_calls = max(1, int(math.ceil(n / soft_max))) if soft_max > 0 else 1
    calls = max(1, int(desired_calls or 1), min_calls)
    base_slices: List[List[Dict[str, Any]]] = []
    for i in range(calls):
        start = (i * n) // calls
        end = ((i + 1) * n) // calls
        ch = subtitles[start:end]
        if ch:
            base_slices.append(ch)
    split_slices: List[List[Dict[str, Any]]] = []
    for ch in base_slices:
        split_slices.extend(_split_subtitles_if_oversize(ch, max_items, soft_factor))
    chunks: List[Dict[str, Any]] = []
    for idx, ch in enumerate(split_slices):
        try:
            start_s = float(ch[0].get("start") or 0.0)
            end_s = float(ch[-1].get("end") or start_s)
        except Exception:
            start_s = 0.0
            end_s = 0.0
        chunks.append(
            {
                "idx": idx,
                "start": start_s,
                "end": end_s,
                "subs": ch,
            }
        )
    return chunks


def _parse_timestamp_pair(ts_range: str) -> Tuple[float, float]:
    """将 "HH:MM:SS,mmm-HH:MM:SS,mmm" 解析为秒数对"""

    def _to_seconds(ts: str) -> float:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    parts = re.split(r"\s*[-–]\s*", ts_range.strip())
    if len(parts) != 2:
        raise ValueError(f"时间戳范围格式错误: {ts_range}")
    return _to_seconds(parts[0]), _to_seconds(parts[1])


def _format_timestamp(s: float) -> str:
    total_ms = int(round(s * 1000))
    ms = total_ms % 1000
    total_sec = total_ms // 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    sec = total_sec % 60
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _format_timestamp_range(start_s: float, end_s: float) -> str:
    return _format_timestamp(start_s) + "-" + _format_timestamp(end_s)


def _parse_srt_subtitles(subtitle_content: str) -> List[Dict[str, Any]]:
    """解析字幕文本为结构化列表，支持标准SRT与压缩行内时间戳格式"""
    subs: List[Dict[str, Any]] = []
    content = subtitle_content.strip().replace("\r\n", "\n").replace("\r", "\n")
    if content.startswith('"') and content.endswith('"'):
        content = content[1:-1]
    lines = [ln.strip() for ln in content.split("\n") if ln.strip()]

    bracket_pattern = re.compile(r"^\[(\d{2}:\d{2}:\d{2},\d{3})-(\d{2}:\d{2}:\d{2},\d{3})\]\s*(.+)$")
    bracket_matches = [bracket_pattern.match(ln) for ln in lines]
    if any(bracket_matches):
        idx = 1
        for m in bracket_matches:
            if not m:
                continue
            start_str, end_str, text = m.groups()
            try:
                start_s = _parse_timestamp_str(start_str)
                end_s = _parse_timestamp_str(end_str)
            except Exception:
                continue
            subs.append({
                "index": idx,
                "start": start_s,
                "end": end_s,
                "text": text.strip(),
            })
            idx += 1
        subs.sort(key=lambda s: (s["start"], s["end"]))
        return subs

    pattern = re.compile(r"(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s+(.+?)(?=\n\s*\d+\s+\d{2}:\d{2}:\d{2}|\Z)", re.DOTALL)
    norm = content + "\n"
    matches = pattern.findall(norm)
    for m in matches:
        idx_str, start_str, end_str, text = m
        try:
            start_s = _parse_timestamp_str(start_str)
            end_s = _parse_timestamp_str(end_str)
        except Exception:
            continue
        subs.append({
            "index": int(idx_str),
            "start": start_s,
            "end": end_s,
            "text": text.strip(),
        })
    subs.sort(key=lambda s: (s["start"], s["end"]))
    return subs


def _parse_timestamp_str(ts: str) -> float:
    """解析单个时间戳 00:00:00,000 为秒数"""
    try:
        h, m, s = ts.replace(',', '.').split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return 0.0
