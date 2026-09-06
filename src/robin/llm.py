"""LLM 客户端层：DeepSeekClient（OpenAI 兼容）与 MockLLMClient（离线确定性）。

统一接口 `structured(system, user, schema, agent)`：
- 输入：system/user 提示词 + 目标 pydantic Schema
- 输出：校验通过的结构化实例；JSON 解析/校验失败自动重试
- 每个 Agent 的调用都带 agent 名，便于用量统计与 mock 路由

MockLLMClient 是离线开发与测试的关键：不联网、确定性输出，
按 agent 名路由到基于规则的"伪智能"，保证 mock 全链路可出报。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from robin.config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class UsageTracker:
    """累计 token 用量（run_report 的 llm_usage 数据源）。"""

    def __init__(self) -> None:
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    def as_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


class LLMClient(Protocol):
    usage: UsageTracker

    def structured(
        self, system: str, user: str, schema: type[T], agent: str
    ) -> T: ...


class DeepSeekClient:
    """任意 OpenAI 兼容端点（默认 DeepSeek）。

    重试策略：网络层交给 openai SDK（自带重试），
    JSON 解析/Schema 校验失败时带错误回示重问，最多 settings.llm_max_retries 次。
    """

    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        self._settings = settings
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=60.0,
            max_retries=1,
        )
        self.usage = UsageTracker()

    def structured(self, system: str, user: str, schema: type[T], agent: str) -> T:
        last_err: Exception | None = None
        for attempt in range(1, self._settings.llm_max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self._settings.llm_model,
                    temperature=self._settings.llm_temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user if attempt == 1 else _with_feedback(user, last_err)},
                    ],
                )
            except Exception as e:  # 网络/限流：指数退避后重试
                last_err = e
                logger.warning("[llm:%s] 请求失败(第%s次): %s", agent, attempt, e)
                time.sleep(min(2**attempt, 8))
                continue
            if resp.usage:
                self.usage.add(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
            else:
                self.usage.add()
            content = resp.choices[0].message.content or ""
            try:
                return schema.model_validate_json(content)
            except ValidationError as e:
                last_err = e
                logger.warning("[llm:%s] 输出校验失败(第%s次): %s", agent, attempt, e)
        raise LLMError(f"agent={agent} 结构化输出在重试后仍失败: {last_err}")


def _with_feedback(user: str, err: Exception | None) -> str:
    if err is None:
        return user
    return f"{user}\n\n注意：你上一次的输出未通过校验（{err}），请严格按 schema 输出合法 JSON。"


class MockLLMClient:
    """离线确定性客户端：按 agent 名路由到规则式实现。

    约定：各 Agent 的 user 载荷是 ensure_ascii=False 的 JSON 字符串，
    mock 直接解析后走关键词规则。用量按字符数估算，保证 run_report 结构一致。
    """

    def __init__(self) -> None:
        self.usage = UsageTracker()

    def structured(self, system: str, user: str, schema: type[T], agent: str) -> T:
        self.usage.add(len((system + user).encode()) // 3, len(agent) * 8)
        # 延迟导入避免循环依赖
        from robin.agents.mock_impl import MOCK_HANDLERS

        handler = MOCK_HANDLERS.get(agent)
        if handler is None:
            raise LLMError(f"MockLLMClient 未注册 agent={agent}")
        payload = _extract_input(user)
        result = handler(payload)
        return schema.model_validate(result)


def _extract_input(user: str) -> dict:
    """提取 <input>...</input> 中的 JSON 载荷；无标签时尝试整段解析。"""
    import re as _re

    m = _re.search(r"<input>\s*(\{.*\})\s*</input>", user, _re.S)
    text = m.group(1) if m else user
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
