from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from .llm_client import call_llm_text
from .prompts import build_wash_messages
from .quoted_strip import remove_leading_quoted_subtitle_lines
from .splitter import pair_reference_and_subtitles

logger = logging.getLogger(__name__)

# 与 copywriting_builder 分段并发度一致
_WASH_CONCURRENCY = 3


async def wash_reference_copywriting_pipeline(
    reference_raw: str,
    subs_text: str,
    *,
    drama_name: str = "",
    script_language: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> str:
    """
    参考稿洗稿：规则预清洗 → 按约 2500 字拆参考稿 → 按同片数比例拆字幕 → 分片并发调用模型 → 合并后再规则清洗。
    """
    ref_clean = remove_leading_quoted_subtitle_lines((reference_raw or "").strip())
    if not ref_clean:
        return ""

    pairs = pair_reference_and_subtitles(ref_clean, subs_text or "")
    if not pairs:
        return ""

    total = len(pairs)
    sem = asyncio.Semaphore(_WASH_CONCURRENCY)
    section_texts: List[Optional[str]] = [None] * total

    async def run_one(idx: int, ref_chunk: str, sub_chunk: str) -> None:
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()
        async with sem:
            msgs = build_wash_messages(
                drama_name=drama_name,
                reference_chunk=ref_chunk,
                subtitle_chunk=sub_chunk,
                section_index=idx,
                total_sections=total,
                script_language=script_language,
            )
            out = await call_llm_text(msgs, cancel_event=cancel_event)
            out = remove_leading_quoted_subtitle_lines(out)
            section_texts[idx] = out
            logger.info("reference_copywriting_wash 分段 %s/%s 完成, 字数约 %s", idx + 1, total, len(out or ""))

    await asyncio.gather(*(run_one(i, a, b) for i, (a, b) in enumerate(pairs)))

    merged = "\n\n".join(t for t in section_texts if t)
    merged = remove_leading_quoted_subtitle_lines(merged)
    logger.info("reference_copywriting_wash 合并完成, 总字数约 %s", len(merged))
    return merged
