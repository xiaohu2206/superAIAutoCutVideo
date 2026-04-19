# -*- coding: utf-8 -*-
"""Omni 项目：解说向量 ↔ 多模态镜头 粗筛 / 精筛 / 重排（与 visual 隔离）。"""

from .pure import (
    build_embedding_search_results,
    build_narration_block,
    build_rerank_documents,
    continuity_score,
    cosine_similarity,
    fine_rerank_json_schema,
    get_item_embedding,
    get_shot_embedding,
    get_timeline_info,
    load_fine_prompt_template,
    merge_fine_scores_and_continuity,
    normalize_llm_scores,
    parse_fine_llm_payload,
)

__all__ = [
    "build_embedding_search_results",
    "build_narration_block",
    "build_rerank_documents",
    "continuity_score",
    "cosine_similarity",
    "fine_rerank_json_schema",
    "get_item_embedding",
    "get_shot_embedding",
    "get_timeline_info",
    "load_fine_prompt_template",
    "merge_fine_scores_and_continuity",
    "normalize_llm_scores",
    "parse_fine_llm_payload",
]
