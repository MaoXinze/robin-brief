"""摘要主笔 Agent：批量一句话摘要（严格基于原文，60 字内）。"""

from __future__ import annotations

import logging

from robin.agents._common import call_llm, chunked
from robin.agents.schemas import SummaryBatch
from robin.llm import LLMClient
from robin.models import EnrichedArticle
from robin.utils import truncate

logger = logging.getLogger(__name__)

CHUNK = 10


def make_summarize_agent(llm: LLMClient):
    def summarize_agent(state: dict) -> dict:
        articles: list[EnrichedArticle] = state["scored"]
        summarized: list[EnrichedArticle] = []
        for chunk in chunked(articles, CHUNK):
            payload = {"items": [
                {"id": a.id, "title": a.title, "content": (a.content or a.title)[:800]}
                for a in chunk
            ]}
            batch = None
            try:
                batch = call_llm(llm, "summarizer", SummaryBatch, "summarizer", payload=payload)
            except Exception as e:
                logger.warning("[摘要] 批次失败，退回标题截断: %s", e)
            by_id = {it.id: it for it in (batch.items if batch else [])}
            for a in chunk:
                summary = by_id[a.id].summary if a.id in by_id else truncate(a.title, 60)
                summarized.append(a.model_copy(update={"summary": summary}))
        logger.info("[摘要] %s 条完成", len(summarized))
        return {"summarized": summarized}

    return summarize_agent
