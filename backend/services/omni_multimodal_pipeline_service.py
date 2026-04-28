#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni 项目专用：镜头拆分（TransNet + 字幕语义段）与多模态特征（在线视觉 + 本地 BGE 句向量）。
与 extract_scene / visual 流程完全隔离；产出写入 uploads/omni_multimodal/{project_id}/。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
from PIL import Image

from services.ai_models.unified_model_usage import resolve_video_model_for_online_vision
from modules.projects_store import projects_store
from modules.subtitle_utils import parse_srt
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from services.asr.extract_subtitle_service import _resolve_path, _to_web_path, _uploads_dir
from services.omni_internal.frame_extract import extract_quarter_frames
from services.omni_internal.multimodal_json_crypto import read_multimodal_json, write_encrypted_multimodal_json
from services.omni_internal.shot_subtitle_mapper import ShotSubtitleMapper
from services.ai_models.omni_local_bge_embedding import LOCAL_BGE_MODEL_DISPLAY_NAME, assert_local_bge_model_available, encode_text_async
from services.omni_internal.transnet_omni import detect_shots_from_video
from services.omni_internal.types import Shot, Subtitle
from services.ai_models.vision_frame_analysis_service import (
    _ONLINE_VISION_INFER_CONCURRENT_INTERVAL_SEC,
    _ONLINE_VISION_INFER_RETRY_DELAYS_SEC,
    _OnlineVisionRunner,
    _try_parse_vision_json,
    load_frame_analysis_prompt,
)

logger = logging.getLogger(__name__)

_SCOPE = "omni_multimodal"

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
    if st in ("pending", "error"):
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


def _parse_visual_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {"brief": "", "desc": "", "action": "", "emotion": "", "scene": "", "objects": []}
    parsed = _try_parse_vision_json(raw)
    if isinstance(parsed, dict):
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
    return {"brief": text[:200], "desc": text, "action": "", "emotion": "", "scene": "", "objects": []}


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


def _video_frame_count_hint(video_abs: Path) -> int:
    try:
        cap = cv2.VideoCapture(str(video_abs))
        if not cap.isOpened():
            return 0
        try:
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        finally:
            cap.release()
        return max(n, 0)
    except Exception:
        return 0


