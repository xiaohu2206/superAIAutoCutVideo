import asyncio
import logging
import re
from typing import Any, Dict, List

from modules.ai import ChatMessage
from modules.json_sanitizer import sanitize_json_text_to_dict
from services.ai_service import ai_service

from .subtitle_utils import _parse_timestamp_pair

logger = logging.getLogger(__name__)


async def generate_plot_analysis(subtitle_content: str) -> str:
    system_prompt = (
        "你是一位专业的剧本分析师和剧情概括助手。请仔细分析字幕内容，提取关键剧情信息。"
    )
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(
            role="user",
            content=(
                "请分析以下字幕内容，提取关键剧情信息与爆点（包含时间节点的要点列表）：\n\n"
                + subtitle_content
            ),
        ),
    ]
    resp = await ai_service.send_chat(messages)
    return str(resp.content)


def _chunk_text(
    text: str,
    chunk_chars_max: int = 15000,
    overlap_ratio: float = 0.12,
    min_last_ratio: float = 0.4,
) -> List[str]:
    text = str(text or "").strip()
    if not text:
        return []
    max_len = max(1000, int(chunk_chars_max))
    overlap = max(0, int(max_len * overlap_ratio))
    chunks: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(n, i + max_len)
        cand = text[i:end]
        cut = len(cand)
        for sep in ["\n\n", "\n", "。", "！", "？"]:
            pos = cand.rfind(sep)
            if pos >= int(max_len * 0.6):
                cut = pos + len(sep)
                break
        chunk = cand[:cut]
        chunks.append(chunk)
        if end >= n:
            break
        i = i + cut - overlap if overlap > 0 else i + cut
        if i < 0:
            i = 0
    if len(chunks) >= 2:
        last_len = len(chunks[-1])
        if last_len < int(max_len * min_last_ratio):
            prev = chunks[-2]
            needed = int(max_len * min_last_ratio) - last_len
            movable = min(needed, int(max_len * 0.5), max(0, len(prev) // 2))
            start_region = max(0, len(prev) - movable - int(max_len * 0.1))
            cut_pos = max(start_region, len(prev) - movable)
            for sep in ["\n\n", "\n", "。", "！", "？"]:
                pos = prev.rfind(sep, start_region)
                if pos != -1:
                    cut_pos = pos + len(sep)
                    break
            move = prev[cut_pos:]
            chunks[-2] = prev[:cut_pos]
            chunks[-1] = move + chunks[-1]
            if len(chunks[-2]) == 0:
                merged = chunks[-1]
                chunks = chunks[:-2]
                chunks.append(merged)
    return chunks


async def _extract_plot_points_for_chunk(
    subtitle_chunk: str,
    chunk_id: int,
    max_points: int = 12,
) -> List[Dict[str, Any]]:
    sys_prompt = (
        "你是一位专业的剧本分析师。请基于提供的字幕片段，提取包含时间范围的关键剧情爆点，严格输出JSON。"
    )
    fmt_lines = [
        "JSON格式:",
        "{",
        '  "plot_points": [',
        "    {",
        '      "timestamp": "HH:MM:SS,mmm-HH:MM:SS,mmm",',
        '      "title": "...",',
        '      "summary": "...",',
        '      "keywords": ["..."],',
        '      "confidence": 0.0',
        "    }",
        "  ]",
        "}",
        "",
    ]
    head = (
        "请从以下字幕片段中提取不超过"
        + str(max_points)
        + "条关键剧情爆点，严格输出JSON对象，不要包含其他文字。"
    )
    user_prompt = (
        head
        + "\n\n"
        + "\n".join(fmt_lines)
        + "\n字幕片段:\n\n"
        + subtitle_chunk
    )
    messages = [
        ChatMessage(role="system", content=sys_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
    data, _raw = sanitize_json_text_to_dict(resp.content)
    items = data.get("plot_points") or []
    if not isinstance(items, list):
        items = []
    out: List[Dict[str, Any]] = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        ts = it.get("timestamp")
        title = it.get("title")
        summary = it.get("summary")
        keywords = it.get("keywords")
        conf = it.get("confidence")
        if not ts or not title:
            continue
        try:
            _parse_timestamp_pair(str(ts))
        except Exception:
            continue
        out.append({
            "timestamp": str(ts),
            "title": str(title),
            "summary": str(summary or ""),
            "keywords": [str(k) for k in (keywords or []) if k],
            "confidence": float(conf) if isinstance(conf, (int, float)) else 0.5,
            "chunk_id": int(chunk_id),
            "local_rank": idx + 1,
        })
    return out


def _normalize_title(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "").lower())


def _merge_plot_points(
    points: List[Dict[str, Any]],
    similarity_threshold: float = 0.6,
    time_merge_threshold_ms: int = 30000,
) -> List[Dict[str, Any]]:
    def _ms_pair(ts: str):
        a, b = _parse_timestamp_pair(ts)
        return int(a * 1000), int(b * 1000)

    merged: List[Dict[str, Any]] = []
    for pt in points:
        ts = str(pt.get("timestamp"))
        title = str(pt.get("title"))
        s_ms, e_ms = _ms_pair(ts)
        found = False
        for mp in merged:
            ms, me = _ms_pair(str(mp["timestamp"]))
            ov = min(e_ms, me) - max(s_ms, ms)
            near = max(0, max(s_ms, ms) - min(e_ms, me)) <= time_merge_threshold_ms
            title_sim = 1.0 if _normalize_title(title) == _normalize_title(mp["title"]) else 0.0
            if (ov > 0 or near) and title_sim >= similarity_threshold:
                mp["summary"] = (
                    mp.get("summary", "")
                    if len(str(mp.get("summary", "")))
                    >= len(str(pt.get("summary", "")))
                    else str(pt.get("summary", ""))
                )
                mp["keywords"] = list({*(mp.get("keywords") or []), *(pt.get("keywords") or [])})
                mp["confidence"] = (
                    float(mp.get("confidence", 0.5))
                    + float(pt.get("confidence", 0.5))
                ) / 2.0
                found = True
                break
        if not found:
            merged.append(pt)
    merged.sort(key=lambda x: _parse_timestamp_pair(str(x["timestamp"]))[0])
    return merged


def _compose_plot_analysis_text(points: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for i, pt in enumerate(points, start=1):
        ts = str(pt.get("timestamp"))
        title = str(pt.get("title"))
        summary = str(pt.get("summary", ""))
        kws = ",".join([str(k) for k in (pt.get("keywords") or [])])
        line = (
            "爆点{}：{}\n".format(i, title)
            + "时间：{}\n".format(ts)
            + "摘要：{}\n".format(summary)
            + "关键词：{}\n".format(kws)
        )
        lines.append(line)
    return "\n".join(lines).strip()


async def generate_plot_analysis_pipeline(
    subtitle_content: str,
    chunk_chars_max: int = 15000,
    overlap_ratio: float = 0.12,
    max_points_per_chunk: int = 20,
) -> str:
    chunks = _chunk_text(
        subtitle_content,
        chunk_chars_max,
        overlap_ratio,
    )
    all_points: List[Dict[str, Any]] = []
    sem = asyncio.Semaphore(4)

    async def run_one(i: int, ch: str) -> List[Dict[str, Any]]:
        async with sem:
            try:
                return await _extract_plot_points_for_chunk(
                    ch,
                    i,
                    max_points_per_chunk,
                )
            except Exception:
                return []

    tasks = [run_one(idx, ch) for idx, ch in enumerate(chunks)]
    results = await asyncio.gather(*tasks)
    for pts in results:
        if pts:
            all_points.extend(pts)
    merged = _merge_plot_points(all_points)
    return _compose_plot_analysis_text(merged)


def _filter_plot_analysis_by_time(plot_analysis: str, start_s: float, end_s: float) -> str:
    if not plot_analysis:
        return ""
    lines = plot_analysis.split('\n')
    relevant_lines: List[str] = []
    current_block: List[str] = []
    in_block = False
    block_time_range = None
    for line in lines:
        if line.startswith("爆点"):
            if current_block and block_time_range:
                bs, be = block_time_range
                if not (be < start_s or bs > end_s):
                    relevant_lines.extend(current_block)
            current_block = [line]
            in_block = True
            block_time_range = None
        elif line.startswith("时间：") and in_block:
            current_block.append(line)
            try:
                ts_str = line.replace("时间：", "").strip()
                block_time_range = _parse_timestamp_pair(ts_str)
            except Exception:
                pass
        elif in_block:
            current_block.append(line)

    if current_block and block_time_range:
        bs, be = block_time_range
        if not (be < start_s or bs > end_s):
            relevant_lines.extend(current_block)
    if not relevant_lines:
        return plot_analysis[:500] + "..."
    return "\n".join(relevant_lines)


def _clean_plot_analysis_for_prompt(text: str) -> str:
    if not text:
        return ""
    lines = [ln for ln in str(text).splitlines() if not re.match(r"^\s*(时间：|时间:|关键词：|关键词:)", ln)]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out
