# -*- coding: utf-8 -*-
"""结构化条目 → 向量模型输入文本（与 aiSearchShot demo 语义一致，独立实现）。"""

from __future__ import annotations

from typing import Any, Dict


def build_omni_embedding_input(n: Dict[str, Any], *, prompt_language: str = "zh") -> str:
    visual_keywords = n.get("visual_keywords") or []
    if not isinstance(visual_keywords, list):
        visual_keywords = [str(visual_keywords)]

    language = str(prompt_language or "zh").strip().lower()
    if language == "en":
        translation = str(n.get("translation") or "").strip()
        return "\n".join(
            [
                f"event: {n.get('event', '')}",
                f"subject: {n.get('subject', '')}",
                f"emotion: {n.get('emotion', '')}",
                f"scene_type: {n.get('scene_type', '')}",
                f"action: {n.get('action', '')}",
                f"visual_keywords: {', '.join([str(x) for x in visual_keywords])}",
                f"translation: {translation}",
            ]
        )

    return "\n".join(
        [
            f"事件:{n.get('event', '')}",
            f"主体:{n.get('subject', '')}",
            f"情绪:{n.get('emotion', '')}",
            f"场景:{n.get('scene_type', '')}",
            f"动作:{n.get('action', '')}",
            f"关键词:{','.join([str(x) for x in visual_keywords])}",
            f"描述:{n.get('text', '')}",
        ]
    )
