from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from modules.ai import ChatMessage
from services.ai_service import ai_service

logger = logging.getLogger(__name__)

LLM_CALL_MAX_RETRIES = 3
LLM_RETRY_BACKOFF_BASE_SEC = 1.0
LLM_RETRY_BACKOFF_MAX_SEC = 30.0


def _strip_code_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _is_non_retryable_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, RuntimeError):
        msg = str(exc)
        if "没有激活" in msg or "不支持的AI提供商" in msg:
            return True
    return False


async def call_llm_text(
    messages: List[ChatMessage],
    *,
    cancel_event: Optional[asyncio.Event] = None,
    max_retries: int = LLM_CALL_MAX_RETRIES,
) -> str:
    total_attempts = max_retries + 1
    for attempt in range(total_attempts):
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()
        try:
            if cancel_event:
                llm_task = asyncio.create_task(ai_service.send_chat(messages))
                cancel_task = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait({llm_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
                if cancel_task in done:
                    try:
                        llm_task.cancel()
                    except Exception:
                        pass
                    raise asyncio.CancelledError()
                try:
                    cancel_task.cancel()
                except Exception:
                    pass
                resp = await llm_task
            else:
                resp = await ai_service.send_chat(messages)
            return _strip_code_fences(str(resp.content or "").strip())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if _is_non_retryable_llm_error(e):
                raise
            if attempt < max_retries:
                delay = min(LLM_RETRY_BACKOFF_MAX_SEC, LLM_RETRY_BACKOFF_BASE_SEC * (2**attempt))
                logger.warning("reference_copywriting_wash LLM failed (%s/%s): %s, retry in %.1fs", attempt + 1, total_attempts, e, delay)
                if cancel_event:
                    try:
                        await asyncio.wait_for(cancel_event.wait(), timeout=delay)
                        raise asyncio.CancelledError()
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(delay)
                continue
            logger.error("reference_copywriting_wash LLM failed after retries: %s", e)
            raise
    return ""
