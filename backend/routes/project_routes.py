#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目管理、文件上传与脚本相关API路由

实现API文档中的以下接口：
- GET /api/projects                 获取项目列表
- GET /api/projects/{project_id}    获取项目详情
- POST /api/projects                创建项目
- POST /api/projects/{project_id}   更新项目
- POST /api/projects/{project_id}/delete  删除项目
- POST /api/projects/{project_id}/upload/video    上传视频
- POST /api/projects/generate-script               生成解说脚本（简化实现）
- POST /api/projects/{project_id}/script          保存脚本
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio
import logging
import cv2
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
import json
import uuid

from modules.projects_store import projects_store, Project
from modules.video_processor import video_processor
from services.script_generation_service import ScriptGenerationService
from services.video_generation_service import video_generation_service
from services.asr_bcut import BcutASR
from services.asr_utils import utterances_to_srt
from modules.config.content_model_config import content_model_config_manager
from modules.config.tts_config import tts_engine_config_manager
from modules.config.video_model_config import video_model_config_manager
from modules.ws_manager import manager


router = APIRouter(prefix="/api/projects", tags=["项目管理"])


def now_ts() -> str:
    return datetime.now().isoformat()


def project_root_dir() -> Path:
    # backend/routes/... -> backend -> project root
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def uploads_dir() -> Path:
    root = project_root_dir()
    up = root / "uploads"
    (up / "videos").mkdir(parents=True, exist_ok=True)
    (up / "subtitles").mkdir(parents=True, exist_ok=True)
    (up / "audios").mkdir(parents=True, exist_ok=True)
    (up / "analyses").mkdir(parents=True, exist_ok=True)
    return up


def to_web_path(p: Path) -> str:
    # 返回以 /uploads/... 开头的路径
    root = project_root_dir()
    rel = p.relative_to(root)
    return "/" + str(rel).replace("\\", "/")


