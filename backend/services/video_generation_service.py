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
from modules.video_processor import video_processor
from modules.tts_service import tts_service
from modules.ws_manager import manager

logger = logging.getLogger(__name__)


def _backend_root_dir() -> Path:
    # backend/services/... -> backend -> project root
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def _uploads_dir() -> Path:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    (up / "videos").mkdir(parents=True, exist_ok=True)
    return up


def _to_web_path(p: Path) -> str:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    rel = p.relative_to(up)
    return "/uploads/" + str(rel).replace("\\", "/")


class VideoGenerationService:
    @staticmethod
    def _resolve_path(path_or_web: str) -> Path:
        root = _backend_root_dir()
        path_str = (path_or_web or "").strip()
        if not path_str:
            return Path("")
        s_norm = path_str.replace("\\", "/")
        if s_norm.startswith("/uploads/") or s_norm == "/uploads":
            env = os.environ.get("SACV_UPLOADS_DIR")
            rel = s_norm[len("/uploads/"):] if s_norm.startswith("/uploads/") else ""
            candidates: List[Path] = []
            try:
                if env:
                    candidates.append(Path(env) / rel)
            except Exception:
                pass
            try:
                candidates.append((_backend_root_dir() / "uploads") / rel)
            except Exception:
                pass
            for c in candidates:
                try:
                    if c.exists():
                        return c
                except Exception:
                    pass
            return candidates[0] if candidates else Path(rel)
        if s_norm.startswith("/"):
            return root / s_norm[1:]
        try:
            p = Path(path_str)
            if p.is_absolute():
                return p
        except Exception:
            pass
        return Path(path_str)

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
    async def generate_from_script(project_id: str) -> Dict[str, Any]:
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

        try:
            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "progress",
                        "scope": "generate_video",
                        "project_id": project_id,
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
                        "phase": "cutting_segments_start",
                        "message": "正在剪切视频片段并生成配音",
                        "progress": 15,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass

            for idx, seg in enumerate(segments, start=1):
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
                logger.info(f"DEBUG segment_init idx={idx} start={start} end={end} duration={duration} ost={ost_flag} text_len={len(text)} is_original={is_original}")

                ok = await video_processor.cut_video_segment(
                    str(input_abs), str(clip_abs), start, duration
                )
                if not ok:
                    raise RuntimeError(f"剪切片段失败: {idx}")

                try:
                    clip_size = clip_abs.stat().st_size
                except Exception:
                    clip_size = None
                logger.info(f"DEBUG segment_clip idx={idx} path={clip_abs} size={clip_size}")

                if is_original:
                    clip_paths.append(str(clip_abs))
                    logger.info(f"DEBUG segment_use_original idx={idx} path={clip_abs}")
                else:
                    seg_audio = aud_tmp_dir / f"seg_{idx:04d}.mp3"
                    sy = await tts_service.synthesize(text, str(seg_audio), None)
                    if not sy.get("success"):
                        raise RuntimeError(f"TTS合成失败: {idx} - {sy.get('error')}")
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
                            str(input_abs), str(clip_abs), new_start, new_dur
                        )
                        if not ok2:
                            raise RuntimeError(f"片段延长失败: {idx}")
                    elif adur > 0.0 and (adur + 0.05) < duration:
                        new_start = start
                        new_dur = adur
                        logger.info(f"DEBUG segment_shorten idx={idx} new_start={new_start} new_dur={new_dur}")
                        ok2s = await video_processor.cut_video_segment(
                            str(input_abs), str(clip_abs), new_start, new_dur
                        )
                        if not ok2s:
                            raise RuntimeError(f"片段缩短失败: {idx}")
                    clip_nar_abs = clip_abs.with_name(f"{clip_abs.stem}_nar{clip_abs.suffix}")
                    rep_ok = await video_processor.replace_audio_with_narration(str(clip_abs), str(seg_audio), str(clip_nar_abs))
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
                            stderr=asyncio.subprocess.PIPE
                        )
                        _, e3 = await p3.communicate()
                        if p3.returncode != 0:
                            raise RuntimeError(f"片段配音替换失败(强制重编码): {idx} - {e3.decode(errors='ignore')}")
                        vinfo_chk2, _ = await video_processor._probe_stream_info(str(clip_nar_abs))
                        if vinfo_chk2 is None:
                            logger.warning(f"片段配音替换失败(无视频流), 降级使用原片音轨: {idx}")
                            clip_paths.append(str(clip_abs))
                            continue
                    clip_paths.append(str(clip_nar_abs))

                try:
                    base = 15
                    span = 55
                    progress = base + int((idx / max(1, total_segments)) * span)
                    await manager.broadcast(
                        __import__("json").dumps({
                            "type": "progress",
                            "scope": "generate_video",
                            "project_id": project_id,
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
                        "phase": "concat_start",
                        "message": "正在拼接视频片段",
                        "progress": 75,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass

            ok_concat = await video_processor.concat_videos(clip_paths, str(output_abs))
            if not ok_concat:
                try:
                    if tmp_dir.exists():
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass
                raise RuntimeError("拼接视频失败")

            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "progress",
                        "scope": "generate_video",
                        "project_id": project_id,
                        "phase": "concat_done",
                        "message": "片段拼接完成",
                        "progress": 85,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass

            norm_abs = outputs_dir / f"{p.id}_output_{ts}_normalized.mp4"
            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "progress",
                        "scope": "generate_video",
                        "project_id": project_id,
                        "phase": "normalize_start",
                        "message": "正在统一响度标准化",
                        "progress": 90,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass

            ok_norm = await video_processor.audio_normalizer.normalize_video_loudness(str(output_abs), str(norm_abs))
            if not ok_norm:
                raise RuntimeError("响度标准化失败")
            try:
                if output_abs.exists():
                    output_abs.unlink()
            except Exception:
                pass
            final_abs = norm_abs
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

            try:
                await manager.broadcast(
                    __import__("json").dumps({
                        "type": "progress",
                        "scope": "generate_video",
                        "project_id": project_id,
                        "phase": "normalize_done",
                        "message": "响度标准化完成",
                        "progress": 95,
                        "timestamp": datetime.now().isoformat(),
                    })
                )
            except Exception:
                pass

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
