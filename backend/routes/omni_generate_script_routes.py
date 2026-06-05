#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni：解说脚本生成（独立路由，与 /generate-script 隔离）。"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from modules.projects_store import ScriptRevisionConflict, projects_store
from modules.task_progress_store import task_progress_store
from services.omni_generate_script_service import omni_generate_script_service
from services.omni_script_tts_service import omni_script_tts_service
from services.omni_shot_options_service import omni_shot_options_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Omni 解说脚本生成"])


def _now_ts() -> str:
    return datetime.now().isoformat()


class OmniGenerateScriptRunRequest(BaseModel):
    force: bool = Field(default=False)
    task_id: Optional[str] = None
    input_global_path_web_path: Optional[str] = Field(
        default=None,
        description="可选。显式指定段落-镜头候选 JSON；省略时依次使用项目 omni_global_path_search_path、omni_shot_match_rerank_path",
    )
    input_multimodal_web_path: Optional[str] = Field(
        default=None,
        description="覆盖项目上的 omni_multimodal_json_path；默认使用多模态 shots JSON",
    )
    generation_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="分块/时间窗等参数，语义对齐 Step4.9（chunk_target_size、timeline_window_mode 等）",
    )
    script_language: Optional[str] = Field(default=None, description="解说语言：zh/en；默认使用项目配置")
    original_ratio: Optional[int] = Field(default=None, ge=0, le=100, description="原片占比 0-100；默认使用项目配置")
    temperature: Optional[float] = Field(default=None, description="覆盖当前文案模型温度")
    chunk_llm_concurrency: int = Field(default=4, ge=1, le=16, description="分块 LLM 并发数")
    use_prev_result_directly: Optional[bool] = Field(
        default=None,
        description="为 true 时跳过大模型，直接用上一步镜头候选每条 Top1 的时间拼装解说脚本以省成本；"
        "为 null 时跟随「使用本地模型」配置（开启本地模型默认跳过）",
    )


@router.post("/{project_id}/omni/generate-script/run")
async def omni_generate_script_run(
    project_id: str,
    req: OmniGenerateScriptRunRequest = Body(default=OmniGenerateScriptRunRequest()),
):
    try:
        data = await omni_generate_script_service.submit_run(
            project_id,
            force=bool(req.force),
            task_id=req.task_id,
            input_global_path_web_path=req.input_global_path_web_path,
            input_multimodal_web_path=req.input_multimodal_web_path,
            generation_params=req.generation_params,
            script_language=req.script_language,
            original_ratio=req.original_ratio,
            temperature=req.temperature,
            chunk_llm_concurrency=req.chunk_llm_concurrency,
            use_prev_result_directly=req.use_prev_result_directly,
        )
        return {"message": "任务已提交", "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("omni generate-script submit failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/omni/generate-script/status/{task_id}")
async def omni_generate_script_status(project_id: str, task_id: str):
    st = task_progress_store.get_state(omni_generate_script_service.SCOPE, project_id, task_id)
    if not st:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "获取进度成功", "data": st, "timestamp": _now_ts()}


@router.get("/{project_id}/omni/generate-script/paths")
async def omni_generate_script_paths(project_id: str) -> Dict[str, Any]:
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "message": "获取路径成功",
        "data": {
            "omni_generate_script_path": getattr(p, "omni_generate_script_path", None),
            "omni_generate_script_updated_at": getattr(p, "omni_generate_script_updated_at", None),
            "omni_global_path_search_path": getattr(p, "omni_global_path_search_path", None),
            "omni_multimodal_json_path": getattr(p, "omni_multimodal_json_path", None),
        },
        "timestamp": _now_ts(),
    }


class OmniScriptTtsRunRequest(BaseModel):
    force: bool = Field(default=False)


class OmniScriptSegmentTtsRequest(BaseModel):
    expected_revision: Optional[int] = None
    expected_text_hash: Optional[str] = None


@router.post("/{project_id}/omni/script/segments/{segment_id}/tts")
async def omni_script_segment_tts(
    project_id: str,
    segment_id: str,
    req: OmniScriptSegmentTtsRequest = Body(default=OmniScriptSegmentTtsRequest()),
):
    try:
        data = await omni_script_tts_service.synthesize_segment(
            project_id,
            segment_id,
            source="manual",
            expected_revision=req.expected_revision,
            expected_text_hash=req.expected_text_hash,
        )
        return {"message": "单条配音完成", "data": data, "timestamp": _now_ts()}
    except ScriptRevisionConflict as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "脚本已被其他任务更新，本次配音结果已忽略",
                "current_revision": e.current_revision,
                "expected_revision": e.expected_revision,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("omni script segment tts failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/omni/script/tts/run")
async def omni_script_tts_run(
    project_id: str,
    req: OmniScriptTtsRunRequest = Body(default=OmniScriptTtsRunRequest()),
):
    try:
        data = await omni_script_tts_service.submit_bulk_run(project_id, force=bool(req.force))
        msg = "任务已存在" if data.get("dedup_hit") else "开始批量配音"
        return {"message": msg, "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("omni script bulk tts failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/omni/generate-script/shot-options")
async def omni_generate_script_shot_options(project_id: str) -> Dict[str, Any]:
    try:
        data = omni_shot_options_service.get_options(project_id)
        return {"message": "获取候选镜头成功", "data": data, "timestamp": _now_ts()}
    except ValueError as e:
        detail = str(e)
        status = 404 if detail == "项目不存在" else 400
        raise HTTPException(status_code=status, detail=detail)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("omni generate-script shot-options failed")
        raise HTTPException(status_code=500, detail=str(e))
