"""
解说文案生成器 —— 使用提示词模板（含用户自定义）生成纯文本解说文案。
支持大字数分段生成：大纲→分段→合并。
"""

import asyncio
import logging
import math
import re
from typing import Any, Dict, List, Optional

from modules.ai import ChatMessage
from modules.prompts.prompt_manager import prompt_manager
from services.ai_service import ai_service

from .constants import MAX_SUBTITLE_CHARS_PER_CALL
from .prompt_resolver import _default_prompt_key_for_project, _resolve_prompt_key
from .scene_utils import scenes_to_timeline_items
from .subtitle_utils import _format_timestamp_range, _parse_srt_subtitles

logger = logging.getLogger(__name__)

SINGLE_CALL_MAX_CHARS = 3000
CHARS_PER_ITEM_ZH = 80
CHARS_PER_ITEM_EN = 200


def _is_english(language: Optional[str]) -> bool:
    if not language:
        return False
    lang = str(language).strip().lower()
    return lang in {"en", "en-us", "英文", "english"}


def _is_chinese(language: Optional[str]) -> bool:
    if not language:
        return True
    lang = str(language).strip().lower()
    return lang in {"zh", "zh-cn", "中文", "chinese", ""}


def _estimate_target_word_count(
    script_length: Optional[str],
    script_language: Optional[str],
    copywriting_word_count: Optional[int] = None,
) -> Optional[int]:
    """
    根据 copywriting_word_count 决定目标文案字数。
    返回 None 表示"自动"模式，不限制模型输出字数。
    仅当用户明确设置了 copywriting_word_count 且 > 0 时才返回具体数字。
    """
    if copywriting_word_count is not None and int(copywriting_word_count) > 0:
        return int(copywriting_word_count)
    return None


def _resolve_template_key(
    project_id: Optional[str],
    script_language: Optional[str],
) -> str:
    default_key = _default_prompt_key_for_project(project_id)
    key = _resolve_prompt_key(project_id, default_key)

    if script_language and ":" in key:
        lang = str(script_language).strip().lower()
        cat, name = key.split(":", 1)
        if lang in {"en", "en-us", "英文", "english"}:
            # 仅在「默认中文模板」与英文模板之间切换，保留用户选择的其它官方模板（如幽默搞笑）
            if name == "script_generation":
                candidate = f"{cat}:script_generation_en"
                try:
                    if prompt_manager.get_prompt(candidate):
                        key = candidate
                except Exception:
                    pass
        elif lang in {"zh", "zh-cn", "中文", "chinese"}:
            if name == "script_generation_en":
                candidate = f"{cat}:script_generation"
                try:
                    if prompt_manager.get_prompt(candidate):
                        key = candidate
                except Exception:
                    pass
    return key


def _build_template_messages(
    key: str,
    default_key: str,
    drama_name: str,
) -> List[ChatMessage]:
    # 字幕正文由 _append_subtitles_context_message 注入；subtitle_content 仅留空以兼容仍含 ${subtitle_content} 的自定义模板
    variables = {
        "drama_name": drama_name,
        "plot_analysis": "",
        "subtitle_content": "",
    }
    try:
        messages_dicts = prompt_manager.build_chat_messages(key, variables)
    except KeyError:
        try:
            cat = key.split(":", 1)[0] if ":" in key else "short_drama_narration"
            if cat == "movie_narration":
                from modules.prompts.movie_narration import register_prompts
            else:
                from modules.prompts.short_drama_narration import register_prompts
            register_prompts()
            messages_dicts = prompt_manager.build_chat_messages(key, variables)
        except Exception:
            messages_dicts = prompt_manager.build_chat_messages(default_key, variables)
    return [ChatMessage(role=m["role"], content=m["content"]) for m in messages_dicts]


def _append_subtitles_context_message(messages: List[ChatMessage], subs_text: str) -> List[ChatMessage]:
    """将带时间戳的字幕作为独立 user 消息附加（不再通过模板变量 subtitle_content 注入正文）。"""
    msgs = list(messages)
    text = str(subs_text or "").strip()
    if not text:
        return msgs
    msgs.append(
        ChatMessage(
            role="user",
            content=(
                "补充剧情参考字幕（含时间戳）如下，请据此理解剧情并创作：\n"
                f"{text}"
            ),
        )
    )
    return msgs


