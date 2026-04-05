#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频处理模块
集成FFmpeg、OpenCV和PyTorch进行AI智能视频剪辑
"""

import asyncio
import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json

import cv2
import numpy as np
from .audio_normalizer import AudioNormalizer
from modules.task_cancel_store import task_cancel_store

logger = logging.getLogger(__name__)
WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _concat_list_file_encoding() -> str:
    """concat 列表必须用无 BOM 的 UTF-8：带 BOM 时首行会变成「\\ufefffile ...」，ffmpeg 报 unknown keyword file。"""
    return "utf-8"

class VideoProcessor:
    """视频处理器类"""
    
    def __init__(self):
        self.supported_formats = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
        self.audio_normalizer = AudioNormalizer()
        self.last_concat_error: Optional[str] = None
        self.last_concat_cmd: Optional[List[str]] = None
        self._encoder_usable_cache: Dict[str, bool] = {}

    def _should_track(self, scope: Optional[str], project_id: Optional[str], task_id: Optional[str], cancel_event: Optional[asyncio.Event]) -> bool:
        return bool(scope and project_id and task_id and cancel_event)

    def _register_proc(self, scope: str, project_id: str, task_id: str, proc: asyncio.subprocess.Process) -> None:
        try:
            task_cancel_store.register_process(scope, project_id, task_id, proc)
        except Exception:
            return

    def _unregister_proc(self, scope: str, project_id: str, task_id: str, proc: asyncio.subprocess.Process) -> None:
        try:
            task_cancel_store.unregister_process(scope, project_id, task_id, proc)
        except Exception:
            return

    async def _communicate_with_cancel(
        self,
        proc: asyncio.subprocess.Process,
        cancel_event: Optional[asyncio.Event],
    ) -> Tuple[bytes, bytes]:
        if not cancel_event:
            return await proc.communicate()

        comm_task = asyncio.create_task(proc.communicate())
        cancel_task = asyncio.create_task(cancel_event.wait())
        done, pending = await asyncio.wait({comm_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
        if cancel_task in done:
            try:
                if proc.returncode is None:
                    try:
                        proc.terminate()
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
        return await comm_task
    
    async def cut_video_segment(
        self,
        input_path: str,
        output_path: str,
        start_time: float,
        duration: float,
        *,
        scope: Optional[str] = None,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> bool:
        """剪切视频片段
        说明：为减少后续拼接处出现非关键帧引起的卡顿，将 `-ss` 前置到 `-i` 之前，
        以便按关键帧就近截取（仍使用 `-c copy` 保持高效）。
        """
        try:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", input_path,
                "-c", "copy",  # 不重新编码，快速剪切（关键帧对齐更稳定）
                "-y",
                output_path
            ]

            logger.info(f"剪切视频片段(关键帧对齐): {start_time}s-{start_time+duration}s -> {output_path}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW
            )

            tracking = self._should_track(scope, project_id, task_id, cancel_event)
            if tracking:
                self._register_proc(str(scope), str(project_id), str(task_id), process)
            try:
                stdout, stderr = await self._communicate_with_cancel(process, cancel_event)
            finally:
                if tracking:
                    self._unregister_proc(str(scope), str(project_id), str(task_id), process)

            if process.returncode == 0:
                try:
                    dur = await self._ffprobe_video_duration(output_path)
                except Exception:
                    dur = None
                if dur is not None and dur > 0.01:
                    try:
                        a_dur = await self._ffprobe_duration(output_path, "audio")
                        a_dur_val = float(a_dur or 0.0)
                    except Exception:
                        a_dur_val = 0.0
                    tol = 0.20
                    if a_dur_val > 0.0 and (a_dur_val + tol) < float(dur):
                        logger.warning(
                            "剪切结果音画时长不一致，进入重编码回退: audio=%.3fs video=%.3fs target=%.3fs path=%s",
                            a_dur_val,
                            float(dur),
                            float(duration),
                            output_path,
                        )
                    else:
                        logger.info(f"视频剪切成功: {output_path}")
                        return True
                logger.warning("剪切结果时长异常，进入重编码回退")
            else:
                err = stderr.decode(errors="ignore")
                logger.error(f"视频剪切失败，进入重编码回退: {err}")

            try:
                enc_name, vcodec_args = await self._pick_fast_encoder()
            except Exception:
                enc_name, vcodec_args = ("libx264", ["-c:v", "libx264", "-preset", "superfast", "-crf", "18"])
            reencode_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-i", input_path,
                "-ss", str(start_time),
                "-t", str(duration),
                *vcodec_args,
                "-pix_fmt", self._preferred_pix_fmt(enc_name),
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                "-movflags", "+faststart",
                "-y",
                output_path
            ]
            p2 = await asyncio.create_subprocess_exec(
                *reencode_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW
            )
            tracking2 = self._should_track(scope, project_id, task_id, cancel_event)
            if tracking2:
                self._register_proc(str(scope), str(project_id), str(task_id), p2)
            try:
                _, e2 = await self._communicate_with_cancel(p2, cancel_event)
            finally:
                if tracking2:
                    self._unregister_proc(str(scope), str(project_id), str(task_id), p2)
            if p2.returncode == 0:
                try:
                    dur2 = await self._ffprobe_video_duration(output_path)
                except Exception:
                    dur2 = None
                if dur2 is not None and dur2 > 0.01:
                    logger.info(f"视频剪切成功(重编码): {output_path}")
                    return True
                logger.error("重编码剪切后时长仍为0")
                return False
            else:
                logger.error(f"视频剪切失败(重编码): {e2.decode(errors='ignore')}")
                return False

        except Exception as e:
            logger.error(f"剪切视频时出错: {e}")
            return False

    async def concat_videos(
        self,
        inputs: List[str],
        output_path: str,
        on_progress=None,
        *,
        scope: Optional[str] = None,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
        force_reencode: bool = False,
    ) -> bool:
        """
        """
        try:
            self.last_concat_error = None
            self.last_concat_cmd = None
            if not inputs:
                logger.error("拼接视频失败: 输入列表为空")
                return False

            n = len(inputs)

            async def _concat_in_batches(batch_size: int = 20) -> bool:
                tmp_dir = Path(output_path).parent
                token_b = uuid.uuid4().hex[:10]
                outputs: List[str] = []
                num_batches = (n + batch_size - 1) // batch_size

                try:
                    for bi in range(num_batches):
                        start = bi * batch_size
                        end = min(start + batch_size, n)
                        out_i = tmp_dir / f".concat_{token_b}_b{bi}.mp4"
                        outputs.append(str(out_i))

                        async def _on_batch_progress(pct: float, _bi: int = bi) -> None:
                            if not on_progress:
                                return
                            portion = 90.0 / float(num_batches)
                            base = float(_bi) * portion
                            mapped = base + (max(0.0, min(100.0, float(pct))) * (portion / 100.0))
                            await on_progress(mapped)

                        ok_i = await self.concat_videos(
                            inputs[start:end],
                            str(out_i),
                            _on_batch_progress if on_progress else None,
                            scope=scope,
                            project_id=project_id,
                            task_id=task_id,
                            cancel_event=cancel_event,
                            force_reencode=force_reencode,
                        )
                        if not ok_i:
                            return False

                    async def _on_final_progress(pct: float) -> None:
                        if not on_progress:
                            return
                        mapped = 90.0 + (max(0.0, min(100.0, float(pct))) * 0.10)
                        await on_progress(mapped)

                    ok_final = await self.concat_videos(
                        outputs,
                        output_path,
                        _on_final_progress if on_progress else None,
                        scope=scope,
                        project_id=project_id,
                        task_id=task_id,
                        cancel_event=cancel_event,
                        force_reencode=force_reencode,
                    )
                    return ok_final
                finally:
                    for p in outputs:
                        try:
                            fp = Path(p)
                            if fp.exists():
                                fp.unlink()
                        except Exception:
                            pass

            if n == 1:
                src = str(inputs[0])
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-i", src,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    "-y", output_path,
                ]
                self.last_concat_cmd = cmd
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW
                )
                tracking = self._should_track(scope, project_id, task_id, cancel_event)
                if tracking:
                    self._register_proc(str(scope), str(project_id), str(task_id), process)
                try:
                    _, stderr = await self._communicate_with_cancel(process, cancel_event)
                finally:
                    if tracking:
                        self._unregister_proc(str(scope), str(project_id), str(task_id), process)
                if process.returncode == 0:
                    if on_progress:
                        try:
                            await on_progress(100.0)
                        except Exception:
                            pass
                    return True
                err = stderr.decode(errors="ignore")
                self.last_concat_error = err.strip() or "单段重封装失败"
                logger.error(f"视频拼接失败: {err}")
                return False

            durations: List[float] = []
            has_audio: List[bool] = []
            vinfo_list: List[Dict[str, Any]] = []
            ainfo_list: List[Optional[Dict[str, Any]]] = []
            format_names: List[str] = []
            keyframe_starts: List[bool] = []
            for p in inputs:
                d = await self._ffprobe_video_duration(p)
                if d is None:
                    d = await self._ffprobe_duration(p, "format")
                d = d or 0.0
                durations.append(max(d, 0.0))
                a_dur = await self._ffprobe_duration(p, "audio")
                has_audio.append(a_dur is not None and a_dur > 0.0)
                vi, ai = await self._probe_stream_info(p)
                vinfo_list.append(vi or {})
                ainfo_list.append(ai)
                fmt = await self._ffprobe_format_name(p)
                format_names.append(fmt or "")
                kf = await self._first_frame_is_keyframe(p)
                keyframe_starts.append(bool(kf))

            def _fr_to_float(s: Optional[str]) -> Optional[float]:
                if not s:
                    return None
                try:
                    if "/" in s:
                        a, b = s.split("/")
                        return float(a) / float(b) if float(b) != 0 else None
                    return float(s)
                except Exception:
                    return None

            copy_possible = True
            if not vinfo_list:
                copy_possible = False
            else:
                base_v = vinfo_list[0]
                base_a = ainfo_list[0]
                base_fr = _fr_to_float(base_v.get("r_frame_rate"))
                for i in range(1, n):
                    vi = vinfo_list[i]
                    ai = ainfo_list[i]
                    if not vi:
                        copy_possible = False
                        break
                    fr = _fr_to_float(vi.get("r_frame_rate"))
                    if not (
                        vi.get("codec_name") == base_v.get("codec_name") and
                        vi.get("pix_fmt") == base_v.get("pix_fmt") and
                        vi.get("width") == base_v.get("width") and
                        vi.get("height") == base_v.get("height") and
                        ((fr is None and base_fr is None) or (fr is not None and base_fr is not None and abs(fr - base_fr) < 0.001))
                    ):
                        copy_possible = False
                        break
                    if (base_a is None) != (ai is None):
                        copy_possible = False
                        break
                    if base_a and ai:
                        if not (
                            ai.get("codec_name") == base_a.get("codec_name") and
                            ai.get("sample_rate") == base_a.get("sample_rate") and
                            ai.get("channels") == base_a.get("channels")
                        ):
                            copy_possible = False
                            break
            if force_reencode:
                copy_possible = False
            token = uuid.uuid4().hex[:10]
            can_concat_demuxer = False
            list_path = Path(output_path).with_suffix(f".{token}.concat.txt")
            if copy_possible:
                try:
                    lines = []
                    for p in inputs:
                        q = Path(p).as_posix()
                        lines.append(f"file '{q}'")
                    list_path.write_text("\n".join(lines), encoding=_concat_list_file_encoding())
                    can_concat_demuxer = True
                except Exception:
                    can_concat_demuxer = False

            vcodec0 = (vinfo_list[0] or {}).get("codec_name") if vinfo_list else None
            acodec0 = (ainfo_list[0] or {}).get("codec_name") if ainfo_list else None
            is_mp4_like = any(((format_names[i] or "").lower().find("mp4") != -1 or (format_names[i] or "").lower().find("mov") != -1) for i in range(n))
            is_h264_hevc = vcodec0 in {"h264", "hevc"}
            audio_all_same_codec = all(((ainfo_list[i] or {}).get("codec_name") == acodec0) for i in range(n)) if ainfo_list else True
            can_concat_ts = copy_possible and is_mp4_like and is_h264_hevc and (acodec0 in {None, "aac"}) and audio_all_same_codec

            if can_concat_ts:
                try:
                    bsfilter_v = "h264_mp4toannexb" if vcodec0 == "h264" else "hevc_mp4toannexb"
                    tmp_dir = Path(output_path).parent
                    ts_files: List[Path] = []
                    ts_list_path = tmp_dir / f".concat_{token}.ts.concat.txt"
                    procs = []
                    for idx, p in enumerate(inputs):
                        ts_path = tmp_dir / f".concat_{token}_{idx}.ts"
                        ts_files.append(ts_path)
                        cmd_ts = [
                            "ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-i", str(p),
                            "-c", "copy",
                            "-bsf:v", bsfilter_v,
                            "-f", "mpegts",
                            "-y", str(ts_path)
                        ]
                        procs.append(asyncio.create_subprocess_exec(
                            *cmd_ts,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            creationflags=WIN_NO_WINDOW
                        ))
                    created = await asyncio.gather(*procs, return_exceptions=True)
                    waits = []
                    for pr in created:
                        if hasattr(pr, "communicate"):
                            waits.append(pr.communicate())
                    if waits:
                        outs = await asyncio.gather(*waits, return_exceptions=True)
                        for pr in created:
                            if hasattr(pr, "returncode") and pr.returncode != 0:
                                can_concat_ts = False
                                break
                    if not can_concat_ts:
                        for f in ts_files:
                            try:
                                if f.exists():
                                    f.unlink()
                            except Exception:
                                pass
                    else:
                        try:
                            if on_progress:
                                await on_progress(5.0)
                        except Exception:
                            pass
                        try:
                            lines = []
                            for f in ts_files:
                                q = f.as_posix()
                                lines.append(f"file '{q}'")
                            ts_list_path.write_text("\n".join(lines), encoding=_concat_list_file_encoding())
                        except Exception:
                            can_concat_ts = False
                            for f in ts_files:
                                try:
                                    if f.exists():
                                        f.unlink()
                                except Exception:
                                    pass
                            try:
                                if ts_list_path.exists():
                                    ts_list_path.unlink()
                            except Exception:
                                pass
                            raise

                        cmd = [
                            "ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-f", "concat", "-safe", "0",
                            "-i", str(ts_list_path),
                            "-c", "copy",
                        ]
                        if acodec0 == "aac":
                            cmd.extend(["-bsf:a", "aac_adtstoasc"])
                        cmd.extend(["-progress", "pipe:1", "-y", output_path])
                        self.last_concat_cmd = cmd
                        process = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            creationflags=WIN_NO_WINDOW
                        )
                        tracking = self._should_track(scope, project_id, task_id, cancel_event)
                        if tracking:
                            self._register_proc(str(scope), str(project_id), str(task_id), process)
                        total_duration = sum(durations)
                        if on_progress:
                            try:
                                last_bucket = -1
                                seen_end = False
                                while True:
                                    if cancel_event and cancel_event.is_set():
                                        raise asyncio.CancelledError()
                                    rl = asyncio.create_task(process.stdout.readline())
                                    wt = asyncio.create_task(cancel_event.wait()) if cancel_event else None
                                    if wt:
                                        done, _ = await asyncio.wait({rl, wt}, return_when=asyncio.FIRST_COMPLETED)
                                        if wt in done:
                                            try:
                                                rl.cancel()
                                            except Exception:
                                                pass
                                            raise asyncio.CancelledError()
                                        line = await rl
                                        try:
                                            wt.cancel()
                                        except Exception:
                                            pass
                                    else:
                                        line = await rl
                                    if not line:
                                        break
                                    s = line.decode(errors="ignore").strip()
                                    if s.startswith("out_time_ms="):
                                        try:
                                            ms = float(s.split("=", 1)[1])
                                            if total_duration > 0:
                                                pct = (ms / (total_duration * 1000.0)) * 100.0
                                                if pct < 0:
                                                    pct = 0.0
                                                if pct > 100:
                                                    pct = 100.0
                                                if not seen_end and pct >= 100.0:
                                                    pct = 99.0
                                                await on_progress(pct)
                                                bucket = int(pct // 5)
                                                if bucket > last_bucket:
                                                    logger.info(f"拼接进度: {pct:.1f}%")
                                                    last_bucket = bucket
                                        except Exception:
                                            pass
                                    elif s.startswith("progress=") and s.endswith("end"):
                                        seen_end = True
                                        logger.info("拼接进度: 99.0% (等待完成)")
                            except Exception:
                                pass
                        try:
                            stdout, stderr = await self._communicate_with_cancel(process, cancel_event)
                        finally:
                            if tracking:
                                self._unregister_proc(str(scope), str(project_id), str(task_id), process)
                        for f in ts_files:
                            try:
                                if f.exists():
                                    f.unlink()
                            except Exception:
                                pass
                        try:
                            if ts_list_path.exists():
                                ts_list_path.unlink()
                        except Exception:
                            pass
                        if process.returncode == 0:
                            if on_progress:
                                try:
                                    await on_progress(100.0)
                                except Exception:
                                    pass
                            logger.info(f"视频拼接成功: {output_path}")
                            return True
                        else:
                            err = stderr.decode(errors="ignore")
                            self.last_concat_error = err.strip() or "concat(ts) 失败"
                            logger.error(f"视频拼接失败: {err}")
                            return False
                except Exception:
                    can_concat_ts = False

            if can_concat_demuxer and not can_concat_ts:
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-f", "concat", "-safe", "0",
                    "-i", str(list_path),
                    "-c", "copy",
                    "-progress", "pipe:1",
                    "-y", output_path,
                ]
                self.last_concat_cmd = cmd
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW
                )
                tracking = self._should_track(scope, project_id, task_id, cancel_event)
                if tracking:
                    self._register_proc(str(scope), str(project_id), str(task_id), process)
                total_duration = sum(durations)
                if on_progress:
                    try:
                        last_bucket = -1
                        seen_end = False
                        while True:
                            if cancel_event and cancel_event.is_set():
                                raise asyncio.CancelledError()
                            rl = asyncio.create_task(process.stdout.readline())
                            wt = asyncio.create_task(cancel_event.wait()) if cancel_event else None
                            if wt:
                                done, _ = await asyncio.wait({rl, wt}, return_when=asyncio.FIRST_COMPLETED)
                                if wt in done:
                                    try:
                                        rl.cancel()
                                    except Exception:
                                        pass
                                    raise asyncio.CancelledError()
                                line = await rl
                                try:
                                    wt.cancel()
                                except Exception:
                                    pass
                            else:
                                line = await rl
                            if not line:
                                break
                            s = line.decode(errors="ignore").strip()
                            if s.startswith("out_time_ms="):
                                try:
                                    ms = float(s.split("=", 1)[1])
                                    if total_duration > 0:
                                        pct = (ms / (total_duration * 1000.0)) * 100.0
                                        if pct < 0:
                                            pct = 0.0
                                        if pct > 100:
                                            pct = 100.0
                                        if not seen_end and pct >= 100.0:
                                            pct = 99.0
                                        await on_progress(pct)
                                        bucket = int(pct // 5)
                                        if bucket > last_bucket:
                                            logger.info(f"拼接进度: {pct:.1f}%")
                                            last_bucket = bucket
                                except Exception:
                                    pass
                            elif s.startswith("progress=") and s.endswith("end"):
                                seen_end = True
                                logger.info("拼接进度: 99.0% (等待完成)")
                    except Exception:
                        pass
                try:
                    stdout, stderr = await self._communicate_with_cancel(process, cancel_event)
                finally:
                    if tracking:
                        self._unregister_proc(str(scope), str(project_id), str(task_id), process)
                try:
                    if list_path.exists():
                        list_path.unlink()
                except Exception:
                    pass
                if process.returncode == 0:
                    if on_progress:
                        try:
                            await on_progress(100.0)
                        except Exception:
                            pass
                    logger.info(f"视频拼接成功: {output_path}")
                    return True
                else:
                    err = stderr.decode(errors="ignore")
                    self.last_concat_error = err.strip() or "concat(demuxer) 失败"
                    logger.error(f"视频拼接失败: {err}")
                    return False

            cmd: List[str] = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
            ]
            for p in inputs:
                cmd.extend(["-i", str(p)])

            # concat 要求各段视频分辨率、SAR、帧率等一致；仅做偶数对齐不足以统一不同尺寸的素材
            tw, th = 0, 0
            for vi in vinfo_list:
                if not vi:
                    continue
                try:
                    w = int(vi.get("width") or 0)
                    h = int(vi.get("height") or 0)
                except Exception:
                    w, h = 0, 0
                tw = max(tw, w)
                th = max(th, h)
            if tw < 2:
                tw = 1280
            if th < 2:
                th = 720
            tw = tw - (tw % 2)
            th = th - (th % 2)

            vf_parts = []
            for i in range(n):
                base_fr_val = _fr_to_float(vinfo_list[0].get("r_frame_rate")) if vinfo_list and vinfo_list[0] else None
                v_norm = (
                    f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                    f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
                )
                if base_fr_val is not None:
                    vf_parts.append(
                        f"[{i}:v:0]{v_norm},fps={base_fr_val},setpts=PTS-STARTPTS[v{i}]"
                    )
                else:
                    vf_parts.append(
                        f"[{i}:v:0]{v_norm},setpts=PTS-STARTPTS[v{i}]"
                    )
                if has_audio[i]:
                    vf_parts.append(f"[{i}:a:0]aresample=48000,asetpts=PTS-STARTPTS[a{i}]")
                else:
                    dur = durations[i]
                    vf_parts.append(
                        f"anullsrc=r=48000:cl=stereo,atrim=0:{dur},asetpts=PTS-STARTPTS[a{i}]"
                    )

            concat_inputs = "".join([f"[v{i}][a{i}]" for i in range(n)])
            filter_complex = ";".join(vf_parts) + f";{concat_inputs}concat=n={n}:v=1:a=1[v][a]"

            encoder_sets = await self._get_encoder_priority_list()
            last_err = None
            for vcodec_args in encoder_sets:
                enc_name = self._encoder_name_from_args(vcodec_args)
                pix_fmt = self._preferred_pix_fmt(enc_name)
                cmd_try = list(cmd)
                cmd_try.extend([
                    "-filter_complex", filter_complex,
                    "-map", "[v]", "-map", "[a]",
                    *vcodec_args,
                    "-pix_fmt", pix_fmt,
                    "-c:a", "aac", "-b:a", "128k"
                ])
                cmd_try.extend([
                    "-movflags", "+faststart",
                    "-max_muxing_queue_size", "1024",
                    "-progress", "pipe:1",
                    "-y", output_path
                ])
                self.last_concat_cmd = cmd_try

                try:
                    process = await asyncio.create_subprocess_exec(
                        *cmd_try,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        creationflags=WIN_NO_WINDOW
                    )
                except OSError as e:
                    winerr = getattr(e, "winerror", None)
                    if os.name == "nt" and winerr == 206:
                        try:
                            if list_path.exists():
                                list_path.unlink()
                        except Exception:
                            pass
                        return await _concat_in_batches()
                    raise
                tracking = self._should_track(scope, project_id, task_id, cancel_event)
                if tracking:
                    self._register_proc(str(scope), str(project_id), str(task_id), process)

                total_duration = sum(durations)
                if on_progress:
                    try:
                        last_bucket = -1
                        seen_end = False
                        while True:
                            if cancel_event and cancel_event.is_set():
                                raise asyncio.CancelledError()
                            rl = asyncio.create_task(process.stdout.readline())
                            wt = asyncio.create_task(cancel_event.wait()) if cancel_event else None
                            if wt:
                                done, _ = await asyncio.wait({rl, wt}, return_when=asyncio.FIRST_COMPLETED)
                                if wt in done:
                                    try:
                                        rl.cancel()
                                    except Exception:
                                        pass
                                    raise asyncio.CancelledError()
                                line = await rl
                                try:
                                    wt.cancel()
                                except Exception:
                                    pass
                            else:
                                line = await rl
                            if not line:
                                break
                            s = line.decode(errors="ignore").strip()
                            if s.startswith("out_time_ms="):
                                try:
                                    ms = float(s.split("=", 1)[1])
                                    if total_duration > 0:
                                        pct = (ms / (total_duration * 1000.0)) * 100.0
                                        if pct < 0:
                                            pct = 0.0
                                        if pct > 100:
                                            pct = 100.0
                                        if not seen_end and pct >= 100.0:
                                            pct = 99.0
                                        await on_progress(pct)
                                        bucket = int(pct // 5)
                                        if bucket > last_bucket:
                                            logger.info(f"拼接进度: {pct:.1f}%")
                                            last_bucket = bucket
                                except Exception:
                                    pass
                            elif s.startswith("progress=") and s.endswith("end"):
                                seen_end = True
                                logger.info("拼接进度: 99.0% (等待完成)")
                    except Exception:
                        pass

                try:
                    stdout, stderr = await self._communicate_with_cancel(process, cancel_event)
                finally:
                    if tracking:
                        self._unregister_proc(str(scope), str(project_id), str(task_id), process)
                try:
                    if list_path.exists():
                        list_path.unlink()
                except Exception:
                    pass
                if process.returncode == 0:
                    if on_progress:
                        try:
                            await on_progress(100.0)
                        except Exception:
                            pass
                    logger.info(f"视频拼接成功: {output_path}")
                    return True
                else:
                    err = stderr.decode(errors="ignore")
                    self.last_concat_error = err.strip() or "filter_complex 拼接失败"
                    last_err = err
                    logger.error(f"视频拼接失败: {err}")
                    try:
                        if Path(output_path).exists():
                            Path(output_path).unlink()
                    except Exception:
                        pass

            if last_err:
                logger.error(f"视频拼接失败: {last_err}")
                self.last_concat_error = str(last_err).strip() or self.last_concat_error
            return False

        except Exception as e:
            logger.error(f"拼接视频时出错: {e}")
            self.last_concat_error = str(e) or self.last_concat_error
            return False

    async def _probe_stream_info(self, path: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-print_format", "json",
                "-show_streams",
                path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW
            )
            out, _ = await proc.communicate()
            if proc.returncode != 0:
                return None, None
            data = json.loads(out.decode(errors="ignore") or "{}")
            streams = data.get("streams") or []
            v = None
            a = None
            for s in streams:
                if s.get("codec_type") == "video" and v is None:
                    v = {
                        "codec_name": s.get("codec_name"),
                        "pix_fmt": s.get("pix_fmt"),
                        "width": s.get("width"),
                        "height": s.get("height"),
                        "r_frame_rate": s.get("r_frame_rate"),
                    }
                elif s.get("codec_type") == "audio" and a is None:
                    sr = s.get("sample_rate")
                    try:
                        sr_int = int(sr) if sr is not None else None
                    except Exception:
                        sr_int = None
                    a = {
                        "codec_name": s.get("codec_name"),
                        "sample_rate": sr_int,
                        "channels": s.get("channels"),
                    }
            return v, a
        except Exception:
            return None, None

    _WEB_PREVIEW_CONTAINERS = {".mp4", ".mov", ".m4v"}

    def _upload_needs_web_transcode(
        self, path: Path, v: Optional[Dict[str, Any]], a: Optional[Dict[str, Any]]
    ) -> bool:
        """前端 / WebView2 预览：优先 H.264 + yuv420p + AAC，封装在 MP4/MOV。"""
        if not v:
            return False
        suf = path.suffix.lower()
        if suf not in self._WEB_PREVIEW_CONTAINERS:
            return True
        c = (v.get("codec_name") or "").lower()
        px = (v.get("pix_fmt") or "").lower()
        if c not in ("h264", "avc"):
            return True
        if px and "p10" in px:
            return True
        if px in ("yuv422p", "yuv444p", "gbrp", "yuv420p12le"):
            return True
        if px and "420" not in px and "j420" not in px and px not in ("yuv420p", "yuvj420p"):
            return True
        if a:
            ac = (a.get("codec_name") or "").lower()
            if ac not in ("aac", "mp3"):
                return True
        return False

    async def normalize_upload_for_web_preview(self, path: Path) -> Path:
        """
        上传保存后调用：必要时转码为 H.264(yuv420p) + AAC 的 MP4（+faststart），
        避免 HEVC/10bit/非 MP4 容器等导致 WebView2 黑屏或无法解码。
        失败时返回原路径，不阻断上传。
        """
        try:
            v, a = await self._probe_stream_info(str(path))
            if not v:
                logger.warning("normalize_upload_for_web_preview: 无视频轨，跳过: %s", path)
                return path
            # 1) 完全兼容：直接跳过
            if not self._upload_needs_web_transcode(path, v, a):
                logger.info("normalize_upload_for_web_preview: 已兼容 Web 预览，跳过: %s", path.name)
                return path

            # 2) 仅“容器不兼容”，但码流已兼容：优先 remux 成 MP4（不重编码，速度极快）
            #    典型：mkv/avi 内部其实是 h264(yuv420p) + aac
            suf = path.suffix.lower()
            vcodec = (v.get("codec_name") or "").lower()
            pix = (v.get("pix_fmt") or "").lower()
            acodec = (a.get("codec_name") or "").lower() if a else ""
            video_codec_ok = vcodec in ("h264", "avc")
            pix_ok = (not pix) or (pix in ("yuv420p", "yuvj420p")) or (("420" in pix or "j420" in pix) and ("p10" not in pix))
            audio_codec_ok = (not a) or (acodec in ("aac", "mp3"))
            if suf not in self._WEB_PREVIEW_CONTAINERS and video_codec_ok and pix_ok and audio_codec_ok:
                tmp_out = path.parent / f".{path.stem}_remux_{uuid.uuid4().hex[:10]}.mp4"
                try:
                    if tmp_out.exists():
                        tmp_out.unlink()
                except Exception:
                    pass
                out_final = path.with_suffix(".mp4")
                cmd_remux: List[str] = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-i",
                    str(path),
                    "-map",
                    "0:v:0",
                ]
                if a:
                    cmd_remux.extend(["-map", "0:a:0"])
                else:
                    cmd_remux.append("-an")
                cmd_remux.extend(["-c", "copy", "-movflags", "+faststart", "-y", str(tmp_out)])
                proc = await asyncio.create_subprocess_exec(
                    *cmd_remux,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW,
                )
                _stdout, stderr = await proc.communicate()
                if proc.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 0:
                    try:
                        try:
                            if path.exists():
                                path.unlink()
                        except Exception:
                            pass
                        os.replace(str(tmp_out), str(out_final))
                        logger.info("normalize_upload_for_web_preview: remux 为 Web 预览 MP4: %s", out_final.name)
                        return out_final
                    except Exception as e:
                        logger.error("normalize_upload_for_web_preview remux 替换文件失败: %s", e)
                        try:
                            if tmp_out.exists():
                                tmp_out.unlink()
                        except Exception:
                            pass
                        return path
                err = (stderr or b"").decode(errors="ignore").strip()
                logger.warning("normalize_upload_for_web_preview remux 失败，转码回退: %s | %s", path, err[:500])
                try:
                    if tmp_out.exists():
                        tmp_out.unlink()
                except Exception:
                    pass

            _, enc_args = await self._pick_fast_encoder()
            tmp_out = path.parent / f".{path.stem}_web_{uuid.uuid4().hex[:10]}.mp4"
            try:
                if tmp_out.exists():
                    tmp_out.unlink()
            except Exception:
                pass
            out_final = path.with_suffix(".mp4")
            cmd: List[str] = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                str(path),
                "-map",
                "0:v:0",
            ]
            if a:
                cmd.extend(["-map", "0:a:0"])
            else:
                cmd.append("-an")
            cmd.extend(enc_args)
            cmd.extend(["-pix_fmt", "yuv420p"])
            if a:
                # 音频如果已是 AAC/MP3，直接 copy 可明显提速；否则转 AAC 保证兼容
                ac = (a.get("codec_name") or "").lower()
                if ac in ("aac", "mp3"):
                    cmd.extend(["-c:a", "copy"])
                else:
                    cmd.extend(["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000"])
            cmd.extend(["-movflags", "+faststart", "-y", str(tmp_out)])
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0 or not tmp_out.exists() or tmp_out.stat().st_size <= 0:
                err = (stderr or b"").decode(errors="ignore").strip()
                logger.error("normalize_upload_for_web_preview 转码失败: %s | %s", path, err[:800])
                try:
                    if tmp_out.exists():
                        tmp_out.unlink()
                except Exception:
                    pass
                return path
            try:
                if path.suffix.lower() == ".mp4" and path.resolve() == out_final.resolve():
                    os.replace(str(tmp_out), str(path))
                else:
                    try:
                        if path.exists():
                            path.unlink()
                    except Exception:
                        pass
                    os.replace(str(tmp_out), str(out_final))
            except Exception as e:
                logger.error("normalize_upload_for_web_preview 替换文件失败: %s", e)
                try:
                    if tmp_out.exists():
                        tmp_out.unlink()
                except Exception:
                    pass
                return path
            logger.info("normalize_upload_for_web_preview: 已转码为 Web 预览用 MP4: %s", out_final.name)
            return out_final
        except Exception as e:
            logger.exception("normalize_upload_for_web_preview 异常: %s", e)
            return path

    async def _pick_fast_encoder(self) -> Tuple[str, List[str]]:
        await self._detect_cuda()
        encoders = await self._detect_encoders()
        if getattr(self, "_cuda_available", False) and ("h264_nvenc" in encoders) and await self._is_encoder_usable("h264_nvenc"):
            logger.info("编码器选择: h264_nvenc (GPU)")
            return "h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p3"]
        if "h264_qsv" in encoders and await self._is_encoder_usable("h264_qsv"):
            logger.info("编码器选择: h264_qsv (GPU)")
            return "h264_qsv", ["-c:v", "h264_qsv"]
        if "h264_amf" in encoders and await self._is_encoder_usable("h264_amf"):
            logger.info("编码器选择: h264_amf (GPU)")
            return "h264_amf", ["-c:v", "h264_amf"]
        if "libx264" in encoders:
            logger.info("编码器选择: libx264 (CPU)")
            # 上传后“只用于预览”：优先速度，避免让上传接口长时间等待
            # crf 18 体积/耗时都偏高；改为更快的 veryfast + crf 23（在预览清晰度与速度间更平衡）
            return "libx264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "0"]
        if "libopenh264" in encoders:
            logger.info("编码器选择: libopenh264 (CPU)")
            return "libopenh264", ["-c:v", "libopenh264", "-b:v", "4M"]
        if "h264_mf" in encoders:
            logger.info("编码器选择: h264_mf (CPU)")
            return "h264_mf", ["-c:v", "h264_mf", "-b:v", "4M"]
        if "mpeg4" in encoders:
            logger.info("编码器选择: mpeg4 (CPU)")
            return "mpeg4", ["-c:v", "mpeg4", "-q:v", "4"]
        logger.info("编码器选择: libx264 (CPU)")
        return "libx264", ["-c:v", "libx264", "-preset", "superfast", "-crf", "18"]

    async def _get_encoder_priority_list(self) -> List[List[str]]:
        await self._detect_cuda()
        names = await self._detect_encoders()
        seq: List[List[str]] = []
        cpu_seq: List[List[str]] = []

        if getattr(self, "_cuda_available", False) and ("h264_nvenc" in names) and await self._is_encoder_usable("h264_nvenc"):
            seq.append(["-c:v", "h264_nvenc", "-preset", "p3", "-rc:v", "vbr_hq", "-cq:v", "19"])
        if "h264_qsv" in names and await self._is_encoder_usable("h264_qsv"):
            seq.append(["-c:v", "h264_qsv"])
        if "h264_amf" in names and await self._is_encoder_usable("h264_amf"):
            seq.append(["-c:v", "h264_amf"])

        if "libx264" in names:
            cpu_seq.append(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "0"])
        if "libopenh264" in names:
            cpu_seq.append(["-c:v", "libopenh264", "-b:v", "4M"])
        if "h264_mf" in names:
            cpu_seq.append(["-c:v", "h264_mf", "-b:v", "4M"])
        if "mpeg4" in names:
            cpu_seq.append(["-c:v", "mpeg4", "-q:v", "4"])
        if not cpu_seq:
            cpu_seq.append(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "0"])

        seq.extend(cpu_seq)
        return seq

    async def _detect_encoders(self) -> List[str]:
        if getattr(self, "_encoders_cache", None) is not None:
            return getattr(self, "_encoders_cache")
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-encoders",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW
            )
            out, _ = await proc.communicate()
            text = out.decode(errors="ignore")
            names = []
            for name in ["h264_nvenc", "h264_qsv", "h264_amf", "libx264", "libopenh264", "h264_mf", "mpeg4"]:
                if name in text:
                    names.append(name)
            setattr(self, "_encoders_cache", names)
            return names
        except Exception:
            setattr(self, "_encoders_cache", ["libx264"])
            return ["libx264"]

    def _preferred_pix_fmt(self, encoder_name: Optional[str]) -> str:
        name = (encoder_name or "").lower().strip()
        if name in {"h264_qsv", "h264_amf"}:
            return "nv12"
        return "yuv420p"

    def _encoder_name_from_args(self, vcodec_args: List[str]) -> Optional[str]:
        try:
            for i in range(len(vcodec_args) - 1):
                if vcodec_args[i] == "-c:v":
                    return str(vcodec_args[i + 1])
        except Exception:
            return None
        return None

    async def _is_encoder_usable(self, encoder_name: str) -> bool:
        key = (encoder_name or "").strip()
        if not key:
            return False
        cached = self._encoder_usable_cache.get(key)
        if cached is not None:
            return bool(cached)
        pix_fmt = self._preferred_pix_fmt(key)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x64:rate=30",
            "-t",
            "0.2",
            "-an",
            "-c:v",
            key,
            "-pix_fmt",
            pix_fmt,
            "-f",
            "null",
            "-",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=6.0)
            except asyncio.TimeoutError:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    out, err = await asyncio.wait_for(proc.communicate(), timeout=1.5)
                except Exception:
                    out, err = b"", b""
                ok = False
            else:
                ok = (proc.returncode == 0)
            if not ok:
                msg = (err or b"")[:600].decode("utf-8", errors="ignore").strip()
                if msg:
                    logger.info("编码器不可用: %s err=%s", key, msg.replace("\n", " ")[:300])
        except FileNotFoundError:
            ok = False
        except Exception:
            ok = False
        self._encoder_usable_cache[key] = bool(ok)
        return bool(ok)

    async def _ffmpeg_supports_cuda_hwaccel(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-hwaccels",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW
            )
            out, _ = await proc.communicate()
            if proc.returncode == 0:
                text = out.decode(errors="ignore").lower()
                return ("cuda" in text) or ("nvdec" in text) or ("cuvid" in text)
            return False
        except Exception:
            return False

    async def _detect_cuda(self) -> bool:
        if getattr(self, "_cuda_checked", False):
            return bool(getattr(self, "_cuda_available", False))
        has_hwaccel = await self._ffmpeg_supports_cuda_hwaccel()
        use = has_hwaccel
        setattr(self, "_cuda_checked", True)
        setattr(self, "_cuda_available", use)
        if use:
            if not getattr(self, "_cuda_log_done", False):
                logger.info("检测到CUDA/NVENC，已启用GPU加速")
                setattr(self, "_cuda_log_done", True)
        else:
            if not getattr(self, "_cuda_log_done", False):
                logger.info("未检测到CUDA/NVENC，使用CPU编码")
                setattr(self, "_cuda_log_done", True)
        return use

    async def _ffprobe_format_name(self, path: str) -> Optional[str]:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=format_name",
                "-of", "default=nk=1:nw=1",
                path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=WIN_NO_WINDOW
            )
            out, _ = await proc.communicate()
            if proc.returncode == 0:
                s = out.decode(errors="ignore").strip()
                return s or None
            return None
        except Exception:
            return None

    async def _first_frame_is_keyframe(self, path: str) -> bool:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-skip_frame", "nokey",
                "-show_entries", "frame=pkt_pts_time",
                "-of", "csv=p=0",
                "-read_intervals", "%+0.2",
                path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=WIN_NO_WINDOW
            )
            out, _ = await proc.communicate()
            if proc.returncode != 0:
                return False
            text = out.decode(errors="ignore").strip()
            if not text:
                return False
            try:
                first_kf_time = float(text.splitlines()[0].strip())
                return abs(first_kf_time) < 0.001
            except Exception:
                return False
        except Exception:
            return False

    async def _ffprobe_video_duration(self, path: str) -> Optional[float]:
        """读取视频流的时长，优先于容器总时长，避免音频缺失或容器元数据不准导致总时长偏差"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration",
                "-of", "default=nk=1:nw=1",
                path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=WIN_NO_WINDOW
            )
            out, _ = await proc.communicate()
            if proc.returncode == 0:
                try:
                    return float(out.decode().strip())
                except Exception:
                    return None
            return None
        except Exception:
            return None

    async def _ffprobe_has_audio(self, path: str) -> bool:
        """探测是否存在音频流"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=nk=1:nw=1",
                path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW
            )
            out, _ = await proc.communicate()
            if proc.returncode == 0:
                s = out.decode().strip().lower()
                return s == "audio"
            return False
        except Exception:
            return False

    async def _ffprobe_duration(self, path: str, stream_type: str = "format") -> Optional[float]:
        try:
            if stream_type == "audio":
                cmd_a = [
                    "ffprobe", "-v", "error",
                    "-select_streams", "a:0",
                    "-show_entries", "stream=duration",
                    "-of", "default=nk=1:nw=1",
                    path,
                ]
                proc_a = await asyncio.create_subprocess_exec(
                    *cmd_a,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW
                )
                out_a, _ = await proc_a.communicate()
                if proc_a.returncode == 0:
                    try:
                        return float(out_a.decode().strip())
                    except Exception:
                        pass
                cmd_f = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=nk=1:nw=1",
                    path,
                ]
                proc_f = await asyncio.create_subprocess_exec(
                    *cmd_f,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW
                )
                out_f, _ = await proc_f.communicate()
                if proc_f.returncode == 0:
                    try:
                        return float(out_f.decode().strip())
                    except Exception:
                        return None
                return None
            else:
                cmd = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=nk=1:nw=1",
                    path,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW
                )
                out, _ = await proc.communicate()
                if proc.returncode == 0:
                    try:
                        return float(out.decode().strip())
                    except Exception:
                        return None
                return None
        except Exception:
            return None

    async def replace_audio_with_narration(
        self,
        video_path: str,
        narration_path: str,
        output_path: str,
        *,
        scope: Optional[str] = None,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> bool:
        try:
            narr_used = narration_path
            vdur = await self._ffprobe_duration(video_path, "format") or 0.0
            adur = await self._ffprobe_duration(narr_used, "audio") or 0.0
            if vdur <= 0.0:
                logger.error("无法获取视频时长")
                return False
            if adur <= 0.0:
                logger.error("无法获取音频时长")
                return False
            enc_name, vcodec_args_pick = await self._pick_fast_encoder()
            tol = 0.05
            if abs(adur - vdur) <= tol:
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-i", video_path,
                    "-i", narr_used,
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-shortest",
                    "-movflags", "+faststart",
                    "-y", output_path,
                ]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW
                )
                tracking = self._should_track(scope, project_id, task_id, cancel_event)
                if tracking:
                    self._register_proc(str(scope), str(project_id), str(task_id), process)
                try:
                    stdout, stderr = await self._communicate_with_cancel(process, cancel_event)
                finally:
                    if tracking:
                        self._unregister_proc(str(scope), str(project_id), str(task_id), process)
                if process.returncode == 0:
                    vinfo, _ = await self._probe_stream_info(output_path)
                    if vinfo is not None:
                        return True
                    vcodec_args_fb = ["-c:v", "libx264", "-preset", "superfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
                    cmd_fb_direct = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-i", video_path,
                        "-i", narr_used,
                        "-map", "0:v:0", "-map", "1:a:0",
                        *vcodec_args_fb,
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-shortest",
                        "-y", output_path,
                    ]
                    p2 = await asyncio.create_subprocess_exec(
                        *cmd_fb_direct,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        creationflags=WIN_NO_WINDOW
                    )
                    tracking2 = self._should_track(scope, project_id, task_id, cancel_event)
                    if tracking2:
                        self._register_proc(str(scope), str(project_id), str(task_id), p2)
                    try:
                        _, e2 = await self._communicate_with_cancel(p2, cancel_event)
                    finally:
                        if tracking2:
                            self._unregister_proc(str(scope), str(project_id), str(task_id), p2)
                    if p2.returncode == 0:
                        return True
                    err = stderr.decode(errors="ignore")
                    logger.error(f"配音替换失败(无视频流回退): {err}\n{e2.decode(errors='ignore')}")
                    return False
                else:
                    err = stderr.decode(errors="ignore")
                    logger.error(f"配音替换失败(拷贝路径): {err}")
                    return False
            if adur >= vdur:
                pad = max(adur - vdur, 0.0)
                pad_str = f"{pad:.3f}"
                f = f"[0:v]tpad=stop_mode=clone:stop_duration={pad_str},setpts=PTS-STARTPTS[v];[1:a]asetpts=PTS-STARTPTS[a]"
                filter_complex = f
                map_args = ["-map", "[v]", "-map", "[a]"]
                extra = []
            else:
                adur_str = f"{adur:.3f}"
                f = f"[0:v]trim=start=0:end={adur_str},setpts=PTS-STARTPTS[v];[1:a]asetpts=PTS-STARTPTS[a]"
                filter_complex = f
                map_args = ["-map", "[v]", "-map", "[a]"]
                extra = []
            vcodec_args = list(vcodec_args_pick)
            if enc_name == "h264_nvenc":
                vcodec_args.extend(["-rc:v", "vbr_hq", "-cq:v", "19"])
            elif enc_name == "libx264":
                vcodec_args.extend(["-crf", "18"])
            vcodec_args.extend(["-pix_fmt", self._preferred_pix_fmt(enc_name), "-movflags", "+faststart"])

            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", video_path,
                "-i", narr_used,
                "-filter_complex", filter_complex,
                *map_args,
                *vcodec_args,
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                *extra,
                "-y", output_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW
            )
            tracking = self._should_track(scope, project_id, task_id, cancel_event)
            if tracking:
                self._register_proc(str(scope), str(project_id), str(task_id), process)
            try:
                stdout, stderr = await self._communicate_with_cancel(process, cancel_event)
            finally:
                if tracking:
                    self._unregister_proc(str(scope), str(project_id), str(task_id), process)
            if process.returncode == 0:
                vinfo, _ = await self._probe_stream_info(output_path)
                if vinfo is not None:
                    return True
                vcodec_args_fb = ["-c:v", "libx264", "-preset", "superfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
                cmd_fb = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-i", video_path,
                    "-i", narr_used,
                    "-filter_complex", filter_complex,
                    *map_args,
                    *vcodec_args_fb,
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    *extra,
                    "-y", output_path,
                ]
                p2 = await asyncio.create_subprocess_exec(
                    *cmd_fb,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=WIN_NO_WINDOW
                )
                tracking2 = self._should_track(scope, project_id, task_id, cancel_event)
                if tracking2:
                    self._register_proc(str(scope), str(project_id), str(task_id), p2)
                try:
                    _, e2 = await self._communicate_with_cancel(p2, cancel_event)
                finally:
                    if tracking2:
                        self._unregister_proc(str(scope), str(project_id), str(task_id), p2)
                if p2.returncode == 0:
                    return True
                err = stderr.decode(errors="ignore")
                logger.error(f"片段音频替换失败(无视频流回退): {err}\n{e2.decode(errors='ignore')}")
                return False
            else:
                err = stderr.decode(errors="ignore")
                if ("Cannot load nvcuda.dll" in err) or ("Error while opening encoder" in err) or ("Could not open encoder" in err):
                    vcodec_args_fb = ["-c:v", "libx264", "-preset", "superfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
                    cmd_fb = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-i", video_path,
                        "-i", narr_used,
                        "-filter_complex", filter_complex,
                        *map_args,
                        *vcodec_args_fb,
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        *extra,
                        "-y", output_path,
                    ]
                    p2 = await asyncio.create_subprocess_exec(
                        *cmd_fb,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        creationflags=WIN_NO_WINDOW
                    )
                    tracking2 = self._should_track(scope, project_id, task_id, cancel_event)
                    if tracking2:
                        self._register_proc(str(scope), str(project_id), str(task_id), p2)
                    try:
                        _, e2 = await self._communicate_with_cancel(p2, cancel_event)
                    finally:
                        if tracking2:
                            self._unregister_proc(str(scope), str(project_id), str(task_id), p2)
                    if p2.returncode == 0:
                        return True
                    else:
                        logger.error(f"片段音频替换失败: {err}\n{e2.decode(errors='ignore')}")
                        return False
                logger.error(f"片段音频替换失败: {err}")
                return False

        except Exception as e:
            logger.error(f"片段音频替换出错: {e}")
            return False
        

    async def extract_audio_mp3(self, input_video: str, output_mp3: str) -> bool:
        try:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-i", input_video,
                "-vn",
                "-acodec", "libmp3lame",
                "-q:a", "2",
                "-y", output_mp3,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WIN_NO_WINDOW
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return True
            else:
                err = stderr.decode(errors="ignore")
                logger.error(f"提取音频失败: {err}")
                return False
        except Exception as e:
            logger.error(f"提取音频出错: {e}")
            return False

# 全局视频处理器实例
video_processor = VideoProcessor()
