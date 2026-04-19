# -*- coding: utf-8 -*-
"""按标点与目标长度拆分长文案（独立实现，不依赖 .trae demo 包）。"""

from __future__ import annotations

from typing import List

SPLIT_PUNCTUATION_PRIORITIES: List[List[str]] = [
    ["\n", "\r"],
    ["。", "！", "？", "!", "?", ".", ";", "；"],
    ["，", ",", "、", ":", "："],
]


def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _compute_dynamic_chunk_target(total_len: int, base_chunk_chars: int) -> int:
    if total_len <= 0:
        return max(1, base_chunk_chars)
    base = max(1, int(base_chunk_chars or 500))
    chunk_count = max(1, -(-total_len // base))
    return max(1, total_len // chunk_count)


def split_copywriting_text(
    text: str,
    *,
    target_chunk_chars: int = 500,
    lookback_chars: int = 100,
) -> List[str]:
    normalized = _normalize_newlines(text).strip()
    if not normalized:
        return []

    chunks: List[str] = []
    start = 0
    total_len = len(normalized)
    dynamic_target_chunk_chars = _compute_dynamic_chunk_target(total_len, target_chunk_chars)

    while start < total_len:
        remaining = normalized[start:]
        if len(remaining) <= dynamic_target_chunk_chars:
            final_chunk = remaining.strip()
            if final_chunk:
                chunks.append(final_chunk)
            break

        tentative_end = min(total_len, start + max(1, dynamic_target_chunk_chars))
        search_start = max(start, tentative_end - max(0, lookback_chars))
        split_at = -1

        for punctuation_group in SPLIT_PUNCTUATION_PRIORITIES:
            for idx in range(tentative_end - 1, search_start - 1, -1):
                if normalized[idx] in punctuation_group:
                    split_at = idx + 1
                    break
            if split_at != -1:
                break

        if split_at == -1 or split_at <= start:
            split_at = tentative_end

        chunk = normalized[start:split_at].strip()
        if chunk:
            chunks.append(chunk)

        next_start = split_at
        while next_start < total_len and normalized[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks
