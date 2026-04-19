#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni 项目专用：镜头拆分（TransNet + 字幕语义段）与多模态特征（在线视觉 + 向量模型配置）。
与 extract_scene / visual 流程完全隔离；产出写入 uploads/omni_multimodal/{project_id}/。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image

from modules.config.ai_search_shot_model_config import ai_search_shot_model_config_manager
from modules.config.video_model_config import video_model_config_manager
from modules.projects_store import projects_store
from modules.subtitle_utils import parse_srt
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from services.extract_subtitle_service import _resolve_path, _to_web_path, _uploads_dir
from services.omni_internal.frame_extract import extract_quarter_frames
from services.omni_internal.multimodal_json_crypto import write_encrypted_multimodal_json
from services.omni_internal.shot_subtitle_mapper import ShotSubtitleMapper
from services.omni_internal.transnet_omni import detect_shots_from_video
from services.omni_internal.types import Shot, Subtitle
from services.vision_frame_analysis_service import _OnlineVisionRunner, _try_parse_vision_json, load_frame_analysis_prompt

logger = logging.getLogger(__name__)

_SCOPE = "omni_multimodal"

_ONLINE_VL_PROVIDERS = frozenset({"yunwu", "302ai", "qwen", "doubao", "custom_openai_vision"})


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
    return {
        "video_path": video_path,
        "srt_path": srt_path,
        "total_shots_raw": len(shots_raw_data),
        "total_segments_semantic": len(segments_semantic),
        "shots_raw": shots_raw_data,
        "segments_semantic": segments_semantic,
        "total_shots": len(shots_data),
        "total_duration": total_duration,
        "shots": shots_data,
    }


def _step1_sync(video_abs: Path, srt_abs: Path) -> Dict[str, Any]:
    shots_raw, _fps = detect_shots_from_video(str(video_abs), progress_callback=None)
    if not shots_raw:
        raise ValueError("未能检测到任何镜头边界")
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
    mapper = ShotSubtitleMapper()
    mapped = mapper.map_subtitles_to_shots(shots_raw, subtitles)
    segments_semantic = mapper.build_semantic_segments(mapped)
    segments_semantic = mapper.merge_short_segments_bidirectional(segments_semantic)
    return _build_step1_export(
        video_path=str(video_abs),
        srt_path=str(srt_abs),
        shots_raw=shots_raw,
        segments_semantic=segments_semantic,
    )


