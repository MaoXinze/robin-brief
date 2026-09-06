"""快讯编辑 Agent：头条之外的条目 → 一句话快讯列表。

设计决策：快讯直接复用摘要主笔的产物（不重复调用 LLM），
排序按重要性，最多 15 条 —— 快讯的价值在「扫读效率」。
"""

from __future__ import annotations

import logging

from robin.models import EnrichedArticle, QuickNewsView

logger = logging.getLogger(__name__)

MAX_QUICK_NEWS = 15
MIN_IMPORTANCE = 2


def make_quicknews_agent(llm, settings):
    def quicknews_agent(state: dict) -> dict:
        articles: list[EnrichedArticle] = state["summarized"]
        headline_ids = {h.title for h in state.get("headlines", [])}
        ranked = sorted(
            [a for a in articles if a.importance >= MIN_IMPORTANCE and a.title not in headline_ids],
            key=lambda a: (-a.importance, -(a.points or 0)),
        )
        quick_news = [
            QuickNewsView(
                text=a.summary or a.title,
                url=a.url,
                source_name=a.source_name,
                category=a.category,
            )
            for a in ranked[:MAX_QUICK_NEWS]
        ]
        logger.info("[快讯] 生成 %s 条", len(quick_news))
        return {"quick_news": quick_news, "stage_done": {"quicknews": True}}

    return quicknews_agent