def _make_transnet_progress_logger(
    video_abs: Path,
    *,
    progress_hook: Optional[Callable[[str, float], None]] = None,
) -> Callable[[float], None]:
    """TransNet predict_video 回调：先约 1% 表示开始，随后约 10–100 为推理进度。"""
    total = _video_frame_count_hint(video_abs)
    last_mono = 0.0
    last_bucket = -1
    logged_init = False

    def _transnet_progress_pct(inner_pct: float) -> float:
        inner = max(0.0, min(100.0, float(inner_pct)))
        return 6.0 + inner * 22.0 / 100.0

    def cb(pct: float) -> None:
        nonlocal last_mono, last_bucket, logged_init
        p = float(pct)
        now = time.monotonic()
        if p <= 1.5:
            if not logged_init:
                init_msg = (
                    f"Step1: TransNet 镜头分割已启动，总帧数约 {total}，准备抽帧/推理…"
                    if total > 0
                    else "Step1: TransNet 镜头分割已启动，准备抽帧/推理…"
                )
                logger.info(
                    "[omni-pipeline] Step1 TransNet：已提交视频，总帧数约 %s，开始抽帧/推理…",
                    total if total > 0 else "未知",
                )
                if progress_hook:
                    progress_hook(init_msg, 5.5)
                logged_init = True
            return
        inner = max(0.0, min(100.0, (p - 10.0) / 0.9)) if p >= 10.0 else 0.0
        bucket = int(inner // 5)
        if total > 0:
            cur_frames = min(total, max(0, int(total * inner / 100.0)))
            msg = f"Step1: TransNet 分割进度 {cur_frames}/{total} 帧（{inner:.1f}%）"
            log_msg = f"TransNet 推理进度 约 {cur_frames}/{total} 帧 ({inner:.1f}%)"
        else:
            msg = f"Step1: TransNet 分割进度 {inner:.1f}%（总帧数未知）"
            log_msg = f"TransNet 推理进度 {inner:.1f}%"
        if bucket != last_bucket or (now - last_mono) >= 3.0:
            last_mono = now
            last_bucket = bucket
            logger.info("[omni-pipeline] Step1 %s", log_msg)
            if progress_hook:
                progress_hook(msg, _transnet_progress_pct(inner))

    return cb


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


def _step1_sync(
    video_abs: Path,
    srt_abs: Path,
    *,
    progress_hook: Optional[Callable[[str, float], None]] = None,
) -> Dict[str, Any]:
    logger.info(
        "[omni-pipeline] Step1 开始镜头检测 video=%s srt=%s",
        video_abs,
        srt_abs,
    )
    if progress_hook:
        progress_hook("Step1: TransNet 镜头分割与字幕对齐，正在加载模型/读取视频…", 5.0)
    shots_raw, _fps = detect_shots_from_video(
        str(video_abs),
        progress_callback=_make_transnet_progress_logger(video_abs, progress_hook=progress_hook),
    )
    if not shots_raw:
        raise ValueError("未能检测到任何镜头边界")
    logger.info(
        "[omni-pipeline] Step1 TransNet 完成：原始镜头 %s 个，fps=%.3f",
        len(shots_raw),
        float(_fps or 0.0),
    )
    if progress_hook:
        progress_hook(
            f"Step1: TransNet 完成，原始镜头 {len(shots_raw)} 个（fps={float(_fps or 0.0):.2f}）",
            28.0,
        )
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
                step1_path = work / "shots_step1.json"

                step1: Optional[Dict[str, Any]] = None
                if mma == "restart":
                    logger.info(
                        "[omni-pipeline] Step1 multimodal_action=restart，跳过历史分割缓存 project_id=%s task_id=%s",
                        project_id,
                        task_id,
                    )
                if mma != "restart" and step1_path.exists():
                    try:
                        prev_step1 = json.loads(step1_path.read_text(encoding="utf-8"))
                    except Exception as e:
                        logger.warning(
                            "[omni-pipeline] Step1 读取历史 shots_step1.json 失败，将重新分割 project_id=%s err=%s",
                            project_id,
                            e,
                        )
                        prev_step1 = None
                    if isinstance(prev_step1, dict) and _step1_snapshot_matches_sources(
                        prev_step1, video_abs, subtitle_abs
                    ):
                        step1 = prev_step1
                        nshots = len(step1.get("shots") or [])
                        logger.info(
                            "[omni-pipeline] Step1 复用已有镜头分割 project_id=%s task_id=%s 语义段=%s（视频/字幕指纹未变）",
                            project_id,
                            task_id,
                            nshots,
                        )
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=28,
                            message=f"Step1: 已复用历史分割（{nshots} 段），视频与字幕未修改",
                            phase="step1",
                        )
                    elif isinstance(prev_step1, dict):
                        logger.info(
                            "[omni-pipeline] Step1 历史分割与当前文件不一致，重新运行 TransNet project_id=%s task_id=%s",
                            project_id,
                            task_id,
                        )

                if step1 is None:
                    step1 = await asyncio.to_thread(
                        partial(
                            _step1_sync,
                            video_abs,
                            subtitle_abs,
                            progress_hook=_step1_task_progress_hook(self.SCOPE, project_id, task_id),
                        )
                    )
                    if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
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
                    infer_wall_sec = float(str(os.environ.get("VISION_ONLINE_INFER_TIMEOUT_SEC") or "").strip() or "180")
                except Exception:
                    infer_wall_sec = 60
                if infer_wall_sec < 1.0:
                    infer_wall_sec = 60
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
                vl_policy_blocked_count = 0

                def _meta_base(*, partial: bool) -> Dict[str, Any]:
                    meta: Dict[str, Any] = {
                        "vl_provider": active_vl.provider,
                        "vl_model": active_vl.model_name,
                        "embedding_model": LOCAL_BGE_MODEL_DISPLAY_NAME,
                        "completed_at": datetime.now().isoformat(),
                    }
                    if vl_policy_blocked_count > 0:
                        meta["step2_vl_policy_blocked_shots"] = int(vl_policy_blocked_count)
                    if partial:
                        meta["partial"] = True
                    return meta

                async def _persist_snapshot(*, partial: bool) -> None:
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
                max_concurrency = 128
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
                        extract_quarter_frames,
                        str(video_abs),
                        shot,
                        str(frames_dir),
                    )
                    images: List[Image.Image] = []
                    for fp in frame_paths:
                        images.append(Image.open(fp).convert("RGB"))
                    return (idx, shot, frame_paths, images)

                try:
                    logger.info(
                        "[omni-pipeline] Step2 阶段一抽帧开始 project_id=%s task_id=%s pending=%s extract_concurrency=%s",
                        project_id,
                        task_id,
                        len(pending_idx),
                        extract_concurrency,
                    )
                    bundles = await asyncio.gather(*(_extract_shot_for_step2(i, shots[i]) for i in pending_idx))
                finally:
                    try:
                        extract_executor.shutdown(wait=True, cancel_futures=True)
                    except Exception:
                        try:
                            extract_executor.shutdown(wait=True)
                        except Exception:
                            pass

                async def _infer_embed_one(
                    idx: int,
                    shot: Dict[str, Any],
                    frame_paths: List[str],
                    images: List[Image.Image],
                ) -> None:
                    nonlocal done_count, vl_policy_blocked_count
                    if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                        raise asyncio.CancelledError()
                    sub_text = str(shot.get("subtitle_full_text") or "")
                    prompt = load_frame_analysis_prompt(vl_prompt_language, sub_text)
                    logger.debug(
                        "[omni-pipeline] Step2 单镜头 VL 请求开始 project_id=%s task_id=%s shot_idx=%s runner_id=%s",
                        project_id,
                        task_id,
                        idx,
                        id(runner),
                    )
                    retry_delays: Tuple[float, ...] = _ONLINE_VISION_INFER_RETRY_DELAYS_SEC
                    max_attempts = 1 + len(retry_delays)
                    raw: Optional[str] = None
                    _stats: Dict[str, Any] = {}
                    last_fail: Optional[BaseException] = None
                    last_was_timeout = False
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
                                    timeout=infer_wall_sec,
                                )
                            last_fail = None
                            break
                        except asyncio.TimeoutError as te:
                            last_fail = te
                            last_was_timeout = True
                            if attempt < max_attempts - 1:
                                logger.warning(
                                    "[omni-pipeline] Step2 在线视觉超时：project_id=%s task_id=%s shot_idx=%s %.1fs 后重试 (%s/%s)，超时阈值=%s秒",
                                    project_id,
                                    task_id,
                                    idx,
                                    retry_delays[attempt],
                                    attempt + 1,
                                    max_attempts - 1,
                                    infer_wall_sec,
                                )
                                await asyncio.sleep(retry_delays[attempt])
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            last_fail = e
                            last_was_timeout = False
                            if attempt < max_attempts - 1:
                                logger.warning(
                                    "[omni-pipeline] Step2 在线视觉失败：project_id=%s task_id=%s shot_idx=%s %.1fs 后重试 (%s/%s)，错误=%s",
                                    project_id,
                                    task_id,
                                    idx,
                                    retry_delays[attempt],
                                    attempt + 1,
                                    max_attempts - 1,
                                    e,
                                )
                                await asyncio.sleep(retry_delays[attempt])
                    if raw is None:
                        if last_fail is not None and (not last_was_timeout) and _is_upstream_vision_policy_block(last_fail):
                            logger.warning(
                                "[omni-pipeline] Step2 上游视觉内容策略拦截，改为仅字幕/占位语义向量: project_id=%s task_id=%s shot_idx=%s err=%s",
                                project_id,
                                task_id,
                                idx,
                                last_fail,
                            )
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
                                pct = 35.0 + 60.0 * (done_count / max(1, len(shots)))
                                task_progress_store.set_state(
                                    scope=self.SCOPE,
                                    project_id=project_id,
                                    task_id=task_id,
                                    status="processing",
                                    progress=min(95.0, pct),
                                    message=f"Step2: 多模态处理 {done_count}/{len(shots)}（含策略降级）",
                                    phase="step2",
                                )
                            await _persist_snapshot(partial=True)
                            return
                        if last_fail is not None:
                            if last_was_timeout:
                                msg = f"单次模型调用超过{int(infer_wall_sec)}秒未返回（已重试{len(retry_delays)}次）"
                                logger.error(
                                    "[omni-pipeline] Step2 在线视觉超时：project_id=%s task_id=%s shot_idx=%s %s",
                                    project_id,
                                    task_id,
                                    idx,
                                    msg,
                                )
                                raise TimeoutError(msg) from last_fail
                            logger.error(
                                "[omni-pipeline] Step2 在线视觉失败：project_id=%s task_id=%s shot_idx=%s 错误=%s",
                                project_id,
                                task_id,
                                idx,
                                last_fail,
                            )
                            raise last_fail
                        raise RuntimeError("在线视觉调用未返回结果且无异常信息")
                    logger.debug(
                        "[omni-pipeline] Step2 单镜头 VL 请求结束 project_id=%s task_id=%s shot_idx=%s runner_id=%s",
                        project_id,
                        task_id,
                        idx,
                        id(runner),
                    )
                    visual = _parse_visual_json(raw)
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
                        pct = 35.0 + 60.0 * (done_count / max(1, len(shots)))
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=min(95.0, pct),
                            message=f"Step2: 多模态处理 {done_count}/{len(shots)}",
                            phase="step2",
                        )
                    await _persist_snapshot(partial=True)

                try:
                    logger.info(
                        "[omni-pipeline] Step2 阶段二推理 gather 开始 project_id=%s task_id=%s runner_id=%s n_tasks=%s api_concurrency=%s",
                        project_id,
                        task_id,
                        id(runner),
                        len(bundles),
                        api_concurrency,
                    )
                    # 必须用 return_exceptions=True：默认 gather 在首个子任务抛错时会立刻返回，
                    # 但 finally 仍会关闭 runner，其余仍在跑的推理会打到已关闭的 httpx 客户端，
                    # 从而刷屏「Cannot send a request, as the client has been closed」。
                    step2_results = await asyncio.gather(
                        *(
                            _infer_embed_one(idx, sh, fps, imgs)
                            for idx, sh, fps, imgs in bundles
                        ),
                        return_exceptions=True,
                    )
                    for res in step2_results:
                        if isinstance(res, asyncio.CancelledError):
                            raise res
                    for res in step2_results:
                        if isinstance(res, BaseException):
                            raise res
                    logger.info(
                        "[omni-pipeline] Step2 gather 正常结束 project_id=%s task_id=%s runner_id=%s",
                        project_id,
                        task_id,
                        id(runner),
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

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                await _persist_snapshot(partial=False)

                done_msg = "Omni 管线完成（镜头拆分 + 多模态向量化）"
                if vl_policy_blocked_count > 0:
                    done_msg += f"；{vl_policy_blocked_count} 个语义段因上游内容策略未生成画面描述，已用语义占位向量继续"
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