async def ensure_models_ready_for_script(project_id: Optional[str] = None) -> None:
    """在生成脚本前统一校验：
    1) 当前激活的文案生成模型（大模型）是否就绪
    2) 当前激活的 TTS 配置是否就绪
    3) 可选：若存在激活的视频分析模型，打印连通性结果（不阻断脚本生成）

    失败则抛出 HTTPException。
    """
    # 校验文案生成模型（用于剧情分析与脚本JSON生成）
    # 进度：验证文案生成模型
    if project_id:
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": project_id,
                "phase": "validating_content_model",
                "message": "正在验证生成文本大模型是否可用",
                "progress": 5,
                "timestamp": now_ts(),
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
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
        raise HTTPException(status_code=400, detail="未找到激活的文案生成模型配置，请在“模型配置”中启用一个配置")
    content_result = await content_model_config_manager.test_connection(active_content_id)
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
                    "timestamp": now_ts(),
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
                "timestamp": now_ts(),
            }))
        except Exception:
            pass

    # 校验 TTS（用于后续配音合成）
    # 进度：验证TTS
    if project_id:
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": project_id,
                "phase": "validating_tts",
                "message": "正在验证TTS功能是否可用",
                "progress": 15,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass

    active_tts_id = tts_engine_config_manager.get_active_config_id()
    if not active_tts_id:
        if project_id:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "tts_missing",
                    "message": "未找到激活的TTS配置，请在“TTS配置”中启用并完善凭据",
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
        raise HTTPException(status_code=400, detail="未找到激活的TTS配置，请在“TTS配置”中启用并完善凭据")

    # 根据 provider 区分校验策略：
    # - 腾讯云 TTS：仍然严格校验，失败则阻断流程（避免后续配音时报错）
    # - Edge TTS：连通性依赖外网 / 代理，失败时仅记录告警，不阻断脚本生成
    tts_cfg = tts_engine_config_manager.get_config(active_tts_id)
    provider = (getattr(tts_cfg, "provider", None) or "tencent_tts").lower()

    tts_result = await tts_engine_config_manager.test_connection(active_tts_id)
    if not tts_result.get("success", False):
        msg = tts_result.get("error") or tts_result.get("message") or "TTS配置不可用"

        # Edge TTS：不阻断脚本生成，只提示告警
        if provider == "edge_tts":
            logging.warning(f"Edge TTS 配置连通性检查失败（忽略，不阻断脚本生成）：{msg}")
            if project_id:
                try:
                    await manager.broadcast(json.dumps({
                        "type": "warning",
                        "scope": "generate_script",
                        "project_id": project_id,
                        "phase": "tts_unavailable_edge",
                        "message": f"Edge TTS 配置连通性检查失败，将跳过强制校验：{msg}",
                        "timestamp": now_ts(),
                    }))
                except Exception:
                    pass
            # 直接返回，不再抛错
            return

        # 其他 TTS（例如腾讯云）：保持原有严格行为
        if project_id:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": project_id,
                    "phase": "tts_unavailable",
                    "message": f"TTS配置不可用：{msg}",
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=f"TTS配置不可用：{msg}")

    if project_id:
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": project_id,
                "phase": "tts_ready",
                "message": "TTS功能连通性正常",
                "progress": 20,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass

    # 可选：视频分析模型（仅记录日志，不阻断）
    # try:
    #     active_video_id = video_model_config_manager.get_active_config_id()
    #     if active_video_id:
    #         if project_id:
    #             try:
    #                 await manager.broadcast(json.dumps({
    #                     "type": "progress",
    #                     "scope": "generate_script",
    #                     "project_id": project_id,
    #                     "phase": "validating_video_model",
    #                     "message": "正在验证视频分析模型连通性（不影响脚本生成）",
    #                     "progress": 22,
    #                     "timestamp": now_ts(),
    #                 }))
    #             except Exception:
    #                 pass
    #         video_result = await video_model_config_manager.test_connection(active_video_id)
    #         if video_result.get("success", False):
    #             logging.info(f"视频分析模型连通性测试成功：{video_result}")
    #             if project_id:
    #                 try:
    #                     await manager.broadcast(json.dumps({
    #                         "type": "progress",
    #                         "scope": "generate_script",
    #                         "project_id": project_id,
    #                         "phase": "video_model_ready",
    #                         "message": "视频分析模型连通性正常（不影响脚本生成）",
    #                         "progress": 24,
    #                         "timestamp": now_ts(),
    #                     }))
    #                 except Exception:
    #                     pass
    #         else:
    #             logging.warning(f"视频分析模型连通性测试失败（不影响脚本生成）：{video_result}")
    #             if project_id:
    #                 try:
    #                     await manager.broadcast(json.dumps({
    #                         "type": "progress",
    #                         "scope": "generate_script",
    #                         "project_id": project_id,
    #                         "phase": "video_model_unavailable",
    #                         "message": "视频分析模型连通性失败（不影响脚本生成）",
    #                         "progress": 24,
    #                         "timestamp": now_ts(),
    #                     }))
    #                 except Exception:
    #                     pass
    # except Exception as e:
        # logging.warning(f"视频分析模型连通性测试异常（不阻断）：{e}")
        # if project_id:
        #     try:
        #         await manager.broadcast(json.dumps({
        #             "type": "progress",
        #             "scope": "generate_script",
        #             "project_id": project_id,
        #             "phase": "video_model_error",
        #             "message": "视频分析模型验证异常（不影响脚本生成）",
        #             "progress": 24,
        #             "timestamp": now_ts(),
        #         }))
        #     except Exception:
        #         pass


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None
    narration_type: Optional[str] = Field(default="短剧解说")


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    narration_type: Optional[str] = None
    status: Optional[str] = None
    video_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    audio_path: Optional[str] = None
    plot_analysis_path: Optional[str] = None
    script: Optional[Dict[str, Any]] = None


class DeleteVideoRequest(BaseModel):
    file_path: Optional[str] = None

class MergeTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str
    file_path: Optional[str] = None

MERGE_TASKS: Dict[str, MergeTaskStatus] = {}


class UpdateVideoOrderRequest(BaseModel):
    ordered_paths: List[str]


class GenerateScriptRequest(BaseModel):
    project_id: str
    video_path: str
    subtitle_path: Optional[str] = None
    narration_type: str