class OmniMultimodalPipelineService:
    SCOPE = _SCOPE

    async def submit_pipeline(self, project_id: str, force: bool = False, task_id: Optional[str] = None) -> Dict[str, Any]:
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

        running = task_progress_store.get_latest_running(self.SCOPE, project_id)
        if running:
            r_status = str(running.get("status") or "").strip().lower()
            r_task_id = running.get("task_id")
            if not force:
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
                    message="Step1: TransNet 镜头拆分与字幕对齐...",
                    phase="step1",
                )

                step1 = await asyncio.to_thread(_step1_sync, video_abs, subtitle_abs)
                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()
                work = _omni_project_dir(project_id)
                work.mkdir(parents=True, exist_ok=True)
                step1_path = work / "shots_step1.json"
                step1_path.write_text(json.dumps(step1, ensure_ascii=False, indent=2), encoding="utf-8")
                step1_web = _to_web_path(step1_path)
                projects_store.update_project(
                    project_id,
                    {
                        "omni_step1_json_path": step1_web,
                        "omni_pipeline_updated_at": datetime.now().isoformat(),
                    },
                )

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=35,
                    message="Step1 完成，开始 Step2 多模态与向量化...",
                    phase="step2",
                )

                active_vl = video_model_config_manager.get_active_config()
                if not active_vl or active_vl.provider not in _ONLINE_VL_PROVIDERS:
                    raise ValueError(
                        "Omni Step2 需要在线视觉模型：请在「视频理解模型」中选择 yunwu / 302ai / qwen / doubao / custom_openai_vision 之一并配置密钥"
                    )
                emb_cfg = ai_search_shot_model_config_manager.get_config()
                if not emb_cfg or not (emb_cfg.api_key or "").strip():
                    raise ValueError("请先在「向量模型」设置中配置云雾向量接口与 API Key")

                shots: List[Dict[str, Any]] = list(step1.get("shots") or [])
                if not shots:
                    raise ValueError("Step1 未产生镜头列表")

                frames_dir = work / "frames"
                frames_dir.mkdir(parents=True, exist_ok=True)

                runner = _OnlineVisionRunner(
                    provider=str(active_vl.provider),
                    api_key=str(active_vl.api_key or ""),
                    base_url=str(active_vl.base_url or ""),
                    model_name=str(active_vl.model_name or ""),
                    timeout=int(active_vl.timeout or 120),
                )
                sem = asyncio.Semaphore(3)
                enriched: List[Optional[Dict[str, Any]]] = [None] * len(shots)
                done_count = 0
                lock = asyncio.Lock()

                vl_prompt_language = "zh"

                async def _embed_one(text: str) -> List[float]:
                    headers = {
                        "Authorization": f"Bearer {emb_cfg.api_key}",
                        "Content-Type": "application/json",
                    }
                    payload = {"model": emb_cfg.embedding_model, "input": text}
                    timeout = httpx.Timeout(float(emb_cfg.timeout_seconds or 300))
                    last_err: Optional[Exception] = None
                    retries = max(1, int(emb_cfg.max_retries or 3))
                    base_sleep = float(emb_cfg.retry_sleep_seconds or 2.0)
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        for attempt in range(retries):
                            try:
                                r = await client.post(str(emb_cfg.embedding_base_url), headers=headers, json=payload)
                                r.raise_for_status()
                                data = r.json()
                                emb = data["data"][0]["embedding"]
                                if isinstance(emb, list) and emb:
                                    return emb
                                raise RuntimeError("embedding 为空")
                            except asyncio.CancelledError:
                                raise
                            except Exception as e:
                                last_err = e
                                if attempt + 1 >= retries:
                                    break
                                delay = min(60.0, base_sleep * (2**attempt))
                                await asyncio.sleep(delay)
                    raise RuntimeError(f"向量化失败: {last_err}")

                async def _one(idx: int, shot: Dict[str, Any]) -> None:
                    nonlocal done_count
                    if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                        raise asyncio.CancelledError()
                    async with sem:
                        if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                            raise asyncio.CancelledError()
                        frame_paths = await asyncio.to_thread(
                            extract_quarter_frames,
                            str(video_abs),
                            shot,
                            str(frames_dir),
                        )
                        images: List[Image.Image] = []
                        for fp in frame_paths:
                            images.append(Image.open(fp).convert("RGB"))
                        sub_text = str(shot.get("subtitle_full_text") or "")
                        prompt = load_frame_analysis_prompt(vl_prompt_language, sub_text)
                        raw, _stats = await runner.infer_multi(images, prompt, max_tokens=1024)
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

                try:
                    await asyncio.gather(*[_one(i, s) for i, s in enumerate(shots)])
                finally:
                    await runner.close()

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                out = dict(step1)
                out["shots"] = [x for x in enriched if x is not None]
                out["omni_pipeline_meta"] = {
                    "vl_provider": active_vl.provider,
                    "vl_model": active_vl.model_name,
                    "embedding_model": emb_cfg.embedding_model,
                    "completed_at": datetime.now().isoformat(),
                }
                out_path = work / "shots_multimodal.json"
                write_encrypted_multimodal_json(out_path, out)
                out_web = _to_web_path(out_path)
                projects_store.update_project(
                    project_id,
                    {
                        "omni_multimodal_json_path": out_web,
                        "omni_pipeline_updated_at": datetime.now().isoformat(),
                    },
                )

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message="Omni 管线完成（镜头拆分 + 多模态向量化）",
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
