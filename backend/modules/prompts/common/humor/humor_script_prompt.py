#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""幽默搞笑解说文案：正文来自 humor.md（含 __WORK_KIND__ / __SOURCE_LABEL__ 占位符，按注册时的 label 替换）。"""

from ...base import TextPrompt, PromptMetadata, ModelType, OutputFormat
from .humor_loader import load_humor_markdown

# 变量块与现有 script_generation 保持一致，供项目剧情与字幕注入
_MATERIAL_SUFFIX = """
--------------------------------
## 素材信息

### 作品名称
《${drama_name}》

### 补充信息（剧情概述）
<plot>
${plot_analysis}
</plot>

### 原始字幕（含精确时间戳）
<subtitles>
完整带时间戳的字幕在同轮对话中「补充剧情参考字幕」用户消息内提供，请严格依据该消息中的事实理解剧情并创作。
${subtitle_content}
</subtitles>

请基于以上规范与上述素材，完成解说文案创作。
"""


class HumorScriptGenerationPrompt(TextPrompt):
    """幽默搞笑风格；模板正文来自 humor.md，不内嵌副本。"""

    def __init__(self, category: str, label: str) -> None:
        metadata = PromptMetadata(
            name="幽默搞笑",
            category=category,
            version="v1.0",
            description="吐槽向、分段输出，在讲清剧情的同时制造笑点与反差，轻松好笑、适合剪辑切分。",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.TEXT,
            tags=[label, "解说文案", "幽默搞笑", "吐槽", "分段解说"],
            parameters=["drama_name", "plot_analysis", "subtitle_content"],
        )
        super().__init__(metadata)
        self._system_prompt = None
        self._label = label

    def get_template(self) -> str:
        body = load_humor_markdown()
        # 与 movie/short_drama 的 script_generation 用语对齐：电影用「原片」，短剧用「原剧」
        source_label = "原片" if self._label == "电影" else "原剧"
        body = body.replace("__WORK_KIND__", self._label).replace("__SOURCE_LABEL__", source_label)
        return body.rstrip() + "\n" + _MATERIAL_SUFFIX
