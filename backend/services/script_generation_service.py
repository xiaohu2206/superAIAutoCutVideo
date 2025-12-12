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
import re
from typing import Any, Dict, List, Tuple
import asyncio

from modules.ai import ChatMessage
from modules.prompts.prompt_manager import prompt_manager
from services.ai_service import ai_service
from modules.json_sanitizer import sanitize_json_text_to_dict, validate_script_items
from modules.projects_store import projects_store

logger = logging.getLogger(__name__)


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
        return resp.content

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
        start_time: float,
        end_time: float,
        subtitles: List[Dict[str, Any]],
        plot_analysis_snippet: str,
        drama_name: str,
        project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        subs_text_lines = []
        for s in subtitles:
            ts = _format_timestamp_range(float(s["start"]), float(s["end"]))
            subs_text_lines.append(f"[{ts}] {s['text']}")
        subs_text = "\n".join(subs_text_lines)
        if len(subs_text) > 6000:
            subs_text = subs_text[:6000]
        default_key = "short_drama_narration:script_generation"
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
                from modules.prompts.short_drama_narration import register_prompts
                register_prompts()
                messages_dicts = prompt_manager.build_chat_messages(key, variables)
            except Exception as e:
                key = default_key
                messages_dicts = prompt_manager.build_chat_messages(key, variables)
        messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages_dicts]
        try:
            resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
            data, _ = sanitize_json_text_to_dict(resp.content)
            data = validate_script_items(data)
            items = data.get("items") or []
            valid_items: List[Dict[str, Any]] = []
            for it in items:
                try:
                    s_t, e_t = _parse_timestamp_pair(str(it.get("timestamp")))
                    if e_t < start_time - 5 or s_t > end_time + 5:
                        continue
                    valid_items.append({
                        "_id": it.get("_id"),
                        "timestamp": str(it.get("timestamp")),
                        "picture": it.get("picture"),
                        "narration": str(it.get("narration", "")),
                        "OST": 1 if it.get("OST") == 1 else 0,
                        "_chunk_idx": chunk_idx,
                    })
                except Exception:
                    continue
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
        for i, it in enumerate(merged, start=1):
            it["_id"] = i
        return merged

    @staticmethod
    async def _refine_full_script(
        segments: List[Dict[str, Any]],
        drama_name: str,
        plot_analysis: str
    ) -> List[Dict[str, Any]]:
        items = segments
        if not items:
            return []
        draft_lines = [f"ID:{it['_id'] or i+1} | {it['timestamp']} | {it['narration']}" for i, it in enumerate(items)]
        draft_str = "\n".join(draft_lines)
        system_prompt = (
            "你是一位短剧解说主编。请在保持每条 '_id' 与 'timestamp' 不变的前提下优化文案。"
            "严格输出一个 JSON 对象，包含 'items' 列表，元素字段必须为 '_id', 'timestamp', 'picture', 'narration', 'OST'。"
            "只允许修改 'narration' 与 'picture'，不要新增或删除条目，不要输出任何非JSON字符。"
        )
        user_content = (
            f"剧名：{drama_name}\n"
            f"剧情背景：\n{plot_analysis[:1000]}...\n\n"
            f"草稿：\n{draft_str}\n\n"
            "请按要求返回 JSON。"
        )
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content)
        ]
        try:
            resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
            data, _ = sanitize_json_text_to_dict(resp.content)
            data = validate_script_items(data)
            new_items_map = {int(it.get("_id")): it for it in data.get("items", []) if it.get("_id") is not None}
            final_items: List[Dict[str, Any]] = []
            for i, it in enumerate(items, start=1):
                _id = int(it.get("_id") or i)
                if _id in new_items_map:
                    new_it = new_items_map[_id]
                    it["narration"] = str(new_it.get("narration", it.get("narration", "")))
                    it["picture"] = new_it.get("picture")
                it["_id"] = _id
                final_items.append(it)
            return final_items
        except Exception as e:
            logger.warning(f"Refine script failed, returning draft: {e}")
            return items

    @staticmethod
    async def generate_script_json(drama_name: str, plot_analysis: str, subtitle_content: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        生成解说脚本（Map-Reduce-Refine 模式）
        1. 解析字幕
        2. 滑动窗口分块 (Map)
        3. 并发生成各块脚本
        4. 合并去重 (Reduce)
        5. 全局润色 (Refine)
        """
        # 1. 解析字幕
        subtitles = ScriptGenerationService._parse_srt_subtitles(subtitle_content)
        if not subtitles:
            # Fallback to simple generation if parsing fails
            logger.warning("Subtitle parsing failed, fallback to simple generation")
            return await ScriptGenerationService._generate_script_json_simple(drama_name, plot_analysis, subtitle_content, project_id)
        total_duration = subtitles[-1]["end"] if subtitles else 0
        if total_duration == 0:
            return await ScriptGenerationService._generate_script_json_simple(drama_name, plot_analysis, subtitle_content, project_id)

        # 2. 分块配置
        WINDOW_SIZE = 2500  # 5分钟
        OVERLAP = 60       # 1分钟重叠
        chunks = []
        curr_time = 0
        idx = 0
        while curr_time < total_duration:
            end_time = curr_time + WINDOW_SIZE
            # 获取该时间段内的字幕
            chunk_subs = [s for s in subtitles if s["start"] >= curr_time and s["start"] < end_time]
            if chunk_subs:
                chunks.append({
                    "idx": idx,
                    "start": curr_time,
                    "end": end_time,
                    "subs": chunk_subs
                })
                idx += 1
            if curr_time + WINDOW_SIZE >= total_duration:
                break
            curr_time += (WINDOW_SIZE - OVERLAP)

        # 3. 并发生成 (限制并发数为 5)
        sem = asyncio.Semaphore(5)

        async def generate_one(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
            async with sem:
                # 筛选相关的剧情爆点
                local_plot = ScriptGenerationService._filter_plot_analysis_by_time(plot_analysis, chunk["start"], chunk["end"])
                return await ScriptGenerationService._generate_script_chunk(
                    chunk["idx"], chunk["start"], chunk["end"], chunk["subs"], local_plot, drama_name, project_id
                )
        tasks = [generate_one(c) for c in chunks]
        results = await asyncio.gather(*tasks)
        all_items: List[Dict[str, Any]] = []
        for res in results:
            all_items.extend(res)
        merged_items = ScriptGenerationService._merge_items(all_items)
        final_items = await ScriptGenerationService._refine_full_script(merged_items, drama_name, plot_analysis)
        data = {"items": final_items}
        data = validate_script_items(data)
        return data

    @staticmethod
    async def _generate_script_json_simple(drama_name: str, plot_analysis: str, subtitle_content: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """(旧版逻辑) 直接调用提示词模块生成"""
        default_key = "short_drama_narration:script_generation"
        key = ScriptGenerationService._resolve_prompt_key(project_id, default_key)
        variables = {
            "drama_name": drama_name,
            "plot_analysis": plot_analysis,
            "subtitle_content": subtitle_content,
        }
        try:
            messages_dicts = prompt_manager.build_chat_messages(key, variables)
        except KeyError:
            # 回退：显式注册短剧解说提示词模块，防止自动发现因环境路径导致未执行
            try:
                from modules.prompts.short_drama_narration import register_prompts
                register_prompts()
                messages_dicts = prompt_manager.build_chat_messages(key, variables)
            except Exception as e:
                key = default_key
                messages_dicts = prompt_manager.build_chat_messages(key, variables)
        messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages_dicts]
        resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
        raw_text = resp.content

        # 清洗与校验
        data, raw_json = sanitize_json_text_to_dict(raw_text)
        data = validate_script_items(data)
        return data

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

        return {
            "version": "v2.0",
            "total_duration": float(total_duration or 0.0),
            "segments": segments,
            "metadata": {
                "created_at": None,
            },
        }
