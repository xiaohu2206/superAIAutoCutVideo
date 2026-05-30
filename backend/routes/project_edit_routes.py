#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频编辑相关API路由：视频合并、视频裁剪
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
import asyncio
import uuid
import os
import subprocess
from threading import RLock

from fastapi import APIRouter, HTTPException

from .project_routes import (
    now_ts,
    to_web_path,
    resolve_abs_path,
    remove_path,
    safe_dir_name,
    uploads_dir,
    MergeTaskStatus,
    TrimTimeRange,
    TrimVideoRequest,
    TrimTaskStatus,
    MERGE_TASKS,
    _merge_lock,
    _active_merge_keys,
    TRIM_TASKS,
    _trim_lock,
    _active_trim_keys,
)
from modules.projects_store import projects_store
from modules.task_cancel_store import task_cancel_store
from modules.video_processor import video_processor, _trim_log_tag, _trim_timeout_label
from modules.ws_manager import manager

router = APIRouter(prefix="/api/projects", tags=["项目管理"])
logger = logging.getLogger(__name__)


def _merge_ranges(ranges: List[List[int]]) -> List[List[int]]:
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda x: (x[0], x[1]))
    merged: List[List[int]] = []
    for s, e in ordered:
        if not merged:
            merged.append([s, e])
            continue
        last = merged[-1]
        if s <= last[1]:
            last[1] = max(last[1], e)
        else:
            merged.append([s, e])
    return merged


def _normalize_ranges_ms(ranges: List[TrimTimeRange], duration_ms: int) -> List[List[int]]:
    if duration_ms <= 0:
        return []
    norm: List[List[int]] = []
    for r in ranges or []:
        try:
            s = int(r.start_ms)
            e = int(r.end_ms)
        except Exception:
            continue
        if s < 0:
            s = 0
        if e < 0:
            e = 0
        if s > duration_ms:
            s = duration_ms
        if e > duration_ms:
            e = duration_ms
        if e <= s:
            continue
        norm.append([s, e])
    return _merge_ranges(norm)


def _invert_ranges_ms(ranges: List[List[int]], duration_ms: int) -> List[List[int]]:
    if duration_ms <= 0:
        return []
    if not ranges:
        return [[0, duration_ms]]
    keep: List[List[int]] = []
    cur = 0
    for s, e in ranges:
        if s > cur:
            keep.append([cur, s])
        cur = max(cur, e)
        if cur >= duration_ms:
            break
    if cur < duration_ms:
        keep.append([cur, duration_ms])
    return keep


