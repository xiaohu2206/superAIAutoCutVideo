import json
import logging
from typing import Any, Dict, List, Optional

from modules.ai import ChatMessage
from modules.json_sanitizer import sanitize_json_text_to_dict, validate_script_items
from modules.prompts.prompt_manager import prompt_manager
from services.ai_service import ai_service

from .constants import MAX_SUBTITLE_CHARS_PER_CALL
from .prompt_resolver import _default_prompt_key_for_project, _resolve_prompt_key
from .subtitle_utils import _format_timestamp_range, _parse_timestamp_pair
from modules.prompts.common.output_format_blocks import short_drama, movie

logger = logging.getLogger(__name__)


def _normalize_original_ratio(value: Optional[int]) -> int:
    try:
        num = int(value)
    except Exception:
        return 70
    if num < 10:
        return 10
    if num > 90:
        return 90
    return num


async def _generate_script_chunk(
    chunk_idx: int,
    chunk_total: int,
    start_time: float,
    end_time: float,
    subtitles: List[Dict[str, Any]],
    plot_analysis_snippet: str,
    drama_name: str,
    project_id: Optional[str] = None,
    target_items_count: Optional[int] = None,
    original_ratio: Optional[int] = None,
    script_language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    subs_text_lines = []
    for s in subtitles:
        ts = _format_timestamp_range(float(s["start"]), float(s["end"]))
        subs_text_lines.append(f"[{ts}] {s['text']}")
    subs_text = "\n".join(subs_text_lines)
    if len(subs_text) > MAX_SUBTITLE_CHARS_PER_CALL:
        subs_text = subs_text[:MAX_SUBTITLE_CHARS_PER_CALL]
    default_key = _default_prompt_key_for_project(project_id)
    key = _resolve_prompt_key(project_id, default_key)
    if script_language and ":" in key:
        lang = str(script_language).strip().lower()
        cat, name = key.split(":", 1)
        if lang in {"en", "en-us", "英文", "english"}:
            if name != "script_generation_en":
                candidate = f"{cat}:script_generation_en"
                try:
                    if prompt_manager.get_prompt(candidate):
                        key = candidate
                except Exception:
                    pass
        elif lang in {"zh", "zh-cn", "中文", "chinese"}:
            if name != "script_generation":
                candidate = f"{cat}:script_generation"
                try:
                    if prompt_manager.get_prompt(candidate):
                        key = candidate
                except Exception:
                    pass
    variables = {
        "drama_name": drama_name,
        "plot_analysis": plot_analysis_snippet or "",
        "subtitle_content": subs_text,
    }
    try:
        messages_dicts = prompt_manager.build_chat_messages(key, variables)
    except KeyError:
        try:
            cat = (key.split(":", 1)[0] if ":" in key else "short_drama_narration")
            if cat == "movie_narration":
                from modules.prompts.movie_narration import register_prompts
            else:
                from modules.prompts.short_drama_narration import register_prompts
            register_prompts()
            messages_dicts = prompt_manager.build_chat_messages(key, variables)
        except Exception:
            key = default_key
            messages_dicts = prompt_manager.build_chat_messages(key, variables)
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages_dicts]

    # 如果是用户自定义提示词（或提示词中缺少格式要求），需要根据语言拼接 output_format_blocks
    sys_msgs_content = "".join([m.content for m in messages if m.role == "system" and m.content])
    if "## 原声片段格式要求" not in sys_msgs_content:
        current_lang = "zh"
        if script_language:
            l = str(script_language).strip().lower()
            if l in {"en", "en-us", "英文", "english"}:
                current_lang = "en"

        prompt_cat = "short_drama_narration"
        if ":" in key:
            prompt_cat = key.split(":", 1)[0]

        if prompt_cat == "movie_narration":
            format_block = movie(current_lang)
        else:
            format_block = short_drama(current_lang)

        messages.append(ChatMessage(role="system", content=format_block))

    logger.info(f"⚡ 正在生成分段 {int(chunk_idx)+1}/{chunk_total}...")

    ratio_val = _normalize_original_ratio(original_ratio)
    if int(chunk_total or 0) > 0:
        total = int(chunk_total)
        idx = int(chunk_idx)
        if idx <= 0:
            pos_label = "开始段"
        elif idx >= total - 1:
            pos_label = "末尾段"
        else:
            pos_label = "中间段"
        messages.insert(
            0,
            ChatMessage(
                role="system",
                content=(
                    f"这是分段生成脚本的第{idx + 1}段/共{total}段，位置为{pos_label}。"
                    "开始（1）段可引入剧情，中间段不要重复开场或收尾（因为需要合并其它段进来），末尾段需要收束剧情并避免新开头。"
                ),
            ),
        )
    if target_items_count and int(target_items_count) > 0:
        n = int(target_items_count)
        messages.insert(
            0,
            ChatMessage(
                role="system",
                content=(
                    f"你必须仅输出一个JSON对象，键为'items'。"
                    f"items数组长度必须严格等于{n}，不能多不能少。"
                    f"start_time和end_time时间间隔不能低于1s"
                    f"每条必须包含'_id','timestamp','picture','narration','OST'。"
                    f"不得输出除JSON以外的任何文字。"
                ),
            ),
        )
    messages.insert(
        0,
        ChatMessage(
            role="system",
            content=(
                f"原片占比范围：本次原片占比为{ratio_val}%，解说占比为{100 - ratio_val}%。"
                "原声片段标识：OST=1表示原声，OST=0表示解说。"
            ),
        ),
    )
    if script_language:
        lang = str(script_language).strip().lower()
        if lang in {"en", "en-us", "英文", "english"}:
            messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content=(
                        "你必须将所有 'narration' 文本严格用英文撰写；不得输出中文或其他语言。"
                    ),
                ),
            )
        elif lang in {"zh", "zh-cn", "中文", "chinese"}:
            messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content=(
                        "你必须将所有 'narration' 文本严格用中文撰写；不得输出英文或其他语言。"
                    ),
                ),
            )
    system_contents: List[str] = []
    non_system_messages: List[ChatMessage] = []
    for message in messages:
        if message.role == "system":
            if message.content is not None:
                system_contents.append(str(message.content))
        else:
            non_system_messages.append(message)
    if system_contents:
        merged_system = "\n".join([c for c in system_contents if c])
        messages = [ChatMessage(role="system", content=merged_system), *non_system_messages]
    else:
        messages = non_system_messages
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
            data, _ = sanitize_json_text_to_dict(resp.content)
            data = validate_script_items(data)
            items = data.get("items") or []
            logger.info(f"v{int(chunk_idx)+1} 生成分段, 共{len(items)}条")
            valid_items: List[Dict[str, Any]] = []
            for it in items:
                try:
                    s_t, e_t = _parse_timestamp_pair(str(it.get("timestamp")))
                    if e_t < start_time - 5 or s_t > end_time + 5:
                        continue
                    valid_items.append(
                        {
                            "_id": it.get("_id"),
                            "timestamp": str(it.get("timestamp")),
                            "picture": it.get("picture"),
                            "narration": str(it.get("narration", "")),
                            "OST": 1 if it.get("OST") == 1 else 0,
                            "_chunk_idx": chunk_idx,
                        }
                    )
                except Exception:
                    continue
            if target_items_count and int(target_items_count) > 0:
                n = int(target_items_count)
                out: List[Dict[str, Any]] = []
                for it in valid_items:
                    if len(out) >= n:
                        break
                    out.append(it)
                if len(out) < n:
                    for it in items:
                        if len(out) >= n:
                            break
                        out.append(
                            {
                                "_id": it.get("_id"),
                                "timestamp": str(it.get("timestamp")),
                                "picture": it.get("picture"),
                                "narration": str(it.get("narration", "")),
                                "OST": 1 if it.get("OST") == 1 else 0,
                                "_chunk_idx": chunk_idx,
                            }
                        )
                return out
            return valid_items
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Chunk {chunk_idx} generation failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying...")
                continue
            else:
                logger.error(f"Chunk {chunk_idx} generation failed after {max_retries} retries: {e}")
                raise e
    return []


