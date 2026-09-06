"""采集记者 Agent：LangGraph Send 动态 map 并行抓取所有数据源。

- dispatch_collect 返回 Send 列表，LangGraph 会并行执行多个 fetch_source 实例
- 每个实例独立 try/except：单源失败只记入 source_errors，不影响整体（错误隔离）
- relaxed 标志由「宽松重采」节点写入 state 后再次 dispatch（条件边循环）
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.types import Send

from robin.config import SourceCfg
from robin.sources import BaseSource, build_source, create_http_client
from robin.utils import utcnow

logger = logging.getLogger(__name__)


def dispatch_collect(state: dict) -> list[Send]:
    """fan-out：为每个启用的数据源发送一个并行 fetch_source 任务。"""
    sends = []
    for cfg in state["sources"]:
        sends.append(
            Send(
                "fetch_source",
                {
                    "source": cfg.model_dump(),
                    "relaxed": bool(state.get("relaxed", False)),
                    "window_hours": int(state.get("window_hours", 30)),
                    "now": state.get("now"),
                },
            )
        )
    return sends


def make_fetch_source(client_factory=None):
    """图节点工厂：可注入 httpx 客户端工厂（离线演示/测试注入 MockTransport）。"""
    default_factory = client_factory or create_http_client

    async def fetch_source(payload: dict) -> dict:
        """单个数据源抓取（Send 载荷）。返回部分 state 由 reducer 合并。"""
        cfg = SourceCfg(**payload["source"])
        relaxed = bool(payload.get("relaxed", False))
        window_hours = int(payload.get("window_hours", 30))
        now_raw = payload.get("now")
        now = datetime.fromisoformat(now_raw) if now_raw else utcnow()
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("UTC"))

        src: BaseSource = build_source(cfg)
        t0 = time.perf_counter()
        try:
            async with default_factory() as client:
                articles = await src.fetch(client, now=now, window_hours=window_hours, relaxed=relaxed)
            for a in articles:
                a.source_weight = cfg.weight
            duration = round(time.perf_counter() - t0, 3)
            logger.info("[采集] %s: %s 条 (%.2fs)", cfg.name, len(articles), duration)
            return {
                "articles": articles,
                "source_stats": {cfg.id: {"name": cfg.name, "count": len(articles), "duration_s": duration}},
            }
        except Exception as e:  # 错误隔离：单源失败不阻断
            duration = round(time.perf_counter() - t0, 3)
            logger.warning("[采集] %s 失败(%0.2fs): %s", cfg.name, duration, e)
            return {
                "articles": [],
                "source_errors": [{"source": cfg.id, "name": cfg.name, "error": str(e)[:200]}],
                "source_stats": {cfg.id: {"name": cfg.name, "count": 0, "duration_s": duration}},
            }

    return fetch_source


# 默认节点（真实网络）；离线场景用 make_fetch_source(client_factory) 注入
fetch_source = make_fetch_source()


def relax_refetch(state: dict) -> dict:
    """宽松重采：扩大时间窗 + 放开源内过滤（如 HN points 减半）。"""
    return {
        "relaxed": True,
        "window_hours": int(state.get("relaxed_window_hours", 72)),
        "retry_count": int(state.get("retry_count", 0)) + 1,
    }
