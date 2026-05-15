# -*- coding: utf-8 -*-
"""结构化输出的 JSON Schema、校验与模型响应解析。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List


def copywriting_segments_json_schema(*, include_translation: bool) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "text": {"type": "string"},
    }
    if include_translation:
        properties["translation"] = {"type": "string"}
    properties.update(
        {
            "event": {"type": "string"},
            "subject": {"type": "string"},
            "emotion": {"type": "string"},
            "scene_type": {"type": "string"},
            "visual_keywords": {
                "type": "array",
                "items": {"type": "string"},
            },
            "action": {"type": "string"},
            "camera_hint": {"type": "string"},
        }
    )
    required = [
        "text",
        "event",
        "subject",
        "emotion",
        "scene_type",
        "visual_keywords",
        "action",
        "camera_hint",
    ]
    if include_translation:
        required.insert(1, "translation")
    return {
        "name": "copywriting_segments",
        "strict": True,
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def normalize_segment(item: Dict[str, Any]) -> Dict[str, Any]:
    visual_keywords = item.get("visual_keywords")
    if isinstance(visual_keywords, list):
        normalized_keywords = [str(x).strip() for x in visual_keywords if str(x).strip()]
    elif visual_keywords is None:
        normalized_keywords = []
    else:
        normalized_keywords = [str(visual_keywords).strip()] if str(visual_keywords).strip() else []

    return {
        "text": str(item.get("text") or "").strip(),
        "translation": str(item.get("translation") or "").strip(),
        "event": str(item.get("event") or "").strip(),
        "subject": str(item.get("subject") or "").strip(),
        "emotion": str(item.get("emotion") or "").strip(),
        "scene_type": str(item.get("scene_type") or "").strip(),
        "visual_keywords": normalized_keywords,
        "action": str(item.get("action") or "").strip(),
        "camera_hint": str(item.get("camera_hint") or "").strip(),
    }


def validate_segment(
    item: Dict[str, Any],
    chunk_index: int,
    item_index: int,
    *,
    require_translation: bool,
) -> None:
    fields = ["text", "event", "subject", "emotion", "scene_type", "action", "camera_hint"]
    if require_translation:
        fields.insert(1, "translation")
    for field in fields:
        if not item.get(field):
            raise ValueError(f"chunk={chunk_index} item={item_index} 缺少字段或为空: {field}")
    if not isinstance(item.get("visual_keywords"), list):
        raise ValueError(f"chunk={chunk_index} item={item_index} visual_keywords 必须是数组")


def _strip_code_fence(raw: str) -> str:
    s = (raw or "").strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", s, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _looks_like_segment_object(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return isinstance(data.get("text"), str) and any(
        key in data
        for key in (
            "event",
            "subject",
            "emotion",
            "scene_type",
            "visual_keywords",
            "action",
            "camera_hint",
        )
    )


def _looks_like_segment_array(data: Any) -> bool:
    if not isinstance(data, list):
        return False
    if not data:
        return True
    return all(isinstance(x, dict) for x in data)


def parse_model_json_array(raw: str) -> List[Any]:
    s = _strip_code_fence(raw)
    data = json.loads(s)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("segments", "items", "data", "copywriting_segments", "result"):
            v = data.get(key)
            if _looks_like_segment_array(v):
                return v
            if _looks_like_segment_object(v):
                return [v]
        if _looks_like_segment_object(data):
            return [data]
        for v in data.values():
            if _looks_like_segment_array(v):
                return v
        raise ValueError(f"模型输出对象中未找到数组字段: keys={list(data.keys())}")
    raise ValueError(f"模型输出不是 JSON 数组或可解析对象: {type(data)}")
