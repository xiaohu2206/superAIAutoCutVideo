#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


_TYPE_GUIDANCE = {
    "tv_drama_narration": {
        "positioning": "电视剧/长剧集解说，重点是人物关系、阶段性冲突、情绪递进和集与集之间的悬念衔接。",
        "opening": "开头优先抛出本段最强冲突、人物误会、关系翻脸、身份反差或命运转折，不要从演员表或世界观慢慢铺。",
        "structure": "按「本集/本段核心矛盾 -> 关键人物关系 -> 冲突升级 -> 局势反转或情绪落点 -> 下集/后续钩子」推进。",
        "voice": "口播要像一个懂剧、会抓关系线的解说博主，既能讲清剧情，也能点出角色为什么这样选择。",
        "avoid": "不要把长剧写成短剧爽文合集；不要跳过人物动机；不要把未出现的后续剧情提前当事实讲。",
    },
    "anime_narration": {
        "positioning": "动漫解说，重点是世界观设定、角色能力/阵营关系、名场面、情绪爆点和战斗/事件推进，而不是简单复述台词。",
        "opening": "开头优先抛出最强名场面、角色危机、能力反差、身份揭露、战斗逆转或世界观悬念，不要先铺一长段设定。",
        "structure": "按「名场面钩子 -> 必要设定最少交代 -> 角色目标/冲突升级 -> 能力或关系反转 -> 结尾悬念/下一集看点」推进。",
        "voice": "语气要有二次元内容的热血感、代入感和梗感，但必须讲清画面动作、角色动机和设定规则。",
        "avoid": "不要把动漫写成真人短剧；不要乱编设定、战力、角色关系或后续剧情；不要用空泛燃点替代具体画面与动作。",
    },
    "variety_narration": {
        "positioning": "综艺解说，重点是节目任务、嘉宾互动、笑点反差、名场面和现场气氛，而不是硬讲剧情。",
        "opening": "开头优先抛出最强名场面、嘉宾翻车、反差表现、爆笑冲突、意外胜负或现场尴尬点。",
        "structure": "按「名场面钩子 -> 规则/任务最少交代 -> 嘉宾互动升级 -> 笑点或冲突兑现 -> 情绪收束/下个看点」推进。",
        "voice": "语气要轻快、有梗、有现场感，像在带观众复盘一期节目里最值得看的高光。",
        "avoid": "不要写成影视剧情解说；不要过度上价值；不要凭空编造嘉宾心理或台本内幕；不要用过多抽象形容替代具体互动。",
    },
    "documentary_narration": {
        "positioning": "纪录片解说，重点是事实信息、人物/事件脉络、现实质感、观察视角和主题表达。",
        "opening": "开头优先抛出反常识事实、强画面、关键问题、命运节点或事件结果，引导观众追问原因。",
        "structure": "按「核心问题 -> 背景信息 -> 关键证据/现场细节 -> 事件推进 -> 观点或情绪余味」推进。",
        "voice": "语言要克制、有质感、有信息密度，可以有观点，但必须建立在素材事实上。",
        "avoid": "不要写成营销号猎奇腔；不要为刺激感夸大事实；不要把纪录片写成虚构剧情。",
    },
    "sports_narration": {
        "positioning": "体育解说，重点是比赛进程、关键回合、比分/局势变化、运动员表现、战术选择和情绪燃点。",
        "opening": "开头优先抛出逆转、绝杀、失误、爆发、争议判罚、关键对位或比赛命运转折。",
        "structure": "按「关键悬念 -> 局势背景 -> 回合/阶段推进 -> 决定性动作 -> 结果与情绪释放」推进。",
        "voice": "口播要有临场感和节奏，关键动作写得准，情绪能燃起来，但信息不能乱。",
        "avoid": "不要只喊热血口号；不要忽略比分、时间、对位和动作细节；不要虚构战术意图或赛后评价。",
    },
    "general_narration": {
        "positioning": "通用内容解说，重点是把素材里的事件、信息或过程讲清楚，并提炼最适合短视频传播的看点。",
        "opening": "开头优先抛出最反常、最有用、最有冲突或最能引发好奇的信息点。",
        "structure": "按「核心看点 -> 必要背景 -> 过程拆解 -> 关键变化 -> 结论/行动/余味」推进。",
        "voice": "表达要清楚、直接、有节奏，少说空话，多给具体事实和可感知细节。",
        "avoid": "不要套影视剧情话术；不要为了热闹编造因果；不要让段落变成资料堆砌。",
    },
}


