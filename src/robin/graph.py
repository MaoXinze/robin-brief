r"""LangGraph 图组装：知更编辑部的完整流水线拓扑。

        START
          │(条件边 + Send 动态 map)
    fetch_source ×N（并行，错误隔离）
          │
        dedup ──条数不足──► relax（宽松重采，回到 fan-out，仅一次）
          │条数充足
       classify（分类）
          │
        score（规则引擎 + LLM 校准评分）
          │
       summarize（摘要）
        /       \
   editor      analyst      ← 并行两节点
       │
   quicknews（依赖头条结果做排除）
        \       /
        publish（出版）
           │
         END
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from robin.agents import (
    dispatch_collect,
    make_analyze_agent,
    make_classify_agent,
    make_dedup_agent,
    make_edit_agent,
    make_fetch_source,
    make_publisher_node,
    make_quicknews_agent,
    make_score_agent,
    make_summarize_agent,
    relax_refetch,
)
from robin.config import Settings
from robin.state import BriefState
from robin.store.db import Database

logger = logging.getLogger(__name__)


def _timed(name: str, fn: Callable) -> Callable:
    """节点计时包装：耗时写入 agent_stats（run_report 数据源）。"""

    def wrapper(state: BriefState) -> dict:
        t0 = time.perf_counter()
        result = fn(state) or {}
        result = dict(result)
        stats = dict(result.get("agent_stats", {}))
        stats[name] = {"duration_s": round(time.perf_counter() - t0, 3)}
        result["agent_stats"] = stats
        return result

    return wrapper


def _route_after_dedup(settings: Settings) -> Callable:
    def route(state: BriefState) -> str:
        enough = len(state.get("deduped", [])) >= settings.min_articles
        already_relaxed = bool(state.get("relaxed", False))
        if not enough and not already_relaxed and state.get("retry_count", 0) == 0:
            logger.info("[路由] 去重后仅 %s 条，触发宽松重采", len(state.get("deduped", [])))
            return "relax"
        return "continue"

    return route


def build_graph(
    llm,
    settings: Settings,
    db: Database,
    checkpointer=None,
    client_factory=None,
) -> StateGraph:
    g = StateGraph(BriefState)

    # 采集层（条件边 + Send 动态 map 并行：router 返回 Send 列表）
    g.add_node("fetch_source", make_fetch_source(client_factory))
    g.add_node("relax", relax_refetch)

    # 提纯 + 智能层（工厂注入依赖）
    g.add_node("dedup", _timed("dedup", make_dedup_agent(llm, settings)))
    g.add_node("classify", _timed("classify", make_classify_agent(llm)))
    g.add_node("score", _timed("score", make_score_agent(llm, settings)))
    g.add_node("summarize", _timed("summarize", make_summarize_agent(llm)))

    # 编辑层（并行三节点）
    g.add_node("editor", _timed("editor", make_edit_agent(llm, settings)))
    g.add_node("analyst", _timed("analyst", make_analyze_agent(llm, settings)))
    g.add_node("quicknews", _timed("quicknews", make_quicknews_agent(llm, settings)))

    # 出版
    g.add_node("publish", _timed("publisher", make_publisher_node(settings, db)))

    # ---- 拓扑 ----
    g.add_conditional_edges(START, dispatch_collect)   # START -> fetch_source ×N
    g.add_conditional_edges("relax", dispatch_collect)  # 宽松重采后再次 fan-out
    g.add_edge("fetch_source", "dedup")
    g.add_conditional_edges("dedup", _route_after_dedup(settings), {"relax": "relax", "continue": "classify"})
    g.add_edge("classify", "score")
    g.add_edge("score", "summarize")
    g.add_edge("summarize", "editor")
    g.add_edge("summarize", "analyst")
    # quicknews 依赖 editor 的头条结果做排除（同一超步并行读不到彼此输出）
    g.add_edge("editor", "quicknews")
    g.add_edge("editor", "publish")
    g.add_edge("analyst", "publish")
    g.add_edge("quicknews", "publish")
    g.add_edge("publish", END)

    return g.compile(checkpointer=checkpointer)
