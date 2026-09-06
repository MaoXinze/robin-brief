"""评分编辑 Agent：规则引擎打分（可解释、零成本）+ LLM 校准（±1 星 + 理由）。

规则引擎：
  rule_score = 0.55×事件类型权重 + 0.30×公司权重(取最高) + 0.10×时效 + 热度加成(≤0.5)
映射到 1~5 星。LLM 只做校准与写理由 —— 评分理由随日报展示（可信度优先）。
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from robin.agents._common import call_llm, chunked
from robin.agents.schemas import ScoreBatch
from robin.config import Settings
from robin.llm import LLMClient
from robin.models import CATEGORY_LABELS, EnrichedArticle
from robin.utils import utcnow

logger = logging.getLogger(__name__)

CHUNK = 25

EVENT_WEIGHTS = {
    "model_release": 4.5,
    "funding_ma": 4.5,
    "policy": 4.0,
    "product": 3.5,
    "open_source": 3.0,
    "research": 2.5,
    "other": 2.0,
}

COMPANY_WEIGHTS = {
    "OpenAI": 5.0, "Anthropic": 5.0, "NVIDIA": 5.0, "Google": 4.5, "DeepSeek": 4.5,
    "Meta": 4.0, "Microsoft": 4.0, "月之暗面": 4.0, "智谱": 4.0, "阿里": 4.0,
    "腾讯": 4.0, "字节跳动": 4.0, "xAI": 4.0, "百度": 3.5, "Mistral": 3.5, "Manus": 3.5,
}


def recency_factor(published_at: datetime | None, now: datetime | None = None) -> float:
    now = now or utcnow()
    if published_at is None:
        return 0.7
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    hours = max(0.0, (now - published_at).total_seconds() / 3600)
    if hours <= 6:
        return 1.0
    if hours <= 12:
        return 0.9
    if hours <= 24:
        return 0.8
    if hours <= 48:
        return 0.65
    return 0.5


def rule_score(a: EnrichedArticle, now: datetime | None = None) -> int:
    event = EVENT_WEIGHTS.get(a.category.value if hasattr(a.category, "value") else str(a.category), 2.0)
    company = max((COMPANY_WEIGHTS.get(c, 2.5) for c in a.companies), default=2.5)
    score = 0.55 * event + 0.30 * company + 0.10 * recency_factor(a.published_at, now)
    # 社区热度加成设低上限：热度是信号，不应盖过事件本身的重要性
    if a.points:
        score += min(0.25, math.log10(a.points + 1) * 0.12)
    return max(1, min(5, round(score)))


def make_score_agent(llm: LLMClient, settings: Settings):
    def score_agent(state: dict) -> dict:
        articles: list[EnrichedArticle] = state["classified"]
        scored: list[EnrichedArticle] = []
        for chunk in chunked(articles, CHUNK):
            rule_map = {a.id: rule_score(a) for a in chunk}
            payload = {"items": [
                {"id": a.id, "title": a.title, "category": str(a.category.value),
                 "companies": a.companies, "rule_score": rule_map[a.id], "points": a.points}
                for a in chunk
            ]}
            batch = None
            if articles:
                try:
                    batch = call_llm(llm, "scorer", ScoreBatch, "scorer", payload=payload)
                except Exception as e:
                    logger.warning("[评分] LLM 校准失败，退回规则分: %s", e)
            by_id = {it.id: it for it in (batch.items if batch else [])}
            for a in chunk:
                it = by_id.get(a.id)
                importance = it.importance if it else rule_map[a.id]
                reason = it.reason if it else f"规则引擎评分：{CATEGORY_LABELS[str(a.category.value)]}"
                scored.append(a.model_copy(update={"importance": int(importance), "score_reason": reason}))
        logger.info("[评分] %s 条完成", len(scored))
        return {"scored": scored}

    return score_agent
