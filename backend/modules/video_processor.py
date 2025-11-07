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

logger = logging.getLogger(__name__)

class VideoProcessor:
    """视频处理器类"""
    
    def __init__(self):
        self.supported_formats = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
    
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
    

# 全局视频处理器实例
video_processor = VideoProcessor()