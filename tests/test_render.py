"""渲染引擎单测：HTML/Markdown 输出与版面要素。"""

from __future__ import annotations

from datetime import UTC, datetime

from robin.models import (
    AnalysisView,
    BriefDocument,
    Category,
    HeadlineView,
    QuickNewsView,
    YesterdayView,
)
from robin.render.engine import category_label, lunar_str, render_html, render_markdown, stars, weekday_cn


def _doc(**kw) -> BriefDocument:
    base = dict(
        run_date="2026-09-06",
        weekday_cn=weekday_cn("2026-09-06"),
        lunar_str=lunar_str("2026-09-06"),
        agent_count=9,
        epigraph="模型迭代一日千里，清晨一读，先人一步。",
        headlines=[
            HeadlineView(title="DeepSeek 正式发布 V4 大模型", summary="推理成本再降 60%。",
                         comment="头部模型座次重排，开发者选型窗口再变。",
                         url="https://a.com/1", source_name="机器之心",
                         category=Category.MODEL_RELEASE, companies=["DeepSeek"],
                         importance=5, score_reason="5星事件"),
        ],
        quick_news=[QuickNewsView(text="OpenAI 完成 400 亿美元融资。", url="https://b.com/2",
                                  source_name="TechCrunch", category=Category.FUNDING_MA)],
        analysis=[AnalysisView(title="DeepSeek 发布 V4", url="https://a.com/1",
                               source_name="机器之心", background="背景……", impact="影响……")],
        yesterday=YesterdayView(date="2026-09-05", title="昨日头条", url="https://c.com/3"),
        sources_used=["机器之心", "TechCrunch"],
        funnel={"collected": 30, "kept": 12, "headlines": 1, "quick_news": 1},
        generated_at=datetime(2026, 9, 6, 8, 30, tzinfo=UTC),
    )
    base.update(kw)
    return BriefDocument(**base)


def test_html_contains_all_sections():
    html = render_html(_doc())
    for token in ["知更", "早报", "星期日", "农历二零二六年七月廿五", "9 个 Agent", "今日微语",
                  "今日头条", "为什么重要", "一句话快讯", "深度解读", "昨日回顾", "数据来源",
                  "★★★★★", "模型发布", "评分理由", "今日采集 30 条"]:
        assert token in html, f"缺少版面要素: {token}"


def test_html_escapes_malicious_content():
    doc = _doc(epigraph="<script>alert(1)</script>")
    html = render_html(doc)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_markdown_links_and_sections():
    md = render_markdown(_doc())
    assert "[DeepSeek 正式发布 V4 大模型](https://a.com/1)" in md
    assert "**今日微语**" in md and "一句话快讯" in md and "背景" in md


def test_helpers():
    assert weekday_cn("2026-09-06") == "星期日"
    assert stars(4) == "★★★★☆"
    assert category_label(Category.FUNDING_MA) == "融资并购"
    assert "七月" in lunar_str("2026-09-06")
