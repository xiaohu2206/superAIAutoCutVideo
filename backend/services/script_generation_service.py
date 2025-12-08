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
        resp = await ai_service.send_chat(messages)
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
        """解析SRT字幕内容为结构化列表"""
        subs = []
        # 简单正则匹配 SRT 块
        # 格式:
        # 1
        # 00:00:01,000 --> 00:00:04,000
        # 字幕文本
        pattern = re.compile(r"(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s+(.+?)(?=\n\s*\d+\s+\d{2}:\d{2}:\d{2}|\Z)", re.DOTALL)
        
        # 归一化换行
        content = subtitle_content.strip().replace("\r\n", "\n") + "\n"
        
        matches = pattern.findall(content)
        for m in matches:
            idx, start_str, end_str, text = m
            try:
                start_s = ScriptGenerationService._parse_timestamp_str(start_str)
                end_s = ScriptGenerationService._parse_timestamp_str(end_str)
                subs.append({
                    "index": int(idx),
                    "start": start_s,
                    "end": end_s,
                    "text": text.strip()
                })
            except Exception:
                continue
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
        relevant_lines = []
        current_block = []
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
                except:
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
    async def _generate_script_chunk(
        chunk_idx: int,
        start_time: float,
        end_time: float,
        subtitles: List[Dict[str, Any]],
        plot_analysis_snippet: str,
        drama_name: str
    ) -> List[Dict[str, Any]]:
        """生成单个分块的脚本"""
        
        # 1. 准备字幕文本 (带时间标记，方便模型引用)
        subs_text_lines = []
        for s in subtitles:
            # 简单格式: [00:00-00:05] 台词
            s_fmt = f"{int(s['start'] // 60):02d}:{int(s['start'] % 60):02d}"
            e_fmt = f"{int(s['end'] // 60):02d}:{int(s['end'] % 60):02d}"
            subs_text_lines.append(f"[{s_fmt}-{e_fmt}] {s['text']}")
        
        # 限制字幕 tokens (简单的字符截断，防止溢出)
        subs_text = "\n".join(subs_text_lines)
        if len(subs_text) > 6000: # 约 3-4k tokens
            subs_text = subs_text[:6000] + "\n...(字幕过长截断)..."

        system_prompt = (
            "你是一位短剧解说文案创作专家。你的任务是根据提供的字幕片段和剧情爆点，创作一段精彩的解说文案。\n"
            "要求：\n"
            "1. **输出格式**：严格的JSON格式，包含 `segments` 列表，每个元素含 `start_time`(秒), `end_time`(秒), `text`(解说词), `subtitle`(对应画面字幕/画面描述，可选)。\n"
            "2. **内容风格**：紧凑、悬念迭起、情绪饱满。避免流水账，要提炼剧情冲突。\n"
            "3. **时间控制**：生成的解说词时间戳必须严格落在输入的时间窗口内 ({:.1f} - {:.1f} 秒)。\n"
            "4. **真实性**：解说必须基于字幕事实，不可捏造剧情。\n"
            "5. **分段**：每段解说词长度适中（10-20秒），便于观众消化。\n"
        ).format(start_time, end_time)

        user_content = (
            f"剧名：{drama_name}\n"
            f"当前时间窗口：{start_time:.1f}秒 - {end_time:.1f}秒\n\n"
            f"剧情爆点参考：\n{plot_analysis_snippet}\n\n"
            f"字幕片段：\n{subs_text}\n\n"
            "请生成该片段的解说脚本 JSON："
        )

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content)
        ]

        try:
            resp = await ai_service.send_chat(messages)
            data, _ = sanitize_json_text_to_dict(resp.content)
            segments = data.get("segments", [])
            if not isinstance(segments, list):
                return []
            
            # 校验和修正
            valid_segments = []
            for seg in segments:
                # 强制类型转换
                try:
                    s_t = float(seg.get("start_time", 0))
                    e_t = float(seg.get("end_time", 0))
                    # 简单过滤掉完全不在窗口内的（容忍一点误差）
                    if e_t < start_time - 5 or s_t > end_time + 5:
                        continue
                    
                    seg["start_time"] = s_t
                    seg["end_time"] = e_t
                    seg["text"] = str(seg.get("text", "")).strip()
                    # 标记来源 chunk，方便调试
                    seg["_chunk_idx"] = chunk_idx
                    valid_segments.append(seg)
                except:
                    continue
            return valid_segments
        except Exception as e:
            logger.error(f"Chunk {chunk_idx} generation failed: {e}")
            return []

    @staticmethod
    def _merge_segments(all_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并并去重所有分段"""
        # 1. 按开始时间排序
        sorted_segs = sorted(all_segments, key=lambda x: x["start_time"])
        
        merged = []
        if not sorted_segs:
            return []
            
        # 2. 简单的重叠去重逻辑
        # 如果当前段与上一段重叠严重，或者时间包含，则择优保留
        # 这里简化处理：如果重叠 > 50%，保留文本较长的那个（假设信息量大），或者保留后来的（假设覆盖逻辑）
        
        current = sorted_segs[0]
        for next_seg in sorted_segs[1:]:
            # 计算重叠
            overlap_start = max(current["start_time"], next_seg["start_time"])
            overlap_end = min(current["end_time"], next_seg["end_time"])
            overlap_len = max(0, overlap_end - overlap_start)
            
            curr_len = current["end_time"] - current["start_time"]
            next_len = next_seg["end_time"] - next_seg["start_time"]
            
            # 如果重叠超过较短段落的 40%
            if overlap_len > 0 and (overlap_len > 0.4 * min(curr_len, next_len) + 0.1): 
                # 冲突，需合并
                # 策略：保留更靠中心的 chunk 的结果？或者文本更长的？
                # 简单策略：保留文本更长的
                if len(next_seg["text"]) > len(current["text"]):
                    current = next_seg
                else:
                    pass # Keep current
            else:
                # 无显著冲突，加入 current，切换到 next
                merged.append(current)
                current = next_seg
        
        merged.append(current)
        
        # 3. 重新编号 ID
        for i, seg in enumerate(merged):
            seg["id"] = str(i + 1)
            
        return merged

    @staticmethod
    async def _refine_full_script(
        segments: List[Dict[str, Any]],
        drama_name: str,
        plot_analysis: str
    ) -> List[Dict[str, Any]]:
        """全局优化脚本：统一风格，优化过渡"""
        
        if not segments:
            return []
            
        # 构造精简的 segments 文本供模型读取
        # 仅包含时间与文本，节省 token
        draft_text = []
        for seg in segments:
            draft_text.append(f"ID:{seg['id']} | {seg['start_time']:.1f}-{seg['end_time']:.1f} | {seg['text']}")
            
        draft_str = "\n".join(draft_text)
        
        # 如果草稿太长，可能也需要切分优化，但这里假设 Map-Reduce 后的纯文本已经足够小 (通常解说词比字幕少得多)
        # 假设 100个段落 * 50字 = 5000字，勉强可接受。
        
        system_prompt = (
            "你是一位短剧解说主编。请对以下解说文案草稿进行全局润色。\n"
            "目标：\n"
            "1. **统一风格**：确保全篇口吻一致，情绪连贯。\n"
            "2. **优化过渡**：段落间衔接自然，消除生硬的拼接感。\n"
            "3. **增强钩子**：确保关键节点的悬念足够吸引人。\n"
            "4. **结构保持**：严格输出 JSON，**必须保留原 ID 和时间戳**，仅修改 `text` 和 `subtitle`。\n"
            "5. **去重**：如果发现内容重复，请精简。\n"
        )
        
        user_content = (
            f"剧名：{drama_name}\n"
            f"剧情背景：\n{plot_analysis[:1000]}...\n\n" # 提供部分背景
            f"文案草稿：\n{draft_str}\n\n"
            "请输出优化后的 JSON (字段: id, start_time, end_time, text, subtitle):"
        )
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content)
        ]
        
        try:
            resp = await ai_service.send_chat(messages)
            data, _ = sanitize_json_text_to_dict(resp.content)
            
            # 解析返回的 segments，并更新原 segments
            # 因为模型可能会漏掉某些段落或改乱 ID，我们需要做一个健壮的映射
            new_segments_map = {str(s.get("id")): s for s in data.get("segments", []) if s.get("id")}
            
            final_segments = []
            for seg in segments:
                sid = str(seg["id"])
                if sid in new_segments_map:
                    new_seg = new_segments_map[sid]
                    # 更新文本
                    seg["text"] = new_seg.get("text", seg["text"])
                    if "subtitle" in new_seg:
                        seg["subtitle"] = new_seg["subtitle"]
                final_segments.append(seg)
                
            return final_segments
        except Exception as e:
            logger.warning(f"Refine script failed, returning draft: {e}")
            return segments

    @staticmethod
    async def generate_script_json(drama_name: str, plot_analysis: str, subtitle_content: str) -> Dict[str, Any]:
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
            return await ScriptGenerationService._generate_script_json_simple(drama_name, plot_analysis, subtitle_content)
            
        total_duration = subtitles[-1]["end"] if subtitles else 0
        if total_duration == 0:
             return await ScriptGenerationService._generate_script_json_simple(drama_name, plot_analysis, subtitle_content)

        # 2. 分块配置
        WINDOW_SIZE = 300  # 5分钟
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
        
        async def generate_one(chunk):
            async with sem:
                # 筛选相关的剧情爆点
                local_plot = ScriptGenerationService._filter_plot_analysis_by_time(plot_analysis, chunk["start"], chunk["end"])
                return await ScriptGenerationService._generate_script_chunk(
                    chunk["idx"], chunk["start"], chunk["end"], chunk["subs"], local_plot, drama_name
                )
        
        tasks = [generate_one(c) for c in chunks]
        results = await asyncio.gather(*tasks)
        
        all_segments = []
        for res in results:
            all_segments.extend(res)
            
        # 4. 合并去重
        merged_segments = ScriptGenerationService._merge_segments(all_segments)
        
        # 5. 全局润色
        final_segments = await ScriptGenerationService._refine_full_script(merged_segments, drama_name, plot_analysis)
        
        return {"segments": final_segments}

    @staticmethod
    async def _generate_script_json_simple(drama_name: str, plot_analysis: str, subtitle_content: str) -> Dict[str, Any]:
        """(旧版逻辑) 直接调用提示词模块生成"""
        key = "short_drama_narration:script_generation"
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
                raise RuntimeError(f"无法获取提示词 {key}: {e}")
        messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages_dicts]
        resp = await ai_service.send_chat(messages)
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
