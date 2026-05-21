#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


DEFAULT_NARRATION_TYPE = "短剧解说"


@dataclass(frozen=True)
class NarrationTypeConfig:
    value: str
    category: str
    default_script_length: str
    output_format: str
    source_label: str
    work_kind: str
    supports_context: bool = False
    supports_reference_copywriting: bool = False


NARRATION_TYPE_CONFIG: Dict[str, NarrationTypeConfig] = {
    "短剧解说": NarrationTypeConfig(
        value="短剧解说",
        category="short_drama_narration",
        default_script_length="30～40条",
        output_format="short_drama",
        source_label="原剧",
        work_kind="短剧",
    ),
    "电影解说": NarrationTypeConfig(
        value="电影解说",
        category="movie_narration",
        default_script_length="60～80条",
        output_format="movie",
        source_label="原片",
        work_kind="电影",
        supports_context=True,
        supports_reference_copywriting=True,
    ),
    "电视剧解说": NarrationTypeConfig(
        value="电视剧解说",
        category="tv_drama_narration",
        default_script_length="40～60条",
        output_format="short_drama",
        source_label="原剧",
        work_kind="电视剧",
    ),
    "综艺解说": NarrationTypeConfig(
        value="综艺解说",
        category="variety_narration",
        default_script_length="30～40条",
        output_format="short_drama",
        source_label="原节目",
        work_kind="综艺",
    ),
    "纪录片解说": NarrationTypeConfig(
        value="纪录片解说",
        category="documentary_narration",
        default_script_length="40～60条",
        output_format="movie",
        source_label="原片",
        work_kind="纪录片",
    ),
    "体育解说": NarrationTypeConfig(
        value="体育解说",
        category="sports_narration",
        default_script_length="30～40条",
        output_format="short_drama",
        source_label="原赛事",
        work_kind="体育",
    ),
    "通用解说": NarrationTypeConfig(
        value="通用解说",
        category="general_narration",
        default_script_length="30～40条",
        output_format="short_drama",
        source_label="原片",
        work_kind="通用内容",
    ),
    "自定义解说": NarrationTypeConfig(
        value="自定义解说",
        category="custom_narration",
        default_script_length="30～40条",
        output_format="short_drama",
        source_label="原片",
        work_kind="自定义内容",
    ),
}


def list_narration_types() -> List[str]:
    return list(NARRATION_TYPE_CONFIG.keys())


def is_valid_narration_type(value: str) -> bool:
    return str(value or "").strip() in NARRATION_TYPE_CONFIG


def normalize_narration_type(value: str) -> str:
    v = str(value or "").strip()
    return v if v in NARRATION_TYPE_CONFIG else DEFAULT_NARRATION_TYPE


def get_config(value: str) -> NarrationTypeConfig:
    return NARRATION_TYPE_CONFIG[normalize_narration_type(value)]


def get_config_by_category(category: str) -> NarrationTypeConfig:
    cat = str(category or "").strip()
    for cfg in NARRATION_TYPE_CONFIG.values():
        if cfg.category == cat:
            return cfg
    return get_config(DEFAULT_NARRATION_TYPE)


def get_prompt_category(value: str) -> str:
    return get_config(value).category


def get_output_format_kind(value: str) -> str:
    return get_config(value).output_format


def get_original_label(value: str) -> str:
    return get_config(value).source_label


def get_default_script_length(value: str) -> str:
    return get_config(value).default_script_length


def get_work_kind(value: str) -> str:
    return get_config(value).work_kind


def supports_context(value: str) -> bool:
    return get_config(value).supports_context


def supports_reference_copywriting(value: str) -> bool:
    return get_config(value).supports_reference_copywriting
