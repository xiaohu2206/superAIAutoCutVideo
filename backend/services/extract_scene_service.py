#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜头提取服务
"""
import os
import json
import logging
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import uuid

import numpy as np

from modules.projects_store import projects_store
from modules.task_progress_store import task_progress_store
from modules.task_cancel_store import task_cancel_store
from services.extract_subtitle_service import _resolve_path, _uploads_dir, _to_web_path
from services.vision_frame_analysis_service import vision_frame_analyzer
from modules.subtitle_utils import parse_srt
from modules.config.video_model_config import video_model_config_manager

logger = logging.getLogger(__name__)

_SCENES_SPLIT_VERSION = 1
_VISION_SCENE_KEYS = frozenset({"vision", "vision_status", "vision_analyzed", "vision_error", "vision_frame_error"})


class ExtractSceneService:
    SCOPE = "extract_scene"
    
    def __init__(self):
        self._model: Optional[Any] = None
        self._model_lock = asyncio.Lock()

    async def _wait_for_subtitle_path(
        self,
        project_id: str,
        task_id: str,
        timeout_sec: float = 15 * 60,
    ) -> Optional[str]:
        """
        等待项目字幕落盘（主要用于：字幕提取已在进行中，但镜头提取希望尽量使用字幕做优化）。
        注意：这里不会主动触发字幕提取，确保“镜头/字幕”两条逻辑解耦。
        """
        start = asyncio.get_running_loop().time()
        sleep_s = 0.6
        last_msg_at = 0.0
        while True:
            if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                raise asyncio.CancelledError("任务已取消")
            p = projects_store.get_project(project_id)
            if not p:
                return None
            sp = getattr(p, "subtitle_path", None)
            status = str(getattr(p, "subtitle_status", "") or "").strip().lower()
            if sp:
                # 只有当字幕文件真实落盘且非空时才认为就绪
                try:
                    abs_sp = _resolve_path(sp)
                    if abs_sp.exists() and abs_sp.stat().st_size > 0:
                        return str(sp)
                except Exception:
                    # 若路径异常则继续等待或超时
                    pass
            now = asyncio.get_running_loop().time()
            if now - start >= float(timeout_sec or 0):
                return None
            # 仅在“正在提取中”时等待，否则快速退出
            if status not in {"extracting", "processing", "running"}:
                return None
            if now - last_msg_at >= 2.0:
                last_msg_at = now
                try:
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=task_id,
                        status="processing",
                        progress=80,
                        message="等待字幕提取完成以优化镜头...",
                    )
                except Exception:
                    pass
            await asyncio.sleep(sleep_s)
            sleep_s = min(2.0, sleep_s * 1.25)

    def _get_model(self):
        if self._model:
            return self._model

        weights_dir = self._resolve_weights_dir()
        if not weights_dir.exists():
            raise FileNotFoundError(f"TransNetV2 weights not found at {weights_dir}")
            
        logger.info(f"Loading TransNetV2 model from {weights_dir}")
        backend = str(os.environ.get("TRANSNETV2_BACKEND") or "auto").strip().lower()
        if backend in {"torch", "auto"}:
            try:
                import torch
                from modules.transnetv2_torch import TransNetV2Torch

                w = os.environ.get("TRANSNETV2_PYTORCH_WEIGHTS") or str(weights_dir / "transnetv2-pytorch-weights.pth")
                use_torch = bool(w and Path(w).exists() and torch.cuda.is_available())
                if backend == "torch":
                    use_torch = bool(w and Path(w).exists())
                if use_torch:
                    self._model = TransNetV2Torch(str(weights_dir))
                    try:
                        info = self._model.get_backend_info()
                        logger.info(f"TransNetV2 backend: {info}")
                    except Exception:
                        pass
                    return self._model
            except Exception as e:
                if backend == "torch":
                    raise
                logger.warning(f"TransNetV2 torch backend unavailable, fallback to tensorflow: {e}")

        from modules.transnetv2 import TransNetV2
        self._model = TransNetV2(str(weights_dir))
        return self._model

    def _resolve_weights_dir(self) -> Path:
        backend_dir = Path(__file__).resolve().parents[1]
        candidates = [
            backend_dir / "serviceData" / "models" / "transnetv2-weights",
            backend_dir.parent / "backend" / "serviceData" / "models" / "transnetv2-weights",
        ]
        env_path = os.environ.get("TRANSNETV2_WEIGHTS_DIR")
        if env_path:
            candidates.insert(0, Path(env_path))
        for c in candidates:
            try:
                if c.exists():
                    return c
            except Exception:
                continue
        return candidates[0]

    def _video_fingerprint(self, video_abs_path: Path) -> str:
        try:
            st = video_abs_path.stat()
            return f"{st.st_size}:{st.st_mtime_ns}:{video_abs_path.resolve()}"
        except OSError:
            return ""

    def _scenes_split_cache_path(self, project_id: str) -> Path:
        return _uploads_dir() / "analyses" / f"{project_id}_scenes_split.json"

    def _scene_dict_without_vision(self, scene: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in scene.items() if k not in _VISION_SCENE_KEYS}

    def _scenes_analysis_path(self, project_id: str) -> Path:
        return _uploads_dir() / "analyses" / f"{project_id}_scenes.json"

    def _scene_needs_vision_analysis(self, scene: Dict[str, Any], mode: str) -> bool:
        if mode == "all":
            return True
        if mode == "no_subtitles":
            sub = scene.get("subtitle")
            return not sub or sub == "无"
        return False

    def _load_existing_scene_analysis(
        self,
        project_id: str,
    ) -> Optional[Tuple[List[Dict[str, Any]], float, int, Path]]:
        path = self._scenes_analysis_path(project_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("读取镜头分析结果失败: %s", e)
            return None
        scenes = data.get("scenes")
        if not isinstance(scenes, list) or len(scenes) == 0:
            return None
        try:
            fps = float(data.get("fps") or 0)
            total_frames = int(data.get("total_frames") or 0)
        except (TypeError, ValueError):
            fps = 0.0
            total_frames = 0
        if fps <= 0:
            fps = 25.0
        return [dict(s) for s in scenes], fps, total_frames, path

    def _merge_existing_vision_results(
        self,
        base_scenes: List[Dict[str, Any]],
        existing_scenes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        existing_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for scene in existing_scenes:
            try:
                key = (f"{float(scene.get('start_time')):.6f}", f"{float(scene.get('end_time')):.6f}")
            except (TypeError, ValueError):
                continue
            existing_map[key] = scene

        merged: List[Dict[str, Any]] = []
        for scene in base_scenes:
            current = dict(scene)
            try:
                key = (f"{float(scene.get('start_time')):.6f}", f"{float(scene.get('end_time')):.6f}")
            except (TypeError, ValueError):
                merged.append(current)
                continue
            prev = existing_map.get(key)
            if prev:
                for field in _VISION_SCENE_KEYS:
                    if field in prev:
                        current[field] = prev[field]
            merged.append(current)
        return merged

    def _has_pending_vision_scenes(self, scenes: List[Dict[str, Any]], mode: str) -> bool:
        for scene in scenes:
            if not self._scene_needs_vision_analysis(scene, mode):
                continue
            if not bool(scene.get("vision_analyzed")):
                return True
        return False

    def _build_scenes_result_payload(
        self,
        scenes: List[Dict[str, Any]],
        fps: float,
        total_frames: int,
    ) -> Dict[str, Any]:
        return {
            "scenes": scenes,
            "fps": fps,
            "total_frames": total_frames,
            "created_at": datetime.now().isoformat(),
        }

    def _write_scenes_result_file(
        self,
        project_id: str,
        result_data: Dict[str, Any],
    ) -> Path:
        out_path = self._scenes_analysis_path(project_id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        return out_path

    def _save_project_scenes_path(self, project_id: str, out_path: Path) -> None:
        web_path = _to_web_path(out_path)
        projects_store.update_project(project_id, {
            "scenes_path": web_path,
            "scenes_updated_at": datetime.now().isoformat()
        })

    def _save_scenes_result(
        self,
        project_id: str,
        scenes: List[Dict[str, Any]],
        fps: float,
        total_frames: int,
    ) -> Path:
        result_data = self._build_scenes_result_payload(scenes, fps, total_frames)
        out_path = self._write_scenes_result_file(project_id, result_data)
        self._save_project_scenes_path(project_id, out_path)
        return out_path

    def _scenes_list_without_vision(self, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self._scene_dict_without_vision(dict(s)) for s in scenes]

    def _try_load_scenes_split(
        self, project_id: str, video_abs_path: Path
    ) -> Optional[Tuple[List[Dict[str, Any]], float, int]]:
        path = self._scenes_split_cache_path(project_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("读取镜头分割缓存失败: %s", e)
            return None
        if data.get("version") != _SCENES_SPLIT_VERSION:
            return None
        fp = self._video_fingerprint(video_abs_path)
        if not fp or data.get("video_fingerprint") != fp:
            return None
        scenes = data.get("scenes")
        if not isinstance(scenes, list) or len(scenes) == 0:
            return None
        try:
            fps = float(data.get("fps") or 0)
            total_frames = int(data.get("total_frames") or 0)
        except (TypeError, ValueError):
            return None
        if fps <= 0:
            fps = 25.0
        cleaned = self._scenes_list_without_vision(scenes)
        logger.info("复用镜头分割缓存: project_id=%s scenes=%d", project_id, len(cleaned))
        return cleaned, fps, total_frames

    def _save_scenes_split_cache(
        self,
        project_id: str,
        video_abs_path: Path,
        project_video_web: Optional[str],
        fps: float,
        total_frames: int,
        optimized_scenes: List[Dict[str, Any]],
    ) -> None:
        analysis_dir = _uploads_dir() / "analyses"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        path = self._scenes_split_cache_path(project_id)
        payload = {
            "version": _SCENES_SPLIT_VERSION,
            "video_fingerprint": self._video_fingerprint(video_abs_path),
            "project_video_path": project_video_web,
            "fps": fps,
            "total_frames": total_frames,
            "scenes": self._scenes_list_without_vision(optimized_scenes),
            "created_at": datetime.now().isoformat(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("写入镜头分割缓存失败: %s", e)

    async def extract_scenes(
        self,
        project_id: str,
        force: bool = False,
        task_id: Optional[str] = None,
        asr_provider: Optional[str] = None,
        asr_model_key: Optional[str] = None,
        asr_language: Optional[str] = None,
        itn: bool = True,
        hotwords: Optional[List[str]] = None,
        analyze_vision: bool = False,
        vision_mode: str = "all",
        vision_key_frames: int = 1,
        vision_action: str = "auto",
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        
        if not p.video_path:
            raise ValueError("请先上传视频")
            
        # 检查是否已有任务在运行
        running = task_progress_store.get_latest_running(self.SCOPE, project_id)
        if running:
            r_status = str(running.get("status") or "").strip().lower()
            r_task_id = running.get("task_id")
            if not force:
                if r_status in ("pending", "processing", "running"):
                    return running
            else:
                # force=True：二次点击时取消旧任务并重新执行
                if r_task_id and r_status in ("pending", "processing", "running"):
                    try:
                        await task_cancel_store.cancel(self.SCOPE, project_id, str(r_task_id))
                    except Exception:
                        pass
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=str(r_task_id),
                        status="cancelled",
                        message="已取消旧任务，准备重新执行",
                    )

        # 生成任务ID
        if not task_id:
            task_id = f"scene_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # 初始化进度
        task_progress_store.set_state(
            scope=self.SCOPE,
            project_id=project_id,
            task_id=task_id,
            status="pending",
            progress=0,
            message="准备提取镜头...",
        )

        async def _run():
            try:
                current_p = projects_store.get_project(project_id)
                video_abs_path = _resolve_path(current_p.video_path)
                if not video_abs_path.exists():
                    raise FileNotFoundError(f"视频文件不存在: {current_p.video_path}")

                # force=True 时忽略已保存的镜头分割缓存，强制重新分析
                split_loaded = None if force else self._try_load_scenes_split(project_id, video_abs_path)
                split_from_cache = split_loaded is not None

                async def _split_scenes() -> Tuple[List[Dict[str, Any]], float, int]:
                    """
                    获取基础镜头分割（不依赖字幕），可能来自缓存或模型预测。
                    返回：optimized_scenes(基础)、fps、total_frames
                    """
                    nonlocal split_loaded, split_from_cache

                    if split_from_cache:
                        cached_scenes, fps_cached, total_frames_cached = split_loaded
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=40,
                            message="复用已保存的镜头分割，跳过模型检测...",
                        )
                        return cached_scenes, fps_cached, total_frames_cached

                    # 开始提取镜头（TransNetV2）
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=task_id,
                        status="processing",
                        progress=10,
                        message="正在加载镜头模型...",
                    )

                    loop = asyncio.get_running_loop()
                    model = self._get_model()
                    chunk_seconds = 180.0
                    overlap_frames = 25
                    max_chunk_concurrency = 0
                    try:
                        v = str(os.environ.get("TRANSNETV2_CHUNK_SECONDS") or "").strip()
                        if v:
                            chunk_seconds = float(v)
                    except Exception:
                        chunk_seconds = 180.0
                    try:
                        v = str(os.environ.get("TRANSNETV2_OVERLAP_FRAMES") or "").strip()
                        if v:
                            overlap_frames = int(v)
                    except Exception:
                        overlap_frames = 25
                    try:
                        v = str(os.environ.get("TRANSNETV2_MAX_CONCURRENCY") or "").strip()
                        if v:
                            max_chunk_concurrency = int(v)
                    except Exception:
                        max_chunk_concurrency = 0
                    if overlap_frames < 0:
                        overlap_frames = 0
                    if chunk_seconds <= 0:
                        chunk_seconds = 180.0

                    single_frame_predictions = None
                    import cv2

                    cap0 = cv2.VideoCapture(str(video_abs_path))
                    fps0 = cap0.get(cv2.CAP_PROP_FPS)
                    total_frames0 = int(cap0.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    cap0.release()
                    if fps0 <= 0:
                        fps0 = 25.0

                    if total_frames0 <= 0:
                        def cb_tmp(pct):
                            mapped_pct = 10 + (pct * 0.8)
                            task_progress_store.set_state(
                                scope=self.SCOPE,
                                project_id=project_id,
                                task_id=task_id,
                                status="processing",
                                progress=mapped_pct,
                                message=f"正在分析镜头: {pct:.1f}%",
                            )
                            if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                raise asyncio.CancelledError("任务已取消")

                        _, sp_tmp, _ = await loop.run_in_executor(
                            None, lambda: model.predict_video(str(video_abs_path), cb_tmp)
                        )
                        if sp_tmp is None or len(sp_tmp) == 0:
                            raise ValueError("未能从视频中解码任何帧，无法进行镜头分析")
                        single_frame_predictions = sp_tmp
                        total_frames0 = len(single_frame_predictions)
                    else:
                        chunk_frames = max(1, int(round(chunk_seconds * fps0)))
                        starts = list(range(0, total_frames0, chunk_frames))
                        final_pred = np.zeros(total_frames0, dtype=np.float32)
                        total_core = total_frames0
                        chunk_core: Dict[int, int] = {}
                        for i, sf in enumerate(starts):
                            ef = min(total_frames0, sf + chunk_frames)
                            chunk_core[i] = (ef - sf)
                        progress_map: Dict[int, float] = {i: 0.0 for i in chunk_core}
                        prog_lock = threading.Lock()

                        def _update_overall():
                            with prog_lock:
                                acc = 0.0
                                for i, w in chunk_core.items():
                                    acc += w * max(0.0, min(100.0, float(progress_map.get(i, 0.0))))
                                overall = (acc / max(1, total_core)) / 100.0
                            mapped_pct = 10 + (overall * 80.0)
                            loop.call_soon_threadsafe(
                                task_progress_store.set_state,
                                self.SCOPE,
                                project_id,
                                task_id,
                                "processing",
                                mapped_pct,
                                f"正在分析镜头: {overall * 100.0:.1f}%",
                            )

                        def _on_chunk_progress(idx: int, pct: float):
                            with prog_lock:
                                progress_map[idx] = pct
                            _update_overall()

                        async def run_chunk(si, sf, ef, asf, aef):
                            if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                raise asyncio.CancelledError("任务已取消")
                            st = asf / fps0
                            dur = max(0.0, (aef - asf) / fps0)
                            _, sp, _ = await loop.run_in_executor(
                                None,
                                lambda: model.predict_video(
                                    str(video_abs_path),
                                    lambda p: _on_chunk_progress(si, p),
                                    st,
                                    dur,
                                ),
                            )
                            keep_l = ef - sf
                            dl = sf - asf
                            dr = aef - ef
                            if dl < 0:
                                dl = 0
                            if dr < 0:
                                dr = 0
                            pred = sp[int(dl):int(dl) + int(keep_l)]
                            if len(pred) < keep_l:
                                pad_val = float(pred[-1]) if len(pred) > 0 else 0.0
                                pred = np.pad(pred, (0, keep_l - len(pred)), constant_values=pad_val)
                            elif len(pred) > keep_l:
                                pred = pred[:keep_l]
                            with prog_lock:
                                progress_map[si] = 100.0
                            _update_overall()
                            return si, sf, ef, pred

                        pending = set()
                        next_i = 0
                        total_chunks = len(starts)
                        effective_concurrency = total_chunks if max_chunk_concurrency <= 0 else max_chunk_concurrency

                        def _enqueue_more():
                            nonlocal next_i
                            while next_i < total_chunks and len(pending) < effective_concurrency:
                                sf = starts[next_i]
                                ef = min(total_frames0, sf + chunk_frames)
                                asf = max(0, sf - (overlap_frames if sf > 0 else 0))
                                aef = min(total_frames0, ef + (overlap_frames if ef < total_frames0 else 0))
                                pending.add(asyncio.create_task(run_chunk(next_i, sf, ef, asf, aef)))
                                next_i += 1

                        _enqueue_more()
                        processed = 0
                        try:
                            while pending:
                                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                                for t in done:
                                    si, sf, ef, pred = t.result()
                                    final_pred[sf:ef] = pred[: (ef - sf)]
                                    processed += (ef - sf)
                                    pct = (processed / max(1, total_core)) * 100.0
                                    mapped_pct = 10 + (pct * 0.8)
                                    task_progress_store.set_state(
                                        scope=self.SCOPE,
                                        project_id=project_id,
                                        task_id=task_id,
                                        status="processing",
                                        progress=mapped_pct,
                                        message=f"正在分析镜头: {pct:.1f}%",
                                    )
                                    if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                        for pt in pending:
                                            try:
                                                pt.cancel()
                                            except Exception:
                                                pass
                                        await asyncio.gather(*pending, return_exceptions=True)
                                        raise asyncio.CancelledError("任务已取消")
                                _enqueue_more()
                        except Exception:
                            for pt in pending:
                                try:
                                    pt.cancel()
                                except Exception:
                                    pass
                            await asyncio.gather(*pending, return_exceptions=True)
                            raise
                        single_frame_predictions = final_pred

                    scenes = model.predictions_to_scenes(single_frame_predictions)

                    cap = cv2.VideoCapture(str(video_abs_path))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    cap.release()
                    if fps <= 0:
                        fps = 25.0

                    analysis_dir = _uploads_dir() / "analyses"
                    analysis_dir.mkdir(parents=True, exist_ok=True)
                    raw_scenes = []
                    for idx, (start_f, end_f) in enumerate(scenes, start=1):
                        s_t = float(start_f) / float(fps)
                        e_t = float(end_f) / float(fps)
                        raw_scenes.append(
                            {
                                "id": idx,
                                "start_frame": int(start_f),
                                "end_frame": int(end_f),
                                "start_time": s_t,
                                "end_time": e_t,
                                "time_range": f"{self._format_ts(s_t)} - {self._format_ts(e_t)}",
                                "subtitle": "无",
                            }
                        )
                    raw_out_name = f"{project_id}_scenes_raw.json"
                    raw_out_path = analysis_dir / raw_out_name
                    raw_result_data = {
                        "scenes": raw_scenes,
                        "fps": fps,
                        "total_frames": len(single_frame_predictions),
                        "created_at": datetime.now().isoformat(),
                    }
                    with open(raw_out_path, "w", encoding="utf-8") as f:
                        json.dump(raw_result_data, f, ensure_ascii=False, indent=2)
                    raw_web_path = _to_web_path(raw_out_path)
                    projects_store.update_project(
                        project_id,
                        {"scenes_raw_path": raw_web_path, "scenes_raw_updated_at": datetime.now().isoformat()},
                    )

                    # 这里返回“基础镜头”(未按字幕合并/补字幕列)，最终优化在字幕就绪后进行
                    base_scenes_list = [
                        {"start_frame": int(sf), "end_frame": int(ef)} for (sf, ef) in scenes
                    ]
                    scenes_np = np.array([[s["start_frame"], s["end_frame"]] for s in base_scenes_list], dtype=np.int64)
                    total_frames = len(single_frame_predictions)
                    # 暂时先用原始场景结构占位，后续 _optimize_scenes 会输出最终 dict 列表
                    return (
                        [{"start_frame": int(sf), "end_frame": int(ef)} for (sf, ef) in scenes_np],
                        fps,
                        total_frames,
                    )

                # 先做“基础镜头分割”（完全不依赖字幕）。字幕与镜头逻辑解耦：不会在镜头服务里主动触发字幕提取。
                base_scenes, fps, total_frames = await _split_scenes()

                current_p = projects_store.get_project(project_id)
                subtitle_path = getattr(current_p, "subtitle_path", None)
                subtitle_source = getattr(current_p, "subtitle_source", None)
                subtitle_status = str(getattr(current_p, "subtitle_status", "") or "").strip().lower()

                # 用户上传字幕但路径缺失：直接失败（这是用户显式依赖）
                if not subtitle_path and subtitle_source == "user":
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=task_id,
                        status="failed",
                        message="镜头分析失败: 未找到上传的字幕，请先上传字幕文件",
                    )
                    return

                # 若字幕正在提取中，等待字幕就绪，以便做字幕优化；否则直接按“当前已有字幕(或无字幕)”继续
                if not subtitle_path and subtitle_status in {"extracting", "processing", "running"}:
                    subtitle_path = await self._wait_for_subtitle_path(project_id, task_id)
                    if subtitle_path:
                        try:
                            projects_store.update_project(project_id, {"subtitle_path": subtitle_path})
                        except Exception:
                            pass
                        current_p = projects_store.get_project(project_id) or current_p
                        subtitle_path = getattr(current_p, "subtitle_path", None)
                        subtitle_status = str(getattr(current_p, "subtitle_status", "") or "").strip().lower()

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=88,
                    message="正在优化镜头（字幕可用则按字幕优化）...",
                )

                # 统一走 _optimize_scenes（依赖字幕）生成最终结构
                scenes_np = np.array(
                    [[int(s["start_frame"]), int(s["end_frame"])] for s in base_scenes],
                    dtype=np.int64,
                )
                optimized_scenes = self._optimize_scenes(scenes_np, fps, current_p)
                self._save_scenes_split_cache(
                    project_id,
                    video_abs_path,
                    getattr(current_p, "video_path", None),
                    fps,
                    total_frames,
                    optimized_scenes,
                )

                analysis_dir = _uploads_dir() / "analyses"
                analysis_dir.mkdir(parents=True, exist_ok=True)

                existing_analysis = self._load_existing_scene_analysis(project_id)
                if analyze_vision and existing_analysis:
                    existing_scenes, existing_fps, existing_total_frames, existing_path = existing_analysis
                    if vision_action == "continue":
                        optimized_scenes = self._merge_existing_vision_results(optimized_scenes, existing_scenes)
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=88,
                            message="检测到历史视觉分析结果，继续补全未分析镜头...",
                        )
                    elif vision_action == "restart":
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=88,
                            message="检测到历史视觉分析结果，准备重新进行视觉分析...",
                        )
                    else:
                        optimized_scenes = self._merge_existing_vision_results(optimized_scenes, existing_scenes)
                        if not self._has_pending_vision_scenes(optimized_scenes, vision_mode):
                            if existing_fps > 0:
                                fps = existing_fps
                            if existing_total_frames > 0:
                                total_frames = existing_total_frames
                            self._save_scenes_result(project_id, optimized_scenes, fps, total_frames)
                            task_progress_store.set_state(
                                scope=self.SCOPE,
                                project_id=project_id,
                                task_id=task_id,
                                status="completed",
                                progress=100,
                                message="检测到已有视觉分析结果，已直接复用",
                            )
                            return
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=88,
                            message="检测到历史视觉分析结果，自动继续补全未分析镜头...",
                        )
                        logger.info("复用历史视觉分析文件继续执行: project_id=%s path=%s", project_id, existing_path)

                # 4.5 视觉分析 (Moondream or Online Vision)
                # 要求：视觉分析前必须已经拿到整体字幕数据（有字幕文件且已落盘，部分字幕也算有）
                has_subtitles_for_vision = False
                if subtitle_path:
                    try:
                        abs_sp = _resolve_path(subtitle_path)
                        has_subtitles_for_vision = abs_sp.exists() and abs_sp.stat().st_size > 0
                    except Exception:
                        has_subtitles_for_vision = False
                if analyze_vision and not has_subtitles_for_vision:
                    logger.info(
                        "Skip vision analysis because subtitles are not ready: "
                        "project_id=%s, subtitle_status=%s",
                        project_id,
                        subtitle_status,
                    )
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=task_id,
                        status="processing",
                        progress=90,
                        message="字幕尚未生成或未找到，已跳过视觉分析，仅基于镜头与字幕优化结果保存",
                    )
                elif analyze_vision and has_subtitles_for_vision:
                    try:
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=90,
                            message="准备进行视觉分析...",
                        )

                        active_config = video_model_config_manager.get_active_config()
                        if active_config and active_config.provider in (
                            "yunwu",
                            "302ai",
                            "qwen",
                            "doubao",
                            "custom_openai_vision",
                        ):
                            logger.info(
                                "Using online vision model: %s - %s",
                                active_config.provider,
                                active_config.model_name,
                            )
                            vk = int(vision_key_frames) if int(vision_key_frames) in (1, 3) else 1
                            optimized_scenes = await vision_frame_analyzer.analyze_scenes_online(
                                project_id=project_id,
                                video_path=str(video_abs_path),
                                scenes=optimized_scenes,
                                provider=active_config.provider,
                                api_key=active_config.api_key,
                                base_url=active_config.base_url,
                                model_name=active_config.model_name,
                                timeout=active_config.timeout or 120,
                                mode=vision_mode,
                                task_id=task_id,
                                vision_key_frames=vk,
                            )
                        else:
                            logger.info("Using local Moondream model for vision analysis")
                            optimized_scenes = await vision_frame_analyzer.analyze_scenes(
                                project_id=project_id,
                                video_path=str(video_abs_path),
                                scenes=optimized_scenes,
                                mode=vision_mode,
                                task_id=task_id,
                            )
                    except Exception as e:
                        logger.error("Vision analysis failed: %s", e)
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=90,
                            message=f"视觉分析失败: {str(e)} (继续保存结果)",
                        )

                # 5. 保存结果
                out_path = self._save_scenes_result(project_id, optimized_scenes, fps, total_frames)
                
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message="镜头提取完成",
                )
                
            except asyncio.CancelledError:
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="cancelled",
                    message="任务已取消",
                )
            except Exception as e:
                logger.exception("Scene extraction failed")
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="failed",
                    message=f"镜头提取失败: {str(e)}",
                )

        asyncio.create_task(_run())
        
        return {
            "task_id": task_id,
            "status": "pending", 
            "message": "任务已提交"
        }

    def _optimize_scenes(self, scenes: np.ndarray, fps: float, project) -> List[Dict[str, Any]]:
        """
        根据规则优化镜头:
        1. 镜头时间 >= 1.8s
        2. 根据字幕合并
        """
        # 转换 scenes 到 list of dict for easier manipulation
        # scenes_list items: {start_frame, end_frame, start_time, end_time}
        scene_list = []
        for start_f, end_f in scenes:
            scene_list.append({
                "start_frame": int(start_f),
                "end_frame": int(end_f),
                "start_time": start_f / fps,
                "end_time": end_f / fps,
                "merged_from": [
                    {
                        "start_time": start_f / fps,
                        "end_time": end_f / fps
                    }
                ]
            })
            
        # 获取字幕
        subtitles = []
        if project.subtitle_path:
             try:
                 # 解析字幕文件
                 # backend/routes/project_routes.py 里有 parse_srt，但那是 internal function
                 # 我们需要读取文件
                 abs_path = _resolve_path(project.subtitle_path)
                 if abs_path.exists():
                     subtitles = parse_srt(abs_path)
                     # subtitles items: {start_time, end_time, text, ...}
             except Exception as e:
                 logger.error(f"Failed to load subtitles for scene optimization: {e}")

        if subtitles:
            subtitles.sort(key=lambda x: x["start_time"])
            DELTA = 0.2
            j = 0
            while j < len(scene_list) - 1:
                a = scene_list[j]
                b = scene_list[j + 1]
                cut_time = a["end_time"]
                sub_match = None
                for sub in subtitles:
                    if (sub["start_time"] - DELTA) <= cut_time <= (sub["end_time"] + DELTA):
                        sub_match = sub
                        break
                if sub_match and (sub_match["start_time"] - DELTA) <= a["start_time"] <= (sub_match["end_time"] + DELTA):
                    a["end_frame"] = b["end_frame"]
                    a["end_time"] = b["end_time"]
                    a["merged_from"].extend(b.get("merged_from", []))
                    scene_list.pop(j + 1)
                    continue
                j += 1

        # 规则 2: 每个镜头的时间不能少于 1.8s
        # 如果少于就合并。
        # 策略：向后合并，如果是最后一个则向前合并。
        # 这是一个迭代过程。
        
        MIN_DURATION = 1.8
        
        i = 0
        while i < len(scene_list):
            dur = scene_list[i]["end_time"] - scene_list[i]["start_time"]
            if dur < MIN_DURATION:
                # Merge
                if i < len(scene_list) - 1:
                    # Merge with next
                    next_scene = scene_list[i+1]
                    scene_list[i]["end_frame"] = next_scene["end_frame"]
                    scene_list[i]["end_time"] = next_scene["end_time"]
                    scene_list[i]["merged_from"].extend(next_scene.get("merged_from", []))
                    scene_list.pop(i+1)
                    # Don't increment i, check this new merged scene again
                    continue
                elif i > 0:
                    # Merge with prev (only if it's the last one)
                    prev_scene = scene_list[i-1]
                    prev_scene["end_frame"] = scene_list[i]["end_frame"]
                    prev_scene["end_time"] = scene_list[i]["end_time"]
                    prev_scene["merged_from"].extend(scene_list[i].get("merged_from", []))
                    scene_list.pop(i)
                    i -= 1 # Re-check prev
                    continue
                else:
                    # Only one scene left, can't merge
                    break
            else:
                i += 1

        # Final Formatting
        final_results = []
        for idx, s in enumerate(scene_list):
            # 查找对应字幕
            # 字幕列：显示这个镜头对应的字幕，如果没有字幕就显示无。
            # 规则：镜头包含字幕。
            # 我们找出所有落在该镜头时间范围内的字幕。
            # "one scene can contain multiple subtitles"
            # Overlap logic: Subtitle mid-point inside scene? Or Subtitle start inside scene?
            s_start = s["start_time"]
            s_end = s["end_time"]
            
            matched_subs = []
            for sub in subtitles:
                # Calculate overlap
                overlap_start = max(s_start, sub["start_time"])
                overlap_end = min(s_end, sub["end_time"])
                overlap = overlap_end - overlap_start
                
                # If overlap is significant (e.g. > 50% of subtitle duration or > 0.5s)
                sub_dur = sub["end_time"] - sub["start_time"]
                if overlap > 0 and (overlap >= sub_dur * 0.5 or overlap > 0.5):
                    matched_subs.append(sub["text"])
            
            subtitle_text = " ".join(matched_subs) if matched_subs else "无"
            
            final_results.append({
                "id": idx + 1,
                "start_frame": s["start_frame"],
                "end_frame": s["end_frame"],
                "start_time": s_start,
                "end_time": s_end,
                "time_range": f"{self._format_ts(s_start)} - {self._format_ts(s_end)}",
                "subtitle": subtitle_text,
                "merged_from": s.get("merged_from", [])
            })
            
        return final_results

    def _format_ts(self, seconds: float) -> str:
        # Same as project_routes._format_ts but locally defined
        if seconds < 0:
            seconds = 0.0
        ms_total = int(round(seconds * 1000))
        ms = ms_total % 1000
        s_total = ms_total // 1000
        s = s_total % 60
        m_total = s_total // 60
        m = m_total % 60
        h = m_total // 60
        return f"{h:02d}:{m:02d}:{s:02d}" # Simple format for display

extract_scene_service = ExtractSceneService()
