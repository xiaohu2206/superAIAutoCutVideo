import asyncio
import logging
import re
import bisect
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException

from modules.json_sanitizer import validate_script_items
from modules.projects_store import projects_store
from services.ai_service import ai_service

from .constants import MAX_SUBTITLE_ITEMS_PER_CALL, SOFT_INPUT_FACTOR
from .length_planner import parse_script_length_selection, allocate_output_counts, estimate_auto_script_length_plan
from .copywriting_builder import generate_copywriting_from_subtitles, generate_copywriting_from_scenes
from .script_builder import _generate_script_chunk, _merge_items, _refine_full_script
from .visual_script_builder import _generate_visual_script_chunk
from .subtitle_utils import compute_subtitle_chunks, _parse_srt_subtitles, _parse_timestamp_pair
from .scene_utils import scenes_to_timeline_items

logger = logging.getLogger(__name__)


def _split_copywriting_text(text: str, parts: int, script_language: Optional[str]) -> List[str]:
    s = str(text or "")
    n = int(parts or 1)
    if n <= 1:
        return [s]
    lang = str(script_language or "").strip().lower()
    is_en = lang in {"en", "en-us", "英文", "english"} or (sum(1 for ch in s if ("a" <= ch.lower() <= "z")) > max(1, len(s) // 2))
    seps = {
        "\n",
        " ",
        "\t",
        ".",
        "!",
        "?",
        ";",
        "。",
        "！",
        "？",
        "；",
        "：",
        "…",
    }
    boundaries = [i for i, ch in enumerate(s) if ch in seps]
    length = len(s)
    base_positions = [int(round(length * i / n)) for i in range(1, n)]
    cuts: List[int] = []
    last_cut = 0
    tokens = list(re.finditer(r"[A-Za-z]+(?:'[A-Za-z]+)?", s)) if is_en else []
    token_starts = [m.start() for m in tokens] if tokens else []
    token_ends = [m.end() for m in tokens] if tokens else []
    for pos in base_positions:
        if is_en and token_starts:
            base_token = bisect.bisect_right(token_starts, pos)
            min_tok = max(0, base_token - 100)
            max_tok = min(len(token_starts) - 1, base_token + 100)
            window_start = token_starts[min_tok]
            window_end = token_ends[max_tok]
        else:
            window_start = max(0, pos - 100)
            window_end = min(length, pos + 100)
        candidates = [i for i in boundaries if window_start <= i <= window_end]
        if candidates:
            forward = min((i for i in candidates if i >= pos), default=None, key=lambda x: x - pos)
            backward = min((i for i in candidates if i < pos), default=None, key=lambda x: pos - x)
            if forward is None and backward is None:
                cut = pos
            elif forward is None:
                cut = backward + 1
            elif backward is None:
                cut = forward + 1
            else:
                if (forward - pos) <= (pos - backward):
                    cut = forward + 1
                else:
                    cut = backward + 1
        else:
            cut = pos
        if cut <= last_cut:
            cut = max(pos, last_cut + 1)
        cuts.append(cut)
        last_cut = cut
    idxs = [0] + cuts + [length]
    out: List[str] = []
    for i in range(len(idxs) - 1):
        out.append(s[idxs[i] : idxs[i + 1]])
    return out


class ScriptGenerationService:
    @staticmethod
    async def generate_copywriting_pipeline(
        subtitle_content: str,
        drama_name: str,
        project_id: Optional[str] = None,
        script_language: Optional[str] = None,
        script_length: Optional[str] = None,
        copywriting_word_count: Optional[int] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> str:
        """使用提示词模板生成纯文本解说文案。"""
        return await generate_copywriting_from_subtitles(
            subtitle_content=subtitle_content,
            drama_name=drama_name,
            project_id=project_id,
            script_language=script_language,
            script_length=script_length,
            copywriting_word_count=copywriting_word_count,
            cancel_event=cancel_event,
        )

    @staticmethod
    async def generate_copywriting_pipeline_from_scenes(
        scenes_data: Dict[str, Any],
        drama_name: str,
        project_id: Optional[str] = None,
        script_language: Optional[str] = None,
        script_length: Optional[str] = None,
        copywriting_word_count: Optional[int] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> str:
        """使用镜头数据生成纯文本解说文案。"""
        return await generate_copywriting_from_scenes(
            scenes_data=scenes_data,
            drama_name=drama_name,
            project_id=project_id,
            script_language=script_language,
            script_length=script_length,
            copywriting_word_count=copywriting_word_count,
            cancel_event=cancel_event,
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

        try:
            is_auto = str(sel_length or "").strip().lower() == "auto"
        except Exception:
            is_auto = False
        plan = estimate_auto_script_length_plan(copywriting_text) if is_auto else parse_script_length_selection(sel_length)
        chunks = compute_subtitle_chunks(
            subtitles=subtitles,
            desired_calls=plan.preferred_calls,
            max_items=MAX_SUBTITLE_ITEMS_PER_CALL,
            soft_factor=SOFT_INPUT_FACTOR,
        )
        if not chunks:
            raise HTTPException(status_code=400, detail="字幕解析失败：字幕内容为空")

        logger.info(f"📋 执行计划: 共 {len(chunks)} 个分段任务 | 目标总条数: {plan.final_target_count} | selection={plan.normalized_selection}")
        per_call_caps = allocate_output_counts(plan.final_target_count, len(chunks))
        per_call_caps = [min(int(MAX_SUBTITLE_ITEMS_PER_CALL), max(2, int(x))) for x in per_call_caps]
        sem = asyncio.Semaphore(5)
        copywriting_segments = _split_copywriting_text(copywriting_text, len(chunks), script_language)

        async def generate_one(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
            async with sem:
                return await _generate_script_chunk(
                    chunk["idx"],
                    len(chunks),
                    chunk["start"],
                    chunk["end"],
                    chunk["subs"],
                    copywriting_segments[int(chunk["idx"])] if 0 <= int(chunk["idx"]) < len(copywriting_segments) else "",
                    drama_name,
                    project_id,
                    per_call_caps[int(chunk["idx"])],
                    original_ratio,
                    script_language,
                )

        tasks = [generate_one(c) for c in chunks]
        results = await asyncio.gather(*tasks)
        all_items: List[Dict[str, Any]] = []
        for res in results:
            all_items.extend(res)
        merged_items = _merge_items(all_items)
        target = min(len(merged_items), int(plan.final_target_count))
        if target > 0 and len(merged_items) > target:
            final_items = await _refine_full_script(
                segments=merged_items,
                drama_name=drama_name,
                copywriting_text=copywriting_text,
                target_count=int(target),
                original_ratio=original_ratio,
                script_language=script_language,
            )
        else:
            final_items = merged_items
        final_items = sorted(final_items, key=lambda x: _parse_timestamp_pair(str(x.get("timestamp")))[0])
        for i, it in enumerate(final_items, start=1):
            it["_id"] = i
        data = {"items": final_items}
        validated = validate_script_items(data)
        return cast(Dict[str, Any], validated)

    @staticmethod
    async def generate_script_json_from_scenes(
        drama_name: str,
        copywriting_text: str,
        scenes_data: Dict[str, Any],
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        scenes_raw = scenes_data.get("scenes") if isinstance(scenes_data, dict) else None
        if not isinstance(scenes_raw, list):
            raise HTTPException(status_code=400, detail="镜头解析失败：数据结构无效")
        scene_items = scenes_to_timeline_items(cast(List[Dict[str, Any]], scenes_raw))
        if not scene_items:
            raise HTTPException(status_code=400, detail="镜头解析失败：镜头内容为空")
        try:
            total_duration = float(scene_items[-1]["end"] or 0.0)
        except Exception:
            total_duration = 0.0
        if total_duration == 0:
            raise HTTPException(status_code=400, detail="镜头解析失败：镜头时间戳无效")

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
            logger.info(f"🚀 开始生成脚本(visual) | 剧名: {drama_name} | 模型: {m_name} ({m_prov})")
        except Exception:
            logger.info(f"🚀 开始生成脚本(visual) | 剧名: {drama_name}")

        try:
            is_auto = str(sel_length or "").strip().lower() == "auto"
        except Exception:
            is_auto = False
        plan = estimate_auto_script_length_plan(copywriting_text) if is_auto else parse_script_length_selection(sel_length)
        chunks = compute_subtitle_chunks(
            subtitles=scene_items,
            desired_calls=plan.preferred_calls,
            max_items=MAX_SUBTITLE_ITEMS_PER_CALL,
            soft_factor=SOFT_INPUT_FACTOR,
        )
        if not chunks:
            raise HTTPException(status_code=400, detail="镜头解析失败：镜头内容为空")

        logger.info(f"📋 执行计划(visual): 共 {len(chunks)} 个分段任务 | 目标总条数: {plan.final_target_count} | selection={plan.normalized_selection}")
        per_call_caps = allocate_output_counts(plan.final_target_count, len(chunks))
        per_call_caps = [min(int(MAX_SUBTITLE_ITEMS_PER_CALL), max(2, int(x))) for x in per_call_caps]
        sem = asyncio.Semaphore(5)
        copywriting_segments = _split_copywriting_text(copywriting_text, len(chunks), script_language)

        async def generate_one(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
            async with sem:
                return await _generate_visual_script_chunk(
                    chunk["idx"],
                    len(chunks),
                    chunk["start"],
                    chunk["end"],
                    chunk["subs"],
                    copywriting_segments[int(chunk["idx"])] if 0 <= int(chunk["idx"]) < len(copywriting_segments) else "",
                    drama_name,
                    project_id,
                    per_call_caps[int(chunk["idx"])],
                    original_ratio,
                    script_language,
                )

        tasks = [generate_one(c) for c in chunks]
        results = await asyncio.gather(*tasks)
        all_items: List[Dict[str, Any]] = []
        for res in results:
            all_items.extend(res)
        merged_items = _merge_items(all_items)
        target = min(len(merged_items), int(plan.final_target_count))
        if target > 0 and len(merged_items) > target:
            final_items = await _refine_full_script(
                segments=merged_items,
                drama_name=drama_name,
                copywriting_text=copywriting_text,
                target_count=int(target),
                original_ratio=original_ratio,
                script_language=script_language,
            )
        else:
            final_items = merged_items
        final_items = sorted(final_items, key=lambda x: _parse_timestamp_pair(str(x.get("timestamp")))[0])
        for i, it in enumerate(final_items, start=1):
            it["_id"] = i
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
