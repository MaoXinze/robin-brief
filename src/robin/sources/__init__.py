"""数据源适配器注册表：按 sources.yaml 的 type 构造对应实现。"""

from __future__ import annotations

from robin.config import SourceCfg
from robin.sources.arxiv import ArxivSource
from robin.sources.base import BaseSource, create_http_client
from robin.sources.hackernews import HackerNewsSource
from robin.sources.rss import RSSSource
from robin.sources.web import GitHubTrendingSource

_REGISTRY: dict[str, type[BaseSource]] = {
    "rss": RSSSource,
    "hackernews": HackerNewsSource,
    "arxiv": ArxivSource,
    "github_trending": GitHubTrendingSource,
}


def build_source(cfg: SourceCfg) -> BaseSource:
    cls = _REGISTRY.get(cfg.type)
    if cls is None:
        raise ValueError(f"未知数据源类型: {cfg.type} (source id={cfg.id})")
    return cls(cfg)


__all__ = ["BaseSource", "build_source", "create_http_client"]
