from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import cv2
import numpy as np

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


def detect_shots_from_video(
    video_path: str,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Tuple[List[Shot], float]:
    model = _get_model()
    tup = model.predict_video(str(video_path), progress_callback)
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
