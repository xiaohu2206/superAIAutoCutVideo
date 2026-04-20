# -*- coding: utf-8 -*-
"""与前端一致的镜头视觉完成判定（vision_status 为主）及在线视觉与源视频文件一致性。"""

from pathlib import Path
from typing import Any, Dict


def scene_vision_success_ok(scene: Dict[str, Any]) -> bool:
    """
    已成功视觉分析以 vision_status == \"ok\" 为准。
    若存在非空的 vision_status，则仅 ok 为成功（error/empty/no_frame 等均视为未成功）。
    若无 vision_status（旧 JSON），则回退为 vision_analyzed。
    """
    vs = scene.get("vision_status")
    if vs is not None and str(vs).strip() != "":
        return str(vs).strip().lower() == "ok"
    return bool(scene.get("vision_analyzed"))


def path_stat_fingerprint_for_vision(video_abs: Path) -> Dict[str, int]:
    st = video_abs.stat()
    mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    return {"size": int(st.st_size), "mtime_ns": mtime_ns}


def video_abs_for_vision_fp(video_path: str) -> Path:
    try:
        return Path(video_path).expanduser().resolve(strict=False)
    except Exception:
        return Path(video_path).expanduser()


def scene_online_vision_skippable_for_current_video(scene: Dict[str, Any], video_abs: Path) -> bool:
    """
    在线视觉：仅当已成功且 vision_source_video_fp 与当前视频文件 stat 一致时可跳过重新推理。
    无 vision_source_video_fp 的旧数据返回 False，以便重跑并写入指纹（或与换源视频对齐）。
    """
    if not scene_vision_success_ok(scene):
        return False
    try:
        if not video_abs.exists():
            return False
        cur = path_stat_fingerprint_for_vision(video_abs)
    except OSError:
        return False
    stored = scene.get("vision_source_video_fp")
    if not isinstance(stored, dict) or not stored:
        return False
    try:
        return int(stored.get("size", -1)) == cur["size"] and int(stored.get("mtime_ns", -1)) == cur["mtime_ns"]
    except (TypeError, ValueError):
        return False
