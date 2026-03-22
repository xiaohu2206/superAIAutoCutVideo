import json
import logging
from typing import Any, Dict, List, Optional

from modules.ai import ChatMessage
from modules.json_sanitizer import sanitize_json_text_to_dict, validate_script_items
from services.ai_service import ai_service

from .constants import MAX_SUBTITLE_CHARS_PER_CALL
from .subtitle_utils import _format_timestamp_range, _parse_timestamp_pair
from modules.prompts.common.output_format_blocks import short_drama, movie

logger = logging.getLogger(__name__)


def _normalize_original_ratio(value: Optional[int]) -> int:
    try:
        num = int(value)
    except Exception:
        return 70
    if num < 0:
        return 0
    if num > 100:
        return 100
    return num


def _build_ost_system_hint(original_ratio: Optional[int]) -> str:
    if original_ratio is None:
        return "原声片段标识：OST=1表示原声，OST=0表示解说。"
    ratio_val = _normalize_original_ratio(original_ratio)
    if ratio_val <= 0:
        return "本次只生成解说片段：所有条目的OST必须为0，且narration为解说文案；不得使用“播放原片+序号”格式。"
    if ratio_val >= 100:
        return "本次只生成原声片段：所有条目的OST必须为1，且narration必须使用“播放原片+序号”格式；不得输出解说文案。"
    return (
        f"原片占比范围：本次原片占比为{ratio_val}%，解说占比为{100 - ratio_val}%。"
        "原声片段标识：OST=1表示原声，OST=0表示解说。"
    )


def _detect_narration_type(project_id: Optional[str]) -> str:
    if not project_id:
        return "short_drama_narration"
    try:
        from modules.projects_store import projects_store
        p = projects_store.get_project(project_id)
        if p:
            t = str(getattr(p, "narration_type", "") or "")
            if t == "电影解说":
                return "movie_narration"
    except Exception:
        pass
    return "short_drama_narration"


def _build_fixed_script_prompt(
    drama_name: str,
    copywriting_text: str,
    subs_text: str,
    narration_type: str,
    script_language: Optional[str],
    original_ratio: Optional[int] = None,
) -> str:
    """构建固定的脚本生成提示词（不使用提示词模板系统）。"""
    lang = "en" if script_language and str(script_language).strip().lower() in {"en", "en-us", "英文", "english"} else "zh"
    ratio_val = _normalize_original_ratio(original_ratio) if original_ratio is not None else None

    requirements_extra = ""
    ost_rules = ""
    if ratio_val is None:
        requirements_extra = "- 合理分配原声片段（OST=1）和解说片段（OST=0）\n"
        ost_rules = (
            "## 原声片段规则\n"
            "- OST=1 表示保留原声，narration 使用\"播放原片+序号\"格式\n"
            "- OST=0 表示解说，narration 填写对应的解说文案内容\n"
            "- 在关键情绪爆发点、重要对白、爽点瞬间保留原声\n"
        )
    elif ratio_val <= 0:
        requirements_extra = "- 本次只生成解说片段（OST 必须为 0），不得输出原声片段\n"
        ost_rules = (
            "## 解说片段规则\n"
            "- OST=0 表示解说，narration 填写对应的解说文案内容\n"
        )
    elif ratio_val >= 100:
        requirements_extra = "- 本次只生成原声片段（OST 必须为 1），不得输出解说片段\n"
        ost_rules = (
            "## 原声片段规则\n"
            "- OST=1 表示保留原声，narration 使用\"播放原片+序号\"格式\n"
        )
    else:
        requirements_extra = (
            f"- 合理分配原声片段（OST=1）和解说片段（OST=0），原片占比约 {ratio_val}%\n"
        )
        ost_rules = (
            "## 原声片段规则\n"
            "- OST=1 表示保留原声，narration 使用\"播放原片+序号\"格式\n"
            "- OST=0 表示解说，narration 填写对应的解说文案内容\n"
            "- 在关键情绪爆发点、重要对白、爽点瞬间保留原声\n"
        )

    prompt = f"""# 解说脚本生成任务

## 任务目标
从整部视频中挑选“值得解说的精彩片段”，将解说文案的关键内容对齐到字幕时间戳，生成带时间轴的解说脚本。
尽量保留“解说文案”完整拆分并全部对齐到字幕时间轴中对应的时间段，生成带时间轴的解说脚本；尽量不遗漏任何文案内容。允许必要压缩但不得改变原意。

## 输入说明
1. **解说文案**：一段完整的叙述文本，这是要使用的解说内容
2. **字幕内容**：带有精确时间戳的原始字幕，用于确定每段解说对应的时间范围

## 任务要求
- 不需要按时间顺序抽取字幕（时间戳可以大幅跳跃，不要求连续覆盖全片），但尽量覆盖完整“解说文案”内容；
- 只输出需要解说的精彩片段；允许时间戳不连续
- narration 必须严格从“解说文案”拆分/压缩而来；不得新增未出现的信息
{requirements_extra}- 时间戳格式必须与字幕中的格式一致
{ost_rules}

## 原始字幕（含精确时间戳）
<subtitles>
{subs_text}
</subtitles>

## 剧名
《{drama_name}》
"""
    return prompt


