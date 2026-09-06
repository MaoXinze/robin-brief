"""arXiv 适配器（官方 Atom API，关注 cs.AI / cs.CL 最新论文）。"""

from __future__ import annotations

import feedparser

from robin.models import Article
from robin.sources.base import BaseSource, parse_struct_time


class ArxivSource(BaseSource):
    API = "http://export.arxiv.org/api/query"

    async def fetch(self, client, *, now=None, window_hours=30, relaxed=False) -> list[Article]:
        from robin.utils import utcnow

        now = now or utcnow()
        cats = " OR ".join(f"cat:{c}" for c in (self.cfg.categories or ["cs.AI"]))
        params = {
            "search_query": cats,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": self.cfg.max_results,
        }
        resp = await client.get(self.API, params=params)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        articles: list[Article] = []
        for entry in feed.entries:
            a = self._article(
                url=getattr(entry, "link", "") or "",
                title=" ".join((getattr(entry, "title", "") or "").split()),
                content=" ".join((getattr(entry, "summary", "") or "").split())[:1200],
                author=getattr(entry, "author", "") or "",
                published_at=parse_struct_time(getattr(entry, "published_parsed", None)),
            )
            if a and self._in_window(a.published_at, now, window_hours):
                articles.append(a)
        return articles
