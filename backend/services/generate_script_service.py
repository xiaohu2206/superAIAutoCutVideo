from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
from fastapi import HTTPException

from modules.projects_store import projects_store, Project
from modules.ws_manager import manager
from services.script_generation_service import ScriptGenerationService
from modules.config.content_model_config import content_model_config_manager


logger = logging.getLogger(__name__)


def _now_ts() -> str:
    return datetime.now().isoformat()


def _backend_root_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def _uploads_dir() -> Path:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    (up / "videos").mkdir(parents=True, exist_ok=True)
    (up / "subtitles").mkdir(parents=True, exist_ok=True)
    (up / "audios").mkdir(parents=True, exist_ok=True)
    (up / "analyses").mkdir(parents=True, exist_ok=True)
    return up


def _to_web_path(p: Path) -> str:
    env = os.environ.get("SACV_UPLOADS_DIR")
    up = Path(env) if env else (_backend_root_dir() / "uploads")
    rel = p.relative_to(up)
    return "/uploads/" + str(rel).replace("\\", "/")


def _resolve_path(path_str: str) -> Path:
    s = (path_str or "").strip()
    if not s:
        return Path("")
    s_norm = s.replace("\\", "/")
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
    try:
        p = Path(s)
        if p.is_absolute():
            return p
    except Exception:
        pass
    root = _backend_root_dir()
    if s_norm.startswith("/"):
        return root / s_norm[1:]
    return Path(s)


def _compress_srt(content: str) -> str:
    text = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = [b for b in text.split("\n\n") if b.strip()]
    out_lines: List[str] = []
    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if not lines:
            continue
        timing_i = None
        for i, ln in enumerate(lines[:3]):
            if "-->" in ln:
                timing_i = i
                break
        if timing_i is None:
            continue
        parts = lines[timing_i].split("-->")
        if len(parts) < 2:
            continue
        start = parts[0].strip()
        end = parts[1].strip()
        text_lines = lines[timing_i + 1:]
        t = " ".join(text_lines)
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"<[^>]+>", "", t)
        if not t:
            continue
        out_lines.append(f"[{start}-{end}] {t}")
    return ("\n".join(out_lines) + ("\n" if out_lines else ""))


def _parse_srt(srt_path: Path) -> List[Dict[str, Any]]:
    def _parse_ts(ts: str) -> float:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    segments: List[Dict[str, Any]] = []
    try:
        content = srt_path.read_text(encoding="utf-8", errors="ignore")
        norm = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        lines = [ln.strip() for ln in norm.splitlines() if ln.strip()]
        bracket_pattern = re.compile(r"^\[(\d{2}:\d{2}:\d{2},\d{3})-(\d{2}:\d{2}:\d{2},\d{3})\]\s*(.+)$")
        bracket_matches = [bracket_pattern.match(ln) for ln in lines]
        if any(bracket_matches):
            idx = 1
            for m in bracket_matches:
                if not m:
                    continue
                start_str, end_str, text = m.groups()
                start_t = _parse_ts(start_str)
                end_t = _parse_ts(end_str)
                segments.append({
                    "id": str(idx),
                    "start_time": float(start_t),
                    "end_time": float(end_t),
                    "text": text,
                    "subtitle": text,
                })
                idx += 1
        else:
            blocks = [b.strip() for b in norm.split("\n\n") if b.strip()]
            for idx, block in enumerate(blocks, start=1):
                lines_in_block = [line for line in block.splitlines() if line.strip()]
                if len(lines_in_block) < 2:
                    continue
                timing_line = lines_in_block[1] if "-->" in lines_in_block[1] else lines_in_block[0]
                if "-->" not in timing_line:
                    continue
                start_str, end_str = [t.strip() for t in timing_line.split("-->")]
                start_t = _parse_ts(start_str)
                end_t = _parse_ts(end_str)
                text_lines = lines_in_block[2:] if timing_line == lines_in_block[1] else lines_in_block[1:]
                text = " ".join([ln.strip() for ln in text_lines if ln.strip()])
                if not text:
                    text = f"字幕段{idx}"
                segments.append({
                    "id": str(idx),
                    "start_time": float(start_t),
                    "end_time": float(end_t),
                    "text": text,
                    "subtitle": text,
                })
    except Exception:
        pass
    return segments


