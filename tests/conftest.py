"""pytest 公共夹具：固定时间、MockTransport 路由、测试数据源。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# 固定"当前时间"：2026-09-05 16:30 UTC == 东八区 2026-09-06 00:30（清晨出版时刻）
NOW = datetime(2026, 9, 5, 16, 30, tzinfo=UTC)
RUN_DATE = "2026-09-06"


def read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


CONTENT_TYPES = {
    "xml": "application/rss+xml",
    "atom": "application/atom+xml",
    "json": "application/json",
    "html": "text/html; charset=utf-8",
}

# URL 片段 -> fixture 文件（真实生产 URL 即可离线命中）
FIXTURE_ROUTES: dict[str, str] = {
    "jiqizhixin.com/rss": "jiqizhixin.xml",
    "qbitai.com/feed": "qbitai.xml",
    "techcrunch.com": "techcrunch.xml",
    "hn.algolia.com": "hackernews.json",
    "export.arxiv.org": "arxiv.xml",
    "github.com/trending": "github_trending.html",
}


def make_client(routes: dict[str, str] | None = None) -> httpx.AsyncClient:
    """用 fixture 路由表构造离线 httpx 客户端。"""
    routes = routes if routes is not None else FIXTURE_ROUTES

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for fragment, fname in routes.items():
            if fragment in url:
                suffix = fname.rsplit(".", 1)[-1]
                ctype = CONTENT_TYPES.get("atom" if suffix == "xml" and "arxiv" in fname else suffix,
                                          "application/octet-stream")
                return httpx.Response(200, content=read_fixture(fname),
                                      headers={"content-type": ctype})
        return httpx.Response(404, text=f"no fixture route for {url}")

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        timeout=httpx.Timeout(10.0),
    )


def build_test_sources() -> list:
    """与 config/sources.yaml 对应的测试数据源（enabled 全开）。"""
    from robin.config import SourceCfg

    return [
        SourceCfg(id="jiqizhixin", name="机器之心", type="rss", url="https://www.jiqizhixin.com/rss", weight=4, lang="zh"),
        SourceCfg(id="qbitai", name="量子位", type="rss", url="https://www.qbitai.com/feed", weight=4, lang="zh"),
        SourceCfg(id="techcrunch_ai", name="TechCrunch AI", type="rss", url="https://techcrunch.com/feed", weight=4, lang="en"),
        SourceCfg(id="hackernews", name="Hacker News", type="hackernews", query="AI OR LLM", min_points=40, weight=3, lang="en"),
        SourceCfg(id="arxiv", name="arXiv cs.AI", type="arxiv", categories=["cs.AI"], max_results=20, weight=2, lang="en"),
        SourceCfg(id="github_trending", name="GitHub Trending", type="github_trending",
                  ai_keywords=["llm", "agent", "ai", "gpt", "transformer", "rag", "ml", "deep-learning"],
                  weight=3, lang="en", headline_eligible=False),
    ]


@pytest.fixture
def sources() -> list:
    return build_test_sources()


@pytest.fixture
def now() -> datetime:
    return NOW
