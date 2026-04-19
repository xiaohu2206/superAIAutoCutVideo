# -*- coding: utf-8 -*-
"""从 backend/modules/copywriting_structuring_embedding/prompt 读取结构化提示词。"""

from __future__ import annotations

from pathlib import Path


def _prompt_base_dir() -> Path:
    # backend/modules/omni_copywriting_struct_embed -> backend/modules
    return Path(__file__).resolve().parent.parent / "copywriting_structuring_embedding" / "prompt"


def load_structuring_prompt(*, prompt_language: str = "zh") -> str:
    lang = str(prompt_language or "zh").strip().lower()
    name = "prompt_en.md" if lang == "en" else "prompt_zh.md"
    path = _prompt_base_dir() / name
    if not path.exists():
        raise FileNotFoundError(f"未找到结构化提示词文件: {path}")
    return path.read_text(encoding="utf-8", errors="ignore")
