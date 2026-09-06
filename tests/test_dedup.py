"""去重与 SQLite 存储单测。"""

from __future__ import annotations

from datetime import UTC, datetime

from robin.agents.dedup import dedup_articles
from robin.models import Article
from robin.store.db import Database
from robin.utils import make_id, norm_title, normalize_url


def _a(title: str, url: str, *, source: str = "S1", weight: int = 3, points: int | None = None) -> Article:
    return Article(
        id=make_id(url), source_id=source, source_name=source, source_weight=weight,
        url=url, title=title, published_at=datetime(2026, 9, 5, 8, 0, tzinfo=UTC),
        points=points,
    )


def test_normalize_url_strips_tracking():
    u1 = "https://www.Example.com/a/b?utm_source=x&id=1"
    u2 = "https://example.com/a/b?id=1"
    assert normalize_url(u1) == normalize_url(u2)


def test_dedup_url_exact():
    a1 = _a("标题A", "https://example.com/x?utm_source=t")
    a2 = _a("标题A 复制", "https://example.com/x")
    kept, stats = dedup_articles([a1, a2])
    assert len(kept) == 1
    assert stats["after_url"] == 1 and stats["kept"] == 1


def test_dedup_title_exact_keeps_higher_weight():
    lo = _a("OpenAI 发布新模型 GPT-5", "https://a.com/1", source="低权重源", weight=2)
    hi = _a("OpenAI 发布新模型 GPT-5", "https://b.com/2", source="高权重源", weight=5)
    kept, _ = dedup_articles([lo, hi])
    assert len(kept) == 1 and kept[0].source_name == "高权重源"


def test_dedup_fuzzy_near_duplicate():
    a1 = _a("DeepSeek 发布 V4 大模型 推理成本下降60%", "https://a.com/1")
    a2 = _a("DeepSeek 发布 V4 大模型：推理成本下降 60%（快讯）", "https://b.com/2")
    kept, stats = dedup_articles([a1, a2], llm=None)
    assert len(kept) == 1
    assert stats["kept"] == 1


def test_dedup_keeps_distinct_events():
    a1 = _a("OpenAI 完成 400 亿美元融资", "https://a.com/1")
    a2 = _a("Anthropic 发布政府版 Claude", "https://b.com/2")
    a3 = _a("英伟达推出 GB300 芯片", "https://c.com/3")
    kept, _ = dedup_articles([a1, a2, a3], llm=None)
    assert len(kept) == 3


def test_dedup_against_history():
    hist = {norm_title("OpenAI 完成 400 亿美元融资")}
    a1 = _a("OpenAI完成400亿美元融资，估值达5000亿", "https://a.com/1")
    a2 = _a("Anthropic 发布政府版 Claude", "https://b.com/2")
    kept, stats = dedup_articles([a1, a2], history_norms=hist, llm=None)
    assert [a.title for a in kept] == ["Anthropic 发布政府版 Claude"]
    assert stats["after_history"] == 1


def test_database_history_and_yesterday(tmp_path):
    db = Database(tmp_path / "test.db")
    from robin.models import BriefDocument, Category, HeadlineView

    h = HeadlineView(title="昨日头条：某重大事件", summary="s", comment="c",
                     url="https://x.com/1", source_name="X", category=Category.OTHER, importance=5)
    doc = BriefDocument(run_date="2026-09-05", weekday_cn="星期六", headlines=[h])
    db.save_brief(doc, "h.html", "m.md")
    y = db.get_yesterday_top("2026-09-06")
    assert y == {"date": "2026-09-05", "title": "昨日头条：某重大事件", "url": "https://x.com/1"}
    assert db.get_yesterday_top("2026-09-05") is None  # 自身日期之前无报

    from robin.models import EnrichedArticle

    ea = EnrichedArticle(
        id="abc123", source_id="x", source_name="X", url="https://x.com/1",
        title="昨日头条：某重大事件", category=Category.OTHER, importance=5,
    )
    db.upsert_articles("2026-09-05", [ea])
    norms = db.recent_title_norms(days=3, exclude_date="2026-09-06")
    assert norm_title("昨日头条：某重大事件") in norms
    db.close()
