"""深度评论员 Agent：对 1~2 个最大事件写「背景 + 影响」深度解读。"""

from __future__ import annotations

import logging

from robin.agents._common import call_llm
from robin.agents.schemas import AnalysisOut
from robin.config import Settings
from robin.llm import LLMClient
from robin.models import AnalysisView, EnrichedArticle

logger = logging.getLogger(__name__)

MAX_ANALYSIS = 2
MIN_IMPORTANCE = 4


def make_analyze_agent(llm: LLMClient, settings: Settings):
    def analyze_agent(state: dict) -> dict:
        articles: list[EnrichedArticle] = state["summarized"]
        picks = [a for a in articles if a.importance >= MIN_IMPORTANCE]
        picks.sort(key=lambda a: -a.importance)
        # 类别去重：避免两条解读都是同一事件的不同报道
        selected: list[EnrichedArticle] = []
        for a in picks:
            if any(a.id == s.id for s in selected):
                continue
            selected.append(a)
            if len(selected) >= MAX_ANALYSIS:
                break
        analysis: list[AnalysisView] = []
        for a in selected:
            payload = {"item": {"title": a.title, "summary": a.summary, "category": str(a.category.value),
                                "companies": a.companies, "url": a.url}}
            try:
                out: AnalysisOut = call_llm(llm, "analyst", AnalysisOut, "analyst", payload=payload)
                analysis.append(AnalysisView(title=a.title, url=a.url, source_name=a.source_name,
                                             background=out.background, impact=out.impact))
            except Exception as e:
                logger.warning("[解读] %s 失败，跳过: %s", a.id, e)
        logger.info("[解读] 完成 %s 篇", len(analysis))
        return {"analysis": analysis, "stage_done": {"analyst": True}}

    return analyze_agent