def _add_language_and_count_messages(
    messages: List[ChatMessage],
    script_language: Optional[str],
    target_chars: Optional[int],
) -> List[ChatMessage]:
    msgs = list(messages)
    if _is_english(script_language):
        msgs.insert(0, ChatMessage(
            role="system",
            content="You MUST write the entire narration copywriting strictly in English. Do NOT output Chinese or any other language.",
        ))
    elif _is_chinese(script_language):
        msgs.insert(0, ChatMessage(
            role="system",
            content="你必须将整篇解说文案严格用中文撰写；不得输出英文或其他语言。",
        ))

    unit = "words" if _is_english(script_language) else "字"
    if target_chars:
        count_hint = f"字数约为{target_chars}{unit}"
    else:
        count_hint = "不限制字数，尽可能详细完整地讲述剧情"
    msgs.insert(0, ChatMessage(
        role="system",
        content=(
            f"你必须输出一篇连续的纯文本解说文案，{count_hint}。"
            "不要输出JSON格式、代码块或任何格式标记，只输出解说文案正文。"
            "文案应按照剧情时间顺序完整讲述，段落之间用换行分隔。"
            "字幕仅用于理解剧情信息。"
            "不可以有各种符号、表情符号等，纯文本输出。"
        ),
    ))
    return msgs


def _append_film_context_user_message(
    messages: List[ChatMessage],
    film_context: Optional[str],
) -> List[ChatMessage]:
    """在已有消息之后追加影片背景 user；字幕正文由 `_append_subtitles_context_message` 另行附加。"""
    text = (film_context or "").strip()
    if not text:
        return messages
    out = list(messages)
    out.append(
        ChatMessage(
            role="user",
            content=(
                "以下为该影片的背景资料（含剧情脉络、人物关系等），请在严格遵循字幕/对白所呈现的事实前提下参考使用；"
                "写作时不要大段复述背景资料，主要用于理顺人物关系与整体故事线，使解说更准确连贯：\n\n"
                f"{text}"
            ),
        )
    )
    return out


def _append_reference_copywriting_user_message(
    messages: List[ChatMessage],
    reference_copywriting: Optional[str],
) -> List[ChatMessage]:
    """在消息列表末尾追加参考解说 user（须在字幕等 user 之后调用）。"""
    text = (reference_copywriting or "").strip()
    if not text:
        return messages
    out = list(messages)
    out.append(
        ChatMessage(
            role="user",
            content=(
                "以下为用户提供的参考解说文案（仅作风格、节奏与结构上的借鉴；须严格依据上文事实独立创作，禁止整段照搬或与参考高度雷同）：\n\n"
                f"{text}"
            ),
        )
    )
    return out


def _merge_system_messages(messages: List[ChatMessage]) -> List[ChatMessage]:
    system_contents: List[str] = []
    non_system: List[ChatMessage] = []
    for m in messages:
        if m.role == "system" and m.content:
            system_contents.append(str(m.content))
        else:
            non_system.append(m)
    if system_contents:
        merged = "\n".join(system_contents)
        return [ChatMessage(role="system", content=merged), *non_system]
    return non_system


def _strip_code_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _remove_leading_quoted_subtitle_lines(text: str) -> str:
    lines = text.splitlines()
    out: List[str] = []

    for ln in lines:
        s = ln.strip()
        if not s:
            out.append("")
            continue

        opening = s[0]
        closing = {"“": "”", "「": "」", '"': '"', "『": "』"}.get(opening)
        if closing:
            idx = s.find(closing, 1)
            if idx != -1:
                after = s[idx + 1 :].lstrip(" \t-—:：，,。.!！?？\"”'」』")
                if after:
                    out.append(after)
                continue

        if re.fullmatch(r"[“「『\"].{1,120}[”」』\"]", s):
            continue

        out.append(s)

    merged = "\n".join(out)
    merged = re.sub(r"\n{3,}", "\n\n", merged).strip()
    return merged


