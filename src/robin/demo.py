"""离线演示：内置样例数据全链路出报，无需网络与 API Key。

数据说明：config/demo/ 下是与真实源同构的录制样例（内容为演示用虚构条目），
通过 httpx MockTransport 注入，其余流程（去重/分类/评分/编辑/渲染/归档）与真实运行完全一致。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from robin.config import Settings, SourceCfg
from robin.models import BriefDocument, RunReport
from robin.pipeline import run_pipeline

# 演示时间线固定：东八区 2026-09-06 00:30（清晨出版时刻）
DEMO_NOW = datetime(2026, 9, 5, 16, 30, tzinfo=UTC)
DEMO_DATE = "2026-09-06"

DEMO_DIR = Path("config/demo")

DEMO_SOURCES = [
    SourceCfg(id="jiqizhixin", name="机器之心", type="rss", url="https://www.jiqizhixin.com/rss", weight=4, lang="zh"),
    SourceCfg(id="qbitai", name="量子位", type="rss", url="https://www.qbitai.com/feed", weight=4, lang="zh"),
    SourceCfg(id="techcrunch_ai", name="TechCrunch AI", type="rss", url="https://techcrunch.com/feed", weight=4, lang="en"),
    SourceCfg(id="hackernews", name="Hacker News", type="hackernews", query="AI OR LLM", min_points=40, weight=3, lang="en"),
    SourceCfg(id="arxiv", name="arXiv cs.AI", type="arxiv", categories=["cs.AI"], max_results=20, weight=2, lang="en"),
    SourceCfg(id="github_trending", name="GitHub Trending", type="github_trending",
              ai_keywords=["llm", "agent", "ai", "gpt", "transformer", "rag", "ml", "deep-learning"],
              weight=3, lang="en", headline_eligible=False),
]

# URL 片段 -> 演示数据文件
DEMO_ROUTES = {
    "jiqizhixin.com/rss": "jiqizhixin.xml",
    "qbitai.com/feed": "qbitai.xml",
    "techcrunch.com": "techcrunch.xml",
    "hn.algolia.com": "hackernews.json",
    "export.arxiv.org": "arxiv.xml",
    "github.com/trending": "github_trending.html",
}


def _demo_client_factory():
    content_types = {".xml": "application/rss+xml", ".json": "application/json", ".html": "text/html; charset=utf-8"}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for fragment, fname in DEMO_ROUTES.items():
            if fragment in url:
                data = (DEMO_DIR / fname).read_bytes()
                ctype = content_types.get(Path(fname).suffix, "application/octet-stream")
                return httpx.Response(200, content=data, headers={"content-type": ctype})
        return httpx.Response(404, text=f"no demo route for {url}")

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        timeout=httpx.Timeout(10.0),
    )


def run_demo(settings: Settings, *, push: bool = False) -> tuple[BriefDocument, RunReport]:
    """离线生成 2026-09-06 期的演示早报。"""
    return run_pipeline(
        settings,
        mock=True,
        run_date=DEMO_DATE,
        push=push,
        sources=DEMO_SOURCES,
        client_factory=_demo_client_factory,
        now=DEMO_NOW,
    )