def _guidance_for(category: str, label: str, source_label: str) -> dict:
    return _TYPE_GUIDANCE.get(
        category,
        {
            "positioning": f"{label}解说，重点是基于素材事实提炼看点、讲清脉络，并形成可直接口播与剪辑的文案。",
            "opening": "开头优先抛出最强冲突、最大反差、最关键问题或最有画面感的结果。",
            "structure": "按「强钩子 -> 必要背景 -> 过程推进 -> 关键变化 -> 结尾钩子或余味」推进。",
            "voice": f"语气要符合{label}内容气质，既有口播节奏，也要能自然衔接{source_label}画面。",
            "avoid": "不要写成资料摘要；不要虚构素材中没有的信息；不要用空洞情绪替代具体细节。",
        },
    )


class GenericNarrationScriptGenerationPrompt(TextPrompt):
    """Generic default prompt for narration categories backed by optional markdown."""

    def __init__(self, *, category: str, label: str, source_label: str = "原片", name: str = "script_generation") -> None:
        metadata = PromptMetadata(
            name=name,
            category=category,
            version="v1.0",
            description=f"{label}默认解说文案生成提示词；可用本类型目录下的 markdown 覆盖。",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.TEXT,
            tags=[label, "解说文案", "默认模板"],
            parameters=["drama_name", "plot_analysis", "subtitle_content"],
        )
        super().__init__(metadata)
        self._label = label
        self._source_label = source_label
        self._system_prompt = (
            f"你是一位专业的{label}解说编剧，擅长基于素材事实创作口播式、可剪辑、能留住观众的解说文案。"
            "你会优先保证事实准确、信息清楚、节奏有推进，并让每段文案都能对应素材画面。"
            "只输出解说文案正文，不要输出 JSON、代码块、Markdown 标题、格式标记或规则说明。\n\n"
        )

    def get_template(self) -> str:
        base = Path(__file__).resolve().parents[1]
        override_path = base / self.metadata.category / "script_generation" / "script_generation.md"
        if override_path.exists() and override_path.is_file():
            text = override_path.read_text(encoding="utf-8")
            if text.strip():
                return text

        guidance = _guidance_for(self.metadata.category, self._label, self._source_label)
        return f"""# {self._label}《${{drama_name}}》解说文案创作任务

## 任务目标
基于补充信息、镜头理解和原始字幕，为《${{drama_name}}》创作一篇适合短视频口播与剪辑的{self._label}解说文案。

## 类型定位
{guidance["positioning"]}

## 开头策略
{guidance["opening"]}

前 3 秒必须先给观众一个继续看的理由，可以是结果预告、强反差、悬念问题、关键动作、名场面或危机节点。
不要先铺长背景，不要先解释一堆设定。

## 推荐结构
{guidance["structure"]}

每段只承担一个清晰功能：交代变化、推进事件、升级矛盾、释放笑点/燃点/信息点、或承接下一个看点。

## 语言风格
{guidance["voice"]}

- 使用适合短视频口播的自然表达，句子不要过长。
- 允许有判断、有情绪、有节奏，但判断必须来自素材事实。
- 多写具体动作、现场反应、人物关系、局势变化，少写空泛形容词。
- 关键节点可以写成能直接衔接{self._source_label}的触发句，例如一句话落下后切原声、画面或高光片段。

## 剪辑可用性
- 每段文案最好能反向找到对应画面、字幕、动作或现场信息。
- 不要连续复述字幕；要把字幕、画面和补充信息合并理解成顺畅口播。
- 重要转折前不要提前剧透干净，要给画面或原声留下释放空间。
- 信息密度优先于纯氛围；每 1-2 句都要让观众获得新信息或新情绪。

## 输出格式
- 只输出纯文本解说文案正文。
- 可先输出一行短标题，也可以直接进入正文。
- 正文按自然段换行，便于后续剪辑切分。
- 不输出 JSON、代码块、Markdown 标题、规则复述或解释说明。

## 禁止事项
{guidance["avoid"]}

- 严格依据素材事实，不虚构未出现的情节、人物关系、比赛数据、节目内幕或创作背景。
- 不要把所有类型都写成电影/短剧解说；必须贴合{self._label}内容气质。
- 不要为了制造爆点歪曲素材原意。

## 素材信息

### 补充信息
<plot>
${{plot_analysis}}
</plot>

### 原始字幕（含精确时间戳）
<subtitles>
完整带时间戳的字幕在同轮对话中「补充剧情参考字幕」用户消息内提供，请严格依据该消息中的事实理解剧情并创作。
${{subtitle_content}}
</subtitles>
"""


__all__ = ["GenericNarrationScriptGenerationPrompt"]
