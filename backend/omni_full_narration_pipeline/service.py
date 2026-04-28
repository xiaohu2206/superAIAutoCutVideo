#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺序编排：文案结构化+向量 → 镜头匹配 → [可选] 全局路径搜索 → 解说脚本生成。
可通过 skip_global_path_search 关闭第 3 步（默认用上一步镜头匹配的 rerank.json，
或仅在 generate_script_options 中显式传入 input_global_path_web_path）。
与 visual / generate_script 及单步 HTTP 路由解耦；仅组合调用各 omni_*_service.submit_run 并等待子任务结束。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from modules.projects_store import projects_store
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from modules.ws_manager import manager
from services.asr.extract_subtitle_service import _resolve_path
from services.omni_copywriting_struct_embed_service import omni_copywriting_struct_embed_service
from services.omni_generate_script_service import omni_generate_script_service
from services.omni_global_path_search_service import omni_global_path_search_service
from services.omni_shot_match_service import omni_shot_match_service

logger = logging.getLogger(__name__)

_SCOPE = "omni_full_narration_pipeline"


def _now_ts() -> str:
    return datetime.now().isoformat()


async def _broadcast(payload: Dict[str, Any]) -> None:
    try:
        await manager.broadcast(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


def _terminal_status(st: Dict[str, Any]) -> Optional[str]:
    status = str(st.get("status") or "").strip().lower()
    msg_type = str(st.get("type") or "").strip().lower()
    if status in ("completed", "failed", "cancelled"):
        return status
    if msg_type in ("error",):
        return "failed"
    return None


async def _wait_subtask(
    *,
    scope: str,
    project_id: str,
    task_id: str,
    master_task_id: str,
    step_index: int,
    step_label: str,
) -> Dict[str, Any]:
    last_msg = ""
    while True:
        if task_cancel_store.is_cancelled(_SCOPE, project_id, master_task_id):
            raise asyncio.CancelledError()
        st = task_progress_store.get_state(scope, project_id, task_id)
        if not st:
            await asyncio.sleep(0.4)
            continue
        term = _terminal_status(st)
        sub_p = float(st.get("progress") or 0.0)
        blended = float(step_index) * 25.0 + max(0.0, min(100.0, sub_p)) * 0.25
        msg = f"「{step_label}」{st.get('message') or ''}".strip()
        if msg != last_msg or term:
            last_msg = msg
            task_progress_store.set_state(
                scope=_SCOPE,
                project_id=project_id,
                task_id=master_task_id,
                status="processing",
                progress=min(99.0, blended),
                message=msg,
                phase=f"step_{step_index + 1}",
                msg_type="progress",
                timestamp=_now_ts(),
            )
            await _broadcast(
                {
                    "type": "progress",
                    "scope": _SCOPE,
                    "project_id": project_id,
                    "task_id": master_task_id,
                    "phase": f"step_{step_index + 1}",
                    "message": msg,
                    "progress": int(min(99, round(blended))),
                    "timestamp": _now_ts(),
                }
            )
        if term == "completed":
            return st
        if term in ("failed", "cancelled"):
            raise RuntimeError(st.get("message") or f"{step_label} 结束状态: {term}")
        await asyncio.sleep(0.4)


def _merge_opts(base: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(base)
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is not None:
                out[k] = v
    return out


class OmniFullNarrationPipelineService:
    SCOPE = _SCOPE

    async def submit_run(
        self,
        project_id: str,
        *,
        force: bool = False,
        task_id: Optional[str] = None,
        copywriting_embed_options: Optional[Dict[str, Any]] = None,
        shot_match_options: Optional[Dict[str, Any]] = None,
        global_path_search_options: Optional[Dict[str, Any]] = None,
        generate_script_options: Optional[Dict[str, Any]] = None,
        skip_global_path_search: bool = False,
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        if str(getattr(p, "project_type", "") or "").strip().lower() != "omni":
            raise ValueError("仅 omni 类型项目可运行全链路解说脚本编排")

        running = task_progress_store.get_latest_running(self.SCOPE, project_id)
        if running:
            r_status = str(running.get("status") or "").strip().lower()
            r_task_id = running.get("task_id")
            if not force:
                if r_status in ("pending", "processing", "running"):
                    return {"task_id": r_task_id, "status": r_status, "message": "已有全链路任务在运行"}
            else:
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
                        message="已取消旧编排任务，准备重新执行",
                    )

        if not task_id:
            task_id = f"omni_fn_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        task_progress_store.set_state(
            scope=self.SCOPE,
            project_id=project_id,
            task_id=task_id,
            status="pending",
            progress=0,
            message="已提交 Omni 全链路（结构化→镜头→路径→脚本）…",
            phase="queued",
            msg_type="progress",
            timestamp=_now_ts(),
        )
        await _broadcast(
            {
                "type": "progress",
                "scope": self.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "queued",
                "message": "已提交 Omni 全链路…",
                "progress": 0,
                "timestamp": _now_ts(),
            }
        )

        c1 = _merge_opts(
            {
                "force": force,
                "task_id": None,
                "chunk_target_chars": 500,
                "chunk_lookback_chars": 100,
                "structuring_concurrency": 3,
                "embedding_concurrency": 8,
                "prompt_language": "zh",
                "continue_on_embedding_error": True,
            },
            copywriting_embed_options,
        )
        c1["force"] = force
        pl = str(c1.get("prompt_language") or "zh").strip().lower()
        if pl not in ("zh", "en"):
            raise ValueError("prompt_language 仅支持 zh 或 en")

        sm = _merge_opts(
            {
                "force": force,
                "task_id": None,
                "rerank_instruct": None,
                "temperature": 0.2,
                "weights": None,
            },
            shot_match_options,
        )
        sm["force"] = force

        gp = _merge_opts(
            {
                "force": force,
                "task_id": None,
                "input_rerank_web_path": None,
                "search_params": None,
            },
            global_path_search_options,
        )
        gp["force"] = force

        gs = _merge_opts(
            {
                "force": force,
                "task_id": None,
                "input_global_path_web_path": None,
                "input_multimodal_web_path": None,
                "generation_params": None,
                "temperature": None,
                "chunk_llm_concurrency": 4,
            },
            generate_script_options,
        )
        gs["force"] = force
        skip_gps = bool(skip_global_path_search)
        generate_script_gp_web_override: Optional[str] = None

        async def _run() -> None:
            nonlocal generate_script_gp_web_override
            try:
                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                cur = projects_store.get_project(project_id)
                if not cur:
                    raise ValueError("项目不存在")
                if not str(getattr(cur, "omni_multimodal_json_path", "") or "").strip():
                    raise ValueError("请先完成 Omni 多模态管线（缺少 omni_multimodal_json_path）")
                cw = getattr(cur, "narration_copywriting", None)
                if not isinstance(cw, dict) or not str(cw.get("content", "")).strip():
                    raise ValueError("请先生成并保存解说文案（narration_copywriting）")

                # 1) 文案结构化 + 向量
                r1 = await omni_copywriting_struct_embed_service.submit_run(
                    project_id,
                    force=bool(c1["force"]),
                    task_id=c1.get("task_id"),
                    chunk_target_chars=int(c1.get("chunk_target_chars") or 500),
                    chunk_lookback_chars=int(c1.get("chunk_lookback_chars") or 100),
                    structuring_concurrency=int(c1.get("structuring_concurrency") or 3),
                    embedding_concurrency=int(c1.get("embedding_concurrency") or 8),
                    prompt_language=pl,
                    continue_on_embedding_error=bool(c1.get("continue_on_embedding_error", True)),
                )
                tid1 = str(r1.get("task_id") or "").strip()
                if not tid1:
                    raise RuntimeError("文案结构化任务未返回 task_id")
                await _wait_subtask(
                    scope=omni_copywriting_struct_embed_service.SCOPE,
                    project_id=project_id,
                    task_id=tid1,
                    master_task_id=task_id,
                    step_index=0,
                    step_label="文案结构化+向量",
                )

                # 2) 镜头匹配
                sm_weights = sm.get("weights")
                if not isinstance(sm_weights, dict):
                    sm_weights = None
                r2 = await omni_shot_match_service.submit_run(
                    project_id,
                    force=bool(sm["force"]),
                    task_id=sm.get("task_id"),
                    rerank_instruct=sm.get("rerank_instruct"),
                    temperature=float(sm.get("temperature") or 0.2),
                    weights=sm_weights,
                )
                tid2 = str(r2.get("task_id") or "").strip()
                if not tid2:
                    raise RuntimeError("镜头匹配任务未返回 task_id")
                await _wait_subtask(
                    scope=omni_shot_match_service.SCOPE,
                    project_id=project_id,
                    task_id=tid2,
                    master_task_id=task_id,
                    step_index=1,
                    step_label="镜头匹配",
                )

                # 3) 全局路径（可关闭：第 4 步用上一步 rerank.json，或仅显式 path）
                if skip_gps:
                    cur_gp = projects_store.get_project(project_id)
                    if not cur_gp:
                        raise ValueError("项目不存在")
                    gs_path_opt = str(gs.get("input_global_path_web_path") or "").strip()
                    proj_rr = str(getattr(cur_gp, "omni_shot_match_rerank_path", None) or "").strip()
                    # 跳过时不再强制磁盘路径存在：优先请求路径，其次 rerank；均缺失则交给解说脚本
                    # 按「全局路径结果 → 重排」选用第一个存在的文件。
                    if gs_path_opt and _resolve_path(gs_path_opt).exists():
                        generate_script_gp_web_override = gs_path_opt
                        skip_msg = "已跳过「全局路径搜索」，使用请求指定的候选 JSON"
                    elif proj_rr and _resolve_path(proj_rr).exists():
                        generate_script_gp_web_override = proj_rr
                        skip_msg = (
                            "已跳过「全局路径搜索」，使用镜头重排结果"
                            if not gs_path_opt
                            else "已跳过「全局路径搜索」，请求路径不可用，已改用镜头重排结果"
                        )
                    else:
                        skip_msg = (
                            "已跳过「全局路径搜索」，解说脚本将按磁盘上可用的项目候选 JSON 解析"
                        )
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=task_id,
                        status="processing",
                        progress=75.0,
                        message=skip_msg,
                        phase="step_skip_global_path",
                        msg_type="progress",
                        timestamp=_now_ts(),
                    )
                    await _broadcast(
                        {
                            "type": "progress",
                            "scope": self.SCOPE,
                            "project_id": project_id,
                            "task_id": task_id,
                            "phase": "step_skip_global_path",
                            "message": skip_msg,
                            "progress": 75,
                            "timestamp": _now_ts(),
                        }
                    )
                else:
                    r3 = await omni_global_path_search_service.submit_run(
                        project_id,
                        force=bool(gp["force"]),
                        task_id=gp.get("task_id"),
                        input_rerank_web_path=gp.get("input_rerank_web_path"),
                        search_params=gp.get("search_params") if isinstance(gp.get("search_params"), dict) else None,
                    )
                    tid3 = str(r3.get("task_id") or "").strip()
                    if not tid3:
                        raise RuntimeError("全局路径搜索任务未返回 task_id")
                    await _wait_subtask(
                        scope=omni_global_path_search_service.SCOPE,
                        project_id=project_id,
                        task_id=tid3,
                        master_task_id=task_id,
                        step_index=2,
                        step_label="全局路径搜索",
                    )

                # 4) 解说脚本
                gs_gp = str(gs.get("input_global_path_web_path") or "").strip()
                r4 = await omni_generate_script_service.submit_run(
                    project_id,
                    force=bool(gs["force"]),
                    task_id=gs.get("task_id"),
                    input_global_path_web_path=gs_gp or generate_script_gp_web_override,
                    input_multimodal_web_path=gs.get("input_multimodal_web_path"),
                    generation_params=gs.get("generation_params") if isinstance(gs.get("generation_params"), dict) else None,
                    temperature=gs.get("temperature"),
                    chunk_llm_concurrency=int(gs.get("chunk_llm_concurrency") or 4),
                )
                tid4 = str(r4.get("task_id") or "").strip()
                if not tid4:
                    raise RuntimeError("解说脚本生成任务未返回 task_id")
                await _wait_subtask(
                    scope=omni_generate_script_service.SCOPE,
                    project_id=project_id,
                    task_id=tid4,
                    master_task_id=task_id,
                    step_index=3,
                    step_label="解说脚本生成",
                )

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message="Omni 全链路完成",
                    phase="done",
                    msg_type="completed",
                    timestamp=_now_ts(),
                )
                await _broadcast(
                    {
                        "type": "completed",
                        "scope": self.SCOPE,
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": "Omni 全链路解说脚本已完成",
                        "progress": 100,
                        "timestamp": _now_ts(),
                    }
                )
            except asyncio.CancelledError:
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="cancelled",
                    message="全链路任务已取消",
                    phase="cancelled",
                    msg_type="cancelled",
                    timestamp=_now_ts(),
                )
                await _broadcast(
                    {
                        "type": "cancelled",
                        "scope": self.SCOPE,
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": "全链路任务已取消",
                        "timestamp": _now_ts(),
                    }
                )
            except Exception as e:
                logger.exception("omni full narration pipeline failed")
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="failed",
                    message=f"失败: {e}",
                    phase="failed",
                    msg_type="error",
                    timestamp=_now_ts(),
                )
                await _broadcast(
                    {
                        "type": "error",
                        "scope": self.SCOPE,
                        "project_id": project_id,
                        "task_id": task_id,
                        "message": f"Omni 全链路失败: {e}",
                        "timestamp": _now_ts(),
                    }
                )

        asyncio.create_task(_run())
        return {"task_id": task_id, "status": "pending", "message": "全链路任务已提交"}


omni_full_narration_pipeline_service = OmniFullNarrationPipelineService()