def parse_srt(srt_path: Path) -> List[Dict[str, Any]]:
    """简易SRT解析，返回包含 start/end/text 的列表"""
    def _parse_ts(ts: str) -> float:
        # format: HH:MM:SS,mmm
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    segments: List[Dict[str, Any]] = []
    try:
        content = srt_path.read_text(encoding="utf-8", errors="ignore")
        blocks = [b.strip() for b in content.strip().split("\n\n") if b.strip()]
        for idx, block in enumerate(blocks, start=1):
            lines = block.splitlines()
            if len(lines) < 2:
                continue
            # line 0 could be index, line 1 timing
            timing_line = lines[1] if "-->" in lines[1] else lines[0]
            if "-->" not in timing_line:
                continue
            start_str, end_str = [t.strip() for t in timing_line.split("-->")]
            start_t = _parse_ts(start_str)
            end_t = _parse_ts(end_str)
            text_lines = lines[2:] if timing_line == lines[1] else lines[1:]
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
        # 解析失败返回空
        pass
    return segments


def read_video_duration(video_path: Path) -> float:
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


# ========================= 项目管理 =========================

@router.get("")
async def list_projects():
    items = [p.model_dump() for p in projects_store.list_projects()]
    return {
        "message": "获取项目列表成功",
        "data": items,
        "timestamp": now_ts(),
    }


@router.get("/{project_id}")
async def get_project_detail(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "获取项目详情成功",
        "data": p.model_dump(),
        "timestamp": now_ts(),
    }


@router.post("")
async def create_project(req: CreateProjectRequest):
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="项目名称无效")
    p = projects_store.create_project(req.name.strip(), req.description, req.narration_type or "短剧解说")
    return JSONResponse(status_code=201, content={
        "message": "项目创建成功",
        "data": p.model_dump(),
        "timestamp": now_ts(),
    })


# ========================= 脚本生成 =========================

