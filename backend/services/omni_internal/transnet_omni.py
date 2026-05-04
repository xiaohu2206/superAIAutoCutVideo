from __future__ import annotations

import logging
import math
import os
import subprocess
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from modules.ffmpeg_utils import get_ffmpeg_cuda_prefix, resolve_ffmpeg_bin
from modules.subprocess_no_console import popen_no_console

from services.omni_internal.types import Shot

logger = logging.getLogger(__name__)

_model: Optional[Any] = None
_model_lock = threading.Lock()


def _resolve_weights_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[2]
    candidates = [
        backend_dir / "serviceData" / "models" / "transnetv2-weights",
        backend_dir.parent / "backend" / "serviceData" / "models" / "transnetv2-weights",
    ]
    env_path = os.environ.get("TRANSNETV2_WEIGHTS_DIR")
    if env_path:
        candidates.insert(0, Path(env_path))
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return candidates[0]


def _get_model() -> Any:
    global _model
    with _model_lock:
        if _model is not None:
            return _model
        weights_dir = _resolve_weights_dir()
        if not weights_dir.exists():
            raise FileNotFoundError(f"TransNetV2 weights not found at {weights_dir}")
        logger.info("Omni: loading TransNetV2 from %s", weights_dir)
        backend = str(os.environ.get("TRANSNETV2_BACKEND") or "auto").strip().lower()
        if backend in {"torch", "auto"}:
            try:
                import torch
                from modules.transnetv2_torch import TransNetV2Torch

                w = os.environ.get("TRANSNETV2_PYTORCH_WEIGHTS") or str(weights_dir / "transnetv2-pytorch-weights.pth")
                use_torch = bool(w and Path(w).exists() and torch.cuda.is_available())
                if backend == "torch":
                    use_torch = bool(w and Path(w).exists())
                if use_torch:
                    _model = TransNetV2Torch(str(weights_dir))
                    try:
                        info = _model.get_backend_info()
                        logger.info(
                            "[Omni][TransNetV2][%s] backend=%s device=%s",
                            "GPU" if str(info.get("device") or "").lower().startswith("cuda") else "CPU",
                            info.get("backend"),
                            info.get("device"),
                        )
                    except Exception:
                        pass
                    return _model
            except Exception as e:
                if backend == "torch":
                    raise
                logger.warning("Omni: TransNetV2 torch unavailable, fallback tensorflow: %s", e)
        from modules.transnetv2 import TransNetV2

        _model = TransNetV2(str(weights_dir))
        logger.info("[Omni][TransNetV2][CPU] backend=tensorflow device=cpu")
        return _model


def _video_duration_sec(video_path: str) -> float:
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            return 0.0
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        if fps > 0 and n > 0:
            return max(0.0, n / fps)
    finally:
        cap.release()
    return 0.0


def _parallel_decode_config(duration_sec: float) -> Tuple[bool, int]:
    """是否启用分段并行 ffmpeg 解码，以及分段数量（≈线程数）。"""
    raw = str(os.environ.get("TRANSNETV2_PARALLEL_DECODE") or "auto").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False, 1
    min_sec = float(os.environ.get("TRANSNETV2_PARALLEL_DECODE_MIN_SEC") or "40")
    if raw not in {"1", "true", "yes", "on", "force"} and duration_sec < min_sec:
        return False, 1

    n_workers = int(os.environ.get("TRANSNETV2_DECODE_WORKERS") or "0")
    cpu = os.cpu_count() or 4
    if n_workers <= 0:
        n_workers = max(2, min(8, cpu))
    else:
        n_workers = max(2, min(n_workers, 16))

    chunk_target = float(os.environ.get("TRANSNETV2_DECODE_CHUNK_SEC") or "75")
    chunk_target = max(20.0, chunk_target)
    n_chunks = max(2, min(n_workers, int(math.ceil(duration_sec / chunk_target))))
    return True, n_chunks


