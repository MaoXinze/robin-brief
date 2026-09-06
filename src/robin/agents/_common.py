"""Agent 节点公共工具：LLM 调用封装与批量分块。"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from robin.llm import LLMClient
from robin.prompts import load_prompt

T = TypeVar("T", bound=BaseModel)

ROBIN_SYSTEM = (
    "你是「知更早报」编辑部的 AI 成员。严格遵守用户消息中的角色与规则，"
    "只输出符合要求的 JSON，不要输出任何解释性文字或 Markdown 代码块。"
)


def call_llm[T: BaseModel](
    llm: LLMClient,
    prompt_name: str,
    schema: type[T],
    agent: str,
    payload=None,
    **tokens: str,
) -> T:
    """组装 user 消息：提示词规则 + <input> 包裹的 JSON 载荷。

    载荷独立于规则文本并用固定标签包裹 —— MockLLMClient 依赖该约定提取输入。
    """
    rules = load_prompt(prompt_name, **tokens)
    user = rules if payload is None else f"{rules}\n\n<input>\n{to_json(payload)}\n</input>"
    return llm.structured(ROBIN_SYSTEM, user, schema, agent)


def to_json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
