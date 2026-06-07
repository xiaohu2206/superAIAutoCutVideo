#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI内容生成相关API路由：脚本生成、文案生成、字幕提取、场景提取、视频生成、任务管理
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio
import uuid
import logging

from fastapi import APIRouter, HTTPException, Body, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .project_routes import (
    now_ts,
    to_web_path,
    resolve_abs_path,
    uploads_dir,
    _segments_to_compressed_srt,
    GenerateScriptRequest,
    GenerateCopywritingRequest,
    ExtractSubtitleRequest,
    SubtitleSegmentInput,
    SaveSubtitleRequest,
    MergeTaskStatus,
    MERGE_TASKS,
    VIDEO_TASKS,
    DRAFT_TASKS,
    DRAFT_TASK_HANDLES,
    VIDEO_TASK_HANDLES,
)
from modules.projects_store import ScriptRevisionConflict, projects_store
from modules.ws_manager import manager
from modules.task_progress_store import task_progress_store
from modules.task_cancel_store import task_cancel_store
from modules.task_scheduler import task_scheduler
from modules.project_task_queue import project_task_queue
from modules.subtitle_utils import parse_srt, format_ts_srt
from services.generate_script_service import generate_script_service
from services.generate_copywriting_service import generate_copywriting_service
from services.asr.extract_subtitle_service import extract_subtitle_service, EXTRACT_SUBTITLE_SCOPE
from services.extract_scene_service import extract_scene_service
from services.video_generation_service import video_generation_service
from services.jianying_draft_manager import jianying_draft_manager, JianyingDraftManager
from modules.config.jianying_config import jianying_config_manager
from modules.config.generate_concurrency_config import generate_concurrency_config_manager
from modules.auth.omni_project_license import require_valid_license_for_omni
from services.omni_multimodal_pipeline_service import omni_multimodal_pipeline_service
from omni_full_narration_pipeline import omni_full_narration_pipeline_service

router = APIRouter(prefix="/api/projects", tags=["项目管理"])
logger = logging.getLogger(__name__)
ONE_CLICK_GENERATE_SCOPE = "one_click_generate"


class SaveScriptRequest(BaseModel):
    script: Dict[str, Any]
    expected_revision: Optional[int] = None


class SaveCopywritingRequest(BaseModel):
    copywriting: Dict[str, Any]


class CancelTaskRequest(BaseModel):
    scope: str
    task_id: Optional[str] = None


class OneClickGenerateRequest(BaseModel):
    target: str = "draft"
    force: bool = False
    task_id: Optional[str] = None
    asr_provider: Optional[str] = None
    asr_model_key: Optional[str] = None
    asr_language: Optional[str] = None
    itn: bool = True
    hotwords: Optional[List[str]] = None
    analyzeVision: bool = False
    visionMode: str = "all"
    visionKeyFrames: int = 1
    visionAction: str = "auto"
    multimodal_action: str = "auto"


@router.post("/generate-script")
async def generate_script(req: GenerateScriptRequest):
    task_id = f"script_{req.project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    scope = "generate_script"
    await project_task_queue.acquire(req.project_id, scope, task_id)
    try:
        try:
            logger.info(
                "route generate-script project_id=%s video_path=%s subtitle_path=%s narration_type=%s",
                req.project_id,
                req.video_path,
                req.subtitle_path,
                (req.narration_type or "")[:50],
            )
        except Exception:
            pass
        return await generate_script_service.generate_script(
            project_id=req.project_id,
            video_path=req.video_path,
            subtitle_path=req.subtitle_path,
            narration_type=req.narration_type,
        )
    except HTTPException as e:
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": scope,
                "project_id": req.project_id,
                "phase": "failed",
                "message": str(getattr(e, "detail", "")) or "脚本生成失败",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": scope,
                "phase": "failed",
                "message": str(getattr(e, "detail", "")) or "脚本生成失败",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise
    except Exception as e:
        projects_store.update_project(req.project_id, {"status": "failed"})
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": scope,
                "project_id": req.project_id,
                "phase": "failed",
                "message": f"脚本生成失败: {str(e)}",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"脚本生成失败: {str(e)}")
    finally:
        await project_task_queue.release(req.project_id)


