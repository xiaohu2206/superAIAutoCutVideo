#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni 项目专用：镜头拆分（与 extract_scenes 同款分块 TransNetV2 + 字幕语义段）与多模态特征（在线视觉 + 本地 BGE 句向量）。
与 extract_scene_service 共用 TransNet 模型与分块 predict_video 逻辑；产出仍写入 uploads/omni_multimodal/{project_id}/。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from services.ai_models.unified_model_usage import resolve_video_model_for_online_vision
from modules.projects_store import projects_store
from modules.subtitle_utils import parse_srt
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from services.asr.extract_subtitle_service import _resolve_path, _to_web_path, _uploads_dir
from services.omni_internal.frame_extract import extract_middle_frame
from services.omni_internal.multimodal_json_crypto import read_multimodal_json, write_encrypted_multimodal_json
from services.omni_internal.shot_subtitle_mapper import ShotSubtitleMapper
from services.ai_models.omni_local_bge_embedding import LOCAL_BGE_MODEL_DISPLAY_NAME, assert_local_bge_model_available, encode_text_async
from services.extract_scene_service import extract_scene_service
from services.transnet_chunked_split import transnet_chunked_single_frame_predictions
from services.omni_internal.types import Shot, Subtitle
from services.ai_models.vision_frame_analysis_service import (
    _ONLINE_VISION_INFER_CONCURRENT_INTERVAL_SEC,
    _ONLINE_VISION_INFER_RETRY_DELAYS_SEC,
    _OnlineVisionRunner,
    _try_parse_vision_json,
    load_frame_analysis_batch_prompt,
    load_frame_analysis_prompt,
    optimize_image_for_online_vision,
)

logger = logging.getLogger(__name__)

_SCOPE = "omni_multimodal"

# Step2 在线视觉：一次请求合并分析的语义段数量（与 frame_analysis_multi_zh.md 一致）
OMNI_STEP2_VL_BATCH_SIZE = 8

_ONLINE_VL_PROVIDERS = frozenset({"yunwu", "302ai", "qwen", "doubao", "custom_openai_vision"})


def _normalize_multimodal_action(raw: Optional[str]) -> str:
    m = str(raw or "auto").strip().lower()
    return m if m in ("auto", "continue", "restart") else "auto"


def _omni_shot_identity(shot: Dict[str, Any]) -> Tuple[str, str, str]:
    sid = str(shot.get("shot_id") if shot.get("shot_id") is not None else "")
    try:
        st = f"{float(shot.get('start', 0)):.6f}"
        ed = f"{float(shot.get('end', 0)):.6f}"
    except (TypeError, ValueError):
        st, ed = "0.000000", "0.000000"
    return (sid, st, ed)


def _shot_step2_complete(sh: Dict[str, Any]) -> bool:
    if not isinstance(sh, dict):
        return False
    st = str(sh.get("omni_step2_status") or "").strip().lower()
    if st in ("pending", "error", "vl_error"):
        return False
    emb = sh.get("embedding")
    if not isinstance(emb, list) or len(emb) == 0:
        return False
    vis = sh.get("visual")
    if not isinstance(vis, dict):
        return False
    return True


def _exception_message_blob(exc: BaseException) -> str:
    parts: List[str] = []
    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(str(cur))
        cur = cur.__cause__ or cur.__context__
    return " ".join(parts).lower()


def _is_upstream_vision_policy_block(exc: BaseException) -> bool:
    """Gemini / Vertex 等内容安全策略拒绝（非超时、非鉴权类）时返回 True，用于 Step2 单镜头降级。"""
    if isinstance(exc, asyncio.TimeoutError):
        return False
    blob = _exception_message_blob(exc)
    if not blob.strip():
        return False
    needles = (
        "prohibited_content",
        "content is prohibited",
        "blocked by google gemini",
        "safety filters",
        "official usage policies",
        "image_blocked",
        "harm category",
        "responsible ai practices",
        "person_generation",
    )
    return any(n in blob for n in needles)


def _omni_bge_embed_encode_concurrency_cap() -> Optional[int]:
    """>0 时限制 Step2 向量化阶段并发 encode；未设置则不限制（并行 to_thread）。"""
    raw = (os.environ.get("OMNI_BGE_ENCODE_ASYNC_CONCURRENCY") or "").strip()
    if not raw:
        return None
    try:
        n = int(raw, 10)
        if n <= 0:
            return None
        return min(n, 128)
    except Exception:
        return None


@dataclass(frozen=True)
class _Step2VlOutcome:
    idx: int
    shot: Dict[str, Any]
    frame_paths: List[str]
    kind: Literal["success", "policy_blocked", "empty_visual", "vl_failed"]
    visual: Dict[str, Any]
    policy_error: Optional[BaseException] = None
    vl_fail: Optional[BaseException] = None
    vl_fail_was_timeout: bool = False


def _close_shot_pil_images(imgs: List[Image.Image]) -> None:
    for im in imgs:
        try:
            im.close()
        except Exception:
            pass


def _try_load_existing_multimodal_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return read_multimodal_json(path)
    except Exception as e:
        logger.warning("读取已有 Omni 多模态结果失败 path=%s err=%s", path, e)
        return None


