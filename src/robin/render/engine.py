"""渲染引擎：结构化 BriefDocument -> HTML（晨光纸感版）/ Markdown。

内容与呈现分离：本模块是唯一知道"报纸长什么样"的地方；
所有版面信息都在 templates/brief.html.j2 中，不依赖外部资源。
"""

from __future__ import annotations

from datetime import datetime

import cnlunar
from jinja2 import Environment, PackageLoader

from robin.models import BriefDocument

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def weekday_cn(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return _WEEKDAYS[d.weekday()]


def lunar_str(date_str: str) -> str:
    """农历描述（cnlunar），失败时返回空串不影响出版。"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        lunar = cnlunar.Lunar(d, godType="8char")
        month = lunar.lunarMonthCn.replace("大", "").replace("小", "")
        return f"农历{lunar.lunarYearCn}年{month}{lunar.lunarDayCn}"
    except Exception:
        return ""


def render_html(doc: BriefDocument) -> str:
    env = Environment(
        loader=PackageLoader("robin.render", "templates"),
        autoescape=True,  # 模板扩展名是 .j2，select_autoescape 不会命中，必须显式开启
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["stars"] = stars
    env.filters["cat"] = category_label
    tpl = env.get_template("brief.html.j2")
    return tpl.render(doc=doc, stars=stars)


def stars(n: int) -> str:
    n = max(0, min(5, int(n)))
    return "★" * n + "☆" * (5 - n)


def category_label(cat) -> str:
    from robin.models import CATEGORY_LABELS

    key = cat.value if hasattr(cat, "value") else str(cat)
    return CATEGORY_LABELS.get(key, "行业动态")


def render_markdown(doc: BriefDocument) -> str:
    lines: list[str] = []
    lines.append(f"# 知更早报 · {doc.run_date} {doc.weekday_cn}")
    if doc.lunar_str:
        lines.append(f"> {doc.lunar_str} ｜ 由 {doc.agent_count} 个 AI Agent 协作出版")
    lines.append("")
    if doc.epigraph:
        lines.append(f"**今日微语** —— {doc.epigraph}")
        lines.append("")
    if doc.headlines:
        lines.append("## 🔥 今日头条")
        lines.append("")
        for i, h in enumerate(doc.headlines, 1):
            label = category_label(h.category)
            lines.append(f"### {i}. [{h.title}]({h.url})")
            lines.append("")
            lines.append(f"{h.summary}")
            lines.append("")
            lines.append(f"> ✏️ **为什么重要**：{h.comment}")
            lines.append("")
            lines.append(f"*来源：{h.source_name} ｜ {label} ｜ 重要性 {'★' * h.importance}*")
            lines.append("")
    if doc.quick_news:
        lines.append("## ⚡ 一句话快讯")
        lines.append("")
        for i, q in enumerate(doc.quick_news, 1):
            lines.append(f"{i}. {q.text}（[来源]({q.url})）")
        lines.append("")
    if doc.analysis:
        lines.append("## 🔍 深度解读")
        lines.append("")
        for a in doc.analysis:
            lines.append(f"### [{a.title}]({a.url})")
            lines.append("")
            lines.append(f"**背景**：{a.background}")
            lines.append("")
            lines.append(f"**影响**：{a.impact}")
            lines.append("")
    if doc.yesterday:
        lines.append("---")
        lines.append(f"*昨日回顾：{doc.yesterday.title}*")
        lines.append("")
    lines.append("---")
    lines.append(f"*知更 Robin · Multi-Agent Daily Brief ｜ 数据来源：{'、'.join(doc.sources_used)}*")
    return "\n".join(lines)
