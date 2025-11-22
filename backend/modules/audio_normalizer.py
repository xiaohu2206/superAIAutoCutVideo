import asyncio
import json
import logging
import os
import re
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class AudioNormalizer:
    def __init__(self, target_lufs: float = -20.0, max_peak: float = -1.0):
        self.target_lufs = target_lufs
        self.max_peak = max_peak

    async def _first_pass(self, input_path: str) -> Optional[Dict[str, float]]:
        cmd = [
            "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error",
            "-i", input_path,
            "-af", f"loudnorm=I={self.target_lufs}:TP={self.max_peak}:LRA=7:print_format=json",
            "-f", "null", "-",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            return None
        text = stderr.decode(errors="ignore")
        # 提取包含 loudnorm 统计值的 JSON 块
        m = re.search(r"\{\s*\"input_i\"\s*:\s*.*?\}", text, flags=re.DOTALL)
        if not m:
            return None
        block = m.group(0)
        try:
            data = json.loads(block)
            out = {
                "input_i": float(data.get("input_i", 0)),
                "input_lra": float(data.get("input_lra", 0)),
                "input_tp": float(data.get("input_tp", 0)),
                "input_thresh": float(data.get("input_thresh", 0)),
            }
            # 两遍 loudnorm 需要 offset（target_offset），否则效果不稳定
            if "target_offset" in data:
                try:
                    out["target_offset"] = float(data.get("target_offset"))
                except Exception:
                    pass
            return out
        except Exception:
            return None

    async def normalize_video_loudness(self, input_path: str, output_path: str, sample_rate: int = 44100, channels: int = 2) -> bool:
        if not os.path.exists(input_path):
            logger.error(f"音频不存在: {input_path}")
            return False
        measured = await self._first_pass(input_path)
        if measured is None or ("target_offset" not in measured):
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", input_path,
                "-af", f"loudnorm=I={self.target_lufs}:TP={self.max_peak}:LRA=7",
                "-c:v", "copy",
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-c:a", "aac", "-b:a", "192k",
                output_path,
            ]
        else:
            logger.info(
                "两遍 loudnorm 测量: I=%.2f, LRA=%.2f, TP=%.2f, thresh=%.2f, offset=%.2f" % (
                    measured['input_i'], measured['input_lra'], measured['input_tp'], measured['input_thresh'], measured['target_offset']
                )
            )
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", input_path,
                "-af", (
                    f"loudnorm=I={self.target_lufs}:TP={self.max_peak}:LRA=7:"
                    f"measured_I={measured['input_i']}:"
                    f"measured_LRA={measured['input_lra']}:"
                    f"measured_TP={measured['input_tp']}:"
                    f"measured_thresh={measured['input_thresh']}:"
                    f"offset={measured['target_offset']}:"
                    f"linear=true"
                ),
                "-c:v", "copy",
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-c:a", "aac", "-b:a", "192k",
                output_path,
            ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info(f"音频标准化处理完成: {input_path} -> {output_path}")
            return True
        logger.error(stderr.decode(errors="ignore"))
        return False