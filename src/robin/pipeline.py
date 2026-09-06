"""高层编排：一次日报生成的完整入口（图执行 + 运行报告落盘）。"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from robin.config import Settings, load_sources
from robin.graph import build_graph
from robin.llm import DeepSeekClient, LLMError, MockLLMClient
from robin.models import BriefDocument, RunReport
from robin.store.db import Database
from robin.utils import to_tz, utcnow

logger = logging.getLogger(__name__)


def default_run_date(settings: Settings) -> str:
    """以出版时区（默认东八区）的"今天"作为日报日期。"""
    return to_tz(utcnow(), settings.timezone).strftime("%Y-%m-%d")


async def _make_checkpointer(settings: Settings, mock: bool):
    """创建检查点。

    图统一走 ainvoke（采集节点是 async），检查点必须支持异步调用 ——
    因此真实运行用 AsyncSqliteSaver（aiosqlite），mock 用 InMemorySaver。
    同步的 SqliteSaver 在 ainvoke 下会抛 NotImplementedError（实测踩坑，见开发日志 §9）。
    """
    if mock:
        return InMemorySaver()
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    Path(settings.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(settings.checkpoint_path)
    return AsyncSqliteSaver(conn)


def run_pipeline(
    settings: Settings,
    *,
    mock: bool = False,
    run_date: str | None = None,
    push: bool | None = None,
    sources: list | None = None,
    client_factory=None,
    now: datetime | None = None,
    llm_client=None,
) -> tuple[BriefDocument, RunReport]:
    """生成指定日期的知更早报。

    - mock=True：离线确定性演示（MockLLMClient）
    - push=None：自动 —— 配置了飞书 Webhook 且非 mock 才推送
    - sources：数据源列表（None 时从 config/sources.yaml 加载）
    - client_factory：注入 httpx 客户端工厂（离线演示/测试）
    - now：覆盖当前时间（演示固定时间线）
    - llm_client：注入 LLM 客户端（测试接缝，覆盖 mock/真实选择）
    返回 (日报文档, 运行报告)。
    """
    started = now or utcnow()
    run_date = run_date or to_tz(started, settings.timezone).strftime("%Y-%m-%d")
    log = logging.getLogger("robin")

    if llm_client is not None:
        llm = llm_client
    elif mock:
        llm = MockLLMClient()
        log.info("[流水线] mock 模式：LLM 使用离线确定性实现")
    else:
        if not settings.llm_ready:
            raise LLMError(
                "未配置 LLM API Key。请复制 .env.example 为 .env 并填入 ROBIN_LLM_API_KEY，"
                "或使用 --mock 进行离线演示。"
            )
        llm = DeepSeekClient(settings)

    sources = sources if sources is not None else load_sources()
    if not sources:
        log.warning("[流水线] 未找到启用数据源（config/sources.yaml），将生成空日报")
    db = Database(settings.db_path)

    # 跨天去重历史 + 昨日回顾
    history_norms = db.recent_title_norms(days=3, exclude_date=run_date)
    yesterday = db.get_yesterday_top(run_date)

    push_flag = False if mock else (push if push is not None else True)

    initial: dict = {
        "run_date": run_date,
        "sources": sources,
        "now": started.isoformat(),
        "window_hours": settings.collect_window_hours,
        "relaxed_window_hours": settings.relaxed_window_hours,
        "relaxed": False,
        "retry_count": 0,
        "push": push_flag,
        "mock": mock,
        "history_norms": sorted(history_norms),
        "yesterday": yesterday,
        "articles": [],
        "source_errors": [],
        "source_stats": {},
        "agent_stats": {},
    }

    async def _invoke() -> dict:
        checkpointer = await _make_checkpointer(settings, mock)
        graph = build_graph(llm, settings, db, checkpointer=checkpointer,
                            client_factory=client_factory)
        return await graph.ainvoke(
            initial,
            config={"configurable": {"thread_id": f"brief-{run_date}"}, "recursion_limit": 100},
        )

    t0 = time.perf_counter()
    # 采集节点是 async（httpx），统一走 ainvoke；同步节点由 LangGraph 自动适配
    final = asyncio.run(_invoke())
    doc: BriefDocument = final["brief"]

    funnel = dict(doc.funnel)
    funnel["classified"] = len(final.get("classified", []))
    funnel["scored"] = len(final.get("scored", []))

    report = RunReport(
        run_date=run_date,
        started_at=started,
        finished_at=utcnow(),
        duration_s=round(time.perf_counter() - t0, 3),
        mock=mock,
        status="ok" if doc.headlines else "degraded",
        funnel=funnel,
        agent_stats=final.get("agent_stats", {}),
        source_errors=final.get("source_errors", []),
        llm_usage=llm.usage.as_dict(),
        output_files=final.get("published", {}),
    )
    db.save_run(report)
    db.close()
    return doc, report


def valid_date(s: str) -> str:
    date_cls.fromisoformat(s)  # 校验格式
    return s
