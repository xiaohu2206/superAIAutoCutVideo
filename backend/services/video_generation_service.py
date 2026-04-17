#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频生成服务

根据项目中的脚本（script.segments）对原视频进行剪辑并拼接，输出生成视频文件。
"""

import logging
import asyncio
from datetime import datetime
import shutil
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from modules.projects_store import Project, projects_store
from modules.video_processor import WIN_NO_WINDOW, video_processor
from modules.tts_service import tts_service
from modules.config.tts_config import tts_engine_config_manager
from modules.ws_manager import manager
from modules.task_cancel_store import task_cancel_store
from modules.app_paths import uploads_dir as app_uploads_dir, resolve_uploads_path, to_uploads_web_path

logger = logging.getLogger(__name__)


def _uploads_dir() -> Path:
    return app_uploads_dir()


def _to_web_path(p: Path) -> str:
    return to_uploads_web_path(p)


class VideoGenerationService:
    @staticmethod
    def _resolve_path(path_or_web: str) -> Path:
        return resolve_uploads_path(path_or_web)

    @staticmethod
    def _safe_dir_name(name: str, fallback: str) -> str:
        # 过滤Windows非法字符并简化为安全文件夹名
        invalid = '<>:"/\\|?*'
        safe = ''.join('_' if ch in invalid else ch for ch in (name or '').strip())
        safe = safe.strip()
        if not safe:
            safe = f"project_{fallback}"
        # 避免极端情况产生前后点或空格
        safe = safe.replace('.', '_').strip()
        return safe

    @staticmethod
    async def generate_from_script(project_id: str, task_id: str, cancel_event: asyncio.Event) -> Dict[str, Any]:
        """
        根据项目的脚本生成视频：剪辑+拼接。

        Returns: { output_path: str, segments_count: int, started_at: str, finished_at: str }
        """
        p: Optional[Project] = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")

        if not p.video_path:
            raise ValueError("项目未设置原始视频文件")

        if not p.script or not isinstance(p.script, dict):
            raise ValueError("项目未设置有效的脚本")

        logger.info(f"DEBUG generate_video start project_id={project_id} video_path={p.video_path} name={p.name}")

        # 广播：开始生成视频
        try:
            await manager.broadcast(
                __import__("json").dumps({
                    "type": "progress",
                    "scope": "generate_video",
                    "project_id": project_id,
                    "task_id": task_id,
                    "phase": "start",
                    "message": "开始生成视频",
                    "progress": 1,
                    "timestamp": datetime.now().isoformat(),
                })
            )
        except Exception:
            pass

        segments: List[Dict[str, Any]] = p.script.get("segments") or []
        if not segments:
            raise ValueError("脚本中没有可用的 segments")

        input_abs = VideoGenerationService._resolve_path(p.video_path)
        if not input_abs.exists():
            raise ValueError("原始视频文件不存在")
        input_dur = await video_processor._ffprobe_duration(str(input_abs), "format") or 0.0
        try:
            input_size = input_abs.stat().st_size
        except Exception:
            input_size = None
        logger.info(f"DEBUG input_file path={input_abs} size={input_size} duration={input_dur} segments={len(segments)}")

        # 片段输出与最终输出路径
        uploads_root = _uploads_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 输出目录：uploads/videos/outputs/{project_name}
        project_dir_name = VideoGenerationService._safe_dir_name(p.name or p.id, p.id)
        outputs_dir = uploads_root / "videos" / "outputs" / project_dir_name
        outputs_dir.mkdir(parents=True, exist_ok=True)
        output_name = f"{p.id}_output_{ts}.mp4"
        output_abs = outputs_dir / output_name

        # 片段临时目录：uploads/videos/tmp/{project_id}_{ts}
        tmp_dir = uploads_root / "videos" / "tmp" / f"{p.id}_{ts}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        # 配音临时目录：uploads/audios/tmp/{project_id}_{ts}
        aud_tmp_dir = uploads_root / "audios" / "tmp" / f"{p.id}_{ts}"
        aud_tmp_dir.mkdir(parents=True, exist_ok=True)

        async def _ensure_clip_video_not_longer_than_audio(clip_path: Path) -> Path:
            tol = 0.05
            try:
                if cancel_event.is_set():
                    raise asyncio.CancelledError()
                if not clip_path.exists():
                    return clip_path
                adur = await video_processor._ffprobe_duration(str(clip_path), "audio") or 0.0
                if adur <= 0.0:
                    return clip_path
                vdur = await video_processor._ffprobe_video_duration(str(clip_path))
                if vdur is None:
                    vdur = await video_processor._ffprobe_duration(str(clip_path), "format")
                vdur = float(vdur or 0.0)
                if vdur <= 0.0 or vdur <= (adur + tol):
                    return clip_path

                out_copy = clip_path.with_name(f"{clip_path.stem}_sync{clip_path.suffix}")
                cmd_copy = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(clip_path),
                    "-c",
                    "copy",
                    "-shortest",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(out_copy),
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd_copy,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW,
                )
                task_cancel_store.register_process("generate_video", project_id, task_id, proc)
                try:
                    _, stderr = await video_processor._communicate_with_cancel(proc, cancel_event)
                finally:
                    task_cancel_store.unregister_process("generate_video", project_id, task_id, proc)
                if proc.returncode == 0 and out_copy.exists():
                    v2 = await video_processor._ffprobe_video_duration(str(out_copy))
                    if v2 is None:
                        v2 = await video_processor._ffprobe_duration(str(out_copy), "format")
                    v2 = float(v2 or 0.0)
                    if v2 > 0.0 and v2 <= (adur + tol):
                        return out_copy

                out_re = clip_path.with_name(f"{clip_path.stem}_sync_re{clip_path.suffix}")
                adur_str = f"{adur:.3f}"
                enc_name, vcodec_args_pick = await video_processor._pick_fast_encoder()
                vcodec_args = list(vcodec_args_pick)
                if enc_name == "h264_nvenc":
                    vcodec_args.extend(["-rc:v", "vbr_hq", "-cq:v", "19"])
                elif enc_name == "libx264":
                    vcodec_args.extend(["-crf", "18"])
                pix_fmt = "nv12" if enc_name in {"h264_qsv", "h264_amf"} else "yuv420p"
                vcodec_args.extend(["-pix_fmt", pix_fmt, "-movflags", "+faststart"])
                filter_complex = (
                    f"[0:v]trim=start=0:end={adur_str},setpts=PTS-STARTPTS[v];"
                    f"[0:a]atrim=0:{adur_str},asetpts=PTS-STARTPTS[a]"
                )
                cmd_re = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(clip_path),
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    *vcodec_args,
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-ar",
                    "48000",
                    "-y",
                    str(out_re),
                ]
                proc2 = await asyncio.create_subprocess_exec(
                    *cmd_re,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW,
                )
                task_cancel_store.register_process("generate_video", project_id, task_id, proc2)
                try:
                    _, stderr2 = await video_processor._communicate_with_cancel(proc2, cancel_event)
                finally:
                    task_cancel_store.unregister_process("generate_video", project_id, task_id, proc2)
                if proc2.returncode == 0 and out_re.exists():
                    v3 = await video_processor._ffprobe_video_duration(str(out_re))
                    if v3 is None:
                        v3 = await video_processor._ffprobe_duration(str(out_re), "format")
                    v3 = float(v3 or 0.0)
                    if v3 > 0.0 and v3 <= (adur + tol):
                        return out_re
                if proc2.returncode != 0:
                    try:
                        _ = (stderr2 or stderr or b"").decode(errors="ignore")
                    except Exception:
                        _ = ""
                return clip_path
            except asyncio.CancelledError:
                raise
            except Exception:
                return clip_path

        try:
            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "progress",
                        "scope": "generate_video",
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "prepare_output",
                        "message": "准备输出与临时目录",
                        "progress": 10,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass

            clip_paths: List[str] = []
            total_segments = len(segments)
            logger.info(f"DEBUG segments_total count={total_segments}")
            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "progress",
                        "scope": "generate_video",
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "cutting_segments_start",
                        "message": "正在剪切视频片段并生成配音",
                        "progress": 15,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass
            segment_items: List[Dict[str, Any]] = []
            for idx, seg in enumerate(segments, start=1):
                if cancel_event.is_set():
                    raise asyncio.CancelledError()
                start = float(seg.get("start_time", 0.0))
                end = float(seg.get("end_time", 0.0))
                if end <= start:
                    raise ValueError(f"无效片段: idx={idx} start={start} end={end}")
                duration = max(0.0, end - start)
                clip_name = f"clip_{idx:04d}.mp4"
                clip_abs = tmp_dir / clip_name
                text = str(seg.get("text", "") or "").strip()
                ost_flag = seg.get("OST")
                is_original = (ost_flag == 1) or text.startswith("播放原片")
                logger.info(
                    "DEBUG segment_init idx=%s start=%.3f end=%.3f duration=%.3f ost=%s text_len=%s is_original=%s",
                    idx,
                    start,
                    end,
                    duration,
                    ost_flag,
                    len(text),
                    is_original,
                )

                ok = await video_processor.cut_video_segment(
                    str(input_abs),
                    str(clip_abs),
                    start,
                    duration,
                    scope="generate_video",
                    project_id=project_id,
                    task_id=task_id,
                    cancel_event=cancel_event,
                )
                if not ok:
                    raise RuntimeError(f"剪切片段失败: {idx}")

                try:
                    clip_size = clip_abs.stat().st_size
                except Exception:
                    clip_size = None
                logger.info(f"DEBUG segment_clip idx={idx} path={clip_abs} size={clip_size}")

                segment_items.append({
                    "idx": idx,
                    "start": start,
                    "end": end,
                    "duration": duration,
                    "text": text,
                    "is_original": is_original,
                    "clip_abs": clip_abs,
                })
                try:
                    base = 15
                    span = 15
                    progress = base + int((idx / max(1, total_segments)) * span)
                    await manager.broadcast(
                        __import__("json").dumps({
                            "type": "progress",
                            "scope": "generate_video",
                            "project_id": project_id,
                            "task_id": task_id,
                            "phase": "cutting_segments_progress",
                            "message": f"已剪切片段 {idx}/{total_segments}",
                            "progress": min(30, progress),
                            "timestamp": datetime.now().isoformat(),
                        })
                    )
                except Exception:
                    pass

            need_tts = [it for it in segment_items if not bool(it.get("is_original"))]
            tts_results: Dict[int, Dict[str, Any]] = {}
            _cfg_tts = tts_engine_config_manager.get_active_config()
            _tts_provider = (getattr(_cfg_tts, "provider", None) or "").lower()
            if need_tts:
                try:
                    _tts_msg = (
                        f"串行生成配音（{len(need_tts)} 段）"
                        if _tts_provider == "omnivoice_tts"
                        else f"并发生成配音（{len(need_tts)} 段）"
                    )
                    await manager.broadcast(
                        __import__("json").dumps({
                            "type": "progress",
                            "scope": "generate_video",
                            "project_id": project_id,
                            "task_id": task_id,
                            "phase": "tts_generate",
                            "message": _tts_msg,
                            "progress": 31,
                            "timestamp": datetime.now().isoformat(),
                        })
                    )
                except Exception:
                    pass

                async def _tts_job(idx: int, text: str, out_path: Path):
                    if cancel_event.is_set():
                        raise asyncio.CancelledError()
                    res = await tts_service.synthesize(text, str(out_path), None)
                    if not res.get("success"):
                        raise RuntimeError(f"TTS合成失败: {idx} - {res.get('error')}")
                    return idx, (res if isinstance(res, dict) else {})

                if _tts_provider == "omnivoice_tts":
                    completed = 0
                    for it in need_tts:
                        if cancel_event.is_set():
                            raise asyncio.CancelledError()
                        idx = int(it["idx"])
                        seg_audio = aud_tmp_dir / f"seg_{idx:04d}.mp3"
                        idx, r = await _tts_job(idx, str(it.get("text") or ""), seg_audio)
                        tts_results[idx] = r
                        completed += 1
                        try:
                            base = 31
                            span = 19
                            prog = base + int((completed / max(1, len(need_tts))) * span)
                            await manager.broadcast(
                                __import__("json").dumps({
                                    "type": "progress",
                                    "scope": "generate_video",
                                    "project_id": project_id,
                                    "task_id": task_id,
                                    "phase": "tts_generate_progress",
                                    "message": f"配音生成中 {completed}/{len(need_tts)}",
                                    "progress": min(50, prog),
                                    "timestamp": datetime.now().isoformat(),
                                })
                            )
                        except Exception:
                            pass
                else:
                    tasks: List[asyncio.Task] = []
                    for it in need_tts:
                        idx = int(it["idx"])
                        seg_audio = aud_tmp_dir / f"seg_{idx:04d}.mp3"
                        tasks.append(asyncio.create_task(_tts_job(idx, str(it.get("text") or ""), seg_audio)))

                    completed = 0
                    try:
                        for fut in asyncio.as_completed(tasks):
                            if cancel_event.is_set():
                                raise asyncio.CancelledError()
                            try:
                                idx, r = await fut
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                for ot in tasks:
                                    if ot is not fut and not ot.done():
                                        try:
                                            ot.cancel()
                                        except Exception:
                                            pass
                                raise
                            tts_results[idx] = r
                            completed += 1
                            try:
                                base = 31
                                span = 19
                                prog = base + int((completed / max(1, len(need_tts))) * span)
                                await manager.broadcast(
                                    __import__("json").dumps({
                                        "type": "progress",
                                        "scope": "generate_video",
                                        "project_id": project_id,
                                        "task_id": task_id,
                                        "phase": "tts_generate_progress",
                                        "message": f"配音生成中 {completed}/{len(need_tts)}",
                                        "progress": min(50, prog),
                                        "timestamp": datetime.now().isoformat(),
                                    })
                                )
                            except Exception:
                                pass
                    finally:
                        for ot in tasks:
                            if not ot.done():
                                try:
                                    ot.cancel()
                                except Exception:
                                    pass

                try:
                    cfg = tts_engine_config_manager.get_active_config()
                    provider = (getattr(cfg, "provider", None) or "").lower()
                    if provider in ("qwen3_tts", "indextts", "omnivoice_tts"):
                        total_tts_dur = 0.0
                        missing = 0
                        for it in need_tts:
                            idx = int(it.get("idx") or 0)
                            r = tts_results.get(idx) or {}
                            d0 = r.get("duration")
                            if isinstance(d0, (int, float)):
                                d = float(d0)
                            elif isinstance(d0, str):
                                try:
                                    d = float(d0.strip())
                                except Exception:
                                    d = 0.0
                            else:
                                d = 0.0
                            if d <= 0.0:
                                seg_audio = aud_tmp_dir / f"seg_{idx:04d}.mp3"
                                d = await video_processor._ffprobe_duration(str(seg_audio), "audio") or 0.0
                            if d > 0.0:
                                total_tts_dur += d
                            else:
                                missing += 1
                        logger.info(
                            "QwenTTS 总配音时长: project_id=%s task_id=%s segments=%s total_duration_s=%.3f missing=%s",
                            project_id,
                            task_id,
                            len(need_tts),
                            total_tts_dur,
                            missing,
                        )
                except Exception:
                    pass

            for it in segment_items:
                idx = int(it["idx"])
                start = float(it["start"])
                end = float(it["end"])
                duration = float(it["duration"])
                text = str(it.get("text") or "").strip()
                is_original = bool(it.get("is_original"))
                clip_abs: Path = it["clip_abs"]

                if cancel_event.is_set():
                    raise asyncio.CancelledError()

                if is_original:
                    clip_final = await _ensure_clip_video_not_longer_than_audio(clip_abs)
                    clip_paths.append(str(clip_final))
                    logger.info(f"DEBUG segment_use_original idx={idx} path={clip_abs}")
                else:
                    seg_audio = aud_tmp_dir / f"seg_{idx:04d}.mp3"
                    sy = tts_results.get(idx)
                    if not sy:
                        raise RuntimeError(f"TTS合成失败: {idx} - missing_result")
                    adur = float(sy.get("duration") or 0.0) if isinstance(sy.get("duration"), (int, float)) else 0.0
                    if adur <= 0.0:
                        adur = await video_processor._ffprobe_duration(str(seg_audio), "audio") or 0.0
                    try:
                        seg_audio_size = seg_audio.stat().st_size
                    except Exception:
                        seg_audio_size = None
                    logger.info(f"DEBUG tts_audio idx={idx} path={seg_audio} size={seg_audio_size} duration={adur}")
                    if adur > 0.0 and input_dur > 0.0 and adur > duration:
                        ext = adur - duration
                        fwd = max(0.0, input_dur - end)
                        if fwd >= ext:
                            new_start = start
                            new_dur = duration + ext
                        else:
                            shortage = ext - fwd
                            new_start = max(0.0, start - shortage)
                            new_dur = input_dur - new_start
                        logger.info(f"DEBUG segment_extend idx={idx} new_start={new_start} new_dur={new_dur}")
                        ok2 = await video_processor.cut_video_segment(
                            str(input_abs),
                            str(clip_abs),
                            new_start,
                            new_dur,
                            scope="generate_video",
                            project_id=project_id,
                            task_id=task_id,
                            cancel_event=cancel_event,
                        )
                        if not ok2:
                            raise RuntimeError(f"片段延长失败: {idx}")
                    elif adur > 0.0 and (adur + 0.05) < duration:
                        new_start = start
                        new_dur = adur
                        logger.info(f"DEBUG segment_shorten idx={idx} new_start={new_start} new_dur={new_dur}")
                        ok2s = await video_processor.cut_video_segment(
                            str(input_abs),
                            str(clip_abs),
                            new_start,
                            new_dur,
                            scope="generate_video",
                            project_id=project_id,
                            task_id=task_id,
                            cancel_event=cancel_event,
                        )
                        if not ok2s:
                            raise RuntimeError(f"片段缩短失败: {idx}")
                    clip_nar_abs = clip_abs.with_name(f"{clip_abs.stem}_nar{clip_abs.suffix}")
                    rep_ok = await video_processor.replace_audio_with_narration(
                        str(clip_abs),
                        str(seg_audio),
                        str(clip_nar_abs),
                        scope="generate_video",
                        project_id=project_id,
                        task_id=task_id,
                        cancel_event=cancel_event,
                    )
                    if not rep_ok:
                        raise RuntimeError(f"片段配音替换失败: {idx}")
                    try:
                        clip_nar_size = clip_nar_abs.stat().st_size
                    except Exception:
                        clip_nar_size = None
                    logger.info(f"DEBUG segment_narration idx={idx} path={clip_nar_abs} size={clip_nar_size}")
                    vinfo_chk, _ = await video_processor._probe_stream_info(str(clip_nar_abs))
                    if vinfo_chk is None:
                        logger.info(f"DEBUG segment_narration_fallback idx={idx} reencode nar to ensure video stream")
                        cmd_fb = [
                            "ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-i", str(clip_abs),
                            "-i", str(seg_audio),
                            "-map", "0:v:0", "-map", "1:a:0",
                            "-c:v", "libx264", "-preset", "superfast", "-crf", "18",
                            "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                            "-shortest",
                            "-y", str(clip_nar_abs),
                        ]
                        p3 = await asyncio.create_subprocess_exec(
                            *cmd_fb,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            creationflags=WIN_NO_WINDOW,
                        )
                        task_cancel_store.register_process("generate_video", project_id, task_id, p3)
                        try:
                            comm_task = asyncio.create_task(p3.communicate())
                            cancel_task = asyncio.create_task(cancel_event.wait())
                            done, _ = await asyncio.wait({comm_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
                            if cancel_task in done:
                                try:
                                    if p3.returncode is None:
                                        try:
                                            p3.terminate()
                                        except Exception:
                                            pass
                                finally:
                                    try:
                                        await asyncio.wait_for(comm_task, timeout=1.5)
                                    except Exception:
                                        try:
                                            comm_task.cancel()
                                        except Exception:
                                            pass
                                raise asyncio.CancelledError()
                            try:
                                cancel_task.cancel()
                            except Exception:
                                pass
                            _, e3 = await comm_task
                        finally:
                            task_cancel_store.unregister_process("generate_video", project_id, task_id, p3)
                        if p3.returncode != 0:
                            raise RuntimeError(f"片段配音替换失败(强制重编码): {idx} - {e3.decode(errors='ignore')}")
                        vinfo_chk2, _ = await video_processor._probe_stream_info(str(clip_nar_abs))
                        if vinfo_chk2 is None:
                            logger.warning(f"片段配音替换失败(无视频流), 降级使用原片音轨: {idx}")
                            clip_final_fb = await _ensure_clip_video_not_longer_than_audio(clip_abs)
                            clip_paths.append(str(clip_final_fb))
                            continue
                    clip_final_nar = await _ensure_clip_video_not_longer_than_audio(clip_nar_abs)
                    clip_paths.append(str(clip_final_nar))

                try:
                    base = 50
                    span = 20
                    progress = base + int((idx / max(1, total_segments)) * span)
                    await manager.broadcast(
                        __import__("json").dumps({
                            "type": "progress",
                            "scope": "generate_video",
                            "project_id": project_id,
                            "task_id": task_id,
                            "phase": "segment_processed",
                            "message": f"已处理片段 {idx}/{total_segments}",
                            "progress": min(70, progress),
                            "timestamp": datetime.now().isoformat(),
                        })
                    )
                except Exception:
                    pass

            if not clip_paths:
                raise ValueError("未生成任何有效片段，无法拼接")

            missing_paths = [p for p in clip_paths if not Path(p).exists()]
            logger.info(f"DEBUG clip_paths_ready count={len(clip_paths)} missing={len(missing_paths)} output={output_abs}")
            for cidx, pth in enumerate(clip_paths, start=1):
                p_path = Path(pth)
                try:
                    p_size = p_path.stat().st_size
                except Exception:
                    p_size = None
                vinfo, ainfo = await video_processor._probe_stream_info(str(p_path))
                logger.info(f"DEBUG concat_input idx={cidx} path={p_path} size={p_size} vinfo={vinfo} ainfo={ainfo}")

            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "progress",
                        "scope": "generate_video",
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "concat_start",
                        "message": "正在拼接视频片段",
                        "progress": 75,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass

            ok_concat = await video_processor.concat_videos(
                clip_paths,
                str(output_abs),
                scope="generate_video",
                project_id=project_id,
                task_id=task_id,
                cancel_event=cancel_event,
                force_reencode=True,
            )
            if not ok_concat:
                try:
                    if tmp_dir.exists():
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass
                err = getattr(video_processor, "last_concat_error", None) or ""
                if err:
                    raise RuntimeError(f"拼接视频失败: {str(err).strip()[:400]}")
                raise RuntimeError("拼接视频失败")

            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "progress",
                        "scope": "generate_video",
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "concat_done",
                        "message": "片段拼接完成",
                        "progress": 85,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass

            final_abs = output_abs
            try:
                for f in outputs_dir.glob("*.mp4"):
                    if f != final_abs:
                        try:
                            if f.exists():
                                f.unlink()
                        except Exception:
                            pass
            except Exception:
                pass
            web_output = _to_web_path(final_abs)
            projects_store.update_project(project_id, {"output_video_path": web_output, "status": "completed"})

            result = {
                "output_path": web_output,
                "segments_count": len(clip_paths),
                "started_at": datetime.now().isoformat(),
                "finished_at": datetime.now().isoformat(),
            }

            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "completed",
                        "scope": "generate_video",
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "done",
                        "message": "视频生成成功",
                        "progress": 100,
                        "timestamp": datetime.now().isoformat(),
                        "data": result,
                    })
                )
            except Exception:
                pass

            return result
        finally:
            try:
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            try:
                if aud_tmp_dir.exists():
                    shutil.rmtree(aud_tmp_dir, ignore_errors=True)
            except Exception:
                pass


video_generation_service = VideoGenerationService()
