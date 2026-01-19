#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本生成业务服务（与路由分离）
职责：
- 基于字幕srt文本调用AI生成剧情爆点分析（plot_analysis）
- 基于 plot_analysis + 字幕 调用提示词模块生成格式化脚本文案（JSON）
- 清洗与校验格式化JSON，并转换为前端VideoScript结构

本模块不负责持久化存储，由路由层调用保存。
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional, cast
import asyncio
import json

from modules.ai import ChatMessage
from modules.prompts.prompt_manager import prompt_manager
from services.ai_service import ai_service
from modules.json_sanitizer import sanitize_json_text_to_dict, validate_script_items
from modules.projects_store import projects_store
from fastapi import HTTPException

logger = logging.getLogger(__name__)

DEFAULT_SCRIPT_LENGTH_SELECTION = "30～40条"
SCRIPT_LENGTH_PRESETS: Dict[str, Tuple[int, int, int]] = {
    "15～20条": (15, 20, 1),
    "30～40条": (30, 40, 2),
    "40～60条": (40, 60, 3),
    "60～80条": (60, 80, 4),
    "80～100条": (80, 100, 5),
}
MAX_SUBTITLE_ITEMS_PER_CALL = 2000
SOFT_INPUT_FACTOR = 1.8
MAX_SUBTITLE_CHARS_PER_CALL = 20000


@dataclass(frozen=True)
class ScriptTargetPlan:
    normalized_selection: str
    target_min: int
    target_max: int
    preferred_calls: int
    final_target_count: int


