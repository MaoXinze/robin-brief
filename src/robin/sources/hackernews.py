"""Hacker News 适配器（Algolia 官方 API，无需 Key）。

用关键词查询近窗口内的故事，并按 points 阈值过滤热度 ——
relaxed 模式下阈值减半，扩大召回。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from robin.models import Article
from robin.sources.base import BaseSource


class HackerNewsSource(BaseSource):
    API = "https://hn.algolia.com/api/v1/search_by_date"

    async def fetch(self, client, *, now=None, window_hours=30, relaxed=False) -> list[Article]:
        from robin.utils import utcnow

        now = now or utcnow()
        since = int((now - timedelta(hours=window_hours)).timestamp())
        min_points = self.cfg.min_points if not relaxed else max(10, self.cfg.min_points // 2)
        params = {
            "tags": "story",
            "query": self.cfg.query,
            "hitsPerPage": 50,
            "numericFilters": f"created_at_i>{since},points>={min_points}",
        }
        resp = await client.get(self.API, params=params)
        resp.raise_for_status()
        articles: list[Article] = []
        for hit in resp.json().get("hits", []):
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            published = None
            if hit.get("created_at_i"):
                published = datetime.fromtimestamp(hit["created_at_i"], tz=UTC)
            a = self._article(
                url=url,
                title=hit.get("title") or "",
                content=hit.get("story_text") or "",
                author=hit.get("author") or "",
                published_at=published,
                points=hit.get("points"),
            )
            if a:
                articles.append(a)
        # 客户端侧兜底过滤（服务端 numericFilters 之外的双保险，也便于测试）
        articles = [a for a in articles if a.points is None or a.points >= min_points]
        return articles[: self.cfg.max_results]
