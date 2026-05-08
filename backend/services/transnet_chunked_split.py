#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
与 extract_scene_service.extract_scenes 中 _split_scenes 一致的 TransNetV2 分块推理：
chunk + overlap、环境变量 TRANSNETV2_CHUNK_SECONDS / OVERLAP_FRAMES / MAX_CONCURRENCY，
在 asyncio 事件循环中通过 run_in_executor 调用 model.predict_video（与镜头提取服务相同，便于 GPU / PyTorch 后端复用）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store

logger = logging.getLogger(__name__)


def _read_chunk_env() -> Tuple[float, int, int]:
    chunk_seconds = 180.0
    overlap_frames = 25
    max_chunk_concurrency = 0
    try:
        v = str(os.environ.get("TRANSNETV2_CHUNK_SECONDS") or "").strip()
        if v:
            chunk_seconds = float(v)
    except Exception:
        chunk_seconds = 180.0
    try:
        v = str(os.environ.get("TRANSNETV2_OVERLAP_FRAMES") or "").strip()
        if v:
            overlap_frames = int(v)
    except Exception:
        overlap_frames = 25
    try:
        v = str(os.environ.get("TRANSNETV2_MAX_CONCURRENCY") or "").strip()
        if v:
            max_chunk_concurrency = int(v)
    except Exception:
        max_chunk_concurrency = 0
    if overlap_frames < 0:
        overlap_frames = 0
    if chunk_seconds <= 0:
        chunk_seconds = 180.0
    return chunk_seconds, overlap_frames, max_chunk_concurrency


