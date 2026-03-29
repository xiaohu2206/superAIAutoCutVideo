"""从 humor.md 读取幽默解说提示词正文；电影/短剧用语在 HumorScriptGenerationPrompt 中替换占位符。"""

from pathlib import Path


def humor_markdown_path() -> Path:
    return Path(__file__).resolve().parent / "humor.md"


def load_humor_markdown() -> str:
    p = humor_markdown_path()
    return p.read_text(encoding="utf-8")
