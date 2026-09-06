"""分类编辑 Agent：LLM 结构化输出打标（类别 + 公司 + 是否 AI 相关）。"""

from __future__ import annotations

import logging

from robin.agents._common import call_llm, chunked
from robin.agents.schemas import ClassificationBatch
from robin.llm import LLMClient
from robin.models import Article, Category, EnrichedArticle

logger = logging.getLogger(__name__)

CHUNK = 20


def make_classify_agent(llm: LLMClient):
    def classify_agent(state: dict) -> dict:
        articles: list[Article] = state["deduped"]
        enriched: list[EnrichedArticle] = []
        dropped = 0
        for chunk in chunked(articles, CHUNK):
            payload = {"items": [{"id": a.id, "title": a.title, "content": (a.content or "")[:500]} for a in chunk]}
            try:
                batch = call_llm(llm, "classifier", ClassificationBatch, "classifier", payload=payload)
            except Exception as e:
                # 分类失败整块降级为 other（不中断流水线）
                logger.warning("[分类] 批次失败，降级为 other: %s", e)
                batch = None
            by_id = {it.id: it for it in (batch.items if batch else [])}
            for a in chunk:
                it = by_id.get(a.id)
                if it is not None and not it.is_ai:
                    dropped += 1
                    continue
                enriched.append(
                    EnrichedArticle(**a.model_dump(),
                                    category=(it.category if it else Category.OTHER),
                                    companies=(it.companies if it else []))
                )
        logger.info("[分类] %s 条完成，非 AI 条目剔除 %s", len(enriched), dropped)
        return {"classified": enriched}

    return classify_agent
