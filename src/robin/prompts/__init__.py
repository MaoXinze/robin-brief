"""提示词加载器：prompts/*.txt 以 {{TOKEN}} 占位，替换后即为最终提示词。

用 token 替换而非 str.format，避免提示词中的 JSON 花括号转义问题。
"""

from __future__ import annotations

import re
from importlib import resources

_TOKEN_RE = re.compile(r"\{\{(\w+)\}\}")


def load_prompt(name: str, **tokens: str) -> str:
    """读取 prompts/<name>.txt 并替换 {{TOKEN}}；未提供的 token 替换为空串。"""
    text = resources.files("robin.prompts").joinpath(f"{name}.txt").read_text(encoding="utf-8")

    def _sub(m: re.Match) -> str:
        return tokens.get(m.group(1), "")

    return _TOKEN_RE.sub(_sub, text).strip()
