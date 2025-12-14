#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON清洗与校验模块
用于处理大模型返回的格式化JSON：去除代码块标记、提取JSON内容、容错解析、基础结构校验。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Tuple


def _strip_code_fences(text: str) -> str:
    """移除常见的 Markdown 代码块包裹```json ... ```"""
    text = text.strip()
    # 去除最外层三引号代码块
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    # 去除语言标记，如 json
    text = re.sub(r"^(json|JSON)\s*", "", text)
    return text.strip()


def _extract_braced_json(text: str) -> str:
    """从文本中提取首尾大括号内的内容"""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _remove_trailing_commas(s: str) -> str:
    """去除对象或数组中的尾随逗号（简单正则修复）"""
    # 修复对象尾随逗号
    s = re.sub(r",\s*}(?!\s*[,}\]])", "}", s)
    # 修复数组尾随逗号
    s = re.sub(r",\s*](?!\s*[,}\]])", "]", s)
    return s


def sanitize_json_text_to_dict(text: str) -> Tuple[Dict[str, Any], str]:
    """
    清洗并解析JSON文本，返回(dict, raw_json_str)。
    抛出异常由调用方处理。
    """
    cleaned = _strip_code_fences(text)
    cleaned = _extract_braced_json(cleaned)
    cleaned = _remove_trailing_commas(cleaned)

    try:
        data = json.loads(cleaned)
    except Exception:
        def _normalize_json_quotes_stateful(s: str) -> str:
            out = []
            in_string = False
            start_quote = ''
            escape = False
            for ch in s:
                if not in_string:
                    if ch in ('"', '“', '”', "'", '`'):
                        start_quote = ch
                        in_string = True
                        escape = False
                        out.append('"')
                    else:
                        out.append(ch)
                else:
                    if escape:
                        out.append(ch)
                        escape = False
                    else:
                        if ch == '\\':
                            out.append(ch)
                            escape = True
                        else:
                            if start_quote == '“':
                                is_close = (ch == '”')
                            elif start_quote == '”':
                                is_close = (ch == '“')
                            else:
                                is_close = (ch == start_quote)
                            if is_close:
                                in_string = False
                                start_quote = ''
                                out.append('"')
                            else:
                                if start_quote in ("'", '`') and ch == '"':
                                    out.append('\\"')
                                else:
                                    out.append(ch)
            return ''.join(out)
        cleaned2 = _normalize_json_quotes_stateful(cleaned)
        cleaned2 = _remove_trailing_commas(cleaned2)
        data = json.loads(cleaned2)
        cleaned = cleaned2
    if not isinstance(data, dict):
        # 如果是列表，包一层
        data = {"items": data}
    return data, cleaned


def validate_script_items(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    校验并标准化脚本JSON的基础结构，确保存在 items 列表，且元素包含必需字段。
    返回修正后的 data。
    """
    items = data.get("items")
    if items is None:
        # 兼容少量模型使用 segments 或 data 的情况
        items = data.get("segments") or data.get("data")
        if items is not None:
            data = {"items": items}
    if items is None:
        raise ValueError("脚本JSON缺少 'items' 列表")

    if not isinstance(items, list):
        raise ValueError("'items' 必须是列表")

    # 轻量校验字段存在性（不做类型强校验，兼容模型差异）
    normalized: list = []
    for idx, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            raise ValueError("items 中元素必须为对象")
        _id = it.get("_id", idx)
        ts = it.get("timestamp")
        pic = it.get("picture")
        narr = it.get("narration")
        ost = it.get("OST")
        if ts is None or narr is None:
            raise ValueError("每个条目必须包含 'timestamp' 和 'narration'")
        normalized.append({
            "_id": _id,
            "timestamp": str(ts),
            "picture": pic,
            "narration": str(narr),
            "OST": 1 if ost == 1 else 0,
        })
    data["items"] = normalized
    return data
