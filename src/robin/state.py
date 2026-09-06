"""LangGraph 共享状态（blackboard 模式）。

- `articles` / `source_errors` / `source_stats` 用 reducer 合并：
  Send 并行抓取的多路结果自动汇聚
- 其余字段为顺序节点的产物，直接覆盖
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from robin.config import SourceCfg
from robin.models import (
    AnalysisView,
    Article,
    BriefDocument,
    EnrichedArticle,
    HeadlineView,
    QuickNewsView,
)


def merge_dict(a: dict | None, b: dict | None) -> dict:
    """dict 合并 reducer（后写覆盖同键）。"""
    return {**(a or {}), **(b or {})}


class BriefState(TypedDict, total=False):
    # ---- 运行上下文 ----
    run_date: str
    sources: list[SourceCfg]
    now: str                      # ISO 时间（测试可注入固定值）
    window_hours: int
    relaxed_window_hours: int
    relaxed: bool                 # 宽松重采标志
    retry_count: int
    push: bool                    # 是否推送飞书
    mock: bool                    # mock 演示模式（页脚提示 + 不推送）
    history_norms: list[str]      # 近 3 天已报道标题归一（跨天去重）
    yesterday: dict | None        # 昨日回顾 {date,title,url}

    # ---- 采集（map-reduce）----
    articles: Annotated[list[Article], operator.add]
    source_errors: Annotated[list[dict], operator.add]
    source_stats: Annotated[dict, merge_dict]

    # ---- 提纯 ----
    deduped: list[Article]
    dedup_stats: dict

    # ---- 智能层 ----
    classified: list[EnrichedArticle]
    scored: list[EnrichedArticle]
    summarized: list[EnrichedArticle]

    # ---- 编辑层（并行三节点）----
    headlines: list[HeadlineView]
    quick_news: list[QuickNewsView]
    analysis: list[AnalysisView]
    epigraph: str

    # ---- 出版 ----
    brief: BriefDocument
    published: dict               # {html, md}
    stage_done: Annotated[dict, merge_dict]   # 编辑层完成标志（publish 幂等守卫）
    agent_stats: Annotated[dict, merge_dict]
