"""出版发行 Agent：组装 BriefDocument -> 渲染双格式 -> 归档 -> 推送。

这是流水线对"外"的唯一出口：产物文件、数据库归档、飞书推送都在此发生。
"""

from __future__ import annotations

import logging
from pathlib import Path

from robin.config import Settings
from robin.models import BriefDocument, YesterdayView
from robin.push import push_brief
from robin.render import lunar_str, render_html, render_markdown, weekday_cn
from robin.store.db import Database
from robin.utils import to_tz, utcnow

logger = logging.getLogger(__name__)


def make_publisher_node(settings: Settings, db: Database):
    def publish_node(state: dict) -> dict:
        # 幂等守卫：LangGraph 多入边汇聚可能多次触发本节点，
        # 三个编辑节点（editor/analyst/quicknews）的完成标志齐备才出版一次
        done = state.get("stage_done") or {}
        if not all(done.get(k) for k in ("editor", "analyst", "quicknews")):
            logger.info("[出版] 等待编辑层完成，跳过本次触发")
            return {}

        run_date = state["run_date"]
        funnel = dict(state.get("dedup_stats", {}))
        funnel["headlines"] = len(state.get("headlines", []))
        funnel["quick_news"] = len(state.get("quick_news", []))
        funnel["analysis"] = len(state.get("analysis", []))

        doc = BriefDocument(
            run_date=run_date,
            weekday_cn=weekday_cn(run_date),
            lunar_str=lunar_str(run_date),
            agent_count=settings.agent_count,
            epigraph=state.get("epigraph", ""),
            headlines=state.get("headlines", []),
            quick_news=state.get("quick_news", []),
            analysis=state.get("analysis", []),
            yesterday=YesterdayView(**state["yesterday"]) if state.get("yesterday") else None,
            sources_used=[
                v["name"] for v in (state.get("source_stats") or {}).values() if v.get("count", 0) > 0
            ],
            funnel=funnel,
            generated_at=to_tz(utcnow(), settings.timezone),
            is_demo=bool(state.get("mock", False)),
        )

        out_dir = Path(settings.output_dir) / run_date
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / "brief.html"
        md_path = out_dir / "brief.md"
        html_path.write_text(render_html(doc), encoding="utf-8")
        md_path.write_text(render_markdown(doc), encoding="utf-8")

        db.upsert_articles(run_date, state.get("summarized", []))
        db.save_brief(doc, str(html_path), str(md_path))

        published = {"html": str(html_path), "md": str(md_path)}
        if state.get("push") and not state.get("mock"):
            ok, msg = push_brief(settings.feishu_webhook_url, settings.feishu_secret, doc)
            published["pushed"] = str(ok)
            published["push_msg"] = msg
            logger.info("[推送] 飞书: %s %s", "成功" if ok else "失败", msg)

        logger.info("[出版] %s | 头条 %s 快讯 %s 解读 %s",
                    html_path, len(doc.headlines), len(doc.quick_news), len(doc.analysis))
        return {"brief": doc, "published": published}

    return publish_node
