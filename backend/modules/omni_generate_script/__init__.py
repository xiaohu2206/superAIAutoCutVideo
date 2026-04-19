# -*- coding: utf-8 -*-
"""Omni 解说脚本生成：与 visual / script_generation 隔离，语义对齐 aiSearchShot Step4.9。"""

from .pure import (
    OmniNarrationParams,
    build_chunk_metas_and_prompts,
    merge_chunk_items,
    normalize_items_for_validation,
    omni_items_to_video_script,
    parse_timestamp_pair_seconds,
    post_check_chunk_items,
)

__all__ = [
    "OmniNarrationParams",
    "build_chunk_metas_and_prompts",
    "merge_chunk_items",
    "normalize_items_for_validation",
    "omni_items_to_video_script",
    "parse_timestamp_pair_seconds",
    "post_check_chunk_items",
]
