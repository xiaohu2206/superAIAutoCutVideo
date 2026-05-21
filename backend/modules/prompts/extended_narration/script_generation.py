#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class ExtendedNarrationScriptGenerationPrompt(TextPrompt):
    def __init__(
        self,
        *,
        category: str,
        work_kind: str,
        language: str = "zh",
        name: str = "script_generation",
    ) -> None:
        metadata = PromptMetadata(
            name=name,
            category=category,
            version="v1.0",
            description=f"{work_kind}解说：按素材事实生成适合短视频剪辑的口播文案。",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.TEXT,
            tags=[work_kind, "解说文案", "口播", "剪辑可用"],
            parameters=["drama_name", "plot_analysis", "subtitle_content"],
        )
        super().__init__(metadata)
        self._work_kind = work_kind
        self._language = language
        self._system_prompt = (
            f"你是一位专业的{work_kind}解说编剧，擅长把视频素材整理成信息清晰、节奏顺畅、"
            "适合短视频剪辑的口播文案。必须严格基于提供的字幕、镜头与补充信息，不编造素材外事实。"
            "只输出解说文案正文，不要输出 JSON、代码块、格式标记或规则说明。\n\n"
        )

    def get_template(self) -> str:
        lang_rule = (
            "Write the narration copywriting in English."
            if str(self._language).lower().startswith("en")
            else "使用中文输出解说文案。"
        )
        return f"""# {self._work_kind}解说文案创作任务

## 任务目标
为《${{drama_name}}》生成一篇适合短视频剪辑与配音的{self._work_kind}解说文案。

## 写作要求
- 严格依据同轮对话中提供的字幕、镜头信息与补充资料，不虚构未出现的事实。
- 按素材时间线或信息逻辑推进，先抓住最有吸引力的信息点，再逐步展开。
- 每段单独成行，便于后续剪辑与配音。
- 语言要口播化、清晰、有节奏；避免百科式堆资料，也不要写成空泛评论。
- 关键处要写出画面、人物、动作、冲突、反转、知识点或情绪变化，方便剪辑师反向找画面。
- 如果素材偏纪实、赛事、节目或知识讲解，应尊重原内容类型，不要硬套电影或短剧爽文结构。
- 只输出纯文本解说文案正文，不要输出 JSON、Markdown 标题、代码块或说明。
- {lang_rule}

## 素材信息

### 补充信息
<plot>
${{plot_analysis}}
</plot>

### 原始字幕（含精确时间戳）
<subtitles>
完整带时间戳的字幕在同轮对话中「补充剧情参考字幕」用户消息内提供，请严格依据该消息中的事实理解内容并创作。
${{subtitle_content}}
</subtitles>
"""