def _read_video_duration(video_path: Path) -> float:
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return 0.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        cap.release()
        if fps <= 0:
            return 0.0
        return float(frame_count / fps)
    except Exception:
        return 0.0


async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def _ensure_models_ready_for_script(project_id: Optional[str] = None) -> None:
    if project_id:
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": project_id,
                "phase": "validating_content_model",
                "message": "正在验证生成文本大模型是否可用",
                "progress": 5,
                "timestamp": _now_ts(),
            }))
        except Exception:
            pass

    active_content_id = content_model_config_manager.get_active_config_id()
    if not active_content_id:
        if project_id:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "content_model_missing",
                    "message": "未找到激活的文案生成模型配置，请在“模型配置”中启用一个配置",
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
        raise HTTPException(status_code=400, detail="未找到激活的文案生成模型配置，请在“模型配置”中启用一个配置")

    try:
        content_result = await content_model_config_manager.test_connection(active_content_id)
    except asyncio.TimeoutError:
        if project_id:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "content_model_unavailable",
                    "message": "文案生成模型配置连通性测试超时",
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
        raise HTTPException(status_code=504, detail="文案生成模型配置连通性测试超时")
    if not content_result.get("success", False):
        msg = content_result.get("error") or content_result.get("message") or "文案生成模型不可用"
        if project_id:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "content_model_unavailable",
                    "message": f"文案生成模型配置不可用：{msg}",
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=f"文案生成模型配置不可用：{msg}")

    if project_id:
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": project_id,
                "phase": "content_model_ready",
                "message": "生成文本大模型连通性正常",
                "progress": 10,
                "timestamp": _now_ts(),
            }))
        except Exception:
            pass

    # if project_id:
    #     try:
    #         await manager.broadcast(json.dumps({
    #             "type": "progress",
    #             "scope": "generate_script",
    #             "project_id": project_id,
    #             "phase": "validating_tts",
    #             "message": "正在验证TTS功能是否可用",
    #             "progress": 15,
    #             "timestamp": _now_ts(),
    #         }))
    #     except Exception:
    #         pass

    # active_tts_id = tts_engine_config_manager.get_active_config_id()
    # if not active_tts_id:
    #     if project_id:
    #         try:
    #             await manager.broadcast(json.dumps({
    #                 "type": "error",
    #                 "scope": "generate_script",
    #                 "project_id": project_id,
    #                 "phase": "tts_missing",
    #                 "message": "未找到激活的TTS配置，请在“TTS配置”中启用并完善凭据",
    #                 "timestamp": _now_ts(),
    #             }))
    #         except Exception:
    #             pass
    #     raise HTTPException(status_code=400, detail="未找到激活的TTS配置，请在“TTS配置”中启用并完善凭据")

    # tts_cfg = tts_engine_config_manager.get_config(active_tts_id)
    # provider = (getattr(tts_cfg, "provider", None) or "tencent_tts").lower()

    # tts_result = await tts_engine_config_manager.test_connection(active_tts_id)
    # if not tts_result.get("success", False):
    #     msg = tts_result.get("error") or tts_result.get("message") or "TTS配置不可用"
    #     if provider == "edge_tts":
    #         logging.warning(f"Edge TTS 配置连通性检查失败（忽略，不阻断脚本生成）：{msg}")
    #         if project_id:
    #             try:
    #                 await manager.broadcast(json.dumps({
    #                     "type": "warning",
    #                     "scope": "generate_script",
    #                     "project_id": project_id,
    #                     "phase": "tts_unavailable_edge",
    #                     "message": f"Edge TTS 配置连通性检查失败，将跳过强制校验：{msg}",
    #                     "timestamp": _now_ts(),
    #                 }))
    #             except Exception:
    #                 pass
    #         return
    #     if project_id:
    #         try:
    #             await manager.broadcast(json.dumps({
    #                 "type": "error",
    #                 "scope": "generate_script",
    #                 "project_id": project_id,
    #                 "phase": "tts_unavailable",
    #                 "message": f"TTS配置不可用：{msg}",
    #                 "timestamp": _now_ts(),
    #             }))
    #         except Exception:
    #             pass
    #     raise HTTPException(status_code=400, detail=f"TTS配置不可用：{msg}")

    # if project_id:
    #     try:
    #         await manager.broadcast(json.dumps({
    #             "type": "progress",
    #             "scope": "generate_script",
    #             "project_id": project_id,
    #             "phase": "tts_ready",
    #             "message": "TTS功能连通性正常",
    #             "progress": 20,
    #             "timestamp": _now_ts(),
    #         }))
    #     except Exception:
    #         pass


