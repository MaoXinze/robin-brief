"""通用工具：URL/标题规范化、ID 生成、HTML 清洗、时区处理。"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_TRACKING_PARAMS = re.compile(r"^(utm_\w+|spm|fbclid|ref|ref_src|from|share_\w+|scene)$", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_tz(dt: datetime, tz_name: str = "Asia/Shanghai") -> datetime:
    """转换为指定时区（默认东八区）；naive 视为 UTC。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ZoneInfo(tz_name))


def strip_html(text: str) -> str:
    """去掉 HTML 标签与多余空白，保留纯文本。"""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(url: str) -> str:
    """URL 规范化：小写 host、去跟踪参数/锚点/尾斜杠 —— 用于去重与生成稳定 ID。"""
    url = (url or "").strip()
    m = re.match(r"^(https?://)([^/?#]+)([^?#]*)(\?[^#]*)?(#.*)?$", url, re.I)
    if not m:
        return url
    scheme, host, path, query, _frag = m.groups()
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    path = path.rstrip("/")
    query = query or ""
    if query:
        keep = []
        for kv in query.lstrip("?").split("&"):
            key = kv.split("=", 1)[0]
            if key and not _TRACKING_PARAMS.match(key):
                keep.append(kv)
        query = "?" + "&".join(keep) if keep else ""
    return f"{scheme}{host}{path}{query}"


def make_id(url: str) -> str:
    """以规范化 URL 生成全文唯一 ID。"""
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:16]


def norm_title(title: str) -> str:
    """标题归一化：仅保留中英文与数字，用于精确/模糊去重。"""
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", (title or "").lower())


def truncate(text: str, limit: int) -> str:
    """截断到 limit 字符并加省略号；英文尽量按词边界回退（避免词中硬截断）。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    # 断点落在英文字母中间时，回退到最近的空格（中文无空格则保持原位）
    if cut and text[limit - 1].isascii() and text[limit - 1].isalnum() and cut[-1].isascii() and cut[-1].isalnum():
        sp = cut.rfind(" ")
        if sp > limit * 0.5:
            cut = cut[:sp]
    return cut.rstrip() + "…"


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def keyword_hit(blob: str, kw: str) -> bool:
    """关键词命中：ASCII 词用前缀边界（\\bai 不会误中 training/said，但能命中 agents）；
    中文词用子串。"""
    kw = (kw or "").lower().strip()
    if not kw:
        return False
    if _CJK_RE.search(kw):
        return kw in blob
    return re.search(r"\b" + re.escape(kw), blob) is not None
