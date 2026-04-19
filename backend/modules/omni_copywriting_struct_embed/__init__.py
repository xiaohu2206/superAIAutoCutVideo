# -*- coding: utf-8 -*-
"""Omni 项目专用：解说文案结构化 + 向量化（与 visual / extract_scene 逻辑隔离）。"""

from .chunk_split import split_copywriting_text
from .embedding_input import build_omni_embedding_input
from .prompt_loader import load_structuring_prompt
from .segments import (
    copywriting_segments_json_schema,
    normalize_segment,
    parse_model_json_array,
    validate_segment,
)

__all__ = [
    "split_copywriting_text",
    "build_omni_embedding_input",
    "load_structuring_prompt",
    "copywriting_segments_json_schema",
    "normalize_segment",
    "parse_model_json_array",
    "validate_segment",
]
