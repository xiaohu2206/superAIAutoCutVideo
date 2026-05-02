#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni：基于全局路径搜索 + 多模态镜头表生成分块解说脚本（LLM），与 visual / generate_script_service 逻辑隔离。
落盘 uploads/omni_generate_script/{project_id}/；语义对齐 aiSearchShot Step4.9。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
from modules.ai import ChatMessage
from modules.json_sanitizer import sanitize_json_text_to_dict, validate_script_items
from modules.omni_generate_script import (
    OmniNarrationParams,
    build_chunk_metas_and_prompts,
    merge_chunk_items,
    normalize_items_for_validation,
    omni_items_to_video_script,
    post_check_chunk_items,
)
from modules.omni_generate_script.prompt_options import normalize_original_ratio, normalize_script_language
from modules.projects_store import projects_store
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from services.ai_models.ai_service import ai_service
from services.ai_models.unified_model_usage import LlmModelUsage
from services.asr.extract_subtitle_service import _resolve_path, _to_web_path, _uploads_dir
from services.omni_internal.multimodal_json_crypto import read_multimodal_json

logger = logging.getLogger(__name__)

_SCOPE = "omni_generate_script"

# 单批 LLM：网络空响应、JSON 损坏、后验校验失败等均重试（与视觉管线相近的退避）
_CHUNK_LLM_RETRY_DELAYS_SEC: Tuple[float, ...] = (1.0, 2.0, 3.0, 5.0)

# 测试：为 True 时，将每次分块 send_chat 的 messages 以 JSON 写入 `omni_multimodal_json_path` 同目录
_OMNI_GS_LOG_LLM_MESSAGES = True


def _safe_log_filename_segment(s: str) -> str:
    bad = "<>:\"/\\|?*"
    out = "".join(c if c not in bad else "_" for c in (s or ""))
    return (out or "x")[:180]


