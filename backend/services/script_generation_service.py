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
    async def generate_script_json(drama_name: str, plot_analysis: str, subtitle_content: str) -> Dict[str, Any]:
        """调用提示词模块生成格式化脚本文案（返回已校验的原始JSON字典）"""
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
                from modules.prompts.short_drama_narration import register_prompts  # type: ignore
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