async def transnet_chunked_single_frame_predictions(
    video_abs_path: Path,
    model: Any,
    *,
    loop: asyncio.AbstractEventLoop,
    scope: str,
    project_id: str,
    task_id: str,
    progress_lo: float = 10.0,
    progress_hi: float = 90.0,
    message_prefix: str = "正在拆分镜头",
    phase: Optional[str] = None,
) -> Tuple[np.ndarray, float, int]:
    """
    返回 (single_frame_predictions, fps, total_frames)，与 extract_scenes 中分块逻辑一致。
    progress 在 [progress_lo, progress_hi] 之间线性映射（整体完成度 0–100%）。
    """
    chunk_seconds, overlap_frames, max_chunk_concurrency = _read_chunk_env()

    cap0 = cv2.VideoCapture(str(video_abs_path))
    fps0 = float(cap0.get(cv2.CAP_PROP_FPS) or 0.0)
    total_frames0 = int(cap0.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap0.release()
    if fps0 <= 0:
        fps0 = 25.0

    span = max(progress_hi - progress_lo, 1e-6)

    def _map_pct(overall_unit: float) -> float:
        """overall_unit in [0,1] -> progress bar position."""
        return progress_lo + float(overall_unit) * span

    def _report(mapped_pct: float, msg: str) -> None:
        kwargs: Dict[str, Any] = {
            "scope": scope,
            "project_id": project_id,
            "task_id": task_id,
            "status": "processing",
            "progress": mapped_pct,
            "message": msg,
        }
        if phase is not None:
            kwargs["phase"] = phase
        task_progress_store.set_state(**kwargs)

    if total_frames0 <= 0:

        def cb_tmp(pct: float):
            mapped_pct = _map_pct(min(1.0, max(0.0, float(pct) / 100.0)))
            _report(mapped_pct, f"{message_prefix}: {pct:.2f}%")
            if task_cancel_store.is_cancelled(scope, project_id, task_id):
                raise asyncio.CancelledError("任务已取消")

        _, sp_tmp, _ = await loop.run_in_executor(
            None,
            lambda: model.predict_video(str(video_abs_path), cb_tmp),
        )
        if sp_tmp is None or len(sp_tmp) == 0:
            raise ValueError("未能从视频中解码任何帧，无法进行镜头分析")
        single_frame_predictions = sp_tmp
        total_frames0 = len(single_frame_predictions)
        return single_frame_predictions, fps0, total_frames0

    chunk_frames = max(1, int(round(chunk_seconds * fps0)))
    starts = list(range(0, total_frames0, chunk_frames))
    final_pred = np.zeros(total_frames0, dtype=np.float32)
    total_core = total_frames0
    chunk_core: Dict[int, int] = {}
    for i, sf in enumerate(starts):
        ef = min(total_frames0, sf + chunk_frames)
        chunk_core[i] = ef - sf
    progress_map: Dict[int, float] = {i: 0.0 for i in chunk_core}
    prog_lock = threading.Lock()

    def _update_overall():
        with prog_lock:
            acc = 0.0
            for i, w in chunk_core.items():
                acc += w * max(0.0, min(100.0, float(progress_map.get(i, 0.0))))
            overall = (acc / max(1, total_core)) / 100.0
        mapped_pct = _map_pct(overall)
        msg = f"{message_prefix}: {overall * 100.0:.2f}%"
        loop.call_soon_threadsafe(_report, mapped_pct, msg)

    def _on_chunk_progress(idx: int, pct: float):
        with prog_lock:
            progress_map[idx] = pct
        _update_overall()

    async def run_chunk(si: int, sf: int, ef: int, asf: int, aef: int):
        if task_cancel_store.is_cancelled(scope, project_id, task_id):
            raise asyncio.CancelledError("任务已取消")
        st = asf / fps0
        dur = max(0.0, (aef - asf) / fps0)
        _, sp, _ = await loop.run_in_executor(
            None,
            lambda: model.predict_video(
                str(video_abs_path),
                lambda p, _si=si: _on_chunk_progress(_si, p),
                st,
                dur,
            ),
        )
        keep_l = ef - sf
        dl = sf - asf
        if dl < 0:
            dl = 0
        pred = sp[int(dl) : int(dl) + int(keep_l)]
        if len(pred) < keep_l:
            pad_val = float(pred[-1]) if len(pred) > 0 else 0.0
            pred = np.pad(pred, (0, keep_l - len(pred)), constant_values=pad_val)
        elif len(pred) > keep_l:
            pred = pred[:keep_l]
        with prog_lock:
            progress_map[si] = 100.0
        _update_overall()
        return si, sf, ef, pred

    pending = set()
    next_i = 0
    total_chunks = len(starts)
    effective_concurrency = max_chunk_concurrency if max_chunk_concurrency > 0 else 1

    def _enqueue_more():
        nonlocal next_i
        while next_i < total_chunks and len(pending) < effective_concurrency:
            sf = starts[next_i]
            ef = min(total_frames0, sf + chunk_frames)
            asf = max(0, sf - (overlap_frames if sf > 0 else 0))
            aef = min(total_frames0, ef + (overlap_frames if ef < total_frames0 else 0))
            pending.add(asyncio.create_task(run_chunk(next_i, sf, ef, asf, aef)))
            next_i += 1

    _enqueue_more()
    processed = 0
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                si, sf, ef, pred = t.result()
                final_pred[sf:ef] = pred[: (ef - sf)]
                processed += ef - sf
                pct = (processed / max(1, total_core)) * 100.0
                mapped_pct = _map_pct(pct / 100.0)
                _report(mapped_pct, f"{message_prefix}: {pct:.2f}%")
                if task_cancel_store.is_cancelled(scope, project_id, task_id):
                    for pt in pending:
                        try:
                            pt.cancel()
                        except Exception:
                            pass
                    await asyncio.gather(*pending, return_exceptions=True)
                    raise asyncio.CancelledError("任务已取消")
            _enqueue_more()
    except Exception:
        for pt in pending:
            try:
                pt.cancel()
            except Exception:
                pass
        await asyncio.gather(*pending, return_exceptions=True)
        raise

    return final_pred, fps0, total_frames0
