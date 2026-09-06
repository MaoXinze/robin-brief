"""评分规则引擎与 mock LLM 单测。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from robin.agents.mock_impl import (
    mock_analyst,
    mock_classify,
    mock_editor,
    mock_score,
    mock_summarize,
)
from robin.agents.scorer import COMPANY_WEIGHTS, EVENT_WEIGHTS, recency_factor, rule_score
from robin.models import Category, EnrichedArticle
from robin.utils import make_id


def _e(category: Category, companies: list[str], *, points=None,
       published=None, title="标题") -> EnrichedArticle:
    return EnrichedArticle(
        id=make_id("https://x.com/" + title[:6]), source_id="s", source_name="S", url="https://x.com",
        title=title, category=category, companies=companies, points=points, published_at=published,
    )


def test_recency_factor_monotonic():
    now = datetime(2026, 9, 6, tzinfo=UTC)
    fresh = recency_factor(now - timedelta(hours=2), now)
    stale = recency_factor(now - timedelta(hours=60), now)
    assert fresh > stale
    assert recency_factor(None, now) == 0.7


def test_rule_score_headline_vs_marginal():
    now = datetime(2026, 9, 6, tzinfo=UTC)
    big = _e(Category.MODEL_RELEASE, ["OpenAI"], points=500, published=now - timedelta(hours=1),
             title="OpenAI 发布新模型")
    small = _e(Category.RESEARCH, [], published=now - timedelta(hours=70), title="某论文")
    # 头部公司重大事件稳居 4 星档（5 星留给 LLM 校准的行业格局级事件），边缘内容 ≤2 星
    assert rule_score(big, now) >= 4
    assert rule_score(small, now) <= 2
    # 热度加成有上限：不能把普通事件抬进头条档
    hot = _e(Category.PRODUCT, ["Manus"], points=100_000, published=now - timedelta(hours=1),
             title="某产品更新")
    assert rule_score(hot, now) <= rule_score(big, now)


def test_rule_score_known_weights():
    assert EVENT_WEIGHTS["funding_ma"] == 4.5
    assert COMPANY_WEIGHTS["OpenAI"] == 5.0


def test_mock_classify_categories():
    out = mock_classify({"items": [
        {"id": "1", "title": "OpenAI 完成 400 亿美元融资，估值创纪录", "content": ""},
        {"id": "2", "title": "智谱宣布 GLM-5 开源，免费商用", "content": ""},
        {"id": "3", "title": "欧盟 AI 法案首批罚款落地", "content": ""},
        {"id": "4", "title": "城市马拉松开跑", "content": ""},
    ]})
    m = {it["id"]: it for it in out["items"]}
    assert m["1"]["category"] == "funding_ma" and "OpenAI" in m["1"]["companies"]
    assert m["2"]["category"] == "open_source"
    assert m["3"]["category"] == "policy"
    assert m["4"]["is_ai"] is False  # 无 AI 线索 → 丢弃


def test_mock_editor_and_summarizer_deterministic():
    cands = {"candidates": [
        {"id": "a", "title": "A 大事件", "category": "model_release", "companies": ["OpenAI"], "importance": 5, "points": 100},
        {"id": "b", "title": "B 事件", "category": "funding_ma", "companies": [], "importance": 4, "points": 10},
        {"id": "c", "title": "C 事件", "category": "other", "companies": [], "importance": 2, "points": 0},
    ]}
    plan = mock_editor(cands)
    assert [h["id"] for h in plan["headlines"]] == ["a", "b", "c"]  # 默认 max_headlines=5，全选
    assert plan["epigraph"]
    plan2 = mock_editor(cands)
    assert plan2 == plan  # 确定性

    s = mock_summarize({"items": [{"id": "x", "title": "标题", "content": "第一句话内容足够长所以会被优先保留下来。第二句话。" * 3}]})
    assert s["items"][0]["summary"].startswith("第一句话内容足够长")


def test_mock_analyst_structure():
    out = mock_analyst({"item": {"title": "T", "summary": "S", "companies": ["OpenAI"], "category": "model_release"}})
    assert "background" in out and "impact" in out
    assert "OpenAI" in out["background"]


def test_mock_score_uses_rule_score():
    out = mock_score({"items": [{"id": "1", "title": "t", "category": "model_release",
                                 "companies": ["OpenAI"], "rule_score": 4, "points": 88}]})
    assert out["items"][0]["importance"] == 4
    assert "OpenAI" in out["items"][0]["reason"]
