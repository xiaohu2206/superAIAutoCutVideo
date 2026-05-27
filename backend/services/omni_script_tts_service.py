#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni 脚本：单条配音与批量配音任务。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.config.generate_concurrency_config import generate_concurrency_config_manager
from modules.config.tts_config import tts_engine_config_manager
from modules.omni_script_tts import (
    apply_tts_fields_to_segment,
    build_tts_out_path,
    find_segment_index,
    is_original_segment,
    needs_bulk_tts,
    to_web_path,
    tts_text_hash,
)
from modules.project_task_queue import project_task_queue
from modules.projects_store import projects_store
from modules.task_scheduler import task_scheduler
from modules.tts_service import tts_service
from modules.ws_manager import manager

logger = logging.getLogger(__name__)

SCOPE = "omni_script_tts"


class OmniScriptTtsService:
    SCOPE = SCOPE

    def _require_omni_project(self, project_id: str):
        p = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        if str(getattr(p, "project_type", "") or "").strip().lower() != "omni":
            raise ValueError("仅 Omni 项目支持脚本配音")
        if not p.script or not isinstance(p.script, dict):
            raise ValueError("请先生成并保存脚本")
        return p

    async def synthesize_segment(
        self,
        project_id: str,
        segment_id: str,
        *,
        source: str = "manual",
        expected_revision: Optional[int] = None,
        expected_text_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = self._require_omni_project(project_id)
        script = dict(p.script)
        idx = find_segment_index(script, segment_id)
        if idx is None:
            raise ValueError("脚本段落不存在")
        segments: List[Dict[str, Any]] = list(script.get("segments") or [])
        seg = dict(segments[idx])
        if is_original_segment(seg):
            raise ValueError("原片播放段无需配音")
        text = str(seg.get("text") or "").strip()
        if not text:
            raise ValueError("解说文本为空，无法配音")

        text_hash = tts_text_hash(text)
        if expected_text_hash and str(expected_text_hash).strip() != text_hash:
            raise ValueError("脚本文案已变化，请刷新后重试")

        seg_id = str(seg.get("id", idx + 1))
        out_abs = build_tts_out_path(project_id, seg_id, text, source)
        out_abs.parent.mkdir(parents=True, exist_ok=True)

        res = await tts_service.synthesize(text, str(out_abs), None)
        if not res.get("success"):
            raise RuntimeError(str(res.get("error") or "TTS 合成失败"))

        dur = res.get("duration")
        if not isinstance(dur, (int, float)) or float(dur) <= 0:
            from modules.ffmpeg_utils import ffprobe_get_duration

            dur = await ffprobe_get_duration(str(out_abs)) or 0.0

        web_path = to_web_path(out_abs)
        merged_index = idx

        def _merge_latest(latest_script: Dict[str, Any], _revision: int) -> Dict[str, Any]:
            nonlocal merged_index
            latest_idx = find_segment_index(latest_script, seg_id)
            if latest_idx is None:
                raise ValueError("脚本段落已删除，本次配音结果已忽略")
            latest_segments: List[Dict[str, Any]] = list(latest_script.get("segments") or [])
            latest_seg = dict(latest_segments[latest_idx])
            latest_text = str(latest_seg.get("text") or "").strip()
            if is_original_segment(latest_seg) or tts_text_hash(latest_text) != text_hash:
                raise ValueError("脚本段落已变化，本次配音结果已忽略")
            latest_segments[latest_idx] = apply_tts_fields_to_segment(
                latest_seg,
                web_path=web_path,
                duration=float(dur or 0.0),
                source=source,
                text=latest_text,
            )
            latest_script["segments"] = latest_segments
            merged_index = latest_idx
            return latest_script

        p2 = projects_store.update_script_atomic(
            project_id,
            _merge_latest,
        )
        script = dict(p2.script if p2 and p2.script else script)

        return {
            "segment_id": seg_id,
            "segment_index": merged_index,
            "tts_audio_path": web_path,
            "tts_audio_duration": float(dur or 0.0),
            "tts_source": source,
            "tts_text_hash": text_hash,
            "script": script,
        }

    async def submit_bulk_run(self, project_id: str, *, force: bool = False) -> Dict[str, Any]:
        self._require_omni_project(project_id)
        candidate_task_id = (
            f"omni_tts_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
        max_workers, _ = generate_concurrency_config_manager.get_effective("tts")

        async def _run(pid: str, task_id: str, cancel_event: asyncio.Event) -> Dict[str, Any]:
            await project_task_queue.acquire(pid, SCOPE, task_id, cancel_event=cancel_event)
            try:
                return await self._run_bulk(pid, task_id, cancel_event, force=force)
            finally:
                await project_task_queue.release(pid)

        task_id = await task_scheduler.enqueue(
            scope=SCOPE,
            project_id=project_id,
            run_fn=_run,
            task_id=candidate_task_id,
            concurrency=int(max_workers or 2),
            dedup=True,
        )
        return {
            "task_id": task_id,
            "scope": SCOPE,
            "dedup_hit": task_id != candidate_task_id,
        }

    async def _broadcast(
        self,
        *,
        project_id: str,
        task_id: str,
        phase: str,
        message: str,
        progress: float,
    ) -> None:
        try:
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "progress",
                        "scope": SCOPE,
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": phase,
                        "message": message,
                        "progress": float(progress),
                        "timestamp": datetime.now().isoformat(),
                    },
                    ensure_ascii=False,
                )
            )
        except Exception:
            pass

    async def _run_bulk(
        self,
        project_id: str,
        task_id: str,
        cancel_event: asyncio.Event,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        p = self._require_omni_project(project_id)
        script = dict(p.script)
        segments: List[Dict[str, Any]] = [
            dict(s) for s in (script.get("segments") or []) if isinstance(s, dict)
        ]
        targets: List[int] = []
        for i, seg in enumerate(segments):
            if cancel_event.is_set():
                raise asyncio.CancelledError()
            if needs_bulk_tts(seg, force=force):
                targets.append(i)

        total = len(targets)
        if total == 0:
            msg = "无需配音（均已配音或为原片段）" if not force else "没有可重新配音的解说段"
            await self._broadcast(
                project_id=project_id,
                task_id=task_id,
                phase="completed",
                message=msg,
                progress=100.0,
            )
            return {"processed": 0, "skipped": len(segments)}

        cfg = tts_engine_config_manager.get_active_config()
        provider = (getattr(cfg, "provider", None) or "").lower()
        serial = provider == "omnivoice_tts"

        done = 0
        skipped = 0

        async def _one(index: int) -> None:
            nonlocal done, skipped
            if cancel_event.is_set():
                raise asyncio.CancelledError()
            seg = segments[index]
            text = str(seg.get("text") or "").strip()
            seg_id = str(seg.get("id", index + 1))
            out_abs = build_tts_out_path(project_id, seg_id, text, "bulk")
            out_abs.parent.mkdir(parents=True, exist_ok=True)
            res = await tts_service.synthesize(text, str(out_abs), None)
            if not res.get("success"):
                raise RuntimeError(f"段落 {seg_id} 配音失败: {res.get('error')}")
            dur = res.get("duration")
            if not isinstance(dur, (int, float)) or float(dur) <= 0:
                from modules.ffmpeg_utils import ffprobe_get_duration

                dur = await ffprobe_get_duration(str(out_abs)) or 0.0
            web_path = to_web_path(out_abs)
            merged = False

            def _merge_latest(latest_script: Dict[str, Any], _revision: int) -> Optional[Dict[str, Any]]:
                nonlocal merged
                latest_idx = find_segment_index(latest_script, seg_id)
                if latest_idx is None:
                    return None
                latest_segments: List[Dict[str, Any]] = list(latest_script.get("segments") or [])
                latest_seg = dict(latest_segments[latest_idx])
                latest_text = str(latest_seg.get("text") or "").strip()
                if is_original_segment(latest_seg) or tts_text_hash(latest_text) != tts_text_hash(text):
                    return None
                latest_segments[latest_idx] = apply_tts_fields_to_segment(
                    latest_seg,
                    web_path=web_path,
                    duration=float(dur or 0.0),
                    source="bulk",
                    text=latest_text,
                )
                latest_script["segments"] = latest_segments
                merged = True
                return latest_script

            projects_store.update_script_atomic(project_id, _merge_latest)
            if not merged:
                skipped += 1
            done += 1
            prog = 5.0 + (done / max(1, total)) * 90.0
            await self._broadcast(
                project_id=project_id,
                task_id=task_id,
                phase="tts_segment",
                message=f"配音进度 {done}/{total}",
                progress=prog,
            )

        if serial:
            for i in targets:
                await _one(i)
        else:
            sem = asyncio.Semaphore(max(1, int(generate_concurrency_config_manager.get_effective("tts")[0] or 2)))

            async def _guarded(i: int) -> None:
                async with sem:
                    await _one(i)

            await asyncio.gather(*[_guarded(i) for i in targets])

        await self._broadcast(
            project_id=project_id,
            task_id=task_id,
            phase="completed",
            message=f"批量配音完成（{done} 条）",
            progress=100.0,
        )
        return {"processed": max(0, done - skipped), "skipped": skipped, "total_targets": total}


omni_script_tts_service = OmniScriptTtsService()
