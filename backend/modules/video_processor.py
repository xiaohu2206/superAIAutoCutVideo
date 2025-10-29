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
    
    def validate_video_file(self, video_path: str) -> bool:
        """验证视频文件是否有效"""
        try:
            path = Path(video_path)
            if not path.exists():
                logger.error(f"视频文件不存在: {video_path}")
                return False
            
            if path.suffix.lower() not in self.supported_formats:
                logger.error(f"不支持的视频格式: {path.suffix}")
                return False
            
            # 使用OpenCV验证视频文件
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"无法打开视频文件: {video_path}")
                return False
            
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            
            if frame_count <= 0:
                logger.error(f"视频文件无有效帧: {video_path}")
                return False
            
            logger.info(f"视频文件验证成功: {video_path}, 帧数: {frame_count}")
            return True
            
        except Exception as e:
            logger.error(f"验证视频文件时出错: {e}")
            return False
    
    def get_video_info(self, video_path: str) -> Dict:
        """获取视频信息"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"无法打开视频文件: {video_path}")
            
            info = {
                'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'fps': cap.get(cv2.CAP_PROP_FPS),
                'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                'duration': 0,
                'size_mb': 0
            }
            
            # 计算时长
            if info['fps'] > 0:
                info['duration'] = info['frame_count'] / info['fps']
            
            # 获取文件大小
            file_size = os.path.getsize(video_path)
            info['size_mb'] = round(file_size / (1024 * 1024), 2)
            
            cap.release()
            logger.info(f"获取视频信息成功: {info}")
            return info
            
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            raise
    
    async def extract_frames(self, video_path: str, output_dir: str, 
                           frame_interval: int = 30) -> List[str]:
        """提取视频帧"""
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"无法打开视频文件: {video_path}")
            
            frame_paths = []
            frame_count = 0
            saved_count = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 按间隔保存帧
                if frame_count % frame_interval == 0:
                    frame_filename = f"frame_{saved_count:06d}.jpg"
                    frame_path = output_path / frame_filename
                    
                    cv2.imwrite(str(frame_path), frame)
                    frame_paths.append(str(frame_path))
                    saved_count += 1
                
                frame_count += 1
                
                # 每处理100帧休眠一下，避免阻塞
                if frame_count % 100 == 0:
                    await asyncio.sleep(0.01)
            
            cap.release()
            logger.info(f"提取帧完成: 总帧数 {frame_count}, 保存帧数 {saved_count}")
            return frame_paths
            
        except Exception as e:
            logger.error(f"提取视频帧失败: {e}")
            raise
    
    async def compress_video(self, input_path: str, output_path: str, 
                           quality: str = "medium") -> bool:
        """压缩视频"""
        try:
            # 质量设置
            quality_settings = {
                "low": {"crf": "28", "preset": "fast"},
                "medium": {"crf": "23", "preset": "medium"},
                "high": {"crf": "18", "preset": "slow"}
            }
            
            settings = quality_settings.get(quality, quality_settings["medium"])
            
            # FFmpeg命令
            cmd = [
                "ffmpeg", "-i", input_path,
                "-c:v", "libx264",
                "-crf", settings["crf"],
                "-preset", settings["preset"],
                "-c:a", "aac",
                "-b:a", "128k",
                "-y",  # 覆盖输出文件
                output_path
            ]
            
            logger.info(f"开始压缩视频: {input_path} -> {output_path}")
            
            # 异步执行FFmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"视频压缩成功: {output_path}")
                return True
            else:
                logger.error(f"视频压缩失败: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"压缩视频时出错: {e}")
            return False
    
    async def cut_video_segment(self, input_path: str, output_path: str,
                              start_time: float, duration: float) -> bool:
        """剪切视频片段"""
        try:
            cmd = [
                "ffmpeg", "-i", input_path,
                "-ss", str(start_time),
                "-t", str(duration),
                "-c", "copy",  # 不重新编码，快速剪切
                "-y",
                output_path
            ]
            
            logger.info(f"剪切视频片段: {start_time}s-{start_time+duration}s")
            
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
                logger.error(f"视频剪切失败: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"剪切视频时出错: {e}")
            return False
    
    def detect_scene_changes(self, video_path: str, threshold: float = 0.3) -> List[float]:
        """检测场景变化点（简单实现）"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"无法打开视频文件: {video_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            scene_changes = []
            
            ret, prev_frame = cap.read()
            if not ret:
                cap.release()
                return scene_changes
            
            prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            frame_count = 1
            
            while True:
                ret, curr_frame = cap.read()
                if not ret:
                    break
                
                curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
                
                # 计算帧差
                diff = cv2.absdiff(prev_gray, curr_gray)
                diff_score = np.mean(diff) / 255.0
                
                # 如果差异超过阈值，认为是场景变化
                if diff_score > threshold:
                    timestamp = frame_count / fps
                    scene_changes.append(timestamp)
                    logger.debug(f"检测到场景变化: {timestamp:.2f}s, 差异: {diff_score:.3f}")
                
                prev_gray = curr_gray
                frame_count += 1
            
            cap.release()
            logger.info(f"场景变化检测完成，共检测到 {len(scene_changes)} 个变化点")
            return scene_changes
            
        except Exception as e:
            logger.error(f"检测场景变化失败: {e}")
            return []

# 全局视频处理器实例
video_processor = VideoProcessor()