@router.post("/generate-script")
async def generate_script(req: GenerateScriptRequest):
    # 校验项目存在
    p = projects_store.get_project(req.project_id)
    if not p:
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "project_not_found",
                "message": "项目不存在",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="项目不存在")

    # 解析视频与字幕路径（支持 /uploads/... 或绝对路径）
    root = project_root_dir()
    def resolve_path(path_str: str) -> Path:
        path_str = path_str.strip()
        if path_str.startswith("/"):
            return root / path_str[1:]
        return Path(path_str)

    video_abs = resolve_path(req.video_path)
    if not video_abs.exists():
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "video_missing",
                "message": "视频文件不存在",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="视频文件不存在")

    # 生成脚本前，验证当前大模型与TTS是否已正确配置且连通
    try:
        await manager.broadcast(json.dumps({
            "type": "progress",
            "scope": "generate_script",
            "project_id": req.project_id,
            "phase": "start",
            "message": "开始生成解说脚本",
            "progress": 1,
            "timestamp": now_ts(),
        }))
    except Exception:
        pass

    await ensure_models_ready_for_script(req.project_id)

    total_duration = read_video_duration(video_abs)

    segments: List[Dict[str, Any]] = []
    subtitle_text: str = ""
    sub_abs: Optional[Path] = None
    # 优先使用项目已保存的字幕
    if p.subtitle_path:
        cand = resolve_path(p.subtitle_path)
        if cand.exists():
            sub_abs = cand
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "subtitle_exists",
                    "message": "已存在字幕文件，跳过ASR",
                    "progress": 60,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass

    # 其次使用请求传入的字幕
    if not sub_abs and req.subtitle_path:
        cand = resolve_path(req.subtitle_path)
        if cand.exists():
            sub_abs = cand
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "subtitle_exists",
                    "message": "已提供字幕文件，跳过ASR",
                    "progress": 60,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass

    # 若没有字幕，进行ASR识别
    if not sub_abs:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "validating_asr",
                "message": "正在验证ASR服务是否可用",
                "progress": 25,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        asr_check = await _run_in_thread(BcutASR.test_connection)
        if not asr_check.get("success", False):
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "asr_unavailable",
                    "message": asr_check.get("error") or asr_check.get("message") or "ASR服务不可用",
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
            raise HTTPException(status_code=400, detail=asr_check.get("error") or asr_check.get("message") or "ASR服务不可用")
        audio_abs: Optional[Path] = None
        # 复用已提取音频
        if getattr(p, "audio_path", None):
            a_cand = resolve_path(p.audio_path)
            if a_cand.exists():
                audio_abs = a_cand
                try:
                    await manager.broadcast(json.dumps({
                        "type": "progress",
                        "scope": "generate_script",
                        "project_id": req.project_id,
                        "phase": "audio_exists",
                        "message": "已存在提取音频，跳过音频提取",
                        "progress": 35,
                        "timestamp": now_ts(),
                    }))
                except Exception:
                    pass
        # 若无音频则提取
        if not audio_abs:
            audio_out = uploads_dir() / "audios" / f"{req.project_id}_audio_{ts}.mp3"
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "extract_audio",
                    "message": "正在提取音频",
                    "progress": 30,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
            ok_audio = await video_processor.extract_audio_mp3(str(video_abs), str(audio_out))
            if not ok_audio:
                try:
                    await manager.broadcast(json.dumps({
                        "type": "error",
                        "scope": "generate_script",
                        "project_id": req.project_id,
                        "phase": "extract_audio_failed",
                        "message": "音频提取失败",
                        "timestamp": now_ts(),
                    }))
                except Exception:
                    pass
                raise HTTPException(status_code=500, detail="音频提取失败")
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "audio_ready",
                    "message": "音频提取完成",
                    "progress": 40,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
            web_audio_path = to_web_path(audio_out)
            projects_store.update_project(req.project_id, {"audio_path": web_audio_path})
            audio_abs = audio_out

        asr = BcutASR(str(audio_abs))
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "asr_start",
                "message": "正在提取视频字幕（ASR）",
                "progress": 45,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        try:
            data = asr.run()
        except Exception as e:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "asr_exception",
                    "message": f"语音识别服务异常：{str(e)}",
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="语音识别失败")
        utterances = data.get("utterances") if isinstance(data, dict) else None
        if not isinstance(utterances, list) or not utterances:
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "asr_failed",
                    "message": "语音识别失败",
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="语音识别失败")
        srt_text = utterances_to_srt(utterances)
        srt_out = uploads_dir() / "subtitles" / f"{req.project_id}_subtitle_{ts}.srt"
        srt_out.write_text(srt_text, encoding="utf-8")
        web_path = to_web_path(srt_out)
        projects_store.update_project(req.project_id, {"subtitle_path": web_path})
        sub_abs = srt_out
        logging.info(f"asr识别结果保存到 {srt_out}")
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "subtitle_ready",
                "message": "字幕提取完成",
                "progress": 60,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass

    if sub_abs and sub_abs.exists():
        try:
            subtitle_text = sub_abs.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            subtitle_text = ""
        segments = parse_srt(sub_abs)
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "subtitle_parsed",
                "message": "已解析字幕内容",
                "progress": 65,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass

    # 状态变更为 processing
    projects_store.update_project(req.project_id, {"status": "processing"})
    try:
        await manager.broadcast(json.dumps({
            "type": "progress",
            "scope": "generate_script",
            "project_id": req.project_id,
            "phase": "processing",
            "message": "开始使用大模型生成脚本",
            "progress": 68,
            "timestamp": now_ts(),
        }))
    except Exception:
        pass

    try:
        drama_name = p.name or "剧名"
        # 1) 爆点分析
        # 1) 爆点分析
        # 爆点分析：若已存在则复用，否则生成并保存到 uploads/analyses
        plot_analysis: str = ""
        reused_analysis = False
        if getattr(p, "plot_analysis_path", None):
            plot_abs_cand = resolve_path(p.plot_analysis_path)
            if plot_abs_cand.exists():
                try:
                    plot_analysis = plot_abs_cand.read_text(encoding="utf-8", errors="ignore")
                    reused_analysis = True
                except Exception:
                    plot_analysis = ""
        if not plot_analysis:
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "llm_analyze_subtitle",
                    "message": "大模型分析字幕",
                    "progress": 70,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
            plot_analysis = await ScriptGenerationService.generate_plot_analysis(subtitle_text)
            ts_pa = datetime.now().strftime("%Y%m%d_%H%M%S")
            pa_out = uploads_dir() / "analyses" / f"{req.project_id}_analysis_{ts_pa}.txt"
            try:
                pa_out.write_text(plot_analysis, encoding="utf-8")
                web_pa = to_web_path(pa_out)
                projects_store.update_project(req.project_id, {"plot_analysis_path": web_pa})
            except Exception:
                # 写文件失败不阻断流程
                pass
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "llm_analysis_done",
                    "message": "字幕分析完成",
                    "progress": 75,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
        else:
            try:
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "generate_script",
                    "project_id": req.project_id,
                    "phase": "llm_analysis_done",
                    "message": "已复用历史字幕分析",
                    "progress": 75,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
        # 2) 格式化脚本（JSON）
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "llm_generate_script",
                "message": "大模型生成脚本",
                "progress": 80,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        script_json = await ScriptGenerationService.generate_script_json(
            drama_name=drama_name,
            plot_analysis=plot_analysis,
            subtitle_content=subtitle_text,
        )
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "llm_generate_done",
                "message": "脚本生成完成，进行格式化",
                "progress": 85,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        # 3) 转为 VideoScript 结构
        script = ScriptGenerationService.to_video_script(script_json, total_duration)
        try:
            await manager.broadcast(json.dumps({
                "type": "progress",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "script_structured",
                "message": "脚本结构化完成，保存中",
                "progress": 90,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        # 4) 保存到项目并返回
        p2 = projects_store.save_script(req.project_id, script)
        projects_store.update_project(req.project_id, {"status": "completed"})
        try:
            await manager.broadcast(json.dumps({
                "type": "completed",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "done",
                "message": "解说脚本生成成功",
                "progress": 100,
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        return {
            "message": "解说脚本生成成功",
            "data": {
                "script": script,
                "plot_analysis": plot_analysis,
            },
            "timestamp": now_ts(),
        }
    except Exception as e:
        # 失败时更新状态
        projects_store.update_project(req.project_id, {"status": "failed"})
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": "generate_script",
                "project_id": req.project_id,
                "phase": "failed",
                "message": f"脚本生成失败: {str(e)}",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"脚本生成失败: {str(e)}")


@router.post("/{project_id}")
async def update_project(project_id: str, req: UpdateProjectRequest):
    p = projects_store.update_project(project_id, req.model_dump(exclude_unset=True))
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "项目更新成功",
        "data": {
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "updated_at": p.updated_at,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/delete")
async def delete_project(project_id: str):
    ok = projects_store.delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "项目删除成功",
        "success": True,
        "timestamp": now_ts(),
    }


# ========================= 文件上传 =========================

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}


@router.post("/{project_id}/upload/video")
async def upload_video(project_id: str, file: UploadFile = File(...), project_id_form: str = Form(None)):
    # 校验项目存在
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 校验扩展名
    suffix = Path(file.filename).suffix.lower()
    if suffix not in VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="文件格式不支持")

    # 保存文件
    up_dir = uploads_dir() / "videos"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique = uuid.uuid4().hex[:8]
    out_name = f"{project_id}_video_{ts}_{unique}{suffix}"
    out_path = up_dir / out_name

    size = 0
    try:
        with out_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                f.write(chunk)
    finally:
        await file.close()

    # 记录到项目的视频列表，并按规则更新生效路径
    web_path = to_web_path(out_path)
    # 记录路径与原始文件名
    projects_store.append_video_path(project_id, web_path, file.filename)

    return {
        "message": "视频上传成功",
        "data": {
            "file_path": web_path,
            "file_name": file.filename,
            "file_size": size,
            "upload_time": now_ts(),
        },
        "timestamp": now_ts(),
    }


    


# ========================= 文件删除 =========================

@router.post("/{project_id}/delete/video")
async def delete_video_file(project_id: str, request: Request, req: Optional[DeleteVideoRequest] = Body(None), file_path_form: Optional[str] = Form(None)):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 选择目标删除路径：优先使用传入的 file_path，其次兼容旧逻辑（使用生效路径）
    removed = False
    removed_path = None
    target_path = None
    # 同时兼容 JSON Body 与 Form 提交
    if req and req.file_path:
        target_path = req.file_path.strip()
    else:
        # 尝试直接解析原始请求体（JSON 或 Form），以覆盖混合场景
        json_candidate = None
        try:
            body_json = await request.json()
            if isinstance(body_json, dict):
                json_candidate = (body_json.get("file_path") or "").strip() or None
        except Exception:
            pass

        form_candidate = None
        try:
            form = await request.form()
            form_candidate = (form.get("file_path") or form.get("file_path_form") or "").strip() or None
        except Exception:
            pass

        if json_candidate:
            target_path = json_candidate
        elif file_path_form:
            target_path = (file_path_form or "").strip() or None
        elif form_candidate:
            target_path = form_candidate
        else:
            target_path = (p.video_path or "").strip() if p.video_path else None

    if target_path:
        root = project_root_dir()
        path_str = target_path
        abs_path = root / path_str[1:] if path_str.startswith("/") else Path(path_str)
        try:
            if abs_path.exists() and abs_path.is_file():
                removed_path = str(abs_path)
                abs_path.unlink()
                removed = True
        except Exception:
            pass

    # 从列表移除对应项；若未传入路径且是旧逻辑，清空生效路径
    if target_path:
        # 传入已修剪的路径，确保与存储层中的字符串一致
        p2 = projects_store.remove_video_path(project_id, target_path)
        # 若传入的是绝对路径或不同规范，尝试按统一web规范再次移除
        try:
            root = project_root_dir()
            abs_path2 = root / target_path[1:] if target_path.startswith("/") else Path(target_path)
            web_norm = to_web_path(abs_path2)
            if web_norm != target_path:
                p2 = projects_store.remove_video_path(project_id, web_norm) or p2
        except Exception:
            pass
    else:
        p2 = projects_store.clear_video_path(project_id)
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    return {
        "message": "视频删除成功",
        "data": {
            "removed": removed,
            "removed_path": to_web_path(Path(removed_path)) if removed_path else None,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/merge/videos")
async def merge_videos(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.video_paths or len(p.video_paths) < 2:
        raise HTTPException(status_code=400, detail="需要至少两个视频进行合并")

    task_id = f"merge_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    MERGE_TASKS[task_id] = MergeTaskStatus(task_id=task_id, status="pending", progress=0.0, message="准备合并")

    async def _run():
        try:
            MERGE_TASKS[task_id].status = "processing"
            MERGE_TASKS[task_id].message = "正在合并"
            try:
                # 广播任务开始
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "merge_videos",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "开始合并视频",
                    "progress": 0,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass

            root = project_root_dir()
            inputs: List[Path] = []
            for path_str in p.video_paths:
                s = path_str.strip()
                abs_path = root / s[1:] if s.startswith("/") else Path(s)
                if not abs_path.exists():
                    MERGE_TASKS[task_id].status = "failed"
                    MERGE_TASKS[task_id].message = f"源视频不存在: {s}"
                    return
                inputs.append(abs_path)

            out_dir = uploads_dir() / "videos" / "outputs" / p.name
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_name = f"{p.id}_merged_{ts}.mp4"
            out_path = out_dir / out_name

            async def on_progress(pct: float):
                MERGE_TASKS[task_id].progress = float(f"{pct:.2f}")
                try:
                    await manager.broadcast(json.dumps({
                        "type": "progress",
                        "scope": "merge_videos",
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": "正在合并",
                        "progress": MERGE_TASKS[task_id].progress,
                        "timestamp": now_ts(),
                    }))
                except Exception:
                    pass

            ok = await video_processor.concat_videos([str(x) for x in inputs], str(out_path), on_progress)
            if not ok:
                MERGE_TASKS[task_id].status = "failed"
                MERGE_TASKS[task_id].message = "合并失败"
                try:
                    await manager.broadcast(json.dumps({
                        "type": "error",
                        "scope": "merge_videos",
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": "合并失败",
                        "progress": MERGE_TASKS[task_id].progress,
                        "timestamp": now_ts(),
                    }))
                except Exception:
                    pass
                return

            web_path = to_web_path(out_path)
            MERGE_TASKS[task_id].file_path = web_path
            MERGE_TASKS[task_id].progress = 100.0
            MERGE_TASKS[task_id].status = "completed"
            MERGE_TASKS[task_id].message = "合并完成"
            # 设置合并后路径并同步当前文件名（使用输出文件名）
            projects_store.set_merged_video_path(project_id, web_path, out_name)
            try:
                await manager.broadcast(json.dumps({
                    "type": "completed",
                    "scope": "merge_videos",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "合并完成",
                    "progress": 100,
                    "file_path": web_path,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass
        except Exception:
            MERGE_TASKS[task_id].status = "failed"
            MERGE_TASKS[task_id].message = "合并异常"
            try:
                await manager.broadcast(json.dumps({
                    "type": "error",
                    "scope": "merge_videos",
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "合并异常",
                    "progress": MERGE_TASKS[task_id].progress,
                    "timestamp": now_ts(),
                }))
            except Exception:
                pass

    asyncio.create_task(_run())

    return {
        "message": "开始合并",
        "data": {
            "task_id": task_id,
        },
        "timestamp": now_ts(),
    }

@router.get("/{project_id}/merge/videos/status/{task_id}")
async def merge_videos_status(project_id: str, task_id: str):
    t = MERGE_TASKS.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "message": "获取合并进度",
        "data": t.model_dump(),
        "timestamp": now_ts(),
    }


# 更新项目的视频排序（按用户顺序）
@router.post("/{project_id}/videos/order")
async def update_video_order(project_id: str, req: UpdateVideoOrderRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    existing = list(p.video_paths or [])
    new_order = list(req.ordered_paths or [])
    # 校验：必须与现有视频集合一致
    if len(existing) != len(new_order) or set(existing) != set(new_order):
        raise HTTPException(status_code=400, detail="排序列表与现有视频不匹配")
    try:
        updated = projects_store.update_project(project_id, {"video_paths": new_order})
        if not updated:
            raise HTTPException(status_code=500, detail="更新排序失败")
        return {
            "message": "更新排序成功",
            "data": updated.model_dump(),
            "timestamp": now_ts(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"更新数据格式无效: {e}")


@router.post("/{project_id}/delete/subtitle")
async def delete_subtitle_file(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    removed = False
    removed_path = None
    if p.subtitle_path:
        root = project_root_dir()
        path_str = p.subtitle_path.strip()
        abs_path = root / path_str[1:] if path_str.startswith("/") else Path(path_str)
        try:
            if abs_path.exists() and abs_path.is_file():
                removed_path = str(abs_path)
                abs_path.unlink()
                removed = True
        except Exception:
            pass

    p2 = projects_store.clear_subtitle_path(project_id)
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    return {
        "message": "字幕删除成功",
        "data": {
            "removed": removed,
            "removed_path": to_web_path(Path(removed_path)) if removed_path else None,
        },
        "timestamp": now_ts(),
    }


# ========================= 脚本保存 =========================


class SaveScriptRequest(BaseModel):
    script: Dict[str, Any]


@router.post("/{project_id}/script")
async def save_script(project_id: str, req: SaveScriptRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    script = req.script
    if not isinstance(script, dict) or "segments" not in script:
        raise HTTPException(status_code=400, detail="脚本格式错误")

    p2 = projects_store.save_script(project_id, script)
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    return {
        "message": "脚本保存成功",
        "data": script,
        "timestamp": now_ts(),
    }


# ========================= 视频生成与下载 =========================

@router.post("/{project_id}/generate-video")
async def generate_video(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not p.script or not isinstance(p.script, dict):
        raise HTTPException(status_code=400, detail="请先生成并保存脚本")
    if not p.video_path:
        raise HTTPException(status_code=400, detail="请先上传原始视频文件")

    # 状态置为 processing
    projects_store.update_project(project_id, {"status": "processing"})

    try:
        result = await video_generation_service.generate_from_script(project_id)
        return {
            "message": "视频生成成功",
            "data": result,
            "timestamp": now_ts(),
        }
    except Exception as e:
        projects_store.update_project(project_id, {"status": "failed"})
        # 广播错误事件
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": "generate_video",
                "project_id": project_id,
                "phase": "failed",
                "message": f"生成视频失败: {str(e)}",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"生成视频失败: {str(e)}")


@router.get("/{project_id}/output-video")
async def download_output_video(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.output_video_path:
        raise HTTPException(status_code=404, detail="尚未生成输出视频")

    root = project_root_dir()
    path_str = p.output_video_path.strip()
    abs_path = root / path_str[1:] if path_str.startswith("/") else Path(path_str)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="输出视频文件不存在")

    filename = abs_path.name
    return FileResponse(
        path=str(abs_path),
        filename=filename,
        media_type="video/mp4"
    )

# ========================= 合并视频播放 =========================

@router.get("/{project_id}/merged-video")
async def get_merged_video(project_id: str):
    """获取已合并视频文件用于播放。如果不存在则返回404。"""
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.merged_video_path:
        raise HTTPException(status_code=404, detail="尚未存在合并后的视频")

    root = project_root_dir()
    path_str = p.merged_video_path.strip()
    abs_path = root / path_str[1:] if path_str.startswith("/") else Path(path_str)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="合并视频文件不存在")

    filename = abs_path.name
    # 合并输出目前固定为 mp4
    return FileResponse(
        path=str(abs_path),
        filename=filename,
        media_type="video/mp4"
    )
async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