def _log_llm_messages_beside_multimodal(
    mm_abs: Path,
    messages: List[ChatMessage],
    *,
    project_id: str,
    task_id: str,
    chunk_index0: int,
    attempt0: int,
) -> None:
    if not _OMNI_GS_LOG_LLM_MESSAGES:
        return
    try:
        base_dir = mm_abs.parent
        base_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fn = (
            f"omni_gs_llm_messages_{_safe_log_filename_segment(task_id)}_"
            f"c{chunk_index0 + 1:04d}_a{attempt0 + 1:02d}_{ts}.json"
        )
        path = base_dir / fn
        payload: Dict[str, Any] = {
            "meta": {
                "source": "omni_generate_script",
                "project_id": project_id,
                "task_id": task_id,
                "chunk_index": chunk_index0,
                "attempt": attempt0,
                "multimodal_json": str(mm_abs),
                "logged_at": datetime.now().isoformat(),
            },
            "messages": [m.model_dump(mode="json") for m in messages],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("omni_generate_script: 写入 LLM messages 测试 log 失败: %s", e)


def _work_dir(project_id: str) -> Path:
    return _uploads_dir() / "omni_generate_script" / project_id


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


def _pick_paragraph_shot_json_web_path(
    *,
    input_web: Optional[str],
    proj_global: Optional[str],
    proj_rerank: Optional[str],
) -> str:
    """
    显式 input_web 必须存在；否则在项目的全局路径结果与镜头重排结果之间，
    按优先级选用磁盘上第一个存在的路径（避免跳过全局路径搜索后仍命中已失效的
    omni_global_path_search_path）。
    """
    exp = (input_web or "").strip()
    if exp:
        if not _resolve_path(exp).exists():
            raise FileNotFoundError(f"段落-镜头候选 JSON 不存在: {exp}")
        return exp

    fallbacks: List[str] = []
    for x in ((proj_global or "").strip(), (proj_rerank or "").strip()):
        if x:
            fallbacks.append(x)
    for cand in fallbacks:
        if _resolve_path(cand).exists():
            return cand
    if not fallbacks:
        raise ValueError(
            "缺少段落-镜头候选 JSON：请先完成镜头匹配或全局路径搜索，"
            "或传入 input_global_path_web_path，或项目已保存 "
            "omni_global_path_search_path / omni_shot_match_rerank_path"
        )
    raise FileNotFoundError("段落-镜头候选 JSON 不存在，以下项目路径均无效: " + ", ".join(fallbacks))


def _params_from_request_and_project(
    project: Any,
    generation_params: Optional[Dict[str, Any]],
    script_language: Optional[str] = None,
    original_ratio: Optional[int] = None,
) -> OmniNarrationParams:
    project_ratio = getattr(project, "original_ratio", None)
    project_interleave = getattr(project, "interleave_mode", None)
    effective_script_language = normalize_script_language(
        script_language if script_language is not None else getattr(project, "script_language", None)
    )
    effective_original_ratio = (
        normalize_original_ratio(original_ratio)
        if original_ratio is not None
        else (normalize_original_ratio(project_ratio) if project_ratio is not None else None)
    )
    effective_interleave = project_interleave or "smart_interleave"
    base = OmniNarrationParams(
        script_language=effective_script_language,
        original_ratio=effective_original_ratio,
        interleave_mode=effective_interleave,
    )
    if not generation_params:
        return base
    g = generation_params
    gp_script_language = g.get("script_language") if g.get("script_language") is not None else base.script_language
    gp_original_ratio = g.get("original_ratio") if g.get("original_ratio") is not None else base.original_ratio
    gp_interleave_mode = g.get("interleave_mode") if g.get("interleave_mode") is not None else base.interleave_mode
    effective_script_language = normalize_script_language(
        script_language if script_language is not None else gp_script_language
    )
    effective_original_ratio = (
        normalize_original_ratio(original_ratio)
        if original_ratio is not None
        else (normalize_original_ratio(gp_original_ratio) if gp_original_ratio is not None else None)
    )
    effective_interleave = gp_interleave_mode or "smart_interleave"
    return OmniNarrationParams(
        max_items_for_retrieval=int(g.get("max_items_for_retrieval", base.max_items_for_retrieval) or base.max_items_for_retrieval),
        chunk_target_size=max(1, int(g.get("chunk_target_size", base.chunk_target_size) or base.chunk_target_size)),
        chunk_balance_mode=str(g.get("chunk_balance_mode", base.chunk_balance_mode) or base.chunk_balance_mode),
        chunk_min_lines=max(1, int(g.get("chunk_min_lines", base.chunk_min_lines) or base.chunk_min_lines)),
        chunk_overlap_ratio=float(g.get("chunk_overlap_ratio", base.chunk_overlap_ratio) or base.chunk_overlap_ratio),
        timeline_window_mode=str(g.get("timeline_window_mode", base.timeline_window_mode) or base.timeline_window_mode),
        timeline_gap_median_multiplier=float(
            g.get("timeline_gap_median_multiplier", base.timeline_gap_median_multiplier) or base.timeline_gap_median_multiplier
        ),
        timeline_gap_min_seconds=float(g.get("timeline_gap_min_seconds", base.timeline_gap_min_seconds) or base.timeline_gap_min_seconds),
        timeline_shot_id_redundancy_ratio=float(
            g.get("timeline_shot_id_redundancy_ratio", base.timeline_shot_id_redundancy_ratio) or base.timeline_shot_id_redundancy_ratio
        ),
        system_prompt=g.get("system_prompt") if isinstance(g.get("system_prompt"), str) else None,
        user_prompt_template=g.get("user_prompt_template") if isinstance(g.get("user_prompt_template"), str) else None,
        script_language=effective_script_language,
        original_ratio=effective_original_ratio,
        interleave_mode=effective_interleave,
    )


class OmniGenerateScriptService:
    SCOPE = _SCOPE

    async def submit_run(
        self,
        project_id: str,
        *,
        force: bool = False,
        task_id: Optional[str] = None,
        input_global_path_web_path: Optional[str] = None,
        input_multimodal_web_path: Optional[str] = None,
        generation_params: Optional[Dict[str, Any]] = None,
        script_language: Optional[str] = None,
        original_ratio: Optional[int] = None,
        temperature: Optional[float] = None,
        chunk_llm_concurrency: int = 32,
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        if str(getattr(p, "project_type", "") or "").strip().lower() != "omni":
            raise ValueError("仅 omni 类型项目可生成解说脚本")

        running = task_progress_store.get_latest_running(self.SCOPE, project_id)
        if running:
            r_status = str(running.get("status") or "").strip().lower()
            r_task_id = running.get("task_id")
            if not force:
                if r_status in ("pending", "processing", "running"):
                    return {"task_id": r_task_id, "status": r_status, "message": "已有任务在运行"}
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
                        message="已取消旧任务，准备重新执行",
                    )

        if not task_id:
            task_id = f"omni_gs_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        task_progress_store.set_state(
            scope=self.SCOPE,
            project_id=project_id,
            task_id=task_id,
            status="pending",
            progress=0,
            message="准备生成解说脚本…",
            phase="preparing",
        )

        async def _run() -> None:
            try:
                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                cur = projects_store.get_project(project_id)
                if not cur:
                    raise ValueError("项目不存在")

                gp_web = _pick_paragraph_shot_json_web_path(
                    input_web=input_global_path_web_path,
                    proj_global=getattr(cur, "omni_global_path_search_path", None),
                    proj_rerank=getattr(cur, "omni_shot_match_rerank_path", None),
                )

                mm_web = (input_multimodal_web_path or "").strip() or (getattr(cur, "omni_multimodal_json_path", None) or "")
                if not str(mm_web).strip():
                    raise ValueError("缺少多模态镜头 JSON：请先完成 Omni 多模态管线或传入 input_multimodal_web_path")

                video_path = getattr(cur, "video_path", None) or ""
                if not str(video_path).strip():
                    raise ValueError("项目缺少视频路径")

                gp_abs = _resolve_path(str(gp_web))

                mm_abs = _resolve_path(str(mm_web))
                if not mm_abs.exists():
                    raise FileNotFoundError(f"多模态 JSON 不存在: {mm_web}")

                video_abs = _resolve_path(str(video_path))
                if not video_abs.exists():
                    raise FileNotFoundError("视频文件不存在")

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=10,
                    message="读取段落-镜头候选与镜头表…",
                    phase="loading",
                )

                raw_gp = await asyncio.to_thread(lambda: gp_abs.read_text(encoding="utf-8"))
                gp_payload = json.loads(raw_gp)
                if not isinstance(gp_payload, dict):
                    raise ValueError("段落-镜头候选 JSON 根须为对象")
                results = gp_payload.get("results")
                if not isinstance(results, list) or not results:
                    raise ValueError("段落-镜头候选 JSON 须包含非空 results")

                mm_payload = await asyncio.to_thread(read_multimodal_json, mm_abs)
                if not isinstance(mm_payload, dict):
                    raise ValueError("多模态 JSON 根须为对象")
                all_shots = mm_payload.get("shots")
                if not isinstance(all_shots, list) or not all_shots:
                    raise ValueError("多模态 JSON 须包含非空 shots")

                params = _params_from_request_and_project(
                    cur,
                    generation_params,
                    script_language=script_language,
                    original_ratio=original_ratio,
                )
                chunks = build_chunk_metas_and_prompts(results, all_shots, params)
                if not chunks:
                    raise ValueError("分块为空")

                total_duration = await asyncio.to_thread(_read_video_duration, video_abs)

                temp = float(temperature) if temperature is not None else None
                conc = max(1, int(chunk_llm_concurrency or 32))

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=25,
                    message=f"调用大模型生成分块脚本（共 {len(chunks)} 批）…",
                    phase="llm",
                )

                sem = asyncio.Semaphore(conc)
                chunk_outputs: Dict[int, List[Dict[str, Any]]] = {}

                async def _one(ch: Dict[str, Any]) -> None:
                    nonlocal chunk_outputs
                    idx = int(ch["chunk_index"])
                    sys_p = str(ch["system_prompt"])
                    usr_p = str(ch["user_prompt"])
                    messages = [
                        ChatMessage(role="system", content=sys_p),
                        ChatMessage(role="user", content=usr_p),
                    ]
                    delays = _CHUNK_LLM_RETRY_DELAYS_SEC
                    max_attempts = 1 + len(delays)
                    last_exc: Optional[BaseException] = None
                    for attempt in range(max_attempts):
                        if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                            raise asyncio.CancelledError()
                        try:
                            async with sem:
                                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                    raise asyncio.CancelledError()
                                # await asyncio.to_thread(
                                #     _log_llm_messages_beside_multimodal,
                                #     mm_abs,
                                #     messages,
                                #     project_id=project_id,
                                #     task_id=task_id,
                                #     chunk_index0=idx,
                                #     attempt0=attempt,
                                # )
                                # HTTP 重试仅由本函数外层 delays 负责，避免与 send_chat 内层双重重试
                                resp = await ai_service.send_chat(
                                    messages,
                                    response_format={"type": "json_object"},
                                    temperature=temp,
                                    usage=LlmModelUsage.SCRIPT_GENERATION,
                                    http_max_attempts=1,
                                    timeout=600,
                                )
                            data, _ = sanitize_json_text_to_dict(resp.content or "")
                            items = data.get("items") if isinstance(data, dict) else None
                            if not isinstance(items, list) or not items:
                                raise ValueError(f"第 {idx + 1} 批模型未返回 items")
                            await asyncio.to_thread(post_check_chunk_items, items)
                            chunk_outputs[idx] = items
                            return
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            last_exc = e
                            if attempt >= len(delays):
                                break
                            wait_sec = float(delays[attempt])
                            logger.warning(
                                "omni_generate_script 第 %s 批 LLM 第 %s/%s 次失败: %s；%.1fs 后重试",
                                idx + 1,
                                attempt + 1,
                                max_attempts,
                                e,
                                wait_sec,
                            )
                            if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                raise asyncio.CancelledError()
                            await asyncio.sleep(wait_sec)
                    assert last_exc is not None
                    raise last_exc

                await asyncio.gather(*[_one(c) for c in chunks])

                ordered: List[List[Dict[str, Any]]] = []
                for i in range(len(chunks)):
                    ordered.append(chunk_outputs[i])

                merged = merge_chunk_items(ordered)
                validated = validate_script_items(normalize_items_for_validation(merged))
                items_final = validated.get("items") or []
                script = omni_items_to_video_script(items_final, total_duration)

                work = _work_dir(project_id)
                work.mkdir(parents=True, exist_ok=True)
                artifact_path = work / "narration_script_artifact.json"
                preview0 = ""
                if chunks:
                    c0 = chunks[0]
                    preview0 = (str(c0.get("system_prompt", ""))[:1200] + "\n---\n" + str(c0.get("user_prompt", ""))[:4000])

                artifact = {
                    "meta": {
                        "source": "omni_generate_script",
                        "project_id": project_id,
                        "task_id": task_id,
                        "input_global_path_web_path": str(gp_web),
                        "input_multimodal_web_path": str(mm_web),
                        "chunk_batches": len(chunks),
                        "script_language": params.script_language,
                        "original_ratio": params.original_ratio,
                    },
                    "prompt_preview": preview0,
                    "video_duration_sec": total_duration,
                    "script": script,
                }
                artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
                out_web = _to_web_path(artifact_path)

                projects_store.save_script(project_id, script)
                projects_store.update_project(
                    project_id,
                    {
                        "status": "completed",
                        "omni_generate_script_path": out_web,
                        "omni_generate_script_updated_at": datetime.now().isoformat(),
                    },
                )

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message=f"解说脚本生成完成（{len(items_final)} 条）",
                    phase="done",
                )
            except asyncio.CancelledError:
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="cancelled",
                    message="任务已取消",
                    phase="cancelled",
                )
            except Exception as e:
                logger.exception("omni_generate_script failed")
                try:
                    projects_store.update_project(project_id, {"status": "failed"})
                except Exception:
                    pass
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="failed",
                    message=f"失败: {e}",
                    phase="failed",
                )

        asyncio.create_task(_run())
        return {"task_id": task_id, "status": "pending", "message": "任务已提交"}


omni_generate_script_service = OmniGenerateScriptService()