@router.post("/{project_id}/merge/videos")
async def merge_videos(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.video_paths or len(p.video_paths) < 2:
        raise HTTPException(status_code=400, detail="需要至少两个视频进行合并")

    source_paths = [str(path).strip() for path in p.video_paths if path and str(path).strip()]
    if len(source_paths) < 2:
        raise HTTPException(status_code=400, detail="需要至少两个有效视频进行合并")

    old_merged_path = (p.merged_video_path or "").strip()
    merge_key = str(project_id)
    with _merge_lock:
        active = _active_merge_keys.get(merge_key)
        if active:
            active_task = MERGE_TASKS.get(active)
            status = (active_task.status if active_task else "").strip().lower()
            if status in {"pending", "processing", "running"}:
                raise HTTPException(status_code=409, detail="该项目正在合并视频（合并比较慢,如果可以建议外部合并），请稍后")

        task_id = f"merge_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        _active_merge_keys[merge_key] = task_id
        MERGE_TASKS[task_id] = MergeTaskStatus(
            task_id=task_id,
            status="pending",
            progress=0.0,
            message="准备合并",
        )

    async def _broadcast(payload: Dict[str, Any]) -> None:
        try:
            await manager.broadcast(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    async def _run():
        out_path: Optional[Path] = None
        cancel_event = task_cancel_store.get_event("merge_videos", project_id, task_id)
        try:
            MERGE_TASKS[task_id].status = "processing"
            MERGE_TASKS[task_id].message = "正在合并"
            await _broadcast({
                "type": "progress",
                "scope": "merge_videos",
                "project_id": project_id,
                "task_id": task_id,
                "message": "开始合并视频",
                "progress": 0,
                "timestamp": now_ts(),
            })

            inputs: List[Path] = []
            for path_str in source_paths:
                s = path_str.strip()
                abs_path = resolve_abs_path(s)
                if not abs_path.is_file() or abs_path.stat().st_size <= 0:
                    raise RuntimeError(f"源视频不存在或为空: {s}")
                inputs.append(abs_path)

            project_dir_name = safe_dir_name(p.name or p.id, p.id)
            out_dir = uploads_dir() / "videos" / "merged" / project_dir_name
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out_name = f"{p.id}_merged_{ts}.mp4"
            out_path = out_dir / out_name

            async def on_progress(pct: float):
                current = float(MERGE_TASKS[task_id].progress or 0.0)
                next_progress = max(current, min(99.0, max(0.0, float(pct))))
                MERGE_TASKS[task_id].progress = float(f"{next_progress:.2f}")
                await _broadcast({
                    "type": "progress",
                    "scope": "merge_videos",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "正在合并",
                    "progress": MERGE_TASKS[task_id].progress,
                    "timestamp": now_ts(),
                })

            ok = await video_processor.concat_videos(
                [str(x) for x in inputs],
                str(out_path),
                on_progress,
                scope="merge_videos",
                project_id=project_id,
                task_id=task_id,
                cancel_event=cancel_event,
            )
            if not ok or not out_path.is_file() or out_path.stat().st_size <= 0:
                err = video_processor.get_last_concat_error(
                    scope="merge_videos",
                    project_id=project_id,
                    task_id=task_id,
                ) or ""
                raise RuntimeError(("合并失败: " + str(err).strip()[:400]) if err else "合并失败")

            web_path = to_web_path(out_path)
            projects_store.set_merged_video_path(project_id, web_path, out_name)
            if old_merged_path and old_merged_path != web_path:
                try:
                    old_abs = resolve_abs_path(old_merged_path)
                    remove_path(old_abs)
                except Exception:
                    pass
            MERGE_TASKS[task_id].file_path = web_path
            MERGE_TASKS[task_id].progress = 100.0
            MERGE_TASKS[task_id].status = "completed"
            MERGE_TASKS[task_id].message = "合并完成"
            await _broadcast({
                "type": "completed",
                "scope": "merge_videos",
                "project_id": project_id,
                "task_id": task_id,
                "message": "合并完成",
                "progress": 100,
                "file_path": web_path,
                "timestamp": now_ts(),
            })
            logger.info("[merge_videos][project=%s][task=%s] completed output=%s", project_id, task_id, out_path)
        except asyncio.CancelledError:
            MERGE_TASKS[task_id].status = "failed"
            MERGE_TASKS[task_id].message = "合并已取消"
            await _broadcast({
                "type": "error",
                "scope": "merge_videos",
                "project_id": project_id,
                "task_id": task_id,
                "message": MERGE_TASKS[task_id].message,
                "progress": MERGE_TASKS[task_id].progress,
                "timestamp": now_ts(),
            })
        except Exception as e:
            error_text = str(e).strip() or "合并异常"
            MERGE_TASKS[task_id].status = "failed"
            MERGE_TASKS[task_id].message = error_text[:500]
            logger.exception("[merge_videos][project=%s][task=%s] failed: %s", project_id, task_id, error_text)
            await _broadcast({
                "type": "error",
                "scope": "merge_videos",
                "project_id": project_id,
                "task_id": task_id,
                "message": MERGE_TASKS[task_id].message,
                "progress": MERGE_TASKS[task_id].progress,
                "timestamp": now_ts(),
            })
        finally:
            if MERGE_TASKS[task_id].status != "completed" and out_path:
                try:
                    if out_path.exists():
                        out_path.unlink()
                except Exception:
                    pass
            try:
                with _merge_lock:
                    if _active_merge_keys.get(merge_key) == task_id:
                        del _active_merge_keys[merge_key]
            except Exception:
                pass

    asyncio.create_task(_run())

    return {
        "message": "开始合并",
        "data": {
            "task_id": task_id,
        },
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/merge/videos/status/{task_id}")
async def merge_videos_status(project_id: str, task_id: str):
    t = MERGE_TASKS.get(task_id)
    if not t or not task_id.startswith(f"merge_{project_id}_"):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "message": "获取合并进度",
        "data": t.model_dump(),
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/trim/video")
async def trim_video(project_id: str, req: TrimVideoRequest):
    trim_tag = _trim_log_tag(project_id, None)
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    file_path = (req.file_path or "").strip()
    if not file_path:
        raise HTTPException(status_code=400, detail="缺少 file_path")

    mode = (req.mode or "keep").strip().lower()
    if mode not in {"keep", "delete"}:
        raise HTTPException(status_code=400, detail="mode 必须为 keep 或 delete")

    try:
        abs_in = resolve_abs_path(file_path)
    except Exception:
        abs_in = Path("")
    if not abs_in or not abs_in.exists() or not abs_in.is_file():
        raise HTTPException(status_code=404, detail="源视频不存在")

    try:
        duration_sec = await video_processor._ffprobe_video_duration(str(abs_in))
    except Exception:
        duration_sec = None
    duration_ms = int(float(duration_sec or 0.0) * 1000.0)
    if duration_ms <= 0:
        raise HTTPException(status_code=400, detail="无法获取视频时长")

    norm_ranges = _normalize_ranges_ms(req.ranges or [], duration_ms)
    if not norm_ranges:
        raise HTTPException(status_code=400, detail="请先在时间轴选择至少一个区间")
    if mode == "keep":
        keep_ranges = norm_ranges
    else:
        keep_ranges = _invert_ranges_ms(norm_ranges, duration_ms)

    keep_ranges = [r for r in keep_ranges if (r[1] - r[0]) >= 200]
    if not keep_ranges:
        raise HTTPException(status_code=400, detail="裁剪区间为空或过短")
    if len(keep_ranges) > 60:
        raise HTTPException(status_code=400, detail="区间过多（最多 60 段）")

    trim_key = f"{project_id}::{file_path}"
    with _trim_lock:
        active = _active_trim_keys.get(trim_key)
        if active:
            t = TRIM_TASKS.get(active)
            status = (t.status if t else "").strip().lower()
            if status in {"pending", "processing", "running"}:
                raise HTTPException(status_code=409, detail="该视频正在裁剪处理中，请稍后")
        task_id = f"trim_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        _active_trim_keys[trim_key] = task_id
        TRIM_TASKS[task_id] = TrimTaskStatus(task_id=task_id, status="pending", progress=0.0, message="准备裁剪")

    trim_tag = _trim_log_tag(project_id, task_id)
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "%s request file=%s mode=%s ranges=%d keep_ranges=%d duration=%.3fs",
        trim_tag,
        Path(file_path).name,
        mode,
        len(req.ranges or []),
        len(keep_ranges),
        float(duration_ms) / 1000.0,
    )

    async def _broadcast(payload: Dict[str, Any]):
        try:
            await manager.broadcast(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    async def _run():
        seg_paths: List[Path] = []
        out_tmp: Optional[Path] = None
        trim_cancel_event = asyncio.Event()
        try:
            logger.info("%s task start", trim_tag)
            TRIM_TASKS[task_id].status = "processing"
            TRIM_TASKS[task_id].message = "正在裁剪"
            await _broadcast(
                {
                    "type": "progress",
                    "scope": "trim_video",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "开始裁剪",
                    "progress": 0,
                    "timestamp": now_ts(),
                }
            )

            logger.info(
                "%s keep ranges sample=%s",
                trim_tag,
                ", ".join([f"{float(s)/1000.0:.3f}-{float(e)/1000.0:.3f}s" for s, e in keep_ranges[:8]]) + (" ..." if len(keep_ranges) > 8 else ""),
            )
            tmp_dir = uploads_dir() / "videos" / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            total_segments = len(keep_ranges)
            for idx, (s_ms, e_ms) in enumerate(keep_ranges):
                seg_out = tmp_dir / f"{project_id}_trim_{task_id}_{idx}.mp4"
                seg_paths.append(seg_out)
                start_sec = float(s_ms) / 1000.0
                dur_sec = float(e_ms - s_ms) / 1000.0
                logger.info(
                    "%s clip %d/%d start range=%.3fs-%.3fs dur=%.3fs",
                    trim_tag,
                    idx + 1,
                    total_segments,
                    start_sec,
                    start_sec + dur_sec,
                    dur_sec,
                )
                ok = await video_processor.cut_video_segment(
                    str(abs_in),
                    str(seg_out),
                    start_sec,
                    dur_sec,
                    scope="trim_video",
                    project_id=project_id,
                    task_id=task_id,
                    cancel_event=trim_cancel_event,
                )
                if not ok:
                    last_err = getattr(video_processor, "last_cut_error", "") or ""
                    logger.error("%s clip %d/%d failed output_exists=%s output=%s reason=%s", trim_tag, idx + 1, total_segments, seg_out.exists(), seg_out, last_err)
                    raise RuntimeError(f"剪切第 {idx + 1} 段失败" + (f" reason={last_err}" if last_err else ""))
                pct = 10.0 + (40.0 * float(idx + 1) / float(max(total_segments, 1)))
                TRIM_TASKS[task_id].progress = float(f"{pct:.2f}")
                TRIM_TASKS[task_id].message = f"已剪切 {idx + 1}/{total_segments} 段"
                await _broadcast(
                    {
                        "type": "progress",
                        "scope": "trim_video",
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": TRIM_TASKS[task_id].message,
                        "progress": TRIM_TASKS[task_id].progress,
                        "timestamp": now_ts(),
                    }
                )

            out_tmp = abs_in.parent / f".trim_{task_id}.tmp{abs_in.suffix}"
            if out_tmp.exists():
                try:
                    out_tmp.unlink()
                except Exception:
                    pass

            async def _on_concat_progress(pct: float):
                mapped = 60.0 + (float(pct) * 0.35)
                if mapped > 95.0:
                    mapped = 95.0
                if mapped < 60.0:
                    mapped = 60.0
                TRIM_TASKS[task_id].progress = float(f"{mapped:.2f}")
                TRIM_TASKS[task_id].message = "正在拼接"
                await _broadcast(
                    {
                        "type": "progress",
                        "scope": "trim_video",
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": "正在拼接",
                        "progress": TRIM_TASKS[task_id].progress,
                        "timestamp": now_ts(),
                    }
                )

            concat_timeout = max(90.0, min(30 * 60.0, (float(duration_ms) / 1000.0) * 4.0 + 60.0))
            logger.info(
                "%s concat input sample=%s output_tmp=%s",
                trim_tag,
                ", ".join([Path(x).name for x in seg_paths[:8]]) + (" ..." if len(seg_paths) > 8 else ""),
                out_tmp,
            )
            logger.info(
                "%s concat start segments=%d timeout=%s",
                trim_tag,
                len(seg_paths),
                _trim_timeout_label(concat_timeout),
            )
            ok = await asyncio.wait_for(
                video_processor.concat_videos(
                    [str(x) for x in seg_paths],
                    str(out_tmp),
                    _on_concat_progress,
                    scope="trim_video",
                    project_id=project_id,
                    task_id=task_id,
                    cancel_event=trim_cancel_event,
                ),
                timeout=concat_timeout,
            )
            if not ok or not out_tmp.exists():
                err = video_processor.get_last_concat_error(
                    scope="trim_video",
                    project_id=project_id,
                    task_id=task_id,
                ) or ""
                last_cmd = video_processor.get_last_concat_cmd(
                    scope="trim_video",
                    project_id=project_id,
                    task_id=task_id,
                ) or []
                logger.error(
                    "%s concat failed ok=%s out_exists=%s err=%s cmd=%s",
                    trim_tag,
                    ok,
                    bool(out_tmp and out_tmp.exists()),
                    str(err).strip()[:500],
                    " ".join(str(x) for x in last_cmd)[:1000],
                )
                if err:
                    raise RuntimeError(f"拼接失败: {str(err).strip()[:400]}")
                raise RuntimeError("拼接失败")

            out_web_path = file_path
            replaced = False
            last_err: Optional[Exception] = None
            for i in range(20):
                try:
                    os.replace(str(out_tmp), str(abs_in))
                    replaced = True
                    break
                except PermissionError as e:
                    last_err = e
                    winerr = getattr(e, "winerror", None)
                    if os.name == "nt" and winerr in (5, 32):
                        await asyncio.sleep(0.15 + 0.05 * float(i))
                        continue
                    raise
                except OSError as e:
                    last_err = e
                    winerr = getattr(e, "winerror", None)
                    if os.name == "nt" and winerr in (5, 32):
                        await asyncio.sleep(0.15 + 0.05 * float(i))
                        continue
                    raise

            if not replaced:
                try:
                    fallback_out = abs_in.parent / f"{project_id}_trimmed_{task_id}{abs_in.suffix}"
                    if fallback_out.exists():
                        try:
                            fallback_out.unlink()
                        except Exception:
                            pass
                    os.replace(str(out_tmp), str(fallback_out))
                    out_web_path = to_web_path(fallback_out)
                    try:
                        cur_paths = list(p.video_paths or [])
                        cur_names = dict(p.video_names or {})
                        if file_path in cur_paths:
                            cur_paths = [out_web_path if x == file_path else x for x in cur_paths]
                        else:
                            cur_paths.append(out_web_path)
                        if out_web_path != file_path:
                            cur_names[out_web_path] = cur_names.get(file_path) or Path(out_web_path).name
                            if file_path in cur_names:
                                try:
                                    del cur_names[file_path]
                                except Exception:
                                    pass
                        projects_store.update_project(
                            project_id,
                            {
                                "video_paths": cur_paths,
                                "video_names": cur_names,
                            },
                        )
                    except Exception:
                        pass
                except Exception:
                    if last_err:
                        raise last_err
                    raise

            for sp in seg_paths:
                try:
                    if sp.exists():
                        sp.unlink()
                except Exception:
                    pass

            if out_web_path == file_path:
                try:
                    projects_store.update_project(
                        project_id,
                        {
                            "video_paths": list(p.video_paths or []),
                            "video_names": dict(p.video_names or {}),
                        },
                    )
                except Exception:
                    pass

            logger.info("%s concat done replace=%s output=%s", trim_tag, "inplace" if out_web_path == file_path else "fallback", Path(out_web_path).name)
            out_ver = datetime.now().strftime("%Y%m%d%H%M%S%f")
            TRIM_TASKS[task_id].status = "completed"
            TRIM_TASKS[task_id].progress = 100.0
            TRIM_TASKS[task_id].message = "裁剪完成"
            TRIM_TASKS[task_id].file_path = out_web_path
            TRIM_TASKS[task_id].output_version = out_ver
            await _broadcast(
                {
                    "type": "completed",
                    "scope": "trim_video",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "裁剪完成",
                    "progress": 100,
                    "file_path": out_web_path,
                    "output_version": out_ver,
                    "timestamp": now_ts(),
                }
            )
            logger.info("%s task completed", trim_tag)
        except asyncio.TimeoutError:
            TRIM_TASKS[task_id].status = "failed"
            TRIM_TASKS[task_id].message = f"拼接超时（{_trim_timeout_label(concat_timeout)}）"
            try:
                trim_cancel_event.set()
            except Exception:
                pass
            logger.error("%s concat timeout timeout=%s", trim_tag, _trim_timeout_label(concat_timeout))
            if out_tmp:
                try:
                    if out_tmp.exists():
                        out_tmp.unlink()
                except Exception:
                    pass
            for sp in seg_paths:
                try:
                    if sp.exists():
                        sp.unlink()
                except Exception:
                    pass
            await _broadcast(
                {
                    "type": "error",
                    "scope": "trim_video",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": TRIM_TASKS[task_id].message,
                    "progress": float(TRIM_TASKS[task_id].progress or 0.0),
                    "timestamp": now_ts(),
                }
            )
        except Exception as e:
            TRIM_TASKS[task_id].status = "failed"
            TRIM_TASKS[task_id].message = str(e) or "裁剪失败"
            try:
                trim_cancel_event.set()
            except Exception:
                pass
            if out_tmp:
                try:
                    if out_tmp.exists():
                        out_tmp.unlink()
                except Exception:
                    pass
            for sp in seg_paths:
                try:
                    if sp.exists():
                        sp.unlink()
                except Exception:
                    pass
            await _broadcast(
                {
                    "type": "error",
                    "scope": "trim_video",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": TRIM_TASKS[task_id].message,
                    "progress": float(TRIM_TASKS[task_id].progress or 0.0),
                    "timestamp": now_ts(),
                }
            )
        finally:
            logger.info("%s task end status=%s progress=%.1f", trim_tag, TRIM_TASKS[task_id].status, float(TRIM_TASKS[task_id].progress or 0.0))
            with _trim_lock:
                cur = _active_trim_keys.get(trim_key)
                if cur == task_id:
                    try:
                        del _active_trim_keys[trim_key]
                    except Exception:
                        pass

    asyncio.create_task(_run())
    return {
        "message": "开始裁剪",
        "data": {
            "task_id": task_id,
        },
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/trim/video/status/{task_id}")
async def trim_video_status(project_id: str, task_id: str):
    t = TRIM_TASKS.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "message": "获取裁剪进度",
        "data": t.model_dump(),
        "timestamp": now_ts(),
    }
