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

    async def concat_videos(self, inputs: List[str], output_path: str) -> bool:
        """稳健拼接多个视频片段，解决拼接处卡顿问题。
        原因分析：此前使用 concat demuxer + `-c copy` 要求片段参数完全一致且必须从关键帧开始，
        如果某段不是关键帧起始或存在时间戳不连续，播放器可能在拼接处卡顿（等待下一个关键帧）。

        修复策略：改为使用 filter_complex 的 concat 过滤器并重编码输出，统一时间戳，避免GOP跨段依赖。
        - 对每段视频/音频先 reset PTS（setpts/asetpts）
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
            # 为每个输入构建 reset 语句
            vf_parts = []
            for i in range(n):
                vf_parts.append(f"[{i}:v:0]setpts=PTS-STARTPTS[v{i}]")
                vf_parts.append(f"[{i}:a:0]asetpts=PTS-STARTPTS[a{i}]")

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
                "-y", output_path
            ])

            logger.info(f"开始稳健拼接（重编码），共 {n} 段 -> {output_path}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

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
    

# 全局视频处理器实例
video_processor = VideoProcessor()
