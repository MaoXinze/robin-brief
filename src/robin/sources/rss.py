"""RSS/Atom 通用适配器（feedparser 解析，覆盖大多数科技媒体与官方博客）。"""

from __future__ import annotations

import feedparser

from robin.models import Article
from robin.sources.base import BaseSource, parse_struct_time
from robin.utils import strip_html


class RSSSource(BaseSource):
    async def fetch(self, client, *, now=None, window_hours=30, relaxed=False) -> list[Article]:
        from robin.utils import utcnow

        now = now or utcnow()
        resp = await client.get(self.cfg.url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        articles: list[Article] = []
        for entry in feed.entries[: self.cfg.max_results * 3]:
            a = self._article(
                url=getattr(entry, "link", "") or "",
                title=getattr(entry, "title", "") or "",
                content=strip_html(getattr(entry, "summary", "") or "")[:1200],
                author=getattr(entry, "author", "") or "",
                published_at=parse_struct_time(getattr(entry, "published_parsed", None)),
            )
            if a and self._in_window(a.published_at, now, window_hours):
                articles.append(a)
        return articles[: self.cfg.max_results]