def _merge_items(all_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sorted_items = sorted(all_items, key=lambda x: _parse_timestamp_pair(str(x["timestamp"]))[0])
    merged: List[Dict[str, Any]] = []
    if not sorted_items:
        return []
    current = sorted_items[0]
    for next_it in sorted_items[1:]:
        try:
            cs, ce = _parse_timestamp_pair(str(current["timestamp"]))
            ns, ne = _parse_timestamp_pair(str(next_it["timestamp"]))
        except Exception:
            merged.append(current)
            current = next_it
            continue
        overlap_start = max(cs, ns)
        overlap_end = min(ce, ne)
        overlap_len = max(0.0, overlap_end - overlap_start)
        curr_len = max(0.0, ce - cs)
        next_len = max(0.0, ne - ns)
        if overlap_len > 0 and (overlap_len > 0.4 * min(curr_len, next_len) + 0.1):
            if len(str(next_it.get("narration", ""))) > len(str(current.get("narration", ""))):
                current = next_it
            else:
                pass
        else:
            merged.append(current)
            current = next_it
    merged.append(current)
    min_duration = 0.8
    filtered: List[Dict[str, Any]] = []
    for it in merged:
        try:
            s, e = _parse_timestamp_pair(str(it["timestamp"]))
            if max(0.0, e - s) < min_duration:
                continue
        except Exception:
            pass
        filtered.append(it)
    for i, it in enumerate(filtered, start=1):
        it["_id"] = i
    return filtered


async def _refine_full_script(
    segments: List[Dict[str, Any]],
    drama_name: str,
    plot_analysis: str,
    length_mode: Optional[str] = None,
    target_count: Optional[int] = None,
    original_ratio: Optional[int] = None,
    script_language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    items = segments
    if not items:
        return []
    draft_str = json.dumps(items, ensure_ascii=False)
    n = len(items)
    if target_count and int(target_count) > 0:
        target = int(target_count)
    else:
        target = int(n)
    if target < 1:
        target = 1
    if target >= n:
        retain_desc = ""
    else:
        retain_desc = (
            f"必须仅保留 {target} 条最关键条目，其余全部删除（必须遵守）。"
            f"返回的 'items' 长度必须为 {target}，不得新增条目，仅在已有 '_id' 中选择，但一定要确保不能烂尾。"
        )

    ratio_val = _normalize_original_ratio(original_ratio)
    system_prompt = (
        "你是一位分块脚本合并助手。你的任务是将已按时间分块生成的解说脚本进行轻量合并与顺畅衔接。"
        + retain_desc +
        f"**原片占比范围**：本次原片占比为{ratio_val}%，解说占比为{100 - ratio_val}%。"
        "**原声片段标识**：OST=1表示原声，OST=0表示解说"
        "对于单一条目，仅对部分的 'narration' 进行小幅润色，比如补充必要的连接词、消除重复或断裂，让上下文自然连贯；不要改变原有信息与含义。"
        "对于所有脚本内容，是通过多个模型生成的，每个模型生成的脚本段容易出现开头语和结尾语，但可能是中间段，如果是中间段应该把开头语或结尾语条目删除"
        "对于单一条目，一般不修改 'picture' 与 'OST'，如无必要变更则原样返回。"
        "仅返回一个 JSON 对象，键为 'items'，每个元素包含 '_id', 'timestamp', 'picture', 'narration', 'OST'；不要输出除 JSON 以外的任何内容。"
    )
    if script_language:
        lang = str(script_language).strip().lower()
        if lang in {"en", "en-us", "英文", "english"}:
            system_prompt += "你必须将所有 'narration' 文本严格用英文撰写；不得输出中文或其他语言。"
        elif lang in {"zh", "zh-cn", "中文", "chinese"}:
            system_prompt += "你必须将所有 'narration' 文本严格用中文撰写；不得输出英文或其他语言。"
    user_content = (
        f"{retain_desc}\n\n"
        f"剧名：{drama_name}\n"
        f"草稿：\n{draft_str}\n\n"
        "请按要求返回 JSON。"
    )
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_content)
    ]
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"✨ 正在进行全局润色... (目标条数: {target})")
            resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
            data, _ = sanitize_json_text_to_dict(resp.content)
            data = validate_script_items(data)
            llm_items = data.get("items", [])
            llm_ids_ordered: List[int] = []
            for it in llm_items:
                try:
                    if it.get("_id") is None:
                        continue
                    llm_ids_ordered.append(int(it.get("_id")))
                except Exception:
                    continue
            new_items_map = {int(it.get("_id")): it for it in llm_items if it.get("_id") is not None}

            def _update_item(orig: Dict[str, Any], new_it: Optional[Dict[str, Any]]) -> Dict[str, Any]:
                _id_val = int(orig.get("_id") or 0)
                if new_it:
                    orig["narration"] = str(new_it.get("narration", orig.get("narration", "")))
                    orig["picture"] = new_it.get("picture")
                    try:
                        ost_val = 1 if new_it.get("OST") == 1 else 0
                        orig["OST"] = ost_val
                    except Exception:
                        pass
                orig["_id"] = _id_val
                return orig

            if target >= n:
                final_items_all: List[Dict[str, Any]] = []
                for i, it in enumerate(items, start=1):
                    _id = int(it.get("_id") or i)
                    it["_id"] = _id
                    final_items_all.append(_update_item(it, new_items_map.get(_id)))
                return final_items_all

            keep_ids: List[int] = []
            if llm_ids_ordered:
                for _id in llm_ids_ordered:
                    if _id not in keep_ids:
                        keep_ids.append(_id)
                if len(keep_ids) > target:
                    keep_ids = keep_ids[:target]
            else:
                ids_all = [int(it.get("_id") or idx) for idx, it in enumerate(items, start=1)]
                keep_ids = ids_all[:target]

            id_set = set([int(it.get("_id") or idx) for idx, it in enumerate(items, start=1)])
            keep_ids = [i for i in keep_ids if i in id_set]
            if len(keep_ids) < target:
                for i in sorted(id_set):
                    if i not in keep_ids:
                        keep_ids.append(i)
                    if len(keep_ids) >= target:
                        break

            final_items_selected: List[Dict[str, Any]] = []
            for i, it in enumerate(items, start=1):
                _id = int(it.get("_id") or i)
                if _id in keep_ids:
                    it["_id"] = _id
                    final_items_selected.append(_update_item(it, new_items_map.get(_id)))
            return final_items_selected
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Refine script failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying...")
                continue
            else:
                logger.error(f"Refine script failed after {max_retries} retries: {e}")
                raise e
    return items