@router.post("/generate-copywriting")
async def generate_copywriting(req: GenerateCopywritingRequest):
    task_id = f"generate_copywriting_{req.project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    scope = "generate_copywriting"
    await project_task_queue.acquire(req.project_id, scope, task_id)
    try:
        try:
            task_progress_store.set_state(
                scope=scope,
                project_id=req.project_id,
                task_id=task_id,
                status="processing",
                progress=1.0,
                message="开始生成解说文案",
                phase="start",
                msg_type="progress",
                timestamp=now_ts(),
            )
        except Exception:
            pass
        try:
            logger.info(
                "route generate-copywriting project_id=%s video_path=%s subtitle_path=%s narration_type=%s",
                req.project_id,
                req.video_path,
                req.subtitle_path,
                (req.narration_type or "")[:50],
            )
        except Exception:
            pass
        cancel_event = task_cancel_store.get_event(scope, req.project_id, task_id)
        return await generate_copywriting_service.generate_copywriting(
            project_id=req.project_id,
            video_path=req.video_path,
            subtitle_path=req.subtitle_path,
            narration_type=req.narration_type,
            task_id=task_id,
            cancel_event=cancel_event,
        )
    except asyncio.CancelledError:
        try:
            task_progress_store.set_state(
                scope=scope,
                project_id=req.project_id,
                task_id=task_id,
                status="cancelled",
                progress=0.0,
                message="已停止",
                phase="cancelled",
                msg_type="cancelled",
                timestamp=now_ts(),
            )
        except Exception:
            pass
        try:
            await manager.broadcast(json.dumps({
                "type": "cancelled",
                "scope": "generate_copywriting",
                "project_id": req.project_id,
                "task_id": task_id,
                "phase": "cancelled",
                "message": "已停止",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="文案生成已停止")
    except HTTPException as e:
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": "generate_copywriting",
                "project_id": req.project_id,
                "task_id": task_id,
                "phase": "failed",
                "message": str(getattr(e, "detail", "")) or "文案生成失败",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise
    except Exception as e:
        projects_store.update_project(req.project_id, {"status": "failed"})
        try:
            task_progress_store.set_state(
                scope="generate_copywriting",
                project_id=req.project_id,
                task_id=task_id,
                status="failed",
                progress=0.0,
                message=f"文案生成失败: {str(e)}",
                phase="failed",
                msg_type="error",
                timestamp=now_ts(),
            )
        except Exception:
            pass
        try:
            await manager.broadcast(json.dumps({
                "type": "error",
                "scope": "generate_copywriting",
                "project_id": req.project_id,
                "task_id": task_id,
                "phase": "failed",
                "message": f"文案生成失败: {str(e)}",
                "timestamp": now_ts(),
            }))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"文案生成失败: {str(e)}")
    finally:
        await project_task_queue.release(req.project_id)


@router.post("/{project_id}/extract-subtitle")
async def extract_subtitle(project_id: str, req: ExtractSubtitleRequest = Body(default=ExtractSubtitleRequest())):
    task_id = str(req.task_id or "").strip() or f"subtitle_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    cancel_event = task_cancel_store.get_event(EXTRACT_SUBTITLE_SCOPE, project_id, task_id)
    await project_task_queue.acquire(project_id, EXTRACT_SUBTITLE_SCOPE, task_id, cancel_event=cancel_event)
    try:
        data = await extract_subtitle_service.extract_subtitle(
            project_id=project_id,
            force=bool(req.force),
            task_id=task_id,
            asr_provider=req.asr_provider,
            asr_model_key=req.asr_model_key,
            asr_language=req.asr_language,
            itn=bool(getattr(req, "itn", True)),
            hotwords=req.hotwords,
        )
        return {
            "message": "字幕提取成功",
            "data": data,
            "timestamp": now_ts(),
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            p = projects_store.get_project(project_id)
            cur = getattr(p, "subtitle_extract_run_id", None) if p else None
            if not task_id or (cur and cur == task_id):
                projects_store.update_project(project_id, {"subtitle_status": "failed"})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"字幕提取失败: {str(e)}")
    finally:
        await project_task_queue.release(project_id)


@router.post("/{project_id}/extract-scene")
async def extract_scene(project_id: str, req: ExtractSubtitleRequest = Body(default=ExtractSubtitleRequest())):
    try:
        vk = int(getattr(req, "visionKeyFrames", 1) or 1)
        if vk not in (1, 3):
            vk = 1
        va = str(getattr(req, "visionAction", "auto") or "auto").strip().lower()
        if va not in ("auto", "continue", "restart"):
            va = "auto"
        data = await extract_scene_service.extract_scenes(
            project_id=project_id,
            force=bool(req.force),
            task_id=req.task_id,
            asr_provider=req.asr_provider,
            asr_model_key=req.asr_model_key,
            asr_language=req.asr_language,
            itn=bool(getattr(req, "itn", True)),
            hotwords=req.hotwords,
            analyze_vision=bool(req.analyzeVision),
            vision_mode=req.visionMode,
            vision_key_frames=vk,
            vision_action=va,
        )
        return {
            "message": "镜头提取任务已提交",
            "data": data,
            "timestamp": now_ts(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"镜头提取提交失败: {str(e)}")


def _http_detail(exc: BaseException) -> str:
    if isinstance(exc, HTTPException):
        return str(getattr(exc, "detail", "") or "")
    return str(exc)


def _one_click_progress(
    project_id: str,
    task_id: str,
    progress: float,
    message: str,
    *,
    phase: str = "processing",
    status: str = "processing",
    msg_type: str = "progress",
) -> None:
    task_progress_store.set_state(
        scope=ONE_CLICK_GENERATE_SCOPE,
        project_id=project_id,
        task_id=task_id,
        status=status,
        progress=float(progress),
        message=message,
        phase=phase,
        msg_type=msg_type,
        timestamp=now_ts(),
    )


async def _wait_child_task(
    scope: str,
    project_id: str,
    task_id: str,
    parent_cancel_event: asyncio.Event,
    *,
    timeout_sec: float = 60 * 60 * 6,
) -> Dict[str, Any]:
    started = asyncio.get_running_loop().time()
    while True:
        if parent_cancel_event.is_set():
            try:
                await task_cancel_store.cancel(scope, project_id, task_id)
            except Exception:
                pass
            raise asyncio.CancelledError()
        st = task_progress_store.get_state(scope, project_id, task_id)
        if st:
            status = str(st.get("status") or "").strip().lower()
            msg_type = str(st.get("type") or "").strip().lower()
            if status == "completed" or msg_type == "completed":
                return st
            if status in {"failed", "error"} or msg_type == "error":
                raise RuntimeError(str(st.get("message") or "子任务执行失败"))
            if status == "cancelled" or msg_type == "cancelled":
                raise asyncio.CancelledError()
        if asyncio.get_running_loop().time() - started > float(timeout_sec or 0):
            raise TimeoutError(f"{scope} 子任务等待超时")
        await asyncio.sleep(1.0)


@router.post("/{project_id}/one-click-generate")
async def one_click_generate(
    project_id: str,
    request: Request,
    req: OneClickGenerateRequest = Body(default=OneClickGenerateRequest()),
):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    project_type = str(getattr(p, "project_type", "") or "subtitle").strip().lower()
    if project_type not in {"subtitle", "visual", "omni"}:
        raise HTTPException(status_code=400, detail="项目类型不支持一键生成")
    if not p.video_path:
        raise HTTPException(status_code=400, detail="请先上传视频文件")
    if project_type == "omni":
        try:
            await require_valid_license_for_omni(request.headers.get("Authorization"))
        except HTTPException:
            raise
        except Exception:
            logger.exception("Omni one-click license check failed")
            raise HTTPException(status_code=500, detail="License 校验异常，请稍后重试。")

    target = str(req.target or getattr(p, "one_click_generate_target", None) or "draft").strip().lower()
    if target not in {"draft", "video"}:
        target = "draft"
    if target == "draft":
        cfg_path = jianying_config_manager.get_draft_path()
        if not cfg_path or not cfg_path.exists():
            raise HTTPException(status_code=400, detail="未设置剪映草稿路径，无法一键生成草稿")

    candidate_task_id = (
        str(req.task_id).strip()
        if req.task_id
        else f"one_click_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    )

    async def _run(pid: str, task_id: str, cancel_event: asyncio.Event) -> Dict[str, Any]:
        await project_task_queue.acquire(pid, ONE_CLICK_GENERATE_SCOPE, task_id, cancel_event=cancel_event)
        child_ids: Dict[str, str] = {}
        try:
            current = projects_store.get_project(pid)
            if not current:
                raise HTTPException(status_code=404, detail="项目不存在")
            pt = str(getattr(current, "project_type", "") or "subtitle").strip().lower()
            if not current.video_path:
                raise HTTPException(status_code=400, detail="请先上传视频文件")

            _one_click_progress(pid, task_id, 3, "一键生成已启动", phase="start")
            projects_store.update_project(pid, {
                "status": "processing",
                "one_click_generate_target": target,
                "one_click_generate_enabled": True,
            })

            def _ensure_not_cancelled() -> None:
                if cancel_event.is_set():
                    raise asyncio.CancelledError()

            subtitle_source = getattr(current, "subtitle_source", None)
            has_user_subtitle = subtitle_source == "user" and bool(getattr(current, "subtitle_path", None))
            subtitle_ready = bool(getattr(current, "subtitle_path", None)) and (
                not getattr(current, "subtitle_status", None) or getattr(current, "subtitle_status", None) == "ready"
            )
            if not has_user_subtitle and (req.force or not subtitle_ready):
                sub_task_id = f"{task_id}_subtitle"
                child_ids["extract_subtitle"] = sub_task_id
                _one_click_progress(pid, task_id, 8, "正在提取字幕", phase="extract_subtitle")
                await extract_subtitle_service.extract_subtitle(
                    project_id=pid,
                    force=bool(req.force),
                    task_id=sub_task_id,
                    asr_provider=req.asr_provider,
                    asr_model_key=req.asr_model_key,
                    asr_language=req.asr_language,
                    itn=bool(getattr(req, "itn", True)),
                    hotwords=req.hotwords,
                )
            else:
                _one_click_progress(pid, task_id, 12, "字幕已就绪，跳过字幕提取", phase="extract_subtitle")

            _ensure_not_cancelled()
            current = projects_store.get_project(pid) or current

            if pt == "visual":
                scene_task_id = f"{task_id}_scene"
                child_ids["extract_scene"] = scene_task_id
                vk = int(getattr(req, "visionKeyFrames", 1) or 1)
                if vk not in (1, 3):
                    vk = 1
                va = str(getattr(req, "visionAction", "auto") or "auto").strip().lower()
                if va not in ("auto", "continue", "restart"):
                    va = "auto"
                _one_click_progress(pid, task_id, 22, "正在分析镜头", phase="extract_scene")
                await extract_scene_service.extract_scenes(
                    project_id=pid,
                    force=bool(req.force),
                    task_id=scene_task_id,
                    asr_provider=req.asr_provider,
                    asr_model_key=req.asr_model_key,
                    asr_language=req.asr_language,
                    itn=bool(getattr(req, "itn", True)),
                    hotwords=req.hotwords,
                    analyze_vision=bool(req.analyzeVision),
                    vision_mode=req.visionMode,
                    vision_key_frames=vk,
                    vision_action=va,
                )
                await _wait_child_task(extract_scene_service.SCOPE, pid, scene_task_id, cancel_event)
                _one_click_progress(pid, task_id, 40, "镜头分析完成", phase="extract_scene")
            elif pt == "omni":
                omni_task_id = f"{task_id}_omni_multimodal"
                child_ids["omni_multimodal"] = omni_task_id
                mma = str(getattr(req, "multimodal_action", "auto") or "auto").strip().lower()
                if mma not in ("auto", "continue", "restart"):
                    mma = "auto"
                _one_click_progress(pid, task_id, 22, "正在执行 Omni 全感知推理", phase="omni_multimodal")
                await omni_multimodal_pipeline_service.submit_pipeline(
                    project_id=pid,
                    force=bool(req.force) or mma == "restart",
                    task_id=omni_task_id,
                    multimodal_action=mma,
                )
                await _wait_child_task(omni_multimodal_pipeline_service.SCOPE, pid, omni_task_id, cancel_event)
                _one_click_progress(pid, task_id, 40, "Omni 全感知推理完成", phase="omni_multimodal")

            _ensure_not_cancelled()
            current = projects_store.get_project(pid) or current
            subtitle_path = getattr(current, "subtitle_path", None)

            copy_task_id = f"{task_id}_copywriting"
            child_ids["generate_copywriting"] = copy_task_id
            _one_click_progress(pid, task_id, 48, "正在生成解说文案", phase="generate_copywriting")
            copywriting_resp = await generate_copywriting_service.generate_copywriting(
                project_id=pid,
                video_path=current.video_path,
                subtitle_path=subtitle_path,
                narration_type=current.narration_type,
                task_id=copy_task_id,
                cancel_event=cancel_event,
            )
            copywriting_data = None
            try:
                if isinstance(copywriting_resp, dict):
                    data = copywriting_resp.get("data")
                    if isinstance(data, dict):
                        copywriting_data = data.get("copywriting")
            except Exception:
                copywriting_data = None
            if not isinstance(copywriting_data, dict) or not str(copywriting_data.get("content") or "").strip():
                raise HTTPException(status_code=500, detail="解说文案生成结果为空，无法继续生成脚本")
            projects_store.update_project(pid, {"narration_copywriting": copywriting_data})

            _ensure_not_cancelled()
            current = projects_store.get_project(pid) or current
            if pt == "omni":
                full_task_id = f"{task_id}_omni_full"
                child_ids["omni_full_narration_pipeline"] = full_task_id
                _one_click_progress(pid, task_id, 58, "正在执行 Omni 全链路脚本编排", phase="omni_full_narration_pipeline")
                await omni_full_narration_pipeline_service.submit_run(
                    pid,
                    force=bool(req.force),
                    task_id=full_task_id,
                    skip_global_path_search=False,
                    skip_generate_script_llm=None,
                )
                await _wait_child_task(omni_full_narration_pipeline_service.SCOPE, pid, full_task_id, cancel_event)
                _one_click_progress(pid, task_id, 76, "Omni 解说脚本生成完成", phase="omni_generate_script")
            else:
                script_task_id = f"{task_id}_script"
                child_ids["generate_script"] = script_task_id
                task_progress_store.set_state(
                    "generate_script",
                    pid,
                    script_task_id,
                    "processing",
                    1.0,
                    "开始生成解说脚本",
                    phase="start",
                    msg_type="progress",
                    timestamp=now_ts(),
                )
                _one_click_progress(pid, task_id, 68, "正在生成解说脚本", phase="generate_script")
                await generate_script_service.generate_script(
                    project_id=pid,
                    video_path=current.video_path,
                    subtitle_path=getattr(current, "subtitle_path", None),
                    narration_type=current.narration_type,
                )
                task_progress_store.set_state(
                    "generate_script",
                    pid,
                    script_task_id,
                    "completed",
                    100.0,
                    "解说脚本生成成功",
                    phase="done",
                    msg_type="completed",
                    timestamp=now_ts(),
                )

            _ensure_not_cancelled()
            if target == "draft":
                draft_task_id = f"{task_id}_draft"
                child_ids["generate_jianying_draft"] = draft_task_id
                task_progress_store.set_state(
                    JianyingDraftManager.SCOPE,
                    pid,
                    draft_task_id,
                    "processing",
                    1.0,
                    "开始生成剪映草稿",
                    phase="start",
                    msg_type="progress",
                    timestamp=now_ts(),
                )
                _one_click_progress(pid, task_id, 84, "正在生成剪映草稿", phase="generate_draft")
                r = await jianying_draft_manager.generate_draft_folder(
                    project_id=pid,
                    task_id=draft_task_id,
                    cancel_event=cancel_event,
                )
                try:
                    pr = projects_store.get_project(pid)
                    prev_dirs = list((pr.model_dump().get("jianying_draft_dirs") if pr else []) or [])
                    projects_store.update_project(
                        pid,
                        {
                            "jianying_draft_last_dir": str(r.dir_abs),
                            "jianying_draft_last_dir_web": r.dir_web,
                            "jianying_draft_dirs": list(set(prev_dirs + [r.dir_web])),
                        },
                    )
                except Exception:
                    pass
                task_progress_store.set_state(
                    JianyingDraftManager.SCOPE,
                    pid,
                    draft_task_id,
                    "completed",
                    100.0,
                    "剪映草稿生成完成",
                    phase="completed",
                    msg_type="completed",
                    timestamp=now_ts(),
                )
                result: Dict[str, Any] = {"target": target, "file_path": r.dir_web, "child_task_ids": child_ids}
            else:
                video_task_id = f"{task_id}_video"
                child_ids["generate_video"] = video_task_id
                task_progress_store.set_state(
                    "generate_video",
                    pid,
                    video_task_id,
                    "processing",
                    1.0,
                    "开始生成视频",
                    phase="start",
                    msg_type="progress",
                    timestamp=now_ts(),
                )
                _one_click_progress(pid, task_id, 84, "正在生成视频", phase="generate_video")
                video_result = await video_generation_service.generate_from_script(
                    pid,
                    task_id=video_task_id,
                    cancel_event=cancel_event,
                )
                task_progress_store.set_state(
                    "generate_video",
                    pid,
                    video_task_id,
                    "completed",
                    100.0,
                    "视频生成完成",
                    phase="completed",
                    msg_type="completed",
                    timestamp=now_ts(),
                )
                result = {"target": target, **(video_result if isinstance(video_result, dict) else {}), "child_task_ids": child_ids}

            projects_store.update_project(pid, {"status": "completed"})
            _one_click_progress(
                pid,
                task_id,
                100,
                "一键生成完成",
                phase="completed",
                status="completed",
                msg_type="completed",
            )
            return result
        except asyncio.CancelledError:
            for child_key, child_task_id in list(child_ids.items()):
                child_scope = {
                    "extract_subtitle": EXTRACT_SUBTITLE_SCOPE,
                    "extract_scene": extract_scene_service.SCOPE,
                    "generate_copywriting": "generate_copywriting",
                    "generate_script": "generate_script",
                    "omni_multimodal": omni_multimodal_pipeline_service.SCOPE,
                    "omni_full_narration_pipeline": omni_full_narration_pipeline_service.SCOPE,
                    "generate_jianying_draft": JianyingDraftManager.SCOPE,
                    "generate_video": "generate_video",
                }.get(child_key)
                if child_scope and child_task_id:
                    try:
                        await task_cancel_store.cancel(child_scope, pid, child_task_id)
                    except Exception:
                        pass
            projects_store.update_project(pid, {"status": "cancelled"})
            _one_click_progress(
                pid,
                task_id,
                0,
                "一键生成已停止",
                phase="cancelled",
                status="cancelled",
                msg_type="cancelled",
            )
            raise
        except Exception as e:
            projects_store.update_project(pid, {"status": "failed"})
            _one_click_progress(
                pid,
                task_id,
                0,
                f"一键生成失败: {_http_detail(e)}",
                phase="failed",
                status="failed",
                msg_type="error",
            )
            raise
        finally:
            await project_task_queue.release(pid)

    task_id = await task_scheduler.enqueue(
        scope=ONE_CLICK_GENERATE_SCOPE,
        project_id=project_id,
        run_fn=_run,
        task_id=candidate_task_id,
        concurrency=1,
        dedup=True,
    )

    return {
        "message": "一键生成任务已提交" if task_id == candidate_task_id else "一键生成任务已存在",
        "data": {
            "task_id": task_id,
            "scope": ONE_CLICK_GENERATE_SCOPE,
            "target": target,
        },
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/scenes")
async def get_project_scenes(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.scenes_path:
        raise HTTPException(status_code=404, detail="镜头数据未生成")

    abs_path = resolve_abs_path(p.scenes_path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="镜头数据文件丢失")

    import json
    with open(abs_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "message": "获取成功",
        "data": data,
        "timestamp": now_ts()
    }


@router.get("/{project_id}/scene-status/{task_id}")
async def get_scene_status(project_id: str, task_id: str):
    st = task_progress_store.get_state("extract_scene", project_id, task_id)
    if not st:
         raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "message": "获取进度成功",
        "data": st,
        "timestamp": now_ts(),
    }


def _attach_project_name(st: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(st)
    pid = str(row.get("project_id") or "").strip()
    if pid and not row.get("project_name"):
        pr = projects_store.get_project(pid)
        if pr and getattr(pr, "name", None):
            row["project_name"] = str(pr.name)
    return row


def _task_row_still_active(st: Optional[Dict[str, Any]]) -> bool:
    """用于队列浮窗：是否仍视为进行中（终端状态不占用展示）。"""
    if not st:
        return False
    status = str(st.get("status") or "").strip().lower()
    if status in ("completed", "failed", "cancelled"):
        return False
    msg_type = str(st.get("type") or "").strip().lower()
    if msg_type in ("completed", "error", "cancelled"):
        return False
    return True


def _project_queue_scopes() -> List[str]:
    from services.omni_multimodal_pipeline_service import omni_multimodal_pipeline_service
    from services.omni_copywriting_struct_embed_service import omni_copywriting_struct_embed_service
    from services.omni_shot_match_service import omni_shot_match_service
    from services.omni_global_path_search_service import omni_global_path_search_service
    from services.omni_generate_script_service import omni_generate_script_service
    from omni_full_narration_pipeline import omni_full_narration_pipeline_service

    return [
        ONE_CLICK_GENERATE_SCOPE,
        "generate_copywriting",
        "generate_script",
        "generate_video",
        JianyingDraftManager.SCOPE,
        extract_scene_service.SCOPE,
        EXTRACT_SUBTITLE_SCOPE,
        omni_multimodal_pipeline_service.SCOPE,
        omni_copywriting_struct_embed_service.SCOPE,
        omni_shot_match_service.SCOPE,
        omni_global_path_search_service.SCOPE,
        omni_generate_script_service.SCOPE,
        omni_full_narration_pipeline_service.SCOPE,
    ]


def _task_identity(st: Dict[str, Any]) -> tuple:
    return (
        str(st.get("scope") or ""),
        str(st.get("project_id") or ""),
        str(st.get("task_id") or ""),
    )


def _append_active_task(active_tasks: List[Dict[str, Any]], st: Optional[Dict[str, Any]]) -> None:
    if not st or not _task_row_still_active(st):
        return
    row = _attach_project_name(st)
    ident = _task_identity(row)
    if any(_task_identity(x) == ident for x in active_tasks):
        return
    active_tasks.append(row)


@router.get("/tasks/queue")
async def get_project_task_queue():
    """查看当前项目级任务队列状态。
    返回正在执行的项目、活跃任务数、以及排队等待的项目列表。
    """
    queue_status = project_task_queue.get_queue_status()
    enriched_waiting = []
    for wp in queue_status.get("waiting_projects", []):
        enriched_tasks = []
        for t in wp.get("tasks", []):
            st = task_progress_store.get_state(t["scope"], t["project_id"], t["task_id"])
            enriched_tasks.append({
                "project_id": t["project_id"],
                "project_name": t.get("project_name", t["project_id"]),
                "scope": t["scope"],
                "task_id": t["task_id"],
                "queue_status": t["status"],
                "task_state": st,
            })
        enriched_waiting.append({
            "project_id": wp["project_id"],
            "project_name": wp.get("project_name", wp["project_id"]),
            "queue_position": wp["queue_position"],
            "tasks": enriched_tasks,
        })

    active_tasks = []
    scopes = _project_queue_scopes()
    if queue_status.get("active_project"):
        ap = queue_status["active_project"]
        for s in scopes:
            _append_active_task(active_tasks, task_progress_store.get_state(s, ap))

    ap_id = queue_status.get("active_project")
    for s in scopes:
        for st in task_progress_store.iter_states_for_scope(s):
            pid = str(st.get("project_id") or "").strip()
            if ap_id and pid == ap_id:
                continue
            _append_active_task(active_tasks, st)

    for st in await task_scheduler.list_tasks(scopes):
        pid = str(st.get("project_id") or "").strip()
        scope = str(st.get("scope") or "").strip()
        task_id = str(st.get("task_id") or "").strip()
        if not pid or not scope or not task_id:
            continue
        state = task_progress_store.get_state(scope, pid, task_id) or {}
        status = str(state.get("status") or st.get("scheduler_status") or "queued").strip().lower()
        if status in ("completed", "failed", "cancelled"):
            continue
        _append_active_task(active_tasks, {
            **state,
            "scope": scope,
            "project_id": pid,
            "task_id": task_id,
            "status": status,
            "progress": state.get("progress") if isinstance(state.get("progress"), (int, float)) else 1,
            "message": state.get("message") or ("任务已提交，等待调度" if status == "queued" else "任务执行中"),
            "phase": state.get("phase") or status,
            "type": state.get("type") or "progress",
            "timestamp": state.get("timestamp") or now_ts(),
        })

    base_q = int(queue_status.get("active_task_count") or 0)
    display_task_count = max(base_q, len(active_tasks))

    return {
        "message": "获取任务队列状态",
        "data": {
            "active_project": queue_status.get("active_project"),
            "active_project_name": queue_status.get("active_project_name"),
            "active_task_count": display_task_count,
            "active_tasks": active_tasks,
            "waiting_projects": enriched_waiting,
            "total_waiting_projects": queue_status.get("total_waiting_projects"),
        },
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/subtitle")
async def get_subtitle(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not p.subtitle_path:
        raise HTTPException(status_code=404, detail="字幕不存在")
    abs_path = resolve_abs_path(p.subtitle_path.strip())
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="字幕文件不存在")
    segments = parse_srt(abs_path)
    subtitle_meta = {
        "file_path": p.subtitle_path,
        "source": getattr(p, "subtitle_source", None),
        "status": getattr(p, "subtitle_status", None),
        "updated_by_user": bool(getattr(p, "subtitle_updated_by_user", False)),
        "updated_at": getattr(p, "subtitle_updated_at", None),
        "format": getattr(p, "subtitle_format", None),
    }
    return {
        "message": "获取字幕成功",
        "data": {
            "segments": segments,
            "subtitle_meta": subtitle_meta,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/subtitle")
async def save_subtitle(project_id: str, req: SaveSubtitleRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    content: Optional[str] = (req.content or "").strip() if req.content is not None else None
    if content:
        if len(content) > 2_000_000:
            raise HTTPException(status_code=400, detail="字幕内容过大")
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        final_content = normalized + ("\n" if normalized and not normalized.endswith("\n") else "")
    else:
        segments_in = req.segments or []
        if not segments_in:
            raise HTTPException(status_code=400, detail="未提供字幕内容")
        if len(segments_in) > 5000:
            raise HTTPException(status_code=400, detail="字幕段数过多")
        total_chars = sum(len((s.text or "")) for s in segments_in)
        if total_chars > 2_000_000:
            raise HTTPException(status_code=400, detail="字幕文本过大")
        final_content = _segments_to_compressed_srt(segments_in)

    target_abs: Optional[Path] = None
    if p.subtitle_path:
        cand = resolve_abs_path(p.subtitle_path.strip())
        if cand.exists():
            target_abs = cand
    if not target_abs:
        up_dir = uploads_dir() / "subtitles"
        up_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        out_name = f"{project_id}_subtitle_edit_{ts}.srt"
        target_abs = up_dir / out_name

    try:
        target_abs.write_text(final_content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"字幕保存失败: {str(e)}")

    web_path = to_web_path(target_abs)
    src = getattr(p, "subtitle_source", None)
    if src not in {"user", "extracted"}:
        src = "extracted"
    p2 = projects_store.update_project(project_id, {
        "subtitle_path": web_path,
        "subtitle_source": src,
        "subtitle_status": "ready",
        "subtitle_updated_by_user": True,
        "subtitle_updated_at": now_ts(),
        "subtitle_format": "compressed_srt_v1",
    })
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    segments = parse_srt(target_abs)
    subtitle_meta = {
        "file_path": p2.subtitle_path,
        "source": getattr(p2, "subtitle_source", None),
        "status": getattr(p2, "subtitle_status", None),
        "updated_by_user": bool(getattr(p2, "subtitle_updated_by_user", False)),
        "updated_at": getattr(p2, "subtitle_updated_at", None),
        "format": getattr(p2, "subtitle_format", None),
    }
    return {
        "message": "字幕保存成功",
        "data": {
            "segments": segments,
            "subtitle_meta": subtitle_meta,
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/script")
async def save_script(project_id: str, req: SaveScriptRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    script = req.script
    if not isinstance(script, dict) or "segments" not in script:
        raise HTTPException(status_code=400, detail="脚本格式错误")

    try:
        p2 = projects_store.save_script(
            project_id,
            script,
            expected_revision=req.expected_revision,
        )
    except ScriptRevisionConflict as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "脚本已被其他任务更新，请刷新后重试",
                "current_revision": e.current_revision,
                "expected_revision": e.expected_revision,
            },
        )
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    return {
        "message": "脚本保存成功",
        "data": p2.script,
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/copywriting")
async def save_copywriting(project_id: str, req: SaveCopywritingRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    copywriting = req.copywriting
    if not isinstance(copywriting, dict):
        raise HTTPException(status_code=400, detail="文案格式错误")
    if not str(copywriting.get("content", "")).strip():
        raise HTTPException(status_code=400, detail="文案内容不能为空")

    try:
        out_dir = uploads_dir() / "analyses"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"{project_id}_copywriting_{ts}.json"
        out_path.write_text(
            json.dumps(copywriting, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        web_path = to_web_path(out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文案保存失败: {str(e)}")

    p2 = projects_store.update_project(project_id, {
        "narration_copywriting": copywriting,
        "narration_copywriting_path": web_path,
    })
    if not p2:
        raise HTTPException(status_code=500, detail="服务器错误")

    return {
        "message": "文案保存成功",
        "data": copywriting,
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/generate-video")
async def generate_video(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not p.script or not isinstance(p.script, dict):
        raise HTTPException(status_code=400, detail="请先生成并保存脚本")
    if not p.video_path:
        raise HTTPException(status_code=400, detail="请先上传原始视频文件")

    candidate_task_id = f"video_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    max_workers, _src = generate_concurrency_config_manager.get_effective("generate_video")
    logger.info(
        "生成视频入队请求: project_id=%s candidate_task_id=%s concurrency=%s",
        project_id,
        candidate_task_id,
        int(max_workers or 2),
    )

    def _local_update(task_id: str, status: str, progress: float, message: str, file_path: Optional[str]) -> None:
        t = VIDEO_TASKS.get(task_id)
        if not t:
            t = MergeTaskStatus(task_id=task_id, status=status, progress=progress, message=message)
            VIDEO_TASKS[task_id] = t
        t.status = status
        t.progress = progress
        if status == "queued":
            t.message = "进入队列"
        elif status == "processing":
            t.message = "生成中"
        elif status == "completed":
            t.message = "生成完成"
        elif status == "cancelled":
            t.message = "已停止"
        elif status == "failed":
            t.message = message or "生成失败"
        else:
            t.message = message
        if file_path:
            t.file_path = file_path

        if status == "processing":
            projects_store.update_project(project_id, {"status": "processing"})
        elif status == "completed":
            projects_store.update_project(project_id, {"status": "completed"})
        elif status == "cancelled":
            projects_store.update_project(project_id, {"status": "cancelled"})
        elif status == "failed":
            projects_store.update_project(project_id, {"status": "failed"})

    def _handle_update(task_id: str, task: Optional[asyncio.Task]) -> None:
        if task is None:
            VIDEO_TASK_HANDLES.pop(task_id, None)
        else:
            VIDEO_TASK_HANDLES[task_id] = task

    async def _run(project_id: str, task_id: str, cancel_event: asyncio.Event) -> Dict[str, Any]:
        await project_task_queue.acquire(project_id, "generate_video", task_id, cancel_event=cancel_event)
        try:
            result = await video_generation_service.generate_from_script(project_id, task_id=task_id, cancel_event=cancel_event)
            return result if isinstance(result, dict) else {}
        finally:
            await project_task_queue.release(project_id)

    task_id = await task_scheduler.enqueue(
        scope="generate_video",
        project_id=project_id,
        run_fn=_run,
        task_id=candidate_task_id,
        concurrency=int(max_workers or 2),
        dedup=True,
        local_update=_local_update,
        handle_update=_handle_update,
    )
    logger.info(
        "生成视频入队结果: project_id=%s task_id=%s dedup_hit=%s",
        project_id,
        task_id,
        task_id != candidate_task_id,
    )

    return {
        "message": "开始生成视频" if task_id == candidate_task_id else "任务已存在",
        "data": {
            "task_id": task_id,
            "scope": "generate_video",
        },
        "timestamp": now_ts(),
    }


@router.post("/{project_id}/tasks/cancel")
async def cancel_project_task(project_id: str, req: CancelTaskRequest):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    scope = str(req.scope or "").strip()
    if not scope:
        raise HTTPException(status_code=400, detail="缺少 scope")
    task_id = str(req.task_id or "").strip()
    if not task_id:
        st = task_progress_store.get_state(scope, project_id)
        if st and st.get("task_id"):
            task_id = str(st.get("task_id") or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="未找到可停止的任务")

    stopped_procs = await task_cancel_store.cancel(scope, project_id, task_id)
    cancelled = False
    try:
        cancelled = await task_scheduler.cancel(scope, project_id, task_id)
    except Exception:
        pass
    t = VIDEO_TASK_HANDLES.get(task_id) or DRAFT_TASK_HANDLES.get(task_id) or MERGE_TASKS.get(task_id)
    if hasattr(t, "cancel"):
        try:
            t.cancel()
        except Exception:
            pass
    logger.info(
        "停止任务请求: project_id=%s scope=%s task_id=%s processes_stopped=%s scheduler_cancelled=%s",
        project_id,
        scope,
        task_id,
        stopped_procs,
        cancelled,
    )

    return {
        "message": "已请求停止任务",
        "data": {
            "scope": scope,
            "task_id": task_id,
            "processes_stopped": stopped_procs,
        },
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/tasks/running")
async def get_project_running_tasks(project_id: str):
    from services.omni_multimodal_pipeline_service import omni_multimodal_pipeline_service
    from services.omni_copywriting_struct_embed_service import omni_copywriting_struct_embed_service
    from services.omni_shot_match_service import omni_shot_match_service
    from services.omni_global_path_search_service import omni_global_path_search_service
    from services.omni_generate_script_service import omni_generate_script_service
    from services.omni_script_tts_service import omni_script_tts_service
    from omni_full_narration_pipeline import omni_full_narration_pipeline_service

    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    data = {
        "generate_copywriting": task_progress_store.get_latest_running("generate_copywriting", project_id),
        "one_click_generate": task_progress_store.get_latest_running(ONE_CLICK_GENERATE_SCOPE, project_id),
        "generate_script": task_progress_store.get_latest_running("generate_script", project_id),
        "generate_video": task_progress_store.get_latest_running("generate_video", project_id),
        "generate_jianying_draft": task_progress_store.get_latest_running(JianyingDraftManager.SCOPE, project_id),
        "extract_subtitle": task_progress_store.get_latest_running(EXTRACT_SUBTITLE_SCOPE, project_id),
        "extract_scene": task_progress_store.get_latest_running(extract_scene_service.SCOPE, project_id),
        "omni_multimodal": task_progress_store.get_latest_running(omni_multimodal_pipeline_service.SCOPE, project_id),
        "omni_copywriting_embed": task_progress_store.get_latest_running(
            omni_copywriting_struct_embed_service.SCOPE, project_id
        ),
        "omni_shot_match": task_progress_store.get_latest_running(omni_shot_match_service.SCOPE, project_id),
        "omni_global_path_search": task_progress_store.get_latest_running(
            omni_global_path_search_service.SCOPE, project_id
        ),
        "omni_generate_script": task_progress_store.get_latest_running(
            omni_generate_script_service.SCOPE, project_id
        ),
        "omni_full_narration_pipeline": task_progress_store.get_latest_running(
            omni_full_narration_pipeline_service.SCOPE, project_id
        ),
        "omni_script_tts": task_progress_store.get_latest_running(
            omni_script_tts_service.SCOPE, project_id
        ),
    }
    return {
        "message": "获取任务进度",
        "data": data,
        "timestamp": now_ts(),
    }


@router.get("/{project_id}/tasks/latest")
async def get_project_latest_tasks(project_id: str):
    from services.omni_multimodal_pipeline_service import omni_multimodal_pipeline_service
    from services.omni_copywriting_struct_embed_service import omni_copywriting_struct_embed_service
    from services.omni_shot_match_service import omni_shot_match_service
    from services.omni_global_path_search_service import omni_global_path_search_service
    from services.omni_generate_script_service import omni_generate_script_service
    from services.omni_script_tts_service import omni_script_tts_service
    from omni_full_narration_pipeline import omni_full_narration_pipeline_service

    p = projects_store.get_project(project_id)
    if not p:
        return {
            "message": "项目不存在",
            "data": {
                "generate_copywriting": None,
                "one_click_generate": None,
                "generate_script": None,
                "generate_video": None,
                "generate_jianying_draft": None,
                "extract_subtitle": None,
                "extract_scene": None,
                "omni_multimodal": None,
                "omni_copywriting_embed": None,
                "omni_shot_match": None,
                "omni_global_path_search": None,
                "omni_generate_script": None,
                "omni_full_narration_pipeline": None,
                "omni_script_tts": None,
            },
            "timestamp": now_ts(),
        }
    return {
        "message": "获取任务进度",
        "data": {
            "generate_copywriting": task_progress_store.get_state("generate_copywriting", project_id),
            "one_click_generate": task_progress_store.get_state(ONE_CLICK_GENERATE_SCOPE, project_id),
            "generate_script": task_progress_store.get_state("generate_script", project_id),
            "generate_video": task_progress_store.get_state("generate_video", project_id),
            "generate_jianying_draft": task_progress_store.get_state(JianyingDraftManager.SCOPE, project_id),
            "extract_subtitle": task_progress_store.get_state(EXTRACT_SUBTITLE_SCOPE, project_id),
            "extract_scene": task_progress_store.get_state(extract_scene_service.SCOPE, project_id),
            "omni_multimodal": task_progress_store.get_state(omni_multimodal_pipeline_service.SCOPE, project_id),
            "omni_copywriting_embed": task_progress_store.get_state(
                omni_copywriting_struct_embed_service.SCOPE, project_id
            ),
            "omni_shot_match": task_progress_store.get_state(omni_shot_match_service.SCOPE, project_id),
            "omni_global_path_search": task_progress_store.get_state(
                omni_global_path_search_service.SCOPE, project_id
            ),
            "omni_generate_script": task_progress_store.get_state(
                omni_generate_script_service.SCOPE, project_id
            ),
            "omni_full_narration_pipeline": task_progress_store.get_state(
                omni_full_narration_pipeline_service.SCOPE, project_id
            ),
            "omni_script_tts": task_progress_store.get_state(
                omni_script_tts_service.SCOPE, project_id
            ),
        },
        "timestamp": now_ts(),
    }
