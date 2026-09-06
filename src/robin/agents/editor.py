"""头条编辑 Agent：选 3~5 条头条 + 「为什么重要」点评 + 今日微语。

可信度优先：编辑不改标题、不改摘要，只做「选择 + 点评」；
点评与微语通过 schema 单独字段返回，渲染时明确署名"编辑点评"。
"""

from __future__ import annotations

import logging

from robin.agents._common import call_llm
from robin.agents.schemas import EditorialPlan
from robin.config import Settings
from robin.llm import LLMClient
from robin.models import CATEGORY_LABELS, EnrichedArticle, HeadlineView

logger = logging.getLogger(__name__)


def make_edit_agent(llm: LLMClient, settings: Settings):
    def edit_agent(state: dict) -> dict:
        articles: list[EnrichedArticle] = state["summarized"]
        # 编辑方针：headline_eligible=False 的来源（如 GitHub Trending）只进快讯
        ineligible = set()
        for s in state.get("sources", []):
            sid = s.get("id") if isinstance(s, dict) else getattr(s, "id", None)
            eligible = s.get("headline_eligible", True) if isinstance(s, dict) else getattr(s, "headline_eligible", True)
            if sid and not eligible:
                ineligible.add(sid)
        ranked = sorted(
            [a for a in articles if a.source_id not in ineligible],
            key=lambda a: (-a.importance, -(a.points or 0)),
        )
        candidates = [
            {"id": a.id, "title": a.title, "summary": a.summary, "category": str(a.category.value),
             "companies": a.companies, "importance": a.importance, "points": a.points}
            for a in ranked[:25]
        ]
        plan = None
        try:
            plan = call_llm(llm, "editor", EditorialPlan, "editor",
                            payload={"candidates": candidates, "max_headlines": 5})
        except Exception as e:
            logger.warning("[头条] LLM 规划失败，退回评分直选: %s", e)

        by_id = {a.id: a for a in ranked}
        headlines: list[HeadlineView] = []

        def _clean_summary(a: EnrichedArticle) -> str:
            """摘要与标题同文（降级兜底产物）时不展示，避免观感重复。"""
            s = (a.summary or "").strip()
            return "" if not s or s == a.title.strip() else s

        if plan:
            for pick in plan.headlines:
                a = by_id.get(pick.id)
                if a is None:
                    continue
                headlines.append(HeadlineView(
                    title=a.title, summary=_clean_summary(a), comment=pick.comment,
                    url=a.url, source_name=a.source_name, category=a.category,
                    companies=a.companies, importance=a.importance, score_reason=a.score_reason,
                ))
        # 降级保证：头条不足 3 条时按评分直选补齐（LLM 结果优先）
        if len(headlines) < 3:
            chosen_ids = {h.title for h in headlines}
            for a in ranked:
                if a.title in chosen_ids:
                    continue
                headlines.append(HeadlineView(
                    title=a.title, summary=_clean_summary(a),
                    comment=f"{CATEGORY_LABELS[str(a.category.value)]}条线值得关注的事件。",
                    url=a.url, source_name=a.source_name, category=a.category,
                    companies=a.companies, importance=a.importance, score_reason=a.score_reason,
                ))
                if len(headlines) >= 5:
                    break
        epigraph = plan.epigraph if plan and plan.epigraph else "信息过载的时代，挑选本身即是价值。"
        logger.info("[头条] 选出 %s 条", len(headlines))
        return {"headlines": headlines[:5], "epigraph": epigraph, "stage_done": {"editor": True}}

    return edit_agent