class GenerateScriptService:
    @staticmethod
    async def generate_script(project_id: str, video_path: str, subtitle_path: Optional[str], narration_type: str) -> Dict[str, Any]:
        p: Optional[Project] = projects_store.get_project(project_id)
        if not p:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "project_not_found",
                    "message": "项目不存在",
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            raise HTTPException(status_code=404, detail="项目不存在")

        try:
            uploads_env = os.environ.get("SACV_UPLOADS_DIR")
            logger.info(
                f"generate_script start project_id={project_id} video_path={video_path} subtitle_path={subtitle_path} uploads_env={uploads_env}"
            )
        except Exception:
            pass
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": project_id,
                "phase": "start",
                "message": "开始生成解说脚本",
                "progress": 1,
                "timestamp": _now_ts(),
            }))
        except Exception:
            pass

        # await _ensure_models_ready_for_script(project_id)

        root = _backend_root_dir()
        video_abs = _resolve_path(video_path)
        try:
            logger.info(f"resolved video path project_id={project_id} input={video_path} resolved={video_abs} exists={video_abs.exists()} backend_root={root}")
        except Exception:
            pass
        if not video_abs.exists():
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "video_missing",
                    "message": "视频文件不存在",
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            try:
                logger.error(f"video missing project_id={project_id} input={video_path} resolved={video_abs} uploads_env={os.environ.get('SACV_UPLOADS_DIR')}")
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="视频文件不存在")

        total_duration = _read_video_duration(video_abs)
        try:
            logger.info(f"video duration project_id={project_id} path={video_abs} duration={total_duration}")
        except Exception:
            pass

        segments: List[Dict[str, Any]] = []
        subtitle_text: str = ""
        sub_abs: Optional[Path] = None
        created_tmp: List[Path] = []

        subtitle_status = getattr(p, "subtitle_status", None)
        if subtitle_status and subtitle_status != "ready":
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "subtitle_not_ready",
                    "message": "字幕尚未就绪，请先提取字幕或上传字幕",
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="字幕尚未就绪，请先提取字幕或上传字幕")

        if p.subtitle_path:
            cand = _resolve_path(p.subtitle_path)
            try:
                logger.info(f"project subtitle candidate project_id={project_id} cand_input={p.subtitle_path} cand_resolved={cand} exists={cand.exists()}")
            except Exception:
                pass
            if cand.exists():
                sub_abs = cand
                try:
                    await manager.broadcast(json.dumps({
                        "type": "progress",
                        "scope": "generate_script",
                        "project_id": project_id,
                        "phase": "subtitle_exists",
                        "message": "已存在字幕文件，跳过ASR",
                        "progress": 60,
                        "timestamp": _now_ts(),
                    }))
                except Exception:
                    pass
                try:
                    if getattr(p, "subtitle_status", None) != "ready":
                        projects_store.update_project(project_id, {"subtitle_status": "ready"})
                except Exception:
                    pass

        if not sub_abs and subtitle_path:
            cand = _resolve_path(subtitle_path)
            try:
                logger.info(f"request subtitle candidate project_id={project_id} cand_input={subtitle_path} cand_resolved={cand} exists={cand.exists()}")
            except Exception:
                pass
            if cand.exists():
                sub_abs = cand
                try:
                    await manager.broadcast(json.dumps({
                        "type": "progress",
                        "scope": "generate_script",
                        "project_id": project_id,
                        "phase": "subtitle_exists",
                        "message": "已提供字幕文件，跳过ASR",
                        "progress": 60,
                        "timestamp": _now_ts(),
                    }))
                except Exception:
                    pass
                try:
                    if not getattr(p, "subtitle_path", None):
                        projects_store.update_project(project_id, {
                            "subtitle_path": subtitle_path,
                            "subtitle_status": "ready",
                            "subtitle_updated_at": _now_ts(),
                        })
                except Exception:
                    pass

        if not sub_abs:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "subtitle_missing",
                    "message": "请先提取字幕或上传字幕",
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="请先提取字幕或上传字幕")

        if sub_abs and sub_abs.exists():
            try:
                subtitle_text = sub_abs.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                subtitle_text = ""
            segments = _parse_srt(sub_abs)
            try:
                logger.info(f"subtitle parsed project_id={project_id} subtitle_abs={sub_abs} segments_count={len(segments)}")
            except Exception:
                pass
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "subtitle_parsed",
                    "message": "已解析字幕内容",
                    "progress": 65,
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass

        projects_store.update_project(project_id, {"status": "processing"})
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": project_id,
                "phase": "processing",
                "message": "开始使用大模型生成脚本",
                "progress": 68,
                "timestamp": _now_ts(),
            }))
        except Exception:
            pass

        try:
            drama_name = p.name or "剧名"
            plot_analysis: str = ""
            # Always generate plot analysis, ignore cache
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "llm_analyze_subtitle",
                    "message": "大模型分析字幕",
                    "progress": 70,
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            plot_analysis = await ScriptGenerationService.generate_plot_analysis_pipeline(subtitle_text)
            ts_pa = datetime.now().strftime("%Y%m%d_%H%M%S")
            pa_out = _uploads_dir() / "analyses" / f"{project_id}_analysis_{ts_pa}.txt"
            try:
                pa_out.write_text(plot_analysis, encoding="utf-8")
                web_pa = _to_web_path(pa_out)
                projects_store.update_project(project_id, {"plot_analysis_path": web_pa})
            except Exception:
                pass
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "llm_analysis_done",
                    "message": "字幕分析完成",
                    "progress": 75,
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass

            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "llm_generate_script",
                    "message": "大模型生成脚本",
                    "progress": 80,
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            script_json = await ScriptGenerationService.generate_script_json(
                drama_name=drama_name,
                plot_analysis=plot_analysis,
                subtitle_content=subtitle_text,
                project_id=project_id,
            )
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "llm_generate_done",
                    "message": "脚本生成完成，进行格式化",
                    "progress": 85,
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass

            script = ScriptGenerationService.to_video_script(script_json, total_duration)
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "script_structured",
                    "message": "脚本结构化完成，保存中",
                    "progress": 90,
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            projects_store.save_script(project_id, script)
            projects_store.update_project(project_id, {"status": "completed"})
            try:
                logger.info(f"script saved project_id={project_id} segments_count={len(script.get('segments', []))}")
            except Exception:
                pass
            try:
                await manager.broadcast(json.dumps({
                    "type": "completed",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "done",
                    "message": "解说脚本生成成功",
                    "progress": 100,
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            return {
                "message": "解说脚本生成成功",
                "data": {
                    "script": script,
                    "plot_analysis": plot_analysis,
                },
                "timestamp": _now_ts(),
            }
        except HTTPException:
            projects_store.update_project(project_id, {"status": "failed"})
            raise
        except Exception as e:
            projects_store.update_project(project_id, {"status": "failed"})
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "failed",
                    "message": f"脚本生成失败: {str(e)}",
                    "timestamp": _now_ts(),
                }))
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"脚本生成失败: {str(e)}")
        finally:
            try:
                for f in created_tmp:
                    try:
                        if isinstance(f, Path) and f.exists():
                            f.unlink()
                    except Exception:
                        pass
            except Exception:
                pass


generate_script_service = GenerateScriptService()
