"""SQLite 存储：文章库 / 日报归档 / 运行记录。零依赖（stdlib sqlite3），WAL 模式。"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from robin.models import EnrichedArticle, RunReport
from robin.utils import norm_title, utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    run_date   TEXT NOT NULL,
    id         TEXT NOT NULL,
    source_id  TEXT,
    source_name TEXT,
    url        TEXT,
    title      TEXT,
    title_norm TEXT,
    category   TEXT,
    importance INTEGER DEFAULT 0,
    summary    TEXT,
    PRIMARY KEY (run_date, id)
);
CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(run_date);

CREATE TABLE IF NOT EXISTS briefs (
    date           TEXT PRIMARY KEY,
    epigraph       TEXT,
    html_path      TEXT,
    md_path        TEXT,
    headlines_json TEXT,
    funnel_json    TEXT,
    created_at     TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date   TEXT,
    started_at TEXT,
    finished_at TEXT,
    duration_s REAL,
    mock       INTEGER DEFAULT 0,
    status     TEXT,
    report_json TEXT
);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # LangGraph 可能把同步节点放进线程池执行：允许跨线程 + 写锁串行化
        self._conn = sqlite3.connect(str(p), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ---------------- 文章库 ----------------
    def upsert_articles(self, run_date: str, articles: list[EnrichedArticle]) -> None:
        rows = [
            (run_date, a.id, a.source_id, a.source_name, a.url, a.title,
             norm_title(a.title), str(a.category.value), a.importance, a.summary)
            for a in articles
        ]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO articles (run_date, id, source_id, source_name, url, title,"
                " title_norm, category, importance, summary) VALUES (?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            self._conn.commit()

    def recent_title_norms(self, days: int = 3, exclude_date: str | None = None) -> set[str]:
        """近 N 天（不含当天重跑）已入库条目的标题归一集合 —— 跨天去重用。"""
        rows = self._conn.execute(
            "SELECT DISTINCT title_norm, run_date FROM articles"
            " WHERE title_norm != '' AND run_date <= ?"
            " ORDER BY run_date DESC LIMIT ?",
            (exclude_date or "9999-12-31", days * 200),
        )
        cutoff = None
        if exclude_date:
            from datetime import date, timedelta

            cutoff = (date.fromisoformat(exclude_date) - timedelta(days=days)).isoformat()
        out = set()
        for r in rows:
            if cutoff and r["run_date"] < cutoff:
                continue
            if exclude_date and r["run_date"] == exclude_date:
                continue
            out.add(r["title_norm"])
        return out

    # ---------------- 日报归档 ----------------
    def save_brief(self, doc, html_path: str, md_path: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO briefs (date, epigraph, html_path, md_path,"
                " headlines_json, funnel_json, created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    doc.run_date,
                    doc.epigraph,
                    html_path,
                    md_path,
                    json.dumps([h.model_dump() for h in doc.headlines], ensure_ascii=False),
                    json.dumps(doc.funnel, ensure_ascii=False),
                    utcnow().isoformat(),
                ),
            )
            self._conn.commit()

    def get_yesterday_top(self, run_date: str) -> dict | None:
        """上一个已出版日报的头条（用于「昨日回顾」）。"""
        row = self._conn.execute(
            "SELECT date, headlines_json FROM briefs WHERE date < ? ORDER BY date DESC LIMIT 1",
            (run_date,),
        ).fetchone()
        if not row:
            return None
        try:
            heads = json.loads(row["headlines_json"])
        except json.JSONDecodeError:
            return None
        if not heads:
            return None
        return {"date": row["date"], "title": heads[0].get("title", ""), "url": heads[0].get("url", "")}

    def list_briefs(self, limit: int = 30) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT date, epigraph, html_path, md_path, created_at FROM briefs"
            " ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()

    # ---------------- 运行记录 ----------------
    def save_run(self, report: RunReport) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (run_date, started_at, finished_at, duration_s, mock, status, report_json)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    report.run_date,
                    report.started_at.isoformat(),
                    report.finished_at.isoformat() if report.finished_at else None,
                    report.duration_s,
                    int(report.mock),
                    report.status,
                    report.model_dump_json(),
                ),
            )
            self._conn.commit()
