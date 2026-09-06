"""飞书自定义机器人推送：交互卡片消息，支持加签。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import httpx

from robin.models import BriefDocument
from robin.render.engine import category_label


def _sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_card(doc: BriefDocument, md_limit: int = 9000) -> dict:
    """构造飞书 interactive 卡片。正文超长时自动截断（完整内容看 HTML 版）。"""
    elements: list[dict] = []
    if doc.epigraph:
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"今日微语：{doc.epigraph}"}]})
    for i, h in enumerate(doc.headlines, 1):
        lines = [f"**{i}. [{h.title}]({h.url})**", h.summary]
        if h.comment:
            lines.append(f"✏️ {h.comment}")
        lines.append(f"<font color='grey'>{h.source_name} · {category_label(h.category)} · {'★' * h.importance}</font>")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
    if doc.quick_news:
        qn_lines = [f"{i}. {q.text}" for i, q in enumerate(doc.quick_news, 1)]
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**⚡ 一句话快讯**\n" + "\n".join(qn_lines)}})
    footer = f"由 {doc.agent_count} 个 Agent 协作出版 · 完整版见 brief.html"
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": footer}]})

    total = sum(len(str(e)) for e in elements)
    if total > md_limit:
        elements = elements[: max(3, len(doc.headlines))] + [
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "内容较长已截断，请查看完整版日报"}]}
        ]
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "turquoise",
                "title": {"tag": "plain_text", "content": f"🐦 知更早报 · {doc.run_date} {doc.weekday_cn}"},
            },
            "elements": elements,
        },
    }


def push_brief(webhook_url: str, secret: str, doc: BriefDocument) -> tuple[bool, str]:
    """推送日报卡片到飞书群。返回 (是否成功, 说明)。"""
    if not webhook_url:
        return False, "未配置飞书 Webhook"
    payload = build_card(doc)
    if secret:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = _sign(secret, ts)
    try:
        resp = httpx.post(webhook_url, json=payload, timeout=15)
        data = resp.json()
        ok = resp.status_code == 200 and data.get("code") in (0, None) and data.get("StatusCode") in (0, None)
        return ok, str(data)[:200]
    except Exception as e:
        return False, f"推送异常: {e}"
