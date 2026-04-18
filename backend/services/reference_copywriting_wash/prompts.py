from __future__ import annotations

from typing import List, Optional

from modules.ai import ChatMessage


def _is_english(language: Optional[str]) -> bool:
    if not language:
        return False
    lang = str(language).strip().lower()
    return lang in {"en", "en-us", "英文", "english"}


def build_wash_messages(
    *,
    drama_name: str,
    reference_chunk: str,
    subtitle_chunk: str,
    section_index: int,
    total_sections: int,
    script_language: Optional[str],
) -> List[ChatMessage]:
    lang = "English" if _is_english(script_language) else "中文"
    pos = f"第 {section_index + 1}/{total_sections} 段"
    system = (
        f"你是一位专业影视解说文案编辑，帮忙完成洗稿任务。剧名：{drama_name or '未命名'}。"
        f"当前处理{pos}。"
        f"参考稿来自他人解说视频整理，可能混有角色对白、带引号的字幕句；"
        f"请在尽量保持叙述顺序、事实信息与原稿语气风格一致的前提下，删除字幕式对白与引号台词痕迹，只保留解说叙述；"
        f"允许轻微润色（如替换个别形容词、调整语气衔接）。"
        f"必须使用{lang}输出。"
        "只输出本段洗稿后的连续纯文本正文，不要输出 JSON、代码块、标题编号或任何说明。"
    )
    sub = (subtitle_chunk or "").strip()
    sub_block = f"以下为该段对应的剧情参考字幕（纯文本、已去掉时间轴，顺序即剧情顺序），仅供核对事实，不要逐句照抄进正文：\n{sub}" if sub else "（本段无字幕参考，仅依据参考稿洗稿。）"
    user = (
        "【本段参考解说稿】\n"
        f"{reference_chunk.strip()}\n\n"
        f"{sub_block}"
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
