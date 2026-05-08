#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni：在「rerank.json」重排结果之上做全局路径搜索（Beam + 转场 + zigzag + refine）。
独立目录 uploads/omni_global_path_search/{project_id}/；与 visual、omni_shot_match 任务 scope 隔离。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from modules.omni_global_path_search import build_global_path_payload
from modules.projects_store import projects_store
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from modules.project_task_queue import project_task_queue
from services.asr.extract_subtitle_service import _resolve_path, _to_web_path, _uploads_dir

logger = logging.getLogger(__name__)

_SCOPE = "omni_global_path_search"


def _work_dir(project_id: str) -> Path:
    return _uploads_dir() / "omni_global_path_search" / project_id


class OmniGlobalPathSearchService:
    SCOPE = _SCOPE

    async def submit_run(
        self,
        project_id: str,
        *,
        force: bool = False,
        task_id: Optional[str] = None,
        input_rerank_web_path: Optional[str] = None,
        search_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        if str(getattr(p, "project_type", "") or "").strip().lower() != "omni":
            raise ValueError("仅 omni 类型项目可运行全局路径搜索")

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
            task_id = f"omni_gps_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        task_progress_store.set_state(
            scope=self.SCOPE,
            project_id=project_id,
            task_id=task_id,
            status="pending",
            progress=0,
            message="准备全局路径搜索…",
            phase="preparing",
        )

        async def _run() -> None:
            await project_task_queue.acquire(project_id, self.SCOPE, task_id)
            try:
                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                cur = projects_store.get_project(project_id)
                if not cur:
                    raise ValueError("项目不存在")

                rerank_web = (input_rerank_web_path or "").strip() or (
                    getattr(cur, "omni_shot_match_rerank_path", None) or ""
                )
                if not str(rerank_web).strip():
                    raise ValueError("缺少重排结果：请先完成镜头匹配或传入 input_rerank_web_path")

                rerank_abs = _resolve_path(str(rerank_web))
                if not rerank_abs.exists():
                    raise FileNotFoundError(f"重排 JSON 不存在: {rerank_web}")

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=15,
                    message="读取 rerank 结果…",
                    phase="loading",
                )

                raw = await asyncio.to_thread(lambda: rerank_abs.read_text(encoding="utf-8"))
                rerank_payload = json.loads(raw)
                if not isinstance(rerank_payload, dict):
                    raise ValueError("rerank.json 根须为对象")

                gs_cfg: Dict[str, Any] = {}
                if isinstance(search_params, dict):
                    gs_cfg.update({k: v for k, v in search_params.items() if v is not None})

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=40,
                    message="全局路径搜索（Beam + refine）…",
                    phase="global_path_search",
                )

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                def _compute() -> Dict[str, Any]:
                    return build_global_path_payload(rerank_payload, gs_cfg)

                out_payload = await asyncio.to_thread(_compute)

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                work = _work_dir(project_id)
                work.mkdir(parents=True, exist_ok=True)
                out_path = work / "global_path.json"
                out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                out_web = _to_web_path(out_path)

                in_meta = rerank_payload.get("meta") if isinstance(rerank_payload.get("meta"), dict) else {}
                meta = out_payload.get("meta") if isinstance(out_payload.get("meta"), dict) else {}
                meta["project_id"] = project_id
                meta["input_rerank_web_path"] = str(rerank_web)
                meta["output_global_path_web_path"] = out_web
                if in_meta:
                    meta["input_rerank_meta"] = in_meta
                out_payload["meta"] = meta
                out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")

                projects_store.update_project(
                    project_id,
                    {
                        "omni_global_path_search_path": out_web,
                        "omni_global_path_search_updated_at": datetime.now().isoformat(),
                    },
                )

                n_seg = len(out_payload.get("results") or [])
                bgs = meta.get("best_global_score")
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message=f"全局路径搜索完成（段数 {n_seg}，best_global_score={bgs}）",
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
                logger.exception("omni_global_path_search failed")
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="failed",
                    message=f"失败: {e}",
                    phase="failed",
                )
            finally:
                await project_task_queue.release(project_id)

        asyncio.create_task(_run())
        return {"task_id": task_id, "status": "pending", "message": "任务已提交"}


omni_global_path_search_service = OmniGlobalPathSearchService()