def _prior_multimodal_map(existing: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    m: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for s in existing.get("shots") or []:
        if isinstance(s, dict):
            m[_omni_shot_identity(s)] = s
    return m


def _merge_shot_with_prior(step1_shot: Dict[str, Any], prior: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(step1_shot)
    out.pop("omni_step2_status", None)
    for k in ("frames", "visual", "summary", "embedding", "omni_step2_status", "omni_step2_vl_error"):
        if k in prior:
            out[k] = prior[k]
    sub_text = str(step1_shot.get("subtitle_full_text") or "")
    out["subtitle"] = {
        "full_text": sub_text,
        "segments": step1_shot.get("subtitles") or [],
    }
    return out


def _build_multimodal_output(
    step1: Dict[str, Any],
    shots: List[Dict[str, Any]],
    enriched: List[Optional[Dict[str, Any]]],
    *,
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(step1)
    out_shots: List[Dict[str, Any]] = []
    for i, sh in enumerate(shots):
        e = enriched[i] if i < len(enriched) else None
        if e is not None:
            out_shots.append(e)
        else:
            stub = dict(sh)
            stub["omni_step2_status"] = "pending"
            out_shots.append(stub)
    out["shots"] = out_shots
    out["omni_pipeline_meta"] = meta
    return out


def _build_shot_embedding_summary(visual: Dict[str, Any], subtitle_text: str, prompt_language: str = "zh") -> str:
    language = str(prompt_language or "zh").strip().lower()
    desc = visual.get("desc", "") or ""
    brief = visual.get("brief", "") or ""
    if language == "en":
        return (f"Detail: {desc}\n" f"Brief: {brief}\n" f"Subtitles: {subtitle_text or ''}").strip()
    return (f"详细：{desc}\n" f"摘要：{brief}\n" f"字幕：{subtitle_text or ''}").strip()


def _normalize_visual_obj(parsed: Any) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return {"brief": "", "desc": "", "action": "", "emotion": "", "scene": "", "objects": []}
    objs = parsed.get("objects")
    if isinstance(objs, list):
        objects = [str(x).strip() for x in objs if str(x).strip()]
    else:
        objects = []
    return {
        "brief": str(parsed.get("brief", "") or ""),
        "desc": str(parsed.get("desc", "") or ""),
        "action": str(parsed.get("action", "") or ""),
        "emotion": str(parsed.get("emotion", "") or ""),
        "scene": str(parsed.get("scene", "") or ""),
        "objects": objects,
    }


def _parse_visual_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {"brief": "", "desc": "", "action": "", "emotion": "", "scene": "", "objects": []}
    parsed = _try_parse_vision_json(raw)
    if isinstance(parsed, dict):
        return _normalize_visual_obj(parsed)
    return {"brief": text[:200], "desc": text, "action": "", "emotion": "", "scene": "", "objects": []}


def _parse_visual_batch_shots(raw: Optional[str], expected_n: int) -> Optional[List[Dict[str, Any]]]:
    """解析批量视觉 JSON：`shots` 长度须等于 expected_n，且每段含有效 desc/brief。"""
    if expected_n <= 0:
        return []
    text = (raw or "").strip()
    if not text:
        return None
    parsed = _try_parse_vision_json(raw)
    if not isinstance(parsed, dict):
        return None
    arr = parsed.get("shots")
    if not isinstance(arr, list) or len(arr) != expected_n:
        return None
    out: List[Dict[str, Any]] = []
    for item in arr:
        v = _normalize_visual_obj(item if isinstance(item, dict) else {})
        if _visual_missing_core_fields(v):
            return None
        out.append(v)
    return out


def _visual_missing_core_fields(v: Dict[str, Any]) -> bool:
    return not (str(v.get("desc") or "").strip() or str(v.get("brief") or "").strip())


def _omni_project_dir(project_id: str) -> Path:
    return _uploads_dir() / "omni_multimodal" / project_id


def _path_stat_fingerprint(p: Path) -> Dict[str, Any]:
    st = p.stat()
    mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    return {"size": int(st.st_size), "mtime_ns": mtime_ns}


def _fingerprints_equal(stored: Any, current_path: Path) -> bool:
    if not isinstance(stored, dict):
        return False
    try:
        cur = _path_stat_fingerprint(current_path)
    except OSError:
        return False
    try:
        return int(stored.get("size") or -1) == cur["size"] and int(stored.get("mtime_ns") or -1) == cur["mtime_ns"]
    except (TypeError, ValueError):
        return False


def _step1_snapshot_matches_sources(prev: Dict[str, Any], video_abs: Path, srt_abs: Path) -> bool:
    """已有 Step1 JSON 是否与当前磁盘上的视频、字幕一致（未改动则可复用）。"""
    if not isinstance(prev, dict):
        return False
    shots = prev.get("shots")
    if not isinstance(shots, list) or not shots:
        return False
    src = prev.get("step1_sources")
    if not isinstance(src, dict):
        return False
    v = src.get("video")
    s = src.get("subtitle")
    if not isinstance(v, dict) or not isinstance(s, dict):
        return False
    return _fingerprints_equal(v, video_abs) and _fingerprints_equal(s, srt_abs)


def _step1_task_progress_hook(scope: str, project_id: str, task_id: str) -> Callable[[str, float], None]:
    """Step1 在工作线程中更新任务进度（与 vision 在线分析一致，供前端轮询展示）。"""

    def hook(message: str, progress: float) -> None:
        task_progress_store.set_state(
            scope=scope,
            project_id=project_id,
            task_id=task_id,
            status="processing",
            progress=max(5.0, min(34.0, float(progress))),
            message=message,
            phase="step1",
        )

    return hook


def _predictions_to_raw_shots(model: Any, single_frame_predictions: np.ndarray, fps: float) -> List[Shot]:
    """与 extract_scenes 一致：帧级概率 -> scenes -> 秒级 Shot 列表。"""
    if fps <= 0:
        fps = 25.0
    scenes_np = model.predictions_to_scenes(single_frame_predictions)
    shots: List[Shot] = []
    for idx, (start_f, end_f) in enumerate(scenes_np, start=1):
        s_t = float(start_f) / fps
        e_t = float(end_f) / fps
        shots.append(Shot(start=s_t, end=e_t, shot_id=idx, subtitles=[]))
    return shots


def _build_step1_export(
    *,
    video_path: str,
    srt_path: str,
    shots_raw: List[Shot],
    segments_semantic: List[Dict[str, Any]],
) -> Dict[str, Any]:
    mapper = ShotSubtitleMapper()
    shots_raw_data = []
    for shot in shots_raw:
        shots_raw_data.append(
            {
                "shot_id": shot.shot_id,
                "start": round(shot.start, 3),
                "end": round(shot.end, 3),
                "duration": round(shot.end - shot.start, 3),
                "subtitles": list(shot.subtitles or []),
                "subtitle_full_text": mapper.get_full_subtitle_text(shot),
            }
        )
    shots_data = [
        {
            "shot_id": segment["segment_id"],
            "start": segment["start"],
            "end": segment["end"],
            "duration": segment["duration"],
            "is_merged": bool(len(segment.get("shot_ids") or []) > 1),
            "shot_ids": segment.get("shot_ids") or [],
            "source_shots": segment.get("source_shots") or [],
            "subtitles": segment["subtitles"],
            "subtitle_full_text": segment["subtitle_full_text"],
        }
        for segment in segments_semantic
    ]
    total_duration = round(shots_raw[-1].end, 3) if shots_raw else 0.0
    vp = Path(video_path)
    sp = Path(srt_path)
    return {
        "video_path": video_path,
        "srt_path": srt_path,
        "step1_sources": {
            "video": _path_stat_fingerprint(vp),
            "subtitle": _path_stat_fingerprint(sp),
        },
        "total_shots_raw": len(shots_raw_data),
        "total_segments_semantic": len(segments_semantic),
        "shots_raw": shots_raw_data,
        "segments_semantic": segments_semantic,
        "total_shots": len(shots_data),
        "total_duration": total_duration,
        "shots": shots_data,
    }


def _step1_subtitles_and_export_sync(
    video_abs: Path,
    srt_abs: Path,
    shots_raw: List[Shot],
    fps: float,
    *,
    progress_hook: Optional[Callable[[str, float], None]] = None,
) -> Dict[str, Any]:
    """TransNet 已得到 shots_raw 后：解析字幕、语义段、合并、导出（在工作线程运行）。"""
    segments = parse_srt(srt_abs)
    subtitles: List[Subtitle] = []
    for i, seg in enumerate(segments, start=1):
        subtitles.append(
            Subtitle(
                index=i,
                start=float(seg.get("start_time") or 0.0),
                end=float(seg.get("end_time") or 0.0),
                text=str(seg.get("text") or seg.get("subtitle") or "").strip(),
            )
        )
    logger.info(
        "[omni-pipeline] Step1 字幕解析完成：条目 %s/%s（有效字幕段）",
        len(subtitles),
        len(segments),
    )
    if progress_hook:
        progress_hook(
            f"Step1: 字幕解析 {len(subtitles)}/{len(segments)} 条，开始对齐到镜头…",
            29.0,
        )
    mapper = ShotSubtitleMapper()
    logger.info(
        "[omni-pipeline] Step1 字幕对齐到镜头：原始镜头 %s 个",
        len(shots_raw),
    )
    mapped = mapper.map_subtitles_to_shots(shots_raw, subtitles)
    segments_semantic = mapper.build_semantic_segments(mapped)
    logger.info(
        "[omni-pipeline] Step1 语义段构建完成：%s/%s（相对原始镜头）",
        len(segments_semantic),
        len(shots_raw),
    )
    if progress_hook:
        progress_hook(
            f"Step1: 语义段构建 {len(segments_semantic)}/{len(shots_raw)}（相对原始镜头）",
            30.5,
        )
    before_merge = len(segments_semantic)
    segments_semantic = mapper.merge_short_segments_bidirectional(segments_semantic)
    logger.info(
        "[omni-pipeline] Step1 短段双向合并：%s → %s 个语义段",
        before_merge,
        len(segments_semantic),
    )
    if progress_hook:
        progress_hook(
            f"Step1: 短段合并 {before_merge} → {len(segments_semantic)} 个语义段",
            32.5,
        )
    out = _build_step1_export(
        video_path=str(video_abs),
        srt_path=str(srt_abs),
        shots_raw=shots_raw,
        segments_semantic=segments_semantic,
    )
    if progress_hook:
        nshots = len(out.get("shots") or [])
        progress_hook(f"Step1: 分割完成，共 {nshots} 个语义段", 34.0)
    return out


async def _step1_run_async(
    *,
    scope: str,
    project_id: str,
    task_id: str,
    video_abs: Path,
    srt_abs: Path,
    progress_hook: Optional[Callable[[str, float], None]] = None,
) -> Dict[str, Any]:
    """
    Step1：镜头分割与 extract_scenes 一致（分块 predict_video + 重叠），模型与镜头提取服务共用
    extract_scene_service._get_model()（CUDA 可用时走 TransNetV2Torch GPU）；字幕语义段仍在工作线程处理。
    """
    logger.info(
        "[omni-pipeline] Step1 开始镜头检测 video=%s srt=%s",
        video_abs,
        srt_abs,
    )
    task_progress_store.set_state(
        scope=scope,
        project_id=project_id,
        task_id=task_id,
        status="processing",
        progress=5.0,
        message="Step1: 正在加载镜头模型…",
        phase="step1",
    )
    if progress_hook:
        progress_hook("Step1: 正在加载镜头模型…", 5.0)

    model = extract_scene_service._get_model()
    loop = asyncio.get_running_loop()
    pred, fps, _total_frames = await transnet_chunked_single_frame_predictions(
        video_abs,
        model,
        loop=loop,
        scope=scope,
        project_id=project_id,
        task_id=task_id,
        progress_lo=6.0,
        progress_hi=27.0,
        message_prefix="Step1: 镜头分割",
        phase="step1",
    )
    if task_cancel_store.is_cancelled(scope, project_id, task_id):
        raise asyncio.CancelledError()
    shots_raw = _predictions_to_raw_shots(model, pred, fps)
    if not shots_raw:
        raise ValueError("未能检测到任何镜头边界")
    logger.info(
        "[omni-pipeline] Step1 TransNet 完成：原始镜头 %s 个，fps=%.3f",
        len(shots_raw),
        float(fps or 0.0),
    )
    if progress_hook:
        progress_hook(
            f"Step1: TransNet 完成，原始镜头 {len(shots_raw)} 个（fps={float(fps or 0.0):.2f}）",
            28.0,
        )

    return await asyncio.to_thread(
        _step1_subtitles_and_export_sync,
        video_abs,
        srt_abs,
        shots_raw,
        fps,
        progress_hook=progress_hook,
    )


async def _ensure_step1_shot_segmentation(
    *,
    project_id: str,
    task_id: str,
    scope: str,
    video_abs: Path,
    subtitle_abs: Path,
    work: Path,
    mma: str,
) -> Dict[str, Any]:
    """
    Omni Step1：镜头分割（TransNet + 字幕语义段）。一旦分割完成则永久复用 shots_step1.json 缓存，
    任何情况不重新分割。
    """
    step1_path = work / "shots_step1.json"
    step1: Optional[Dict[str, Any]] = None

    if step1_path.exists():
        prev_step1: Optional[Dict[str, Any]] = None
        try:
            prev_step1 = json.loads(step1_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(
                "[omni-pipeline] Step1 读取历史 shots_step1.json 失败 project_id=%s err=%s",
                project_id,
                e,
            )
        if isinstance(prev_step1, dict):
            shots = prev_step1.get("shots")
            if isinstance(shots, list) and shots:
                step1 = prev_step1
                nshots = len(shots)
                logger.info(
                    "[omni-pipeline] Step1 复用已有镜头分割缓存 project_id=%s task_id=%s 语义段=%s（永不重跑）",
                    project_id,
                    task_id,
                    nshots,
                )
                task_progress_store.set_state(
                    scope=scope,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=28,
                    message=f"Step1: 已复用缓存分割（{nshots} 段，永不重跑）",
                    phase="step1",
                )
        if step1 is None:
            logger.warning(
                "[omni-pipeline] Step1 缓存文件无效，将重新分割 project_id=%s task_id=%s",
                project_id,
                task_id,
            )

    if step1 is None:
        step1 = await _step1_run_async(
            scope=scope,
            project_id=project_id,
            task_id=task_id,
            video_abs=video_abs,
            srt_abs=subtitle_abs,
            progress_hook=_step1_task_progress_hook(scope, project_id, task_id),
        )
        if task_cancel_store.is_cancelled(scope, project_id, task_id):
            raise asyncio.CancelledError()
        step1_path.write_text(json.dumps(step1, ensure_ascii=False, indent=2), encoding="utf-8")
        step1_web = _to_web_path(step1_path)
        projects_store.update_project(
            project_id,
            {
                "omni_step1_json_path": step1_web,
                "omni_pipeline_updated_at": datetime.now().isoformat(),
            },
        )
    else:
        step1_web = _to_web_path(step1_path)
        cur = projects_store.get_project(project_id)
        cur_web = str(getattr(cur, "omni_step1_json_path", "") or "") if cur else ""
        if cur_web != step1_web:
            projects_store.update_project(
                project_id,
                {
                    "omni_step1_json_path": step1_web,
                    "omni_pipeline_updated_at": datetime.now().isoformat(),
                },
            )

    return step1


class OmniMultimodalPipelineService:
    SCOPE = _SCOPE

    async def submit_pipeline(
        self,
        project_id: str,
        force: bool = False,
        task_id: Optional[str] = None,
        multimodal_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        if str(getattr(p, "project_type", "") or "").strip().lower() != "omni":
            raise ValueError("仅 omni 类型项目可运行此管线")
        if not p.video_path:
            raise ValueError("请先上传视频")
        sp = getattr(p, "subtitle_path", None)
        if not sp:
            raise ValueError("请先提取或上传字幕（Omni 管线依赖字幕）")
        abs_srt = _resolve_path(str(sp))
        if not abs_srt.exists() or abs_srt.stat().st_size <= 0:
            raise ValueError("字幕文件不存在或为空")

        mma = _normalize_multimodal_action(multimodal_action)
        # 全部重做多模态时必须抢占「进行中」任务，否则会继续轮询旧 task_id，表现为仍走 auto/continue。
        effective_force = bool(force) or (mma == "restart")

        running = task_progress_store.get_latest_running(self.SCOPE, project_id)
        if running:
            r_status = str(running.get("status") or "").strip().lower()
            r_task_id = running.get("task_id")
            if not effective_force:
                if r_status in ("pending", "processing", "running"):
                    return {"task_id": r_task_id, "status": r_status, "message": "已有任务在运行"}
            else:
                if r_task_id and r_status in ("pending", "processing", "running"):
                    try:
                        await task_cancel_store.cancel(self.SCOPE, project_id, str(r_task_id))
                    except Exception:
                        pass
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=str(r_task_id),
                        status="cancelled",
                        message="已取消旧任务，准备重新执行",
                    )

        if not task_id:
            task_id = f"omni_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        task_progress_store.set_state(
            scope=self.SCOPE,
            project_id=project_id,
            task_id=task_id,
            status="pending",
            progress=0,
            message="准备 Omni 管线...",
            phase="preparing",
        )

        async def _run() -> None:
            try:
                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()
                current = projects_store.get_project(project_id)
                if not current or not current.video_path:
                    raise ValueError("项目或视频不存在")
                video_abs = _resolve_path(str(current.video_path))
                if not video_abs.exists():
                    raise FileNotFoundError(f"视频文件不存在: {current.video_path}")
                subtitle_abs = _resolve_path(str(current.subtitle_path or ""))
                if not subtitle_abs.exists():
                    raise FileNotFoundError("字幕文件不存在")

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=5,
                    message="Step1: 镜头分割与字幕对齐（进度将随 TransNet/字幕处理实时更新）…",
                    phase="step1",
                )

                work = _omni_project_dir(project_id)
                work.mkdir(parents=True, exist_ok=True)

                step1 = await _ensure_step1_shot_segmentation(
                    project_id=project_id,
                    task_id=task_id,
                    scope=self.SCOPE,
                    video_abs=video_abs,
                    subtitle_abs=subtitle_abs,
                    work=work,
                    mma=mma,
                )

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=35,
                    message="Step1 完成，开始 Step2 多模态与向量化...",
                    phase="step2",
                )

                active_vl = resolve_video_model_for_online_vision()
                if not active_vl or active_vl.provider not in _ONLINE_VL_PROVIDERS:
                    raise ValueError(
                        "Omni Step2 需要在线视觉模型：请在「视频理解模型」中选择 yunwu / 302ai / qwen / doubao / custom_openai_vision 之一并配置密钥"
                    )
                try:
                    assert_local_bge_model_available()
                except (FileNotFoundError, RuntimeError) as e:
                    raise ValueError(str(e)) from e

                try:
                    infer_wall_sec = 40
                except Exception:
                    infer_wall_sec = 30
                if infer_wall_sec < 1.0:
                    infer_wall_sec = 30
                effective_http_timeout = max(int(active_vl.timeout or 0), int(infer_wall_sec + 0.999))

                shots: List[Dict[str, Any]] = list(step1.get("shots") or [])
                if not shots:
                    raise ValueError("Step1 未产生镜头列表")

                frames_dir = work / "frames"
                frames_dir.mkdir(parents=True, exist_ok=True)
                out_path = work / "shots_multimodal.json"

                existing_payload: Optional[Dict[str, Any]] = None
                if mma in ("auto", "continue") and out_path.exists():
                    existing_payload = _try_load_existing_multimodal_json(out_path)

                enriched: List[Optional[Dict[str, Any]]] = [None] * len(shots)
                if mma in ("auto", "continue") and existing_payload is not None:
                    pri = _prior_multimodal_map(existing_payload)
                    for i, sh in enumerate(shots):
                        prev = pri.get(_omni_shot_identity(sh))
                        if prev is not None and _shot_step2_complete(prev):
                            enriched[i] = _merge_shot_with_prior(sh, prev)

                pending_idx = [i for i in range(len(shots)) if enriched[i] is None or not _shot_step2_complete(enriched[i])]
                done_count = len(shots) - len(pending_idx)

                lock = asyncio.Lock()
                snapshot_io_lock = asyncio.Lock()
                vl_policy_blocked_count = 0
                vl_call_failed_count = 0

                def _meta_base(*, partial: bool) -> Dict[str, Any]:
                    meta: Dict[str, Any] = {
                        "vl_provider": active_vl.provider,
                        "vl_model": active_vl.model_name,
                        "embedding_model": LOCAL_BGE_MODEL_DISPLAY_NAME,
                        "completed_at": datetime.now().isoformat(),
                    }
                    if vl_policy_blocked_count > 0:
                        meta["step2_vl_policy_blocked_shots"] = int(vl_policy_blocked_count)
                    if vl_call_failed_count > 0:
                        meta["step2_vl_call_failed_shots"] = int(vl_call_failed_count)
                    if partial:
                        meta["partial"] = True
                    return meta

                async def _persist_snapshot(*, partial: bool) -> None:
                    async with snapshot_io_lock:
                        async with lock:
                            payload = _build_multimodal_output(
                                step1,
                                shots,
                                enriched,
                                meta=_meta_base(partial=partial),
                            )
                        await asyncio.to_thread(write_encrypted_multimodal_json, out_path, payload)
                        out_web = _to_web_path(out_path)
                        projects_store.update_project(
                            project_id,
                            {
                                "omni_multimodal_json_path": out_web,
                                "omni_pipeline_updated_at": datetime.now().isoformat(),
                            },
                        )

                if not pending_idx:
                    await _persist_snapshot(partial=False)
                    if existing_payload is not None and done_count == len(shots):
                        msg_done = "Omni 管线完成：已复用历史多模态结果，无需再次调用模型"
                    else:
                        msg_done = "Omni 管线完成（镜头拆分 + 多模态向量化）"
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=task_id,
                        status="completed",
                        progress=100,
                        message=msg_done,
                        phase="done",
                    )
                    return

                has_historical = existing_payload is not None and done_count > 0 and mma in ("auto", "continue")
                if has_historical:
                    if mma == "continue":
                        prog_msg = f"已复用 {done_count} 段历史结果，继续补全剩余 {len(pending_idx)} 段..."
                    else:
                        prog_msg = f"检测到历史多模态结果，自动继续补全剩余 {len(pending_idx)} 段..."
                else:
                    prog_msg = f"Step2: 待处理 {len(pending_idx)}/{len(shots)} 个语义段..."
                pct0 = 35.0 + 60.0 * (done_count / max(1, len(shots)))
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=min(94.0, pct0),
                    message=prog_msg,
                    phase="step2",
                )
                last_reported_progress = float(min(94.0, pct0))

                await _persist_snapshot(partial=True)

                runner = _OnlineVisionRunner(
                    provider=str(active_vl.provider),
                    api_key=str(active_vl.api_key or ""),
                    base_url=str(active_vl.base_url or ""),
                    model_name=str(active_vl.model_name or ""),
                    timeout=effective_http_timeout,
                )
                # 与 vision_frame_analysis_service.analyze_scenes_online 默认参数一致：
                # max_concurrency=128 -> extract_concurrency=8, api_concurrency=64
                max_concurrency = 64
                concurrency_cap = max(1, int(max_concurrency or 1))
                extract_concurrency = min(8, concurrency_cap)
                api_concurrency = min(64, concurrency_cap)
                logger.info(
                    "[omni-pipeline] Step2 视觉模型调用入口 project_id=%s task_id=%s runner_id=%s provider=%s model=%s shots=%s pending=%s mma=%s extract_concurrency=%s api_concurrency=%s",
                    project_id,
                    task_id,
                    id(runner),
                    active_vl.provider,
                    active_vl.model_name,
                    len(shots),
                    len(pending_idx),
                    mma,
                    extract_concurrency,
                    api_concurrency,
                )
                infer_sem = asyncio.Semaphore(api_concurrency)
                infer_start_lock = asyncio.Lock()
                infer_last_start_mono = 0.0

                async def _pace_online_infer_start() -> None:
                    nonlocal infer_last_start_mono
                    async with infer_start_lock:
                        now = time.monotonic()
                        gap = _ONLINE_VISION_INFER_CONCURRENT_INTERVAL_SEC - (now - infer_last_start_mono)
                        if gap > 0:
                            await asyncio.sleep(gap)
                        infer_last_start_mono = time.monotonic()

                vl_prompt_language = "zh"

                async def _embed_one(text: str) -> List[float]:
                    return await encode_text_async(text)

                loop = asyncio.get_running_loop()
                extract_executor = ThreadPoolExecutor(
                    max_workers=extract_concurrency, thread_name_prefix="omni_step2_extract"
                )

                async def _extract_shot_for_step2(
                    idx: int, shot: Dict[str, Any]
                ) -> Tuple[int, Dict[str, Any], List[str], List[Image.Image]]:
                    if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                        raise asyncio.CancelledError()
                    frame_paths = await loop.run_in_executor(
                        extract_executor,
                        extract_middle_frame,
                        str(video_abs),
                        shot,
                        str(frames_dir),
                    )
                    images: List[Image.Image] = []
                    for fp in frame_paths:
                        images.append(Image.open(fp).convert("RGB"))
                    return (idx, shot, frame_paths, images)

                extract_total = len(pending_idx)
                extract_prog_lock = asyncio.Lock()
                extract_finished = 0

                async def _extract_shot_with_frame_progress(
                    idx: int, shot: Dict[str, Any]
                ) -> Tuple[int, Dict[str, Any], List[str], List[Image.Image]]:
                    nonlocal extract_finished, last_reported_progress
                    bundle = await _extract_shot_for_step2(idx, shot)
                    async with extract_prog_lock:
                        extract_finished += 1
                        k = extract_finished
                        span_to_fill = max(0.0, min(94.0, 95.0) - pct0)
                        bump = span_to_fill * 0.18 * (k / max(1, extract_total))
                        last_reported_progress = max(
                            last_reported_progress,
                            min(94.0, pct0 + bump),
                        )
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=last_reported_progress,
                            message=(
                                f"Step2: 正在抽帧 {k}/{extract_total}（语义段），随后视觉理解…"
                            ),
                            phase="step2",
                        )
                    return bundle

                try:
                    logger.info(
                        "[omni-pipeline] Step2 阶段一抽帧开始 project_id=%s task_id=%s pending=%s extract_concurrency=%s",
                        project_id,
                        task_id,
                        len(pending_idx),
                        extract_concurrency,
                    )
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=task_id,
                        status="processing",
                        progress=last_reported_progress,
                        message=f"Step2: 开始抽帧（共 {extract_total} 段）…",
                        phase="step2",
                    )
                    bundles = await asyncio.gather(
                        *(_extract_shot_with_frame_progress(i, shots[i]) for i in pending_idx)
                    )
                finally:
                    try:
                        extract_executor.shutdown(wait=True, cancel_futures=True)
                    except Exception:
                        try:
                            extract_executor.shutdown(wait=True)
                        except Exception:
                            pass

                span_to_fill_vl = max(0.0, min(94.0, 95.0) - pct0)
                vl_lo = float(last_reported_progress)
                vl_hi = min(94.0, vl_lo + span_to_fill_vl * 0.55)
                vl_total = max(1, len(bundles))
                vl_done_lock = asyncio.Lock()
                vl_done = 0

                async def _bump_step2_vl_done_for_outcome() -> None:
                    nonlocal vl_done, last_reported_progress
                    async with vl_done_lock:
                        vl_done += 1
                        k = vl_done
                        frac = k / float(vl_total)
                        pr = vl_lo + (vl_hi - vl_lo) * frac
                        last_reported_progress = max(last_reported_progress, pr)
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=last_reported_progress,
                            message=f"Step2: 在线视觉理解 {k}/{vl_total}（调用模型）…",
                            phase="step2",
                        )

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=last_reported_progress,
                    message=f"Step2: 开始在线视觉理解（共 {vl_total} 段）…",
                    phase="step2",
                )

                async def _finalize_step2_success(
                    idx: int,
                    shot: Dict[str, Any],
                    frame_paths: List[str],
                    visual: Dict[str, Any],
                    *,
                    progress_note: str = "",
                ) -> None:
                    nonlocal done_count, last_reported_progress
                    sub_text = str(shot.get("subtitle_full_text") or "")
                    summary = _build_shot_embedding_summary(visual, sub_text, vl_prompt_language)
                    embedding = await _embed_one(summary)
                    item = dict(shot)
                    item["frames"] = list(frame_paths)
                    item["subtitle"] = {
                        "full_text": sub_text,
                        "segments": shot.get("subtitles") or [],
                    }
                    item["visual"] = visual
                    item["summary"] = summary
                    item["embedding"] = embedding
                    async with lock:
                        enriched[idx] = item
                        done_count += 1
                        vision_pct = min(95.0, 35.0 + 60.0 * (done_count / max(1, len(shots))))
                        last_reported_progress = max(last_reported_progress, vision_pct)
                        msg = f"Step2: 多模态处理 {done_count}/{len(shots)}"
                        if progress_note:
                            msg += progress_note
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=last_reported_progress,
                            message=msg,
                            phase="step2",
                        )
                    await _persist_snapshot(partial=True)

                async def _finalize_step2_policy_blocked(
                    idx: int,
                    shot: Dict[str, Any],
                    frame_paths: List[str],
                    last_fail: BaseException,
                ) -> None:
                    nonlocal done_count, vl_policy_blocked_count, last_reported_progress
                    sub_text = str(shot.get("subtitle_full_text") or "")
                    visual = _parse_visual_json("")
                    summary = _build_shot_embedding_summary(visual, sub_text, vl_prompt_language)
                    summary = (summary + "\n[omni:vl_policy_blocked]").strip()[:12000]
                    try:
                        embedding = await _embed_one(summary)
                    except Exception as emb_exc:
                        logger.warning(
                            "[omni-pipeline] Step2 策略降级后向量化失败，尝试中性占位文本: project_id=%s shot_idx=%s err=%s",
                            project_id,
                            idx,
                            emb_exc,
                        )
                        embedding = await _embed_one("omni_shot_semantic_placeholder")
                    item = dict(shot)
                    item["frames"] = list(frame_paths)
                    item["subtitle"] = {
                        "full_text": sub_text,
                        "segments": shot.get("subtitles") or [],
                    }
                    item["visual"] = visual
                    item["summary"] = summary
                    item["embedding"] = embedding
                    item["omni_step2_status"] = "vl_policy_blocked"
                    item["omni_step2_vl_error"] = str(last_fail)[:2000]
                    async with lock:
                        enriched[idx] = item
                        vl_policy_blocked_count += 1
                        done_count += 1
                        vision_pct = min(95.0, 35.0 + 60.0 * (done_count / max(1, len(shots))))
                        last_reported_progress = max(last_reported_progress, vision_pct)
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=last_reported_progress,
                            message=f"Step2: 多模态处理 {done_count}/{len(shots)}（含策略降级）",
                            phase="step2",
                        )
                    await _persist_snapshot(partial=True)

                async def _finalize_step2_vl_call_failed(
                    idx: int,
                    shot: Dict[str, Any],
                    frame_paths: List[str],
                    last_fail: BaseException,
                    *,
                    was_timeout: bool,
                ) -> None:
                    nonlocal done_count, vl_call_failed_count, last_reported_progress
                    sub_text = str(shot.get("subtitle_full_text") or "")
                    visual = _parse_visual_json("")
                    summary = _build_shot_embedding_summary(visual, sub_text, vl_prompt_language)
                    tag = "[omni:vl_timeout]" if was_timeout else "[omni:vl_call_failed]"
                    summary = (summary + "\n" + tag).strip()[:12000]
                    try:
                        embedding = await _embed_one(summary)
                    except Exception as emb_exc:
                        logger.warning(
                            "[omni-pipeline] Step2 VL 失败后向量化失败，尝试中性占位文本: project_id=%s shot_idx=%s err=%s",
                            project_id,
                            idx,
                            emb_exc,
                        )
                        embedding = await _embed_one("omni_shot_semantic_placeholder")
                    item = dict(shot)
                    item["frames"] = list(frame_paths)
                    item["subtitle"] = {
                        "full_text": sub_text,
                        "segments": shot.get("subtitles") or [],
                    }
                    item["visual"] = visual
                    item["summary"] = summary
                    item["embedding"] = embedding
                    item["omni_step2_status"] = "vl_error"
                    item["omni_step2_vl_error"] = str(last_fail)[:2000]
                    async with lock:
                        enriched[idx] = item
                        vl_call_failed_count += 1
                        done_count += 1
                        vision_pct = min(95.0, 35.0 + 60.0 * (done_count / max(1, len(shots))))
                        last_reported_progress = max(last_reported_progress, vision_pct)
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=last_reported_progress,
                            message=f"Step2: 多模态处理 {done_count}/{len(shots)}（含 VL 失败降级）",
                            phase="step2",
                        )
                    await _persist_snapshot(partial=True)

                async def _run_step2_infer_multi_retries(
                    images: List[Image.Image],
                    prompt: str,
                    timeout_sec: float,
                    *,
                    log_kind: str,
                    idxs: List[int],
                ) -> Tuple[Optional[str], Optional[BaseException], bool]:
                    retry_delays: Tuple[float, ...] = _ONLINE_VISION_INFER_RETRY_DELAYS_SEC
                    max_attempts = 1 + len(retry_delays)
                    raw: Optional[str] = None
                    last_fail: Optional[BaseException] = None
                    last_was_timeout = False
                    tgt: int | List[int] = idxs[0] if len(idxs) == 1 else idxs
                    for attempt in range(max_attempts):
                        if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                            raise asyncio.CancelledError()
                        try:
                            await _pace_online_infer_start()
                            async with infer_sem:
                                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                    raise asyncio.CancelledError()
                                raw, _stats = await asyncio.wait_for(
                                    runner.infer_multi(images, prompt),
                                    timeout=timeout_sec,
                                )
                            last_fail = None
                            break
                        except asyncio.TimeoutError as te:
                            last_fail = te
                            last_was_timeout = True
                            if attempt < max_attempts - 1:
                                logger.warning(
                                    "[omni-pipeline] Step2 %s在线视觉超时：project_id=%s task_id=%s target=%s %.1fs 后重试 (%s/%s)，超时阈值=%.1fs",
                                    log_kind,
                                    project_id,
                                    task_id,
                                    tgt,
                                    retry_delays[attempt],
                                    attempt + 1,
                                    max_attempts - 1,
                                    timeout_sec,
                                )
                                await asyncio.sleep(retry_delays[attempt])
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            last_fail = e
                            last_was_timeout = False
                            if attempt < max_attempts - 1:
                                logger.warning(
                                    "[omni-pipeline] Step2 %s在线视觉失败：project_id=%s task_id=%s target=%s %.1fs 后重试 (%s/%s)，错误=%s",
                                    log_kind,
                                    project_id,
                                    task_id,
                                    tgt,
                                    retry_delays[attempt],
                                    attempt + 1,
                                    max_attempts - 1,
                                    e,
                                )
                                await asyncio.sleep(retry_delays[attempt])
                    return raw, last_fail, last_was_timeout

                async def _run_step2_vl_for_bundle(
                    bundle: Tuple[int, Dict[str, Any], List[str], List[Image.Image]],
                    *,
                    allow_split_fallback: bool = True,
                ) -> _Step2VlOutcome:
                    """每镜头一次 infer_multi；仅在线视觉，不向量化。与 analyze_scenes_online 单镜头路径一致。"""
                    idx, shot, frame_paths, imgs = bundle
                    optimized_imgs: List[Image.Image] = []
                    try:
                        optimized_imgs = [optimize_image_for_online_vision(im, max_edge=1024) for im in imgs]
                        sub_text = str(shot.get("subtitle_full_text") or "")
                        prompt = load_frame_analysis_prompt(vl_prompt_language, sub_text)
                        chunk_timeout = float(infer_wall_sec)
                        n_retry_rounds = len(_ONLINE_VISION_INFER_RETRY_DELAYS_SEC)

                        logger.info(
                            "[omni-pipeline] Step2 单镜头 VL 请求开始 project_id=%s task_id=%s runner_id=%s shot_idx=%s n_images=%s timeout=%.1fs",
                            project_id,
                            task_id,
                            id(runner),
                            idx,
                            len(optimized_imgs),
                            chunk_timeout,
                        )

                        raw, last_fail, last_was_timeout = await _run_step2_infer_multi_retries(
                            optimized_imgs,
                            prompt,
                            chunk_timeout,
                            log_kind="单镜头",
                            idxs=[idx],
                        )

                        if raw is None:
                            if last_fail is not None and (not last_was_timeout) and _is_upstream_vision_policy_block(last_fail):
                                logger.warning(
                                    "[omni-pipeline] Step2 上游视觉内容策略拦截，改为仅字幕/占位语义向量: project_id=%s task_id=%s shot_idx=%s err=%s",
                                    project_id,
                                    task_id,
                                    idx,
                                    last_fail,
                                )
                                await _bump_step2_vl_done_for_outcome()
                                return _Step2VlOutcome(
                                    idx=idx,
                                    shot=shot,
                                    frame_paths=list(frame_paths),
                                    kind="policy_blocked",
                                    visual=_parse_visual_json(""),
                                    policy_error=last_fail,
                                )
                            if last_was_timeout:
                                msg = f"单次模型调用超过{int(chunk_timeout)}秒未返回（已重试{n_retry_rounds}次）"
                                logger.warning(
                                    "[omni-pipeline] Step2 单镜头在线视觉超时，跳过该段并降级: project_id=%s task_id=%s shot_idx=%s %s",
                                    project_id,
                                    task_id,
                                    idx,
                                    msg,
                                )
                                await _bump_step2_vl_done_for_outcome()
                                fail_exc = last_fail if isinstance(last_fail, BaseException) else TimeoutError(msg)
                                return _Step2VlOutcome(
                                    idx=idx,
                                    shot=shot,
                                    frame_paths=list(frame_paths),
                                    kind="vl_failed",
                                    visual=_parse_visual_json(""),
                                    vl_fail=fail_exc,
                                    vl_fail_was_timeout=True,
                                )
                            if last_fail is not None:
                                logger.warning(
                                    "[omni-pipeline] Step2 单镜头在线视觉失败（已用尽重试），跳过该段并降级: project_id=%s task_id=%s shot_idx=%s err=%s",
                                    project_id,
                                    task_id,
                                    idx,
                                    last_fail,
                                )
                                await _bump_step2_vl_done_for_outcome()
                                return _Step2VlOutcome(
                                    idx=idx,
                                    shot=shot,
                                    frame_paths=list(frame_paths),
                                    kind="vl_failed",
                                    visual=_parse_visual_json(""),
                                    vl_fail=last_fail,
                                    vl_fail_was_timeout=False,
                                )
                            logger.warning(
                                "[omni-pipeline] Step2 单镜头在线视觉无返回且无异常，跳过该段并降级: project_id=%s task_id=%s shot_idx=%s",
                                project_id,
                                task_id,
                                idx,
                            )
                            await _bump_step2_vl_done_for_outcome()
                            return _Step2VlOutcome(
                                idx=idx,
                                shot=shot,
                                frame_paths=list(frame_paths),
                                kind="vl_failed",
                                visual=_parse_visual_json(""),
                                vl_fail=RuntimeError("在线视觉调用未返回结果且无异常信息"),
                                vl_fail_was_timeout=False,
                            )

                        visual = _parse_visual_json(raw)
                        if _visual_missing_core_fields(visual):
                            if allow_split_fallback:
                                return await _run_step2_vl_for_bundle(bundle, allow_split_fallback=False)
                            await _bump_step2_vl_done_for_outcome()
                            return _Step2VlOutcome(
                                idx=idx,
                                shot=shot,
                                frame_paths=list(frame_paths),
                                kind="empty_visual",
                                visual=_parse_visual_json(""),
                            )

                        logger.info(
                            "[omni-pipeline] Step2 单镜头 VL 请求结束 project_id=%s task_id=%s runner_id=%s shot_idx=%s",
                            project_id,
                            task_id,
                            id(runner),
                            idx,
                        )
                        await _bump_step2_vl_done_for_outcome()
                        return _Step2VlOutcome(
                            idx=idx,
                            shot=shot,
                            frame_paths=list(frame_paths),
                            kind="success",
                            visual=visual,
                        )
                    finally:
                        for oim in optimized_imgs:
                            try:
                                oim.close()
                            except Exception:
                                pass
                        _close_shot_pil_images(imgs)

                async def _fallback_chunk_per_shot(
                    batch: List[Tuple[int, Dict[str, Any], List[str], List[Image.Image]]],
                ) -> List[_Step2VlOutcome]:
                    parts = await asyncio.gather(
                        *(_run_step2_vl_for_bundle(b) for b in batch),
                        return_exceptions=True,
                    )
                    for res in parts:
                        if isinstance(res, asyncio.CancelledError):
                            raise res
                    for res in parts:
                        if isinstance(res, BaseException):
                            raise res
                    return list(parts)

                async def _run_step2_vl_batch(
                    batch: List[Tuple[int, Dict[str, Any], List[str], List[Image.Image]]],
                ) -> List[_Step2VlOutcome]:
                    """每批最多 OMNI_STEP2_VL_BATCH_SIZE 段一次 infer_multi；失败或 JSON 不合法时回退为逐段 _run_step2_vl_for_bundle。"""
                    batch_n = len(batch)
                    idxs = [b[0] for b in batch]
                    optimized_imgs: List[Image.Image] = []
                    used_fallback = False
                    try:
                        imgs_flat: List[Image.Image] = []
                        for _idx, _shot, _fp, imgs in batch:
                            imgs_flat.extend(imgs)
                        optimized_imgs = [optimize_image_for_online_vision(im, max_edge=1024) for im in imgs_flat]
                        subtitle_texts = [str(b[1].get("subtitle_full_text") or "") for b in batch]
                        prompt = load_frame_analysis_batch_prompt(vl_prompt_language, subtitle_texts)
                        chunk_timeout = float(infer_wall_sec)

                        logger.info(
                            "[omni-pipeline] Step2 批量 VL 请求开始 project_id=%s task_id=%s runner_id=%s n_shots=%s n_images=%s shot_idx=%s timeout=%.1fs",
                            project_id,
                            task_id,
                            id(runner),
                            batch_n,
                            len(optimized_imgs),
                            idxs,
                            chunk_timeout,
                        )

                        raw, _lf0, _wt0 = await _run_step2_infer_multi_retries(
                            optimized_imgs,
                            prompt,
                            chunk_timeout,
                            log_kind="批量镜头",
                            idxs=idxs,
                        )
                        visuals = _parse_visual_batch_shots(raw, batch_n)
                        if visuals is None and raw:
                            raw2, _lf1, _wt1 = await _run_step2_infer_multi_retries(
                                optimized_imgs,
                                prompt,
                                chunk_timeout,
                                log_kind="批量镜头(重试)",
                                idxs=idxs,
                            )
                            visuals = _parse_visual_batch_shots(raw2, batch_n)

                        if visuals is not None:
                            for _ in range(batch_n):
                                await _bump_step2_vl_done_for_outcome()
                            logger.info(
                                "[omni-pipeline] Step2 批量 VL 请求结束 project_id=%s task_id=%s runner_id=%s shot_idx=%s",
                                project_id,
                                task_id,
                                id(runner),
                                idxs,
                            )
                            return [
                                _Step2VlOutcome(
                                    idx=b[0],
                                    shot=b[1],
                                    frame_paths=list(b[2]),
                                    kind="success",
                                    visual=visuals[i],
                                )
                                for i, b in enumerate(batch)
                            ]

                        logger.warning(
                            "[omni-pipeline] Step2 批量 VL 解析失败或调用失败，回退逐段: project_id=%s task_id=%s shot_idx=%s",
                            project_id,
                            task_id,
                            idxs,
                        )
                        used_fallback = True
                        return await _fallback_chunk_per_shot(batch)
                    finally:
                        for oim in optimized_imgs:
                            try:
                                oim.close()
                            except Exception:
                                pass
                        if not used_fallback:
                            for b in batch:
                                _close_shot_pil_images(b[3])

                _bge_cap = _omni_bge_embed_encode_concurrency_cap()
                _bge_embed_sem = asyncio.Semaphore(_bge_cap) if _bge_cap is not None else None

                async def _commit_step2_after_vl(out: _Step2VlOutcome) -> None:
                    if _bge_embed_sem is not None:
                        async with _bge_embed_sem:
                            await _commit_step2_after_vl_inner(out)
                    else:
                        await _commit_step2_after_vl_inner(out)

                async def _commit_step2_after_vl_inner(out: _Step2VlOutcome) -> None:
                    if out.kind == "policy_blocked":
                        await _finalize_step2_policy_blocked(
                            out.idx,
                            out.shot,
                            out.frame_paths,
                            out.policy_error or RuntimeError("vl_policy_blocked"),
                        )
                    elif out.kind == "vl_failed":
                        await _finalize_step2_vl_call_failed(
                            out.idx,
                            out.shot,
                            out.frame_paths,
                            out.vl_fail or RuntimeError("vl_failed"),
                            was_timeout=out.vl_fail_was_timeout,
                        )
                    else:
                        await _finalize_step2_success(out.idx, out.shot, out.frame_paths, out.visual)

                try:
                    vl_batches = [
                        bundles[i : i + OMNI_STEP2_VL_BATCH_SIZE]
                        for i in range(0, len(bundles), OMNI_STEP2_VL_BATCH_SIZE)
                    ]
                    logger.info(
                        "[omni-pipeline] Step2 阶段二-A VL gather 开始 project_id=%s task_id=%s runner_id=%s n_shots=%s n_batches=%s batch_size=%s api_concurrency=%s",
                        project_id,
                        task_id,
                        id(runner),
                        len(bundles),
                        len(vl_batches),
                        OMNI_STEP2_VL_BATCH_SIZE,
                        api_concurrency,
                    )
                    # 必须用 return_exceptions=True：默认 gather 在首个子任务抛错时会立刻返回，
                    # 但 finally 仍会关闭 runner，其余仍在跑的推理会打到已关闭的 httpx 客户端，
                    # 从而刷屏「Cannot send a request, as the client has been closed」。
                    vl_nested = await asyncio.gather(
                        *(_run_step2_vl_batch(b) for b in vl_batches),
                        return_exceptions=True,
                    )
                    vl_results: List[_Step2VlOutcome] = []
                    for res in vl_nested:
                        if isinstance(res, asyncio.CancelledError):
                            raise res
                        if isinstance(res, BaseException):
                            raise res
                        vl_results.extend(res)
                    logger.info(
                        "[omni-pipeline] Step2 阶段二-A VL gather 正常结束 project_id=%s task_id=%s runner_id=%s n_outcomes=%s",
                        project_id,
                        task_id,
                        id(runner),
                        len(vl_results),
                    )
                finally:
                    logger.info(
                        "[omni-pipeline] Step2 即将关闭 VL runner project_id=%s task_id=%s runner_id=%s",
                        project_id,
                        task_id,
                        id(runner),
                    )
                    await runner.close()
                    logger.info(
                        "[omni-pipeline] Step2 VL runner 已关闭 project_id=%s task_id=%s runner_id=%s",
                        project_id,
                        task_id,
                        id(runner),
                    )

                outs: List[_Step2VlOutcome] = vl_results
                bge_note = (
                    f"（BGE 并发上限={_bge_cap}，可由 OMNI_BGE_ENCODE_ASYNC_CONCURRENCY 调整）"
                    if _bge_cap is not None
                    else ""
                )
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=max(last_reported_progress, min(94.0, vl_hi)),
                    message=f"Step2: 在线视觉已完成，开始本地向量化（共 {len(outs)} 段）…{bge_note}",
                    phase="step2",
                )
                logger.info(
                    "[omni-pipeline] Step2 阶段二-B 向量化 gather 开始 project_id=%s task_id=%s n=%s%s",
                    project_id,
                    task_id,
                    len(outs),
                    bge_note,
                )
                step2_embed_results = await asyncio.gather(
                    *(_commit_step2_after_vl(o) for o in outs),
                    return_exceptions=True,
                )
                for res in step2_embed_results:
                    if isinstance(res, asyncio.CancelledError):
                        raise res
                for res in step2_embed_results:
                    if isinstance(res, BaseException):
                        raise res
                logger.info(
                    "[omni-pipeline] Step2 阶段二-B 向量化 gather 正常结束 project_id=%s task_id=%s",
                    project_id,
                    task_id,
                )

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                await _persist_snapshot(partial=False)

                done_msg = "Omni 管线完成（镜头拆分 + 多模态向量化）"
                if vl_policy_blocked_count > 0:
                    done_msg += f"；{vl_policy_blocked_count} 个语义段因上游内容策略未生成画面描述，已用语义占位向量继续"
                if vl_call_failed_count > 0:
                    done_msg += f"；{vl_call_failed_count} 个语义段在线视觉多次重试仍失败，已跳过并用语义占位降级（可再次运行管线仅补全失败段）"
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message=done_msg,
                    phase="done",
                )
            except asyncio.CancelledError:
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="cancelled",
                    message="任务已取消",
                    phase="cancelled",
                )
            except Exception as e:
                logger.exception("Omni pipeline failed")
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="failed",
                    message=f"Omni 管线失败: {e}",
                    phase="failed",
                )

        asyncio.create_task(_run())
        return {"task_id": task_id, "status": "pending", "message": "Omni 管线已提交"}


omni_multimodal_pipeline_service = OmniMultimodalPipelineService()
