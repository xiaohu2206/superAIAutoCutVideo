"""
解说文案生成器 —— 使用提示词模板（含用户自定义）生成纯文本解说文案。
支持大字数分段生成：大纲→分段→合并。
"""

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional

from modules.ai import ChatMessage
from modules.prompts.prompt_manager import prompt_manager
from services.ai_service import ai_service

from .constants import MAX_SUBTITLE_CHARS_PER_CALL
from .prompt_resolver import _default_prompt_key_for_project, _resolve_prompt_key
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
    return key


def _build_template_messages(
    key: str,
    default_key: str,
    drama_name: str,
    subs_text: str,
) -> List[ChatMessage]:
    variables = {
        "drama_name": drama_name,
        "plot_analysis": "",
        "subtitle_content": subs_text,
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
        ),
    ))
    return msgs


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


async def _call_llm_text(messages: List[ChatMessage], max_retries: int = 3) -> str:
    merged = _merge_system_messages(messages)
    for attempt in range(max_retries + 1):
        try:
            resp = await ai_service.send_chat(merged)
            return _strip_code_fences(str(resp.content or "").strip())
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
) -> List[str]:
    """让模型生成一个分段大纲，返回各段的标题/摘要列表。"""
    lang_hint = "English" if _is_english(script_language) else "中文"
    system = (
        f"你是一位专业的解说文案策划。请根据字幕内容，为《{drama_name}》的解说文案生成{num_sections}段大纲。"
        f"每段大纲用一行描述该段应该讲述的剧情内容和时间范围（如果能判断的话）。"
        f"只输出大纲列表，每行一段，格式为「段落N：内容摘要」，不要输出其他文字。"
        f"必须使用{lang_hint}输出。"
    )
    user = (
        f"字幕内容：\n{subs_text}\n\n"
        f"请生成{num_sections}段大纲。"
    )
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]
    text = await _call_llm_text(messages)
    lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
    if len(lines) < num_sections:
        chunks_per = max(1, len(subs_text.split("\n")) // num_sections)
        all_lines = subs_text.split("\n")
        lines = []
        for i in range(num_sections):
            start = i * chunks_per
            end = min((i + 1) * chunks_per, len(all_lines))
            snippet = " ".join(all_lines[start:end])[:200]
            lines.append(f"段落{i + 1}：{snippet}")
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
) -> str:
    """根据大纲中某一段的描述，生成对应段落的文案。"""
    messages = _build_template_messages(template_key, default_key, drama_name, subs_text)

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
    text = await _call_llm_text(messages)
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
    if len(subs_text) > MAX_SUBTITLE_CHARS_PER_CALL * 3:
        subs_text = subs_text[: MAX_SUBTITLE_CHARS_PER_CALL * 3]

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
        )

    return await _generate_single(
        target_chars=target_chars,
        drama_name=drama_name,
        subs_text=subs_text,
        template_key=template_key,
        default_key=default_key,
        script_language=script_language,
    )


async def _generate_single(
    target_chars: Optional[int],
    drama_name: str,
    subs_text: str,
    template_key: str,
    default_key: str,
    script_language: Optional[str],
) -> str:
    messages = _build_template_messages(template_key, default_key, drama_name, subs_text)
    messages = _add_language_and_count_messages(messages, script_language, target_chars)
    text = await _call_llm_text(messages)
    logger.info(f"解说文案生成完成 (单次), 字数: {len(text)}")
    return text


async def _generate_segmented(
    target_chars: int,
    drama_name: str,
    subs_text: str,
    template_key: str,
    default_key: str,
    script_language: Optional[str],
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
    )
    logger.info(f"大纲生成完成, 共{len(outline_items)}段")

    sem = asyncio.Semaphore(3)
    section_texts: List[Optional[str]] = [None] * len(outline_items)

    async def gen_one(idx: int):
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
            )

    tasks = [gen_one(i) for i in range(len(outline_items))]
    await asyncio.gather(*tasks)

    merged = "\n\n".join(t for t in section_texts if t)
    logger.info(f"解说文案生成完成 (分段合并), 总字数: {len(merged)}")
    return merged
