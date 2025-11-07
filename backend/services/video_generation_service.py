#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频生成服务

根据项目中的脚本（script.segments）对原视频进行剪辑并拼接，输出生成视频文件。
"""

import asyncio
import logging
from datetime import datetime
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

from modules.projects_store import Project, projects_store
from modules.video_processor import video_processor

logger = logging.getLogger(__name__)


def _backend_root_dir() -> Path:
    # backend/services/... -> backend -> project root
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def _uploads_dir() -> Path:
    root = _backend_root_dir()
    up = root / "uploads"
    (up / "videos").mkdir(parents=True, exist_ok=True)
    return up


def _to_web_path(p: Path) -> str:
    root = _backend_root_dir()
    rel = p.relative_to(root)
    return "/" + str(rel).replace("\\", "/")


class VideoGenerationService:
    @staticmethod
    def _resolve_path(path_or_web: str) -> Path:
        root = _backend_root_dir()
        path_str = (path_or_web or "").strip()
        if not path_str:
            return Path("")
        if path_str.startswith("/"):
            return root / path_str[1:]
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

        segments: List[Dict[str, Any]] = p.script.get("segments") or []
        if not segments:
            raise ValueError("脚本中没有可用的 segments")

        input_abs = VideoGenerationService._resolve_path(p.video_path)
        if not input_abs.exists():
            raise ValueError("原始视频文件不存在")

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

        # 逐段剪切
        clip_paths: List[str] = []
        for idx, seg in enumerate(segments, start=1):
            try:
                start = float(seg.get("start_time", 0.0))
                end = float(seg.get("end_time", 0.0))
                if end <= start:
                    # 跳过无效片段
                    logger.warning(f"跳过无效片段: idx={idx} start={start} end={end}")
                    continue
                duration = max(0.0, end - start)
                clip_name = f"clip_{idx:04d}.mp4"
                clip_abs = tmp_dir / clip_name

                ok = await video_processor.cut_video_segment(
                    str(input_abs), str(clip_abs), start, duration
                )
                if ok:
                    clip_paths.append(str(clip_abs))
                else:
                    logger.warning(f"剪切片段失败，已跳过: {idx}")
            except Exception as e:
                logger.warning(f"处理片段出错（跳过） idx={idx}: {e}")

        if not clip_paths:
            raise ValueError("未生成任何有效片段，无法拼接")

        # 拼接
        ok_concat = await video_processor.concat_videos(clip_paths, str(output_abs))
        if not ok_concat:
            # 失败也清理临时片段
            try:
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            raise RuntimeError("拼接视频失败")

        # 保存到项目
        web_output = _to_web_path(output_abs)
        projects_store.update_project(project_id, {"output_video_path": web_output, "status": "completed"})

        # # 清理临时片段缓存
        # try:
        #     if tmp_dir.exists():
        #         shutil.rmtree(tmp_dir, ignore_errors=True)
        # except Exception:
        #     # 清理失败不影响主流程
        #     pass

        return {
            "output_path": web_output,
            "segments_count": len(clip_paths),
            "started_at": datetime.now().isoformat(),
            "finished_at": datetime.now().isoformat(),
        }


video_generation_service = VideoGenerationService()