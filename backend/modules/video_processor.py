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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from .audio_normalizer import AudioNormalizer

logger = logging.getLogger(__name__)

class VideoProcessor:
    """视频处理器类"""
    
    def __init__(self):
        self.supported_formats = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
        self.audio_normalizer = AudioNormalizer()
    
    async def cut_video_segment(self, input_path: str, output_path: str,
                              start_time: float, duration: float) -> bool:
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
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"视频剪切成功: {output_path}")
                return True
            else:
                err = stderr.decode(errors="ignore")
                logger.error(f"视频剪切失败: {err}")
                return False

        except Exception as e:
            logger.error(f"剪切视频时出错: {e}")
            return False

    async def concat_videos(self, inputs: List[str], output_path: str, on_progress=None) -> bool:
        """稳健拼接多个视频片段，解决拼接处卡顿问题。
        原因分析：此前使用 concat demuxer + `-c copy` 要求片段参数完全一致且必须从关键帧开始，
        如果某段不是关键帧起始或存在时间戳不连续，播放器可能在拼接处卡顿（等待下一个关键帧）。

        修复策略：改为使用 filter_complex 的 concat 过滤器并重编码输出，统一时间戳，避免GOP跨段依赖。
        - 对每段视频/音频先 reset PTS（setpts/asetpts）
        - 统一分辨率为偶数尺寸，统一帧率，提升通用播放器兼容性
        - 对于没有音频轨的片段，自动填充与视频等长的静音音频，避免拼接失败
        - 通过 concat 滤镜合并，再使用 libx264 + aac 重编码输出
        - 输出包含 `-movflags +faststart` 以优化播放体验
        """
        try:
            if not inputs:
                logger.error("拼接视频失败: 输入列表为空")
                return False

            # 构造输入参数
            cmd: List[str] = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
            ]
            for p in inputs:
                cmd.extend(["-i", str(p)])

            n = len(inputs)
            # 预先探测每段时长与是否有音频
            durations: List[float] = []
            has_audio: List[bool] = []
            for p in inputs:
                # 优先使用视频流时长，其次用容器总时长，兜底为 0
                d = await self._ffprobe_video_duration(p)
                if d is None:
                    d = await self._ffprobe_duration(p, "format")
                d = d or 0.0
                durations.append(max(d, 0.0))
                # 探测是否存在音频流
                a_dur = await self._ffprobe_duration(p, "audio")
                has_audio.append(a_dur is not None and a_dur > 0.0)

            # 为每个输入构建 reset 与统一参数语句
            vf_parts = []
            for i in range(n):
                # 统一分辨率为偶数、统一帧率（避免兼容问题）
                # 注意：格式统一到 yuv420p 以提升播放器兼容性
                vf_parts.append(
                    f"[{i}:v:0]scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{i}]"
                )
                if has_audio[i]:
                    # 统一采样率，重置时间戳
                    vf_parts.append(f"[{i}:a:0]aresample=48000,asetpts=PTS-STARTPTS[a{i}]")
                else:
                    # 无音频：生成与视频等长的静音音轨
                    dur = durations[i]
                    # 使用 anullsrc 生成静音，并按时长裁剪
                    vf_parts.append(
                        f"anullsrc=r=48000:cl=stereo,atrim=0:{dur},asetpts=PTS-STARTPTS[a{i}]"
                    )

            # 拼接 concat 段
            concat_inputs = "".join([f"[v{i}][a{i}]" for i in range(n)])
            filter_complex = ";".join(vf_parts) + f";{concat_inputs}concat=n={n}:v=1:a=1[v][a]"

            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[v]", "-map", "[a]",
                # 视频编码参数（质量与速度折中）
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                # 音频编码参数
                "-c:a", "aac", "-b:a", "192k",
                # 提升网络播放体验
                "-movflags", "+faststart",
                "-progress", "pipe:1",
                "-y", output_path
            ])

            logger.info(f"开始稳健拼接（重编码），共 {n} 段 -> {output_path}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            total_duration = 0.0
            for d in durations:
                total_duration += d

            if on_progress:
                try:
                    last_bucket = -1  # 控制日志输出频率（每 5% 一次）
                    seen_end = False  # 在真正结束前不把进度提升到 100
                    while True:
                        line = await process.stdout.readline()
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
                                    # 在未收到 progress=end 之前不显示 100%，避免“瞬间100%”误导
                                    if not seen_end and pct >= 100.0:
                                        pct = 99.0
                                    # 发送回调
                                    await on_progress(pct)
                                    # 限流打印日志（每 5% 打印一次）
                                    bucket = int(pct // 5)
                                    if bucket > last_bucket:
                                        logger.info(f"拼接进度: {pct:.1f}%")
                                        last_bucket = bucket
                            except Exception:
                                pass
                        elif s.startswith("progress=") and s.endswith("end"):
                            seen_end = True
                            await on_progress(100.0)
                            logger.info("拼接进度: 100.0% (完成)")
                except Exception:
                    pass

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"视频拼接成功: {output_path}")
                return True
            else:
                err = stderr.decode(errors="ignore")
                logger.error(f"视频拼接失败: {err}")
                return False

        except Exception as e:
            logger.error(f"拼接视频时出错: {e}")
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
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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
                cmd = [
                    "ffprobe", "-v", "error",
                    "-select_streams", "a:0",
                    "-show_entries", "stream=duration",
                    "-of", "default=nk=1:nw=1",
                    path,
                ]
            else:
                cmd = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=nk=1:nw=1",
                    path,
                ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, _ = await proc.communicate()
            if proc.returncode == 0:
                try:
                    return float(out.decode().strip())
                except Exception:
                    return None
            return None
        except Exception:
            return None

    async def replace_audio_with_narration(self, video_path: str, narration_path: str, output_path: str) -> bool:
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
            if adur >= vdur:
                pad = max(adur - vdur, 0.0)
                pad_str = f"{pad:.3f}"
                f = f"[0:v]tpad=stop_mode=clone:stop_duration={pad_str},setpts=PTS-STARTPTS[v];[1:a]asetpts=PTS-STARTPTS[a]"
                filter_complex = f
                map_args = ["-map", "[v]", "-map", "[a]"]
                extra = []
                vcodec_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            else:
                adur_str = f"{adur:.3f}"
                f = f"[0:v]trim=start=0:end={adur_str},setpts=PTS-STARTPTS[v];[1:a]asetpts=PTS-STARTPTS[a]"
                filter_complex = f
                map_args = ["-map", "[v]", "-map", "[a]"]
                extra = []
                vcodec_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]

            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", video_path,
                "-i", narr_used,
                "-filter_complex", filter_complex,
                *map_args,
                *vcodec_args,
                "-c:a", "aac", "-b:a", "192k",
                *extra,
                "-y", output_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return True
            else:
                err = stderr.decode(errors="ignore")
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
                stderr=asyncio.subprocess.PIPE
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
