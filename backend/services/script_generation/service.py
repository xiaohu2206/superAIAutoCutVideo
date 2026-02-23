import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException

from modules.json_sanitizer import validate_script_items
from modules.projects_store import projects_store
from services.ai_service import ai_service

from .constants import MAX_SUBTITLE_ITEMS_PER_CALL, SOFT_INPUT_FACTOR
from .length_planner import parse_script_length_selection, allocate_output_counts
from .copywriting_builder import generate_copywriting_from_subtitles
from .script_builder import _generate_script_chunk, _merge_items, _refine_full_script
from .subtitle_utils import compute_subtitle_chunks, _parse_srt_subtitles, _parse_timestamp_pair

logger = logging.getLogger(__name__)


class ScriptGenerationService:
    @staticmethod
    async def generate_copywriting_pipeline(
        subtitle_content: str,
        drama_name: str,
        project_id: Optional[str] = None,
        script_language: Optional[str] = None,
        script_length: Optional[str] = None,
        copywriting_word_count: Optional[int] = None,
    ) -> str:
        """使用提示词模板生成纯文本解说文案。"""
        return await generate_copywriting_from_subtitles(
            subtitle_content=subtitle_content,
            drama_name=drama_name,
            project_id=project_id,
            script_language=script_language,
            script_length=script_length,
            copywriting_word_count=copywriting_word_count,
        )

    @staticmethod
    async def generate_script_json(
        drama_name: str,
        copywriting_text: str,
        subtitle_content: str,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        subtitles = _parse_srt_subtitles(subtitle_content)
        if not subtitles:
            logger.warning("Subtitle parsing failed")
            raise HTTPException(status_code=400, detail="字幕解析失败：请上传有效的SRT字幕或标准时间戳格式")
        total_duration = subtitles[-1]["end"] if subtitles else 0
        if total_duration == 0:
            logger.warning("Subtitle total duration invalid")
            raise HTTPException(status_code=400, detail="字幕解析失败：字幕时间戳无效")

        sel_length: Optional[str] = None
        original_ratio: Optional[int] = None
        script_language: Optional[str] = None
        if project_id:
            try:
                p = projects_store.get_project(project_id)
                if p:
                    if getattr(p, "script_length", None):
                        sel_length = str(getattr(p, "script_length", None))
                    if getattr(p, "original_ratio", None) is not None:
                        try:
                            original_ratio = int(getattr(p, "original_ratio", None))
                        except Exception:
                            original_ratio = None
                    if getattr(p, "script_language", None):
                        try:
                            script_language = str(getattr(p, "script_language", None))
                        except Exception:
                            script_language = None
            except Exception:
                sel_length = None

        try:
            model_info = ai_service.get_provider_info()
            m_name = model_info.get("active_model", "Unknown")
            m_prov = model_info.get("active_provider", "Unknown")
            logger.info(f"🚀 开始生成脚本 | 剧名: {drama_name} | 模型: {m_name} ({m_prov})")
        except Exception:
            logger.info(f"🚀 开始生成脚本 | 剧名: {drama_name}")

        plan = parse_script_length_selection(sel_length)
        chunks = compute_subtitle_chunks(
            subtitles=subtitles,
            desired_calls=plan.preferred_calls,
            max_items=MAX_SUBTITLE_ITEMS_PER_CALL,
            soft_factor=SOFT_INPUT_FACTOR,
        )
        if not chunks:
            raise HTTPException(status_code=400, detail="字幕解析失败：字幕内容为空")

        logger.info(f"📋 执行计划: 共 {len(chunks)} 个分段任务 | 目标总条数: {plan.final_target_count}")
        per_call_counts = allocate_output_counts(plan.final_target_count, len(chunks))
        sem = asyncio.Semaphore(5)

        async def generate_one(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
            async with sem:
                return await _generate_script_chunk(
                    chunk["idx"],
                    len(chunks),
                    chunk["start"],
                    chunk["end"],
                    chunk["subs"],
                    copywriting_text,
                    drama_name,
                    project_id,
                    per_call_counts[int(chunk["idx"])],
                    original_ratio,
                    script_language,
                )

        tasks = [generate_one(c) for c in chunks]
        results = await asyncio.gather(*tasks)
        all_items: List[Dict[str, Any]] = []
        for res in results:
            all_items.extend(res)
        merged_items = _merge_items(all_items)
        effective_target = min(len(merged_items), int(plan.final_target_count))
        if len(chunks) <= 1:
            final_items = merged_items[:effective_target] if effective_target > 0 else []
        else:
            final_items = await _refine_full_script(
                merged_items,
                drama_name,
                copywriting_text,
                None,
                effective_target,
                original_ratio,
                script_language,
            )
        data = {"items": final_items}
        validated = validate_script_items(data)
        return cast(Dict[str, Any], validated)

    @staticmethod
    def to_video_script(data: Dict[str, Any], total_duration: float) -> Dict[str, Any]:
        items = data.get("items", [])
        segments: List[Dict[str, Any]] = []
        for it in items:
            start_s, end_s = _parse_timestamp_pair(str(it.get("timestamp")))
            text = str(it.get("narration", "")).strip()
            seg = {
                "id": str(it.get("_id", len(segments) + 1)),
                "start_time": float(start_s),
                "end_time": float(end_s),
                "text": text,
                "OST": it.get("OST", 0),
            }
            pic = it.get("picture")
            if pic:
                seg["subtitle"] = str(pic)
            segments.append(seg)

        now = datetime.now()
        generated_time = now.isoformat()
        version = f"{now.strftime('%Y%m%d%H%M%S')}"
        return {
            "生成时间": generated_time,
            '条数': len(segments),
            "version": version,
            "total_duration": float(total_duration or 0.0),
            "segments": segments,
            "metadata": {
                "created_at": generated_time,
            },
        }