def _ffmpeg_decode_transnet_rgb24_segment(
    video_fn: str,
    start_sec: float,
    duration_sec: float,
    *,
    ffmpeg_bin: str,
    hwaccel_prefix: Sequence[str] = (),
    thread_opt: Sequence[str] = (),
) -> np.ndarray:
    """与 TransNet predict_video 一致：48×27 RGB24 rawvideo；`-i` 后 `-ss`/`-t` 便于多段拼接。"""
    cmd: List[str] = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        *hwaccel_prefix,
        *thread_opt,
        "-i",
        video_fn,
        "-ss",
        f"{float(start_sec):.6f}",
        "-t",
        f"{float(duration_sec):.6f}",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        "scale=48:27",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    p = popen_no_console(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0 or not out:
        msg = (err or b"")[:2000].decode("utf-8", errors="ignore")
        raise RuntimeError(msg or "ffmpeg_extract_failed")
    return np.frombuffer(out, np.uint8).reshape([-1, 27, 48, 3])


def _parallel_transnet_rgb24_decode(
    video_path: str,
    *,
    n_chunks: int,
    progress_callback: Optional[Callable[[float], None]],
) -> np.ndarray:
    duration = _video_duration_sec(video_path)
    if duration <= 0:
        raise RuntimeError("parallel_decode:no_duration")

    ffmpeg_bin = resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        raise RuntimeError("parallel_decode:no_ffmpeg")

    edges = [duration * i / n_chunks for i in range(n_chunks + 1)]
    jobs: List[Tuple[float, float]] = []
    for i in range(n_chunks):
        start = edges[i]
        dur = edges[i + 1] - start
        if dur <= 1e-6:
            continue
        jobs.append((start, dur))
    if len(jobs) <= 1:
        raise RuntimeError("parallel_decode:single_segment")

    try_cuda = str(os.environ.get("TRANSNETV2_PARALLEL_CUDA") or "").strip() in {"1", "true", "yes", "on"}
    cuda_prefix: Tuple[str, ...] = get_ffmpeg_cuda_prefix() if try_cuda else ()

    ff_threads = int(os.environ.get("TRANSNETV2_FFMPEG_THREADS") or "1")
    thread_opt: Tuple[str, ...] = ()
    if ff_threads > 0:
        thread_opt = ("-threads", str(ff_threads))

    def _decode_one(start_dur: Tuple[float, float]) -> np.ndarray:
        start_sec, dur_sec = start_dur
        try:
            return _ffmpeg_decode_transnet_rgb24_segment(
                video_path,
                start_sec,
                dur_sec,
                ffmpeg_bin=ffmpeg_bin,
                hwaccel_prefix=cuda_prefix,
                thread_opt=thread_opt,
            )
        except RuntimeError:
            if cuda_prefix:
                return _ffmpeg_decode_transnet_rgb24_segment(
                    video_path,
                    start_sec,
                    dur_sec,
                    ffmpeg_bin=ffmpeg_bin,
                    hwaccel_prefix=(),
                    thread_opt=thread_opt,
                )
            raise

    total = len(jobs)
    parts: List[Optional[np.ndarray]] = [None] * total

    def _decode_progress(done: int) -> None:
        if not progress_callback or total <= 0:
            return
        frac = done / total
        progress_callback(2.0 + frac * 7.85)

    def _decode_heartbeat(done_cnt: int, ping_state: List[float]) -> None:
        """并行分段解码时，任一段 ffmpeg 可能阻塞数十秒；在段完成前也要周期性回调（与单管道 predict_video 一致）。"""
        if not progress_callback or total <= 0:
            return
        low = 2.0 + (done_cnt / total) * 7.85
        nxt = min(total, done_cnt + 1)
        cap = 2.0 + (nxt / total) * 7.85 - 0.06
        if cap <= low:
            cap = low + 0.2
        ping_state[0] = min(cap, max(low + 0.1, ping_state[0] + 0.38))
        progress_callback(ping_state[0])

    max_workers = min(total, max(2, int(os.environ.get("TRANSNETV2_DECODE_WORKERS") or "0") or (os.cpu_count() or 4)))
    max_workers = max(2, min(max_workers, 16))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_idx = {ex.submit(_decode_one, jobs[i]): i for i in range(total)}
        pending = set(future_to_idx.keys())
        done = 0
        ping_holder = [2.0]
        while pending:
            finished, pending = wait(pending, timeout=2.0, return_when=FIRST_COMPLETED)
            if not finished:
                _decode_heartbeat(done, ping_holder)
                continue
            for fut in finished:
                idx = future_to_idx[fut]
                parts[idx] = fut.result()
                done += 1
                _decode_progress(done)
            ping_holder[0] = 2.0 + (done / total) * 7.85

    stacked = [p for p in parts if p is not None]
    if not stacked:
        raise RuntimeError("parallel_decode:empty")
    return np.concatenate(stacked, axis=0)


def _infer_progress_wrap(progress_callback: Optional[Callable[[float], None]]) -> Optional[Callable[[float], None]]:
    if not progress_callback:
        return None

    def wrapped(pct: float) -> None:
        inner = max(0.0, min(100.0, float(pct)))
        progress_callback(10.0 + inner * 0.9)

    return wrapped


def detect_shots_from_video(
    video_path: str,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Tuple[List[Shot], float]:
    model = _get_model()
    vp = str(video_path)
    duration_sec = _video_duration_sec(vp)
    use_parallel, n_chunks = _parallel_decode_config(duration_sec)

    single_frame_pred: np.ndarray
    if use_parallel:
        if progress_callback:
            progress_callback(1.0)
        try:
            logger.info(
                "[Omni][TransNetV2] 并行 ffmpeg 解码（%s 段）+ 单次推理，时长约 %.1fs",
                n_chunks,
                duration_sec,
            )
            frames_rgb = _parallel_transnet_rgb24_decode(vp, n_chunks=n_chunks, progress_callback=progress_callback)
            infer_cb = _infer_progress_wrap(progress_callback)
            single_frame_pred, _ = model.predict_frames(frames_rgb, progress_callback=infer_cb)
        except Exception as e:
            logger.warning(
                "[Omni][TransNetV2] 并行解码失败，回退单管道 predict_video：%s",
                e,
            )
            tup = model.predict_video(vp, progress_callback)
            if not isinstance(tup, tuple) or len(tup) < 3:
                raise RuntimeError("TransNetV2 predict_video 返回异常") from e
            _, single_frame_pred, _ = tup[0], tup[1], tup[2]
    else:
        tup = model.predict_video(vp, progress_callback)
        if not isinstance(tup, tuple) or len(tup) < 3:
            raise RuntimeError("TransNetV2 predict_video 返回异常")
        _, single_frame_pred, _ = tup[0], tup[1], tup[2]
    cap = cv2.VideoCapture(str(video_path))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    cap.release()
    if fps <= 0:
        fps = 25.0
    scenes_np = model.predictions_to_scenes(single_frame_pred)
    shots: List[Shot] = []
    for idx, (start_f, end_f) in enumerate(scenes_np, start=1):
        s_t = float(start_f) / fps
        e_t = float(end_f) / fps
        shots.append(Shot(start=s_t, end=e_t, shot_id=idx, subtitles=[]))
    return shots, fps
