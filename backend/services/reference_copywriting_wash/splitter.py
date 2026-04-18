"""按参考稿长度拆分片数，并按相同片数比例拆分字幕行（与分段生成里 2500 字/片的思路一致）。"""

from __future__ import annotations

import math
from typing import List, Tuple

# 与 copywriting_builder._generate_segmented 中 per_call_max 一致
PER_CHUNK_MAX_CHARS = 2500


def compute_num_sections(total_chars: int) -> int:
    if total_chars <= 0:
        return 0
    if total_chars <= PER_CHUNK_MAX_CHARS:
        return 1
    return max(2, math.ceil(total_chars / PER_CHUNK_MAX_CHARS))


def split_reference_text(ref: str, n: int) -> List[str]:
    if n <= 0:
        return []
    if n == 1:
        return [ref]
    l = len(ref)
    chunks: List[str] = []
    for i in range(n):
        a = i * l // n
        b = (i + 1) * l // n if i < n - 1 else l
        chunks.append(ref[a:b])
    return chunks


def split_subs_text_by_sections(subs_text: str, n: int) -> List[str]:
    if n <= 0:
        return []
    lines = subs_text.split("\n")
    if n == 1:
        return [subs_text]
    out: List[str] = []
    for i in range(n):
        lo = i * len(lines) // n
        hi = (i + 1) * len(lines) // n if i < n - 1 else len(lines)
        out.append("\n".join(lines[lo:hi]))
    return out


def pair_reference_and_subtitles(ref_clean: str, subs_text: str) -> List[Tuple[str, str]]:
    n = compute_num_sections(len(ref_clean))
    if n == 0:
        return []
    ref_chunks = split_reference_text(ref_clean, n)
    sub_chunks = split_subs_text_by_sections(subs_text, n)
    if not ref_chunks:
        return []
    if len(sub_chunks) < len(ref_chunks):
        sub_chunks = sub_chunks + [""] * (len(ref_chunks) - len(sub_chunks))
    return list(zip(ref_chunks, sub_chunks[: len(ref_chunks)]))