def normalize_script_length_selection(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    v = (
        v.replace(" ", "")
        .replace("~", "～")
        .replace("-", "～")
        .replace("—", "～")
        .replace("–", "～")
    )
    if not v.endswith("条") and re.search(r"\d", v):
        v = v + "条"
    if v in SCRIPT_LENGTH_PRESETS:
        return v
    m = re.search(r"(\d+)\D+(\d+)", v)
    if m:
        a = int(m.group(1))
        b = int(m.group(2))
        key = f"{a}～{b}条"
        if key in SCRIPT_LENGTH_PRESETS:
            return key
    allowed = " | ".join(SCRIPT_LENGTH_PRESETS.keys())
    raise ValueError(f"script_length 无效，可选值: {allowed}")


def parse_script_length_selection(value: Optional[str]) -> ScriptTargetPlan:
    try:
        normalized = normalize_script_length_selection(value) or DEFAULT_SCRIPT_LENGTH_SELECTION
    except ValueError:
        normalized = DEFAULT_SCRIPT_LENGTH_SELECTION
    if normalized not in SCRIPT_LENGTH_PRESETS:
        normalized = DEFAULT_SCRIPT_LENGTH_SELECTION
    target_min, target_max, calls = SCRIPT_LENGTH_PRESETS[normalized]
    final_target_count = int(target_max)
    return ScriptTargetPlan(
        normalized_selection=normalized,
        target_min=int(target_min),
        target_max=int(target_max),
        preferred_calls=int(calls),
        final_target_count=final_target_count,
    )


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


def allocate_output_counts(total_target_count: int, chunk_count: int) -> List[int]:
    t = int(total_target_count or 0)
    c = int(chunk_count or 0)
    if c <= 0:
        return []
    if t <= 0:
        return [1] * c
    if c <= t:
        base = t // c
        rem = t % c
        out = [base + 1 if i < rem else base for i in range(c)]
        return [max(1, int(x)) for x in out]
    return [1] * c


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


class ScriptGenerationService:
    """短剧脚本文案生成服务"""

    @staticmethod
    async def generate_plot_analysis(subtitle_content: str) -> str:
        """
        调用模型生成爆点分析提取（plot_analysis）。
        使用指定系统提示词：
        "你是一位专业的剧本分析师和剧情概括助手。请仔细分析字幕内容，提取关键剧情信息。"
        """
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def _normalize_title(s: str) -> str:
        return re.sub(r"\s+", "", str(s or "").lower())

    @staticmethod
    def _merge_plot_points(
        points: List[Dict[str, Any]],
        similarity_threshold: float = 0.6,
        time_merge_threshold_ms: int = 30000,
    ) -> List[Dict[str, Any]]:
        def _ms_pair(ts: str) -> Tuple[int, int]:
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
                title_sim = 1.0 if ScriptGenerationService._normalize_title(title) == ScriptGenerationService._normalize_title(mp["title"]) else 0.0
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

    @staticmethod
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

    @staticmethod
    async def generate_plot_analysis_pipeline(
        subtitle_content: str,
        chunk_chars_max: int = 15000,
        overlap_ratio: float = 0.12,
        max_points_per_chunk: int = 20,
    ) -> str:
        chunks = ScriptGenerationService._chunk_text(
            subtitle_content,
            chunk_chars_max,
            overlap_ratio,
        )
        all_points: List[Dict[str, Any]] = []
        sem = asyncio.Semaphore(4)

        async def run_one(i: int, ch: str) -> List[Dict[str, Any]]:
            async with sem:
                try:
                    return await ScriptGenerationService._extract_plot_points_for_chunk(
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
        merged = ScriptGenerationService._merge_plot_points(all_points)
        return ScriptGenerationService._compose_plot_analysis_text(merged)

    @staticmethod
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
                    start_s = ScriptGenerationService._parse_timestamp_str(start_str)
                    end_s = ScriptGenerationService._parse_timestamp_str(end_str)
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
                start_s = ScriptGenerationService._parse_timestamp_str(start_str)
                end_s = ScriptGenerationService._parse_timestamp_str(end_str)
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

    @staticmethod
    def _parse_timestamp_str(ts: str) -> float:
        """解析单个时间戳 00:00:00,000 为秒数"""
        try:
            h, m, s = ts.replace(',', '.').split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            return 0.0

    @staticmethod
    def _filter_plot_analysis_by_time(plot_analysis: str, start_s: float, end_s: float) -> str:
        """从剧情分析文本中筛选出当前时间窗口相关的爆点"""
        if not plot_analysis:
            return ""
        # 假设 plot_analysis 是由 _compose_plot_analysis_text 生成的格式
        # 爆点X：Title
        # 时间：HH:MM:SS,mmm-HH:MM:SS,mmm
        lines = plot_analysis.split('\n')
        relevant_lines: List[str] = []
        current_block: List[str] = []
        in_block = False
        block_time_range = None
        for line in lines:
            if line.startswith("爆点"):
                if current_block and block_time_range:
                    # 检查上一块是否相关
                    bs, be = block_time_range
                    # 简单的重叠判断
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

        # 处理最后一块
        if current_block and block_time_range:
            bs, be = block_time_range
            if not (be < start_s or bs > end_s):
                relevant_lines.extend(current_block)
        if not relevant_lines:
            # 如果没有匹配到，为了上下文，返回前300个字符或摘要
            return plot_analysis[:500] + "..."
        return "\n".join(relevant_lines)

    @staticmethod
    def _clean_plot_analysis_for_prompt(text: str) -> str:
        if not text:
            return ""
        lines = [ln for ln in str(text).splitlines() if not re.match(r"^\s*(时间：|时间:|关键词：|关键词:)", ln)]
        out = "\n".join(lines)
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        return out

    @staticmethod
    def _default_prompt_key_for_project(project_id: Optional[str]) -> str:
        """根据项目的解说类型选择默认官方模板键"""
        category = "short_drama_narration"
        if project_id:
            p = projects_store.get_project(project_id)
            if p:
                t = str(getattr(p, "narration_type", "") or "")
                if t == "电影解说":
                    category = "movie_narration"
                else:
                    category = "short_drama_narration"
        return f"{category}:script_generation"

    @staticmethod
    def _resolve_prompt_key(project_id: Optional[str], default_key: str) -> str:
        if not project_id:
            return default_key
        p = projects_store.get_project(project_id)
        if not p:
            return default_key
        sel_map = getattr(p, "prompt_selection", {}) or {}
        sel = sel_map.get(default_key)
        if not isinstance(sel, dict):
            return default_key
        t = str(sel.get("type") or "official").lower()
        kid = str(sel.get("key_or_id") or "")
        if t == "user" and kid:
            return kid.split(":", 1)[-1]
        if t == "official" and kid:
            return kid
        return default_key

    @staticmethod
    async def _generate_script_chunk(
        chunk_idx: int,
        chunk_total: int,
        start_time: float,
        end_time: float,
        subtitles: List[Dict[str, Any]],
        plot_analysis_snippet: str,
        drama_name: str,
        project_id: Optional[str] = None,
        target_items_count: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        subs_text_lines = []
        for s in subtitles:
            ts = _format_timestamp_range(float(s["start"]), float(s["end"]))
            subs_text_lines.append(f"[{ts}] {s['text']}")
        subs_text = "\n".join(subs_text_lines)
        if len(subs_text) > MAX_SUBTITLE_CHARS_PER_CALL:
            subs_text = subs_text[:MAX_SUBTITLE_CHARS_PER_CALL]
        default_key = ScriptGenerationService._default_prompt_key_for_project(project_id)
        key = ScriptGenerationService._resolve_prompt_key(project_id, default_key)
        variables = {
            "drama_name": drama_name,
            "plot_analysis": plot_analysis_snippet or "",
            "subtitle_content": subs_text,
        }
        try:
            messages_dicts = prompt_manager.build_chat_messages(key, variables)
        except KeyError:
            try:
                cat = (key.split(":", 1)[0] if ":" in key else "short_drama_narration")
                if cat == "movie_narration":
                    from modules.prompts.movie_narration import register_prompts
                else:
                    from modules.prompts.short_drama_narration import register_prompts
                register_prompts()
                messages_dicts = prompt_manager.build_chat_messages(key, variables)
            except Exception:
                key = default_key
                messages_dicts = prompt_manager.build_chat_messages(key, variables)
        messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages_dicts]
        
        logger.info(f"⚡ 正在生成分段 {int(chunk_idx)+1}/{chunk_total}...")

        if int(chunk_total or 0) > 0:
            total = int(chunk_total)
            idx = int(chunk_idx)
            if idx <= 0:
                pos_label = "开始段"
            elif idx >= total - 1:
                pos_label = "末尾段"
            else:
                pos_label = "中间段"
            messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content=(
                        f"这是分段生成脚本的第{idx + 1}段/共{total}段，位置为{pos_label}。"
                        "开始（1）段可引入剧情，中间段不要重复开场或收尾（因为需要合并其它段进来），末尾段需要收束剧情并避免新开头。"
                    ),
                ),
            )
        if target_items_count and int(target_items_count) > 0:
            n = int(target_items_count)
            messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content=(
                        f"你必须仅输出一个JSON对象，键为'items'。"
                        f"items数组长度必须严格等于{n}，不能多不能少。"
                        f"start_time和end_time时间间隔不能低于1s"
                        f"每条必须包含'_id','timestamp','picture','narration','OST'。"
                        f"不得输出除JSON以外的任何文字。"
                    ),
                ),
            )
        try:
            resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
            data, _ = sanitize_json_text_to_dict(resp.content)
            data = validate_script_items(data)
            items = data.get("items") or []
            logger.info(f"v{int(chunk_idx)+1} 生成分段, 共{len(items)}条")
            valid_items: List[Dict[str, Any]] = []
            for it in items:
                try:
                    s_t, e_t = _parse_timestamp_pair(str(it.get("timestamp")))
                    if e_t < start_time - 5 or s_t > end_time + 5:
                        continue
                    valid_items.append(
                        {
                            "_id": it.get("_id"),
                            "timestamp": str(it.get("timestamp")),
                            "picture": it.get("picture"),
                            "narration": str(it.get("narration", "")),
                            "OST": 1 if it.get("OST") == 1 else 0,
                            "_chunk_idx": chunk_idx,
                        }
                    )
                except Exception:
                    continue
            if target_items_count and int(target_items_count) > 0:
                n = int(target_items_count)
                out: List[Dict[str, Any]] = []
                for it in valid_items:
                    if len(out) >= n:
                        break
                    out.append(it)
                if len(out) < n:
                    for it in items:
                        if len(out) >= n:
                            break
                        out.append(
                            {
                                "_id": it.get("_id"),
                                "timestamp": str(it.get("timestamp")),
                                "picture": it.get("picture"),
                                "narration": str(it.get("narration", "")),
                                "OST": 1 if it.get("OST") == 1 else 0,
                                "_chunk_idx": chunk_idx,
                            }
                        )
                return out
            return valid_items
        except Exception as e:
            logger.error(f"Chunk {chunk_idx} generation failed: {e}")
            return []

    @staticmethod
    def _merge_items(all_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sorted_items = sorted(all_items, key=lambda x: _parse_timestamp_pair(str(x["timestamp"]))[0])
        merged: List[Dict[str, Any]] = []
        if not sorted_items:
            return []
        current = sorted_items[0]
        for next_it in sorted_items[1:]:
            try:
                cs, ce = _parse_timestamp_pair(str(current["timestamp"]))
                ns, ne = _parse_timestamp_pair(str(next_it["timestamp"]))
            except Exception:
                merged.append(current)
                current = next_it
                continue
            overlap_start = max(cs, ns)
            overlap_end = min(ce, ne)
            overlap_len = max(0.0, overlap_end - overlap_start)
            curr_len = max(0.0, ce - cs)
            next_len = max(0.0, ne - ns)
            if overlap_len > 0 and (overlap_len > 0.4 * min(curr_len, next_len) + 0.1):
                if len(str(next_it.get("narration", ""))) > len(str(current.get("narration", ""))):
                    current = next_it
                else:
                    pass
            else:
                merged.append(current)
                current = next_it
        merged.append(current)
        min_duration = 0.8
        filtered: List[Dict[str, Any]] = []
        for it in merged:
            try:
                s, e = _parse_timestamp_pair(str(it["timestamp"]))
                if max(0.0, e - s) < min_duration:
                    continue
            except Exception:
                pass
            filtered.append(it)
        for i, it in enumerate(filtered, start=1):
            it["_id"] = i
        return filtered

    @staticmethod
    async def _refine_full_script(
        segments: List[Dict[str, Any]],
        drama_name: str,
        plot_analysis: str,
        length_mode: Optional[str] = None,
        target_count: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        items = segments
        if not items:
            return []
        draft_str = json.dumps(items, ensure_ascii=False)
        n = len(items)
        if target_count and int(target_count) > 0:
            target = int(target_count)
        else:
            target = int(n)
        if target < 1:
            target = 1
        if target >= n:
            retain_desc = ""
        else:
            retain_desc = (
                f"必须仅保留 {target} 条最关键条目，其余全部删除（必须遵守）。"
                f"返回的 'items' 长度必须为 {target}，不得新增条目，仅在已有 '_id' 中选择，但一定要确保不能烂尾。"
            )

        system_prompt = (
            "你是一位分块脚本合并助手。你的任务是将已按时间分块生成的解说脚本进行轻量合并与顺畅衔接。"
            + retain_desc +
            "**原声与解说比例**：7:3（原声70%，解说30%）"
            "**原声片段标识**：OST=1表示原声，OST=0表示解说"
            "对于单一条目，仅对部分的 'narration' 进行小幅润色，比如补充必要的连接词、消除重复或断裂，让上下文自然连贯；不要改变原有信息与含义。"
            "对于所有脚本内容，是通过多个模型生成的，每个模型生成的脚本段容易出现开头语和结尾语，但可能是中间段，如果是中间段应该把开头语或结尾语条目删除"
            "对于单一条目，一般不修改 'picture' 与 'OST'，如无必要变更则原样返回。"
            "仅返回一个 JSON 对象，键为 'items'，每个元素包含 '_id', 'timestamp', 'picture', 'narration', 'OST'；不要输出除 JSON 以外的任何内容。"
        )
        user_content = (
            f"{retain_desc}\n\n"
            f"剧名：{drama_name}\n"
            f"草稿：\n{draft_str}\n\n"
            # f"剧情背景：\n{ScriptGenerationService._clean_plot_analysis_for_prompt(plot_analysis)}\n\n"
            "请按要求返回 JSON。"
        )
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content)
        ]
        try:
            logger.info(f"✨ 正在进行全局润色... (目标条数: {target})")
            resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
            data, _ = sanitize_json_text_to_dict(resp.content)
            data = validate_script_items(data)
            llm_items = data.get("items", [])
            llm_ids_ordered: List[int] = []
            for it in llm_items:
                try:
                    if it.get("_id") is None:
                        continue
                    llm_ids_ordered.append(int(it.get("_id")))
                except Exception:
                    continue
            new_items_map = {int(it.get("_id")): it for it in llm_items if it.get("_id") is not None}

            def _update_item(orig: Dict[str, Any], new_it: Optional[Dict[str, Any]]) -> Dict[str, Any]:
                _id_val = int(orig.get("_id") or 0)
                if new_it:
                    orig["narration"] = str(new_it.get("narration", orig.get("narration", "")))
                    orig["picture"] = new_it.get("picture")
                    try:
                        ost_val = 1 if new_it.get("OST") == 1 else 0
                        orig["OST"] = ost_val
                    except Exception:
                        pass
                orig["_id"] = _id_val
                return orig

            if target >= n:
                final_items_all: List[Dict[str, Any]] = []
                for i, it in enumerate(items, start=1):
                    _id = int(it.get("_id") or i)
                    it["_id"] = _id
                    final_items_all.append(_update_item(it, new_items_map.get(_id)))
                return final_items_all

            keep_ids: List[int] = []
            if llm_ids_ordered:
                for _id in llm_ids_ordered:
                    if _id not in keep_ids:
                        keep_ids.append(_id)
                if len(keep_ids) > target:
                    keep_ids = keep_ids[:target]
            else:
                ids_all = [int(it.get("_id") or idx) for idx, it in enumerate(items, start=1)]
                keep_ids = ids_all[:target]

            id_set = set([int(it.get("_id") or idx) for idx, it in enumerate(items, start=1)])
            keep_ids = [i for i in keep_ids if i in id_set]
            if len(keep_ids) < target:
                for i in sorted(id_set):
                    if i not in keep_ids:
                        keep_ids.append(i)
                    if len(keep_ids) >= target:
                        break

            final_items_selected: List[Dict[str, Any]] = []
            for i, it in enumerate(items, start=1):
                _id = int(it.get("_id") or i)
                if _id in keep_ids:
                    it["_id"] = _id
                    final_items_selected.append(_update_item(it, new_items_map.get(_id)))
            return final_items_selected
        except Exception as e:
            logger.warning(f"Refine script failed, returning draft: {e}")
            return items

    @staticmethod
    async def generate_script_json(drama_name: str, plot_analysis: str, subtitle_content: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        生成解说脚本（Map-Reduce-Refine 模式）
        1. 解析字幕
        2. 按目标条数规划调用次数，并按字幕条数切分子任务 (Map)
        3. 并发生成各子任务脚本（每次强制输出指定条数）
        4. 合并去重 (Reduce)
        5. 全局润色并强制输出最终条数 (Refine)
        """
        # 1. 解析字幕
        subtitles = ScriptGenerationService._parse_srt_subtitles(subtitle_content)
        if not subtitles:
            logger.warning("Subtitle parsing failed")
            raise HTTPException(status_code=400, detail="字幕解析失败：请上传有效的SRT字幕或标准时间戳格式")
        total_duration = subtitles[-1]["end"] if subtitles else 0
        if total_duration == 0:
            logger.warning("Subtitle total duration invalid")
            raise HTTPException(status_code=400, detail="字幕解析失败：字幕时间戳无效")

        sel_length: Optional[str] = None
        if project_id:
            try:
                p = projects_store.get_project(project_id)
                if p:
                    if getattr(p, "script_length", None):
                        sel_length = str(getattr(p, "script_length", None))
            except Exception:
                sel_length = None

        # Log model info for user visibility
        try:
            model_info = ai_service.get_provider_info()
            m_name = model_info.get("active_model", "Unknown")
            m_prov = model_info.get("active_provider", "Unknown")
            logger.info(f"🚀 开始生成脚本 | 剧名: {drama_name} | 模型: {m_name} ({m_prov})")
        except Exception:
            logger.info(f"🚀 开始生成脚本 | 剧名: {drama_name}")

        plan = parse_script_length_selection(sel_length)
        chunks = compute_subtitle_chunks(
            subtitles=subtitles,
            desired_calls=plan.preferred_calls,
            max_items=MAX_SUBTITLE_ITEMS_PER_CALL,
            soft_factor=SOFT_INPUT_FACTOR,
        )
        if not chunks:
            raise HTTPException(status_code=400, detail="字幕解析失败：字幕内容为空")

        logger.info(f"📋 执行计划: 共 {len(chunks)} 个分段任务 | 目标总条数: {plan.final_target_count}")
        per_call_counts = allocate_output_counts(plan.final_target_count, len(chunks))
        sem = asyncio.Semaphore(5)

        async def generate_one(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
            async with sem:
                local_plot = ScriptGenerationService._filter_plot_analysis_by_time(
                    plot_analysis, chunk["start"], chunk["end"]
                )
                return await ScriptGenerationService._generate_script_chunk(
                    chunk["idx"],
                    len(chunks),
                    chunk["start"],
                    chunk["end"],
                    chunk["subs"],
                    local_plot,
                    drama_name,
                    project_id,
                    per_call_counts[int(chunk["idx"])],
                )

        tasks = [generate_one(c) for c in chunks]
        results = await asyncio.gather(*tasks)
        all_items: List[Dict[str, Any]] = []
        for res in results:
            all_items.extend(res)
        merged_items = ScriptGenerationService._merge_items(all_items)
        effective_target = min(len(merged_items), int(plan.final_target_count))
        if len(chunks) <= 1:
            final_items = merged_items[:effective_target] if effective_target > 0 else []
        else:
            final_items = await ScriptGenerationService._refine_full_script(
                merged_items,
                drama_name,
                plot_analysis,
                None,
                effective_target,
            )
        data = {"items": final_items}
        validated = validate_script_items(data)
        return cast(Dict[str, Any], validated)

    # @staticmethod
    # async def _generate_script_json_simple(
    #     drama_name: str,
    #     plot_analysis: str,
    #     subtitle_content: str,
    #     project_id: Optional[str] = None,
    #     target_items_count: Optional[int] = None,
    # ) -> Dict[str, Any]:
    #     """(旧版逻辑) 直接调用提示词模块生成"""
    #     default_key = ScriptGenerationService._default_prompt_key_for_project(project_id)
    #     key = ScriptGenerationService._resolve_prompt_key(project_id, default_key)
    #     variables = {
    #         "drama_name": drama_name,
    #         "plot_analysis": plot_analysis,
    #         "subtitle_content": subtitle_content,
    #     }
    #     try:
    #         messages_dicts = prompt_manager.build_chat_messages(key, variables)
    #     except KeyError:
    #         try:
    #             cat = (key.split(":", 1)[0] if ":" in key else "short_drama_narration")
    #             if cat == "movie_narration":
    #                 from modules.prompts.movie_narration import register_prompts
    #             else:
    #                 from modules.prompts.short_drama_narration import register_prompts
    #             register_prompts()
    #             messages_dicts = prompt_manager.build_chat_messages(key, variables)
    #         except Exception:
    #             key = default_key
    #             messages_dicts = prompt_manager.build_chat_messages(key, variables)
    #     messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages_dicts]
    #     if target_items_count and int(target_items_count) > 0:
    #         n = int(target_items_count)
    #         messages.insert(
    #             0,
    #             ChatMessage(
    #                 role="system",
    #                 content=(
    #                     f"你必须仅输出一个JSON对象，键为'items'。"
    #                     f"items数组长度必须严格等于{n}，不能多不能少。"
    #                     f"每条必须包含'_id','timestamp','picture','narration','OST'。"
    #                     f"不得输出除JSON以外的任何文字。"
    #                 ),
    #             ),
    #         )
    #     resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
    #     raw_text = resp.content

    #     # 清洗与校验
    #     data, raw_json = sanitize_json_text_to_dict(raw_text)
    #     validated = validate_script_items(data)
    #     return cast(Dict[str, Any], validated)

    @staticmethod
    def to_video_script(data: Dict[str, Any], total_duration: float) -> Dict[str, Any]:
        """
        将模型的 items JSON 转换为前端 VideoScript 结构：
        { version, total_duration, segments: [{id, start_time, end_time, text, subtitle?}], metadata }
        """
        items = data.get("items", [])
        segments: List[Dict[str, Any]] = []
        for it in items:
            start_s, end_s = _parse_timestamp_pair(str(it.get("timestamp")))
            text = str(it.get("narration", "")).strip()
            seg = {
                "id": str(it.get("_id", len(segments) + 1)),
                "start_time": float(start_s),
                "end_time": float(end_s),
                "text": text,
            }
            # 附带可用信息
            pic = it.get("picture")
            if pic:
                seg["subtitle"] = str(pic)
            segments.append(seg)

        now = datetime.now()
        generated_time = now.isoformat()
        version = f"{now.strftime('%Y%m%d%H%M%S')}"
        return {
            "生成时间": generated_time,
            '条数': len(segments),
            "version": version,
            "total_duration": float(total_duration or 0.0),
            "segments": segments,
            "metadata": {
                "created_at": generated_time,
            },
        }
