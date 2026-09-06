"""源适配器基类与公共逻辑。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from robin.config import SourceCfg
from robin.models import Article
from robin.utils import make_id, utcnow

logger = logging.getLogger(__name__)


def create_http_client() -> httpx.AsyncClient:
    """统一入口：超时、UA、重定向。测试可注入 MockTransport 构造的 client。"""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
        headers={"User-Agent": "RobinBrief/0.1 (multi-agent daily brief)"},
    )


class BaseSource(ABC):
    """所有数据源适配器的接口。

    fetch() 必须自行捕获业务级异常并抛出让上层记录 ——
    上层(collector)对每个源做错误隔离，单源失败不影响整体。
    """

    def __init__(self, cfg: SourceCfg) -> None:
        self.cfg = cfg

    @property
    def id(self) -> str:
        return self.cfg.id

    @property
    def name(self) -> str:
        return self.cfg.name

    @abstractmethod
    async def fetch(
        self,
        client: httpx.AsyncClient,
        *,
        now: datetime | None = None,
        window_hours: int = 30,
        relaxed: bool = False,
    ) -> list[Article]:
        """抓取并归一化为 Article 列表。now 注入当前时间（测试可固定）。"""

    def _article(
        self,
        *,
        url: str,
        title: str,
        content: str = "",
        author: str = "",
        published_at: datetime | None = None,
        points: int | None = None,
    ) -> Article | None:
        """构造 Article；无效条目（无标题/链接）返回 None。"""
        title = (title or "").strip()
        url = (url or "").strip()
        if not title or not url.startswith("http"):
            return None
        return Article(
            id=make_id(url),
            source_id=self.cfg.id,
            source_name=self.cfg.name,
            url=url,
            title=title,
            content=(content or "").strip(),
            author=(author or "").strip(),
            published_at=published_at,
            fetched_at=utcnow(),
            points=points,
        )

    @staticmethod
    def _in_window(published_at: datetime | None, now: datetime, window_hours: int) -> bool:
        """发布时间落在窗口内（无发布时间的条目保守保留，交给去重兜底）。"""
        if published_at is None:
            return True
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        return now - timedelta(hours=window_hours) <= published_at <= now + timedelta(minutes=30)


def parse_struct_time(st: Any) -> datetime | None:
    """feedparser 的 struct_time -> aware UTC datetime。"""
    if not st:
        return None
    try:
        from calendar import timegm

        return datetime.fromtimestamp(timegm(st), tz=UTC)
    except Exception as e:
        logger.warning("时间解析失败 %s: %s", st, e)
        return None