async def _generate_script_chunk(
    chunk_idx: int,
    chunk_total: int,
    start_time: float,
    end_time: float,
    subtitles: List[Dict[str, Any]],
    copywriting_text: str,
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

    narration_type = _detect_narration_type(project_id)
    lang_key = "en" if script_language and str(script_language).strip().lower() in {"en", "en-us", "英文", "english"} else "zh"

    user_prompt = _build_fixed_script_prompt(
        drama_name=drama_name,
        copywriting_text=copywriting_text,
        subs_text=subs_text,
        narration_type=narration_type,
        script_language=script_language,
        original_ratio=original_ratio,
    )

    system_prompt = (
        "你是一位专业的视频脚本时间轴编辑器。"
        "你必须严格按照JSON格式输出，绝不能包含任何其他文字、说明或代码块标记。\n\n"
    )
    ratio_for_blocks = _normalize_original_ratio(original_ratio) if original_ratio is not None else None
    if narration_type == "movie_narration":
        system_prompt += movie(lang_key, ratio_for_blocks)
    else:
        system_prompt += short_drama(lang_key, ratio_for_blocks)

    messages: List[ChatMessage] = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(
            role="user",
            content=(
                "## 解说文案\n"
                "<copywriting>\n"
                f"{copywriting_text}\n"
                "</copywriting>"
            ),
        ),
        ChatMessage(role="user", content=user_prompt),
    ]

    messages.insert(
        0,
        ChatMessage(
            role="system",
            content=(
                "以下为必须严格使用的解说文案文本：所有条目的'narration'必须仅基于该文案进行时间轴拆分；"
                "不得编造或新增任何未出现的内容；允许必要压缩但不得改变含义；如果一段文案太长，匹配不到好的镜头，可以修改文案"
            ),
        ),
    )
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
                    "本段不得输出0条（items 不可为空），并将本时间段内的解说文案对齐到字幕时间轴。"
                    "避免重复的开场白/总结句等套话。"
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
                    # f"items数组长度大约控制为{n}条"
                    "每条时间段长度不能低于1秒。"
                    "每条必须包含'_id','timestamp','picture','narration','OST'。"
                    "不得输出除JSON以外的任何文字。"
                ),
            ),
        )
    messages.insert(
        0,
        ChatMessage(
            role="system",
            content=_build_ost_system_hint(original_ratio),
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

    logger.info(f"⚡ 正在生成分段 {int(chunk_idx)+1}/{chunk_total}...")

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
    copywriting_text: str,
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

    ratio_val = _normalize_original_ratio(original_ratio) if original_ratio is not None else None
    if ratio_val is None:
        ratio_hint = "**原声片段标识**：OST=1表示原声，OST=0表示解说"
    elif ratio_val <= 0:
        ratio_hint = "本次只生成解说片段：所有条目的OST必须为0，且narration为解说文案；不得使用“播放原片+序号”格式。"
    elif ratio_val >= 100:
        ratio_hint = "本次只生成原声片段：所有条目的OST必须为1，且narration必须使用“播放原片+序号”格式；不得输出解说文案。"
    else:
        ratio_hint = (
            f"**原片占比范围**：本次原片占比为{ratio_val}%，解说占比为{100 - ratio_val}%。"
            "**原声片段标识**：OST=1表示原声，OST=0表示解说"
        )
    system_prompt = (
        "你是一位分块脚本合并助手。你的任务是将已按时间分块生成的解说脚本进行轻量合并与顺畅衔接。"
        + retain_desc
        + ratio_hint
        + "本次输出目标是“精彩片段解说”，不要求覆盖整部影片时间轴，允许大段跳过。"
        + "当需要删减时，优先删除那些时间上紧贴上一条/下一条、信息密度低、重复、过渡或铺垫过长的条目；避免出现大量连续衔接的时间戳导致覆盖整片。"
        + "对于单一条目，仅对部分的 'narration' 进行小幅润色，比如补充必要的连接词、消除重复或断裂，让上下文自然连贯；不要改变原有信息与含义。"
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