async def _call_llm_text(
    messages: List[ChatMessage],
    *,
    cancel_event: Optional[asyncio.Event] = None,
    max_retries: int = 3,
) -> str:
    merged = _merge_system_messages(messages)
    for attempt in range(max_retries + 1):
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()
        try:
            if cancel_event:
                llm_task = asyncio.create_task(ai_service.send_chat(merged))
                cancel_task = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait({llm_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
                if cancel_task in done:
                    try:
                        llm_task.cancel()
                    except Exception:
                        pass
                    raise asyncio.CancelledError()
                try:
                    cancel_task.cancel()
                except Exception:
                    pass
                resp = await llm_task
            else:
                resp = await ai_service.send_chat(merged)
            return _strip_code_fences(str(resp.content or "").strip())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}. Retrying...")
                continue
            raise
    return ""


# ─── 大纲生成 ────────────────────────────────────────────

async def _generate_outline(
    drama_name: str,
    subs_text: str,
    num_sections: int,
    script_language: Optional[str],
    *,
    film_context: Optional[str] = None,
    reference_copywriting: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> List[str]:
    """让模型生成一个分段大纲，返回各段的标题/摘要列表。"""
    lang_hint = "English" if _is_english(script_language) else "中文"
    system = (
        f"你是一位专业的解说文案策划。请根据字幕内容，为《{drama_name}》的解说文案生成{num_sections}段大纲。"
        f"每段大纲用一行描述该段应该讲述的剧情内容和时间范围（如果能判断的话）。"
        f"只输出大纲列表，每行一段，格式为「段落N：内容摘要」，不要输出其他文字。"
        "不要逐字引用字幕台词或原句，只做剧情概述。"
        f"必须使用{lang_hint}输出。"
    )
    user = (
        f"字幕内容：\n{subs_text}\n\n"
        f"请生成{num_sections}段大纲。"
    )
    messages = [ChatMessage(role="system", content=system)]
    messages = _append_film_context_user_message(messages, film_context)
    messages.append(ChatMessage(role="user", content=user))
    messages = _append_reference_copywriting_user_message(messages, reference_copywriting)
    text = await _call_llm_text(messages, cancel_event=cancel_event)
    lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
    if len(lines) < num_sections:
        chunks_per = max(1, len(subs_text.split("\n")) // num_sections)
        all_lines = subs_text.split("\n")
        lines = []
        for i in range(num_sections):
            start = i * chunks_per
            end = min((i + 1) * chunks_per, len(all_lines))
            lines.append(f"段落{i + 1}：概述字幕第{start + 1}-{end}行对应剧情")
    return lines[:num_sections]


async def _generate_section(
    section_idx: int,
    total_sections: int,
    section_outline: str,
    drama_name: str,
    subs_text: str,
    template_key: str,
    default_key: str,
    script_language: Optional[str],
    per_section_chars: int,
    *,
    film_context: Optional[str] = None,
    reference_copywriting: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> str:
    """根据大纲中某一段的描述，生成对应段落的文案。"""
    messages = _build_template_messages(template_key, default_key, drama_name)

    position_hints = []
    if section_idx == 0:
        position_hints.append(
            '这是文案的开头段，需要有引人入胜的开场；不要出现结尾语（如"感谢观看"、总结收束等），直接展开剧情。'
        )
    elif section_idx == total_sections - 1:
        position_hints.append(
            '这是文案的结尾段，需要有总结或悬念收束；不要出现开头语（如"大家好"、重新引入等），直接承接上段收尾。'
        )
    else:
        position_hints.append(
            '这是文案的中间段，不要出现开头语（如"大家好"等）和结尾语（如"感谢观看"等），'
            "直接承接上段继续讲述剧情。"
        )

    unit = "words" if _is_english(script_language) else "字"
    position_hints.append(f"本段需要输出约{per_section_chars}{unit}的文案。")
    position_hints.append(f"本段大纲要求：{section_outline}")

    messages.insert(0, ChatMessage(
        role="system",
        content="\n".join(position_hints),
    ))

    messages = _add_language_and_count_messages(messages, script_language, per_section_chars)
    messages = _append_film_context_user_message(messages, film_context)
    messages = _append_subtitles_context_message(messages, subs_text)
    messages = _append_reference_copywriting_user_message(messages, reference_copywriting)
    text = await _call_llm_text(messages, cancel_event=cancel_event)
    text = _remove_leading_quoted_subtitle_lines(text)
    logger.info(f"分段文案 {section_idx + 1}/{total_sections} 生成完成, 字数: {len(text)}")
    return text


# ─── 主入口 ──────────────────────────────────────────────

async def generate_copywriting_from_subtitles(
    subtitle_content: str,
    drama_name: str,
    project_id: Optional[str] = None,
    script_language: Optional[str] = None,
    script_length: Optional[str] = None,
    copywriting_word_count: Optional[int] = None,
    film_context: Optional[str] = None,
    reference_copywriting: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> str:
    """
    使用提示词模板系统生成纯文本解说文案。
    如果目标字数超过 SINGLE_CALL_MAX_CHARS，自动分段：大纲→分段→合并。
    """
    subtitles = _parse_srt_subtitles(subtitle_content)
    if not subtitles:
        return ""

    subs_text_lines = []
    for s in subtitles:
        ts = _format_timestamp_range(float(s["start"]), float(s["end"]))
        subs_text_lines.append(f"[{ts}] {s['text']}")
    subs_text = "\n".join(subs_text_lines)

    target_chars = _estimate_target_word_count(script_length, script_language, copywriting_word_count)

    template_key = _resolve_template_key(project_id, script_language)
    default_key = _default_prompt_key_for_project(project_id)

    need_segmented = target_chars is not None and target_chars > SINGLE_CALL_MAX_CHARS

    if need_segmented:
        return await _generate_segmented(
            target_chars=target_chars,
            drama_name=drama_name,
            subs_text=subs_text,
            template_key=template_key,
            default_key=default_key,
            script_language=script_language,
            film_context=film_context,
            reference_copywriting=reference_copywriting,
            cancel_event=cancel_event,
        )

    return await _generate_single(
        target_chars=target_chars,
        drama_name=drama_name,
        subs_text=subs_text,
        template_key=template_key,
        default_key=default_key,
        script_language=script_language,
        film_context=film_context,
        reference_copywriting=reference_copywriting,
        cancel_event=cancel_event,
    )


async def generate_copywriting_from_scenes(
    scenes_data: Dict[str, Any],
    drama_name: str,
    project_id: Optional[str] = None,
    script_language: Optional[str] = None,
    script_length: Optional[str] = None,
    copywriting_word_count: Optional[int] = None,
    film_context: Optional[str] = None,
    reference_copywriting: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> str:
    scenes_raw = scenes_data.get("scenes") if isinstance(scenes_data, dict) else None
    if not isinstance(scenes_raw, list) or not scenes_raw:
        return ""

    scene_items = scenes_to_timeline_items(scenes_raw)
    if not scene_items:
        return ""

    subs_text_lines = []
    for item in scene_items:
        try:
            start_s = float(item.get("start") or 0.0)
            end_s = float(item.get("end") or start_s)
        except Exception:
            continue
        ts = _format_timestamp_range(start_s, end_s)
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        subs_text_lines.append(f"[{ts}] {text}")
    subs_text = "\n".join(subs_text_lines)

    target_chars = _estimate_target_word_count(script_length, script_language, copywriting_word_count)

    template_key = _resolve_template_key(project_id, script_language)
    default_key = _default_prompt_key_for_project(project_id)

    need_segmented = target_chars is not None and target_chars > SINGLE_CALL_MAX_CHARS

    if need_segmented:
        return await _generate_segmented(
            target_chars=target_chars,
            drama_name=drama_name,
            subs_text=subs_text,
            template_key=template_key,
            default_key=default_key,
            script_language=script_language,
            film_context=film_context,
            reference_copywriting=reference_copywriting,
            cancel_event=cancel_event,
        )

    return await _generate_single(
        target_chars=target_chars,
        drama_name=drama_name,
        subs_text=subs_text,
        template_key=template_key,
        default_key=default_key,
        script_language=script_language,
        film_context=film_context,
        reference_copywriting=reference_copywriting,
        cancel_event=cancel_event,
    )


async def _generate_single(
    target_chars: Optional[int],
    drama_name: str,
    subs_text: str,
    template_key: str,
    default_key: str,
    script_language: Optional[str],
    *,
    film_context: Optional[str] = None,
    reference_copywriting: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> str:
    messages = _build_template_messages(template_key, default_key, drama_name)
    messages = _add_language_and_count_messages(messages, script_language, target_chars)
    messages = _append_film_context_user_message(messages, film_context)
    messages = _append_subtitles_context_message(messages, subs_text)
    messages = _append_reference_copywriting_user_message(messages, reference_copywriting)
    text = await _call_llm_text(messages, cancel_event=cancel_event)
    text = _remove_leading_quoted_subtitle_lines(text)
    logger.info(f"解说文案生成完成 (单次), 字数: {len(text)}")
    return text


async def _generate_segmented(
    target_chars: int,
    drama_name: str,
    subs_text: str,
    template_key: str,
    default_key: str,
    script_language: Optional[str],
    *,
    film_context: Optional[str] = None,
    reference_copywriting: Optional[str] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> str:
    per_call_max = 2500
    num_sections = max(2, math.ceil(target_chars / per_call_max))
    per_section_chars = math.ceil(target_chars / num_sections)

    logger.info(
        f"文案分段生成: 目标{target_chars}字, 分{num_sections}段, 每段约{per_section_chars}字"
    )

    outline_items = await _generate_outline(
        drama_name=drama_name,
        subs_text=subs_text,
        num_sections=num_sections,
        script_language=script_language,
        film_context=film_context,
        reference_copywriting=reference_copywriting,
        cancel_event=cancel_event,
    )
    logger.info(f"大纲生成完成, 共{len(outline_items)}段")

    sem = asyncio.Semaphore(3)
    section_texts: List[Optional[str]] = [None] * len(outline_items)

    async def gen_one(idx: int):
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()
        async with sem:
            section_texts[idx] = await _generate_section(
                section_idx=idx,
                total_sections=len(outline_items),
                section_outline=outline_items[idx],
                drama_name=drama_name,
                subs_text=subs_text,
                template_key=template_key,
                default_key=default_key,
                script_language=script_language,
                per_section_chars=per_section_chars,
                film_context=film_context,
                reference_copywriting=reference_copywriting,
                cancel_event=cancel_event,
            )

    tasks = [gen_one(i) for i in range(len(outline_items))]
    await asyncio.gather(*tasks)

    merged = "\n\n".join(t for t in section_texts if t)
    merged = _remove_leading_quoted_subtitle_lines(merged)
    logger.info(f"解说文案生成完成 (分段合并), 总字数: {len(merged)}")
    return merged
