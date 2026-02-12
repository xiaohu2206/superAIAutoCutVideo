from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from services.asr_bcut import BcutASR


@dataclass
class AsrChunkResult:
    chunk_id: str
    utterances: List[Dict[str, Any]]
    attempts: int
    error: Optional[str] = None


class AsrStartThrottle:
    def __init__(self, min_interval_seconds: float = 2.0):
        self._min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._lock = asyncio.Lock()
        self._last_started_at = 0.0

    async def wait_turn(self) -> None:
        if self._min_interval_seconds <= 0:
            return
        loop = asyncio.get_running_loop()
        async with self._lock:
            now = loop.time()
            delta = now - self._last_started_at
            if delta < self._min_interval_seconds:
                await asyncio.sleep(self._min_interval_seconds - delta)
            self._last_started_at = loop.time()


async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def shift_utterances(utterances: List[Dict[str, Any]], offset_ms: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    off = int(offset_ms)
    for u in utterances or []:
        if not isinstance(u, dict):
            continue
        st = int(u.get("start_time", 0) or 0) + off
        et = int(u.get("end_time", 0) or 0) + off
        if et <= st:
            continue
        nu = dict(u)
        nu["start_time"] = st
        nu["end_time"] = et
        out.append(nu)
    return out


_space_re = re.compile(r"\s+")
_punct_re = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def _norm_text(s: str) -> str:
    t = (s or "").strip().lower()
    t = _punct_re.sub("", t)
    t = _space_re.sub("", t)
    return t


def _similarity(a: str, b: str) -> float:
    na = _norm_text(a)
    nb = _norm_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def dedupe_utterances(
    utterances: List[Dict[str, Any]],
    *,
    similarity_threshold: float = 0.85,
    time_slop_ms: int = 1200,
    lookback: int = 6,
) -> List[Dict[str, Any]]:
    if not utterances:
        return []

    items = sorted(
        [u for u in utterances if isinstance(u, dict)],
        key=lambda x: (int(x.get("start_time", 0) or 0), int(x.get("end_time", 0) or 0)),
    )

    kept: List[Dict[str, Any]] = []
    for u in items:
        st = int(u.get("start_time", 0) or 0)
        et = int(u.get("end_time", 0) or 0)
        if et <= st:
            continue
        txt = (u.get("text") or u.get("transcript") or "").strip()
        if not txt:
            continue

        dup = False
        for prev in reversed(kept[-lookback:]):
            pst = int(prev.get("start_time", 0) or 0)
            pet = int(prev.get("end_time", 0) or 0)
            if pst > st + time_slop_ms:
                continue
            time_overlap = st <= pet and et >= pst
            time_close = abs(st - pst) <= time_slop_ms and abs(et - pet) <= time_slop_ms
            time_touch = st <= pet + time_slop_ms
            if not (time_overlap or time_close or time_touch):
                continue
            ptxt = (prev.get("text") or prev.get("transcript") or "").strip()
            sim = _similarity(txt, ptxt)
            if sim >= similarity_threshold:
                dup = True
                break
        if not dup:
            kept.append(u)

    return kept


async def run_bcut_asr_with_retry(
    audio_path: str,
    *,
    throttle: Optional[AsrStartThrottle] = None,
    retry_max: int = 2,
    backoff_base_seconds: float = 2.0,
) -> Tuple[List[Dict[str, Any]], int]:
    last_err: Optional[str] = None
    attempts = 0
    for i in range(max(0, int(retry_max)) + 1):
        attempts = i + 1
        if throttle:
            await throttle.wait_turn()
        try:
            asr = BcutASR(audio_path)
            data = await _run_in_thread(asr.run)
            utterances = data.get("utterances") if isinstance(data, dict) else None
            if isinstance(utterances, list) and utterances:
                return utterances, attempts
            last_err = "语音识别失败"
        except Exception as e:
            last_err = str(e) or "语音识别失败"

        if i < retry_max:
            await asyncio.sleep(max(0.1, float(backoff_base_seconds)) * (2 ** i))

    raise RuntimeError(last_err or "语音识别失败")

