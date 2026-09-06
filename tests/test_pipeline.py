"""端到端流水线测试：fixtures 离线数据 + mock LLM 全链路出报。"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import NOW, RUN_DATE, build_test_sources
from robin.config import Settings
from robin.llm import LLMError
from robin.models import BriefDocument, RunReport
from robin.pipeline import run_pipeline
from robin.store.db import Database


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch):
    """隔离的运行环境：临时目录；返回 settings。测试直接注入 sources/client_factory。"""
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        db_path=str(tmp_path / "data" / "robin.db"),
        output_dir=str(tmp_path / "output"),
        checkpoint_path=str(tmp_path / "data" / "ckpt.sqlite"),
        llm_api_key="",
        min_articles=5,
    )
    return settings


def _run(settings, **kw):
    import conftest

    return run_pipeline(settings, mock=True, run_date=RUN_DATE, push=False,
                        sources=build_test_sources(),
                        client_factory=conftest.make_client, now=NOW, **kw)


def test_full_pipeline_mock(pipeline_env):
    doc, report = _run(pipeline_env)

    assert isinstance(doc, BriefDocument) and isinstance(report, RunReport)
    assert report.status == "ok"
    assert 1 <= len(doc.headlines) <= 5
    assert len(doc.quick_news) >= 2
    assert doc.epigraph
    assert doc.weekday_cn == "星期日"
    assert "七月" in doc.lunar_str
    # 非AI内容被分类层丢弃
    all_texts = doc.epigraph + " ".join(h.title + h.summary for h in doc.headlines) \
        + " ".join(q.text for q in doc.quick_news)
    assert "马拉松" not in all_texts
    # 同事件模糊去重：两条 V4 发布新闻（机器之心/量子位）只保留一条
    titles = [h.title for h in doc.headlines] + [q.text for q in doc.quick_news]
    news_a = any("正式发布 V4 大模型" in t for t in titles)
    news_b = any("推出全新 V4 模型" in t for t in titles)
    assert not (news_a and news_b)
    # 漏斗一致性
    assert report.funnel["collected"] >= report.funnel["kept"] >= 1
    assert report.funnel["headlines"] == len(doc.headlines)
    # 产物文件
    out_dir = Path(pipeline_env.output_dir)
    html = out_dir / RUN_DATE / "brief.html"
    md = out_dir / RUN_DATE / "brief.md"
    assert html.exists() and "知更" in html.read_text(encoding="utf-8")
    assert md.exists()
    # mock 模式标记
    assert doc.is_demo is True
    # 数据库归档
    db = Database(pipeline_env.db_path)
    assert db.list_briefs()[0]["date"] == RUN_DATE
    norms = db.recent_title_norms(days=3, exclude_date=RUN_DATE)
    assert norms == set()  # 当天条目不计入跨天历史
    db.close()


def test_pipeline_yesterday_review(pipeline_env):
    import conftest

    run_pipeline(pipeline_env, mock=True, run_date="2026-09-05", push=False,
                 sources=build_test_sources(), client_factory=conftest.make_client, now=NOW)
    doc, _ = _run(pipeline_env)
    assert doc.yesterday is not None
    assert doc.yesterday.date == "2026-09-05"
    assert doc.yesterday.title


def test_pipeline_relaxed_refetch_loop(pipeline_env):
    # min_articles 极高 → 触发一次宽松重采（72h 窗口）后仍正常出版
    settings = pipeline_env.model_copy(update={"min_articles": 10_000})
    doc, report = _run(settings)
    assert report.status in ("ok", "degraded")
    assert len(doc.quick_news) >= 1 or doc.headlines
    # 宽松窗口把旧闻也采了进来：漏斗采集数显著大于紧凑窗口
    assert report.funnel["collected"] >= 8


def test_pipeline_source_error_isolation(pipeline_env):
    """单源 404 不影响整体出版。"""
    import conftest

    broken = dict(conftest.FIXTURE_ROUTES)
    broken["qbitai.com/feed"] = "not_exist.xml"  # 触发 404
    doc, report = run_pipeline(
        pipeline_env, mock=True, run_date=RUN_DATE, push=False,
        sources=build_test_sources(),
        client_factory=lambda: conftest.make_client(broken), now=NOW,
    )
    assert report.status == "ok"
    assert any(e["source"] == "qbitai" for e in report.source_errors)
    assert doc.headlines  # 其他源照常供给


def test_mock_llm_usage_tracked(pipeline_env):
    _, report = _run(pipeline_env)
    assert report.llm_usage["calls"] >= 5
    assert report.llm_usage["prompt_tokens"] > 0
    assert set(report.agent_stats) >= {"dedup", "classify", "score", "summarize", "editor", "publisher"}


def test_real_mode_requires_key(pipeline_env):
    with pytest.raises(LLMError):
        run_pipeline(pipeline_env, mock=False, run_date=RUN_DATE, push=False)


def test_async_sqlite_checkpoint(pipeline_env):
    """回归：真实模式走 ainvoke + AsyncSqliteSaver（mock 的 InMemory 不覆盖此路径）。"""
    from robin.llm import MockLLMClient

    doc, report = run_pipeline(
        pipeline_env, mock=False, run_date=RUN_DATE, push=False,
        sources=build_test_sources(), llm_client=MockLLMClient(),
        client_factory=conftest_make_client(), now=__import__("conftest").NOW,
    )
    assert report.status == "ok"
    assert doc.headlines
    assert (Path(pipeline_env.checkpoint_path)).exists()  # checkpoint 落盘


def conftest_make_client():
    import conftest

    return conftest.make_client
