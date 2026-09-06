"""源适配器单测：离线解析 fixtures，验证归一化/时间窗/过滤逻辑。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from conftest import NOW, make_client
from robin.config import SourceCfg
from robin.sources import build_source
from robin.sources.base import BaseSource


def _cfg(**kw) -> SourceCfg:
    base = dict(id="t", name="T", type="rss", url="https://example.com/feed")
    return SourceCfg(**{**base, **kw})


async def test_rss_parses_and_window_filters(now):
    from robin.sources.rss import RSSSource

    src = RSSSource(_cfg(url="https://www.jiqizhixin.com/rss"))
    async with make_client() as client:
        articles = await src.fetch(client, now=NOW, window_hours=30)
    # 4 条 fixture，1 条超窗（9/1）被过滤
    assert len(articles) == 3
    a = articles[0]
    assert a.source_id == "t" and a.source_name == "T"
    assert a.title.startswith("DeepSeek 正式发布 V4")
    assert a.url.startswith("https://www.jiqizhixin.com/articles/")
    assert a.published_at is not None and a.published_at.tzinfo is not None
    # ID 稳定性：同 URL 再次抓取 ID 一致
    again = articles[0].model_copy()
    assert again.id == a.id


async def test_rss_author_and_content_strip(now):
    from robin.sources.rss import RSSSource

    src = RSSSource(_cfg(url="https://www.qbitai.com/feed"))
    async with make_client() as client:
        articles = await src.fetch(client, now=NOW, window_hours=30)
    assert len(articles) == 3
    assert all("（" not in a.content or "测试" in a.content for a in articles)
    first = [a for a in articles if "豆包" in a.title][0]
    assert first.author == "量子位"
    assert "字节跳动" in first.content


async def test_hackernews_points_filter_and_url_fallback(now):
    from robin.sources.hackernews import HackerNewsSource

    src = HackerNewsSource(_cfg(type="hackernews", query="AI OR LLM", min_points=40))
    async with make_client() as client:
        articles = await src.fetch(client, now=NOW, window_hours=30)
    # 5 hits：38 分的低于阈值被过滤，剩 4 条
    assert len(articles) == 4
    assert all((a.points or 0) >= 40 for a in articles)
    # 无 url 的 hit 回退到 HN item 链接
    alphafold = [a for a in articles if "AlphaFold" in a.title][0]
    assert alphafold.url == "https://news.ycombinator.com/item?id=40000003"
    # relaxed 模式阈值减半：38 分的也进来
    async with make_client() as client:
        relaxed = await src.fetch(client, now=NOW, window_hours=30, relaxed=True)
    assert len(relaxed) == 5


async def test_arxiv_window_filter(now):
    from robin.sources.arxiv import ArxivSource

    src = ArxivSource(_cfg(type="arxiv", categories=["cs.AI"]))
    async with make_client() as client:
        articles = await src.fetch(client, now=NOW, window_hours=30)
    assert len(articles) == 2  # 8/28 的旧条目被过滤
    assert all(a.url.startswith("http://arxiv.org/abs/") for a in articles)


async def test_github_trending_ai_filter(now):
    from robin.sources.web import GitHubTrendingSource

    src = GitHubTrendingSource(_cfg(type="github_trending", language="python",
                                    ai_keywords=["llm", "agent", "ai", "gpt"]))
    async with make_client() as client:
        articles = await src.fetch(client, now=NOW, window_hours=30)
    names = [a.title for a in articles]
    # linux 无 AI 关键词被过滤；DeepSeek-V4 因 "deepseek-ai" 命中子串 "ai" 保留
    assert "torvalds/linux" not in names
    assert "microsoft/markitdown" in names and "openai/swarm" in names
    star = [a for a in articles if a.title == "microsoft/markitdown"][0]
    assert star.points == 62000
    assert star.url == "https://github.com/microsoft/markitdown"


async def test_in_window_boundary(now):
    now = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)
    assert BaseSource._in_window(now - timedelta(hours=29), now, 30) is True
    assert BaseSource._in_window(now - timedelta(hours=31), now, 30) is False
    assert BaseSource._in_window(None, now, 30) is True  # 无时间保守保留


def test_registry_unknown_type():
    with pytest.raises(ValueError):
        build_source(_cfg(type="nope"))
