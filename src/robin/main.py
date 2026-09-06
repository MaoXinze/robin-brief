"""知更 Robin CLI。

    robin run          生成今日日报（真实 LLM）
    robin run --mock   离线演示模式（无需 API Key）
    robin schedule     每日定时出版（APScheduler）
    robin archive      查看历史日报归档
    robin init         初始化 .env 配置
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from robin import __version__
from robin.config import Settings
from robin.llm import LLMError
from robin.models import RunReport
from robin.pipeline import default_run_date, run_pipeline
from robin.store.db import Database

app = typer.Typer(add_completion=False, help="知更 Robin — 多 Agent 协作的 AI 行业每日早报")
console = Console(highlight=False)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_report(doc, report: RunReport, output_dir: Path) -> None:
    console.print(Panel.fit(
        f"[bold]🐦 知更早报 · {doc.run_date} {doc.weekday_cn}[/bold]\n"
        f"{doc.lunar_str} ｜ 状态：[{'green' if report.status == 'ok' else 'yellow'}]{report.status}[/]"
        f" ｜ 耗时 {report.duration_s}s",
        border_style="cyan",
    ))
    table = Table(show_header=True, header_style="bold", border_style="dim")
    table.add_column("漏斗环节", justify="left")
    table.add_column("条数", justify="right")
    for key, label in [("collected", "采集"), ("after_url", "URL 去重"), ("after_title", "标题去重"),
                       ("after_fuzzy", "模糊去重"), ("after_history", "历史去重"), ("kept", "去重后"),
                       ("classified", "分类后"), ("scored", "评分后"), ("headlines", "头条"),
                       ("quick_news", "快讯"), ("analysis", "深度解读")]:
        if key in report.funnel:
            table.add_row(label, str(report.funnel[key]))
    console.print(table)
    console.print(f"LLM 用量：{report.llm_usage.get('calls', 0)} 次调用 · "
                  f"{report.llm_usage.get('prompt_tokens', 0)} prompt / "
                  f"{report.llm_usage.get('completion_tokens', 0)} completion tokens")
    if report.source_errors:
        for err in report.source_errors:
            console.print(f"[yellow]⚠ 来源失败：{err['name']} — {err['error']}[/]")
    html = report.output_files.get("html", "")
    console.print(Panel.fit(
        f"[bold]HTML 日报[/bold] {html}\n"
        f"[bold]Markdown[/bold] {report.output_files.get('md', '')}\n"
        f"运行报告 {output_dir / doc.run_date / 'run_report.json'}",
        border_style="green", title="产物",
    ))


@app.command()
def run(
    mock: bool = typer.Option(False, "--mock", help="离线演示模式：无需 API Key，使用规则式伪智能"),
    date: str = typer.Option(None, "--date", help="日报日期 YYYY-MM-DD（默认今天，东八区）"),
    push: bool = typer.Option(None, "--push/--no-push", help="是否推送飞书（默认：配置了 Webhook 即推送，mock 不推送）"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """生成一期知更早报。"""
    _setup_logging(verbose)
    settings = Settings()
    run_date = date or default_run_date(settings)
    if date:
        datetime.strptime(date, "%Y-%m-%d")
    try:
        doc, report = run_pipeline(settings, mock=mock, run_date=run_date, push=push)
    except LLMError as e:
        console.print(f"[red]✘ {e}[/]")
        raise typer.Exit(code=1) from e
    report.output_files.setdefault("report", str(Path(settings.output_dir) / run_date / "run_report.json"))
    Path(settings.output_dir, run_date).mkdir(parents=True, exist_ok=True)
    (Path(settings.output_dir) / run_date / "run_report.json").write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(doc, report, Path(settings.output_dir))


@app.command()
def demo() -> None:
    """离线演示：内置样例数据 + 规则式伪智能，一键生成示例早报（无需 Key/网络）。"""
    _setup_logging(False)
    settings = Settings()
    from robin.demo import run_demo

    doc, report = run_demo(settings)
    report.output_files.setdefault("report", str(Path(settings.output_dir) / doc.run_date / "run_report.json"))
    Path(settings.output_dir, doc.run_date).mkdir(parents=True, exist_ok=True)
    (Path(settings.output_dir) / doc.run_date / "run_report.json").write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(doc, report, Path(settings.output_dir))


@app.command()
def schedule(
    at: str = typer.Option("08:30", "--at", help="每日出版时间 HH:MM（出版时区）"),
    mock: bool = typer.Option(False, "--mock", help="定时任务使用 mock 模式（调试用）"),
    push: bool = typer.Option(None, "--push/--no-push"),
) -> None:
    """常驻进程：每天定时自动出版并推送。"""
    from apscheduler.schedulers.blocking import BlockingScheduler

    settings = Settings()
    hour, minute = at.split(":")
    tz = ZoneInfo(settings.timezone)
    console.print(f"[cyan]知更编辑部每日 {at}（{settings.timezone}）自动出版，Ctrl+C 退出[/]")

    def job() -> None:
        try:
            doc, report = run_pipeline(settings, mock=mock, push=push)
            console.print(f"[green]✔ {doc.run_date} 出版完成 → {report.output_files.get('html')}[/]")
        except Exception as e:
            console.print(f"[red]✘ 出版失败：{e}[/]")

    sched = BlockingScheduler(timezone=tz)
    sched.add_job(job, "cron", hour=int(hour), minute=int(minute))
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("已停止。")


@app.command()
def archive(limit: int = typer.Option(10, "--limit", "-n")) -> None:
    """查看历史日报归档。"""
    settings = Settings()
    if not Path(settings.db_path).exists():
        console.print("[yellow]尚无归档（先运行 robin run）[/]")
        return
    db = Database(settings.db_path)
    rows = db.list_briefs(limit)
    if not rows:
        console.print("[yellow]尚无归档[/]")
        return
    table = Table(show_header=True, header_style="bold", border_style="dim")
    table.add_column("日期")
    table.add_column("今日微语")
    table.add_column("HTML")
    for r in rows:
        table.add_row(r["date"], (r["epigraph"] or "")[:24], r["html_path"])
    console.print(table)
    db.close()


@app.command()
def init() -> None:
    """初始化配置：复制 .env.example 为 .env。"""
    if Path(".env").exists():
        console.print("[yellow].env 已存在，跳过[/]")
        return
    example = Path(".env.example")
    if not example.exists():
        console.print("[red]找不到 .env.example[/]")
        raise typer.Exit(1)
    shutil.copy(example, ".env")
    console.print("[green]✔ 已生成 .env[/] —— 请填入 ROBIN_LLM_API_KEY（DeepSeek），"
                  "可选填 ROBIN_FEISHU_WEBHOOK_URL")


@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"知更 Robin v{__version__}")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    app()
