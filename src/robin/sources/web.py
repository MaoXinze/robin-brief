"""GitHub Trending 适配器（解析趋势页，按 AI 关键词过滤仓库）。"""

from __future__ import annotations

from selectolax.parser import HTMLParser

from robin.models import Article
from robin.sources.base import BaseSource
from robin.utils import keyword_hit


class GitHubTrendingSource(BaseSource):
    BASE = "https://github.com/trending"

    async def fetch(self, client, *, now=None, window_hours=30, relaxed=False) -> list[Article]:
        url = self.BASE
        if self.cfg.language:
            url = f"{self.BASE}/{self.cfg.language}"
        resp = await client.get(url, params={"since": "daily"})
        resp.raise_for_status()
        tree = HTMLParser(resp.text)
        articles: list[Article] = []
        for row in tree.css("article.Box-row"):
            link = row.css_first("h2 a")
            if link is None:
                continue
            href = (link.attributes.get("href") or "").strip()
            repo = href.strip("/")
            desc_node = row.css_first("p")
            desc = desc_node.text(deep=True, separator=" ", strip=True) if desc_node else ""
            stars = None
            stars_node = row.css_first("a[href$='/stargazers']")
            if stars_node:
                try:
                    stars = int(stars_node.text(strip=True).replace(",", ""))
                except ValueError:
                    stars = None
            # AI 关键词过滤：仓库名或描述命中才算 AI 相关（relaxed 模式放行全部）
            blob = f"{repo} {desc}".lower()
            kws = self.cfg.ai_keywords or []
            if kws and not relaxed and not any(keyword_hit(blob, k) for k in kws):
                continue
            a = self._article(
                url=f"https://github.com{href}" if href.startswith("/") else href,
                title=repo,
                content=desc,
                points=stars,
            )
            if a:
                articles.append(a)
        return articles[: self.cfg.max_results]
