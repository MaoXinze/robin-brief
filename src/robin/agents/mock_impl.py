"""MockLLMClient 的规则式实现 —— 离线演示/测试用的"伪智能"。

设计原则：确定性（同输入同输出）、无网络、输出经过与真实链路相同的
pydantic 校验。每个 handler 接收 agent 的 user 载荷（已解析为 dict），
返回可直接 model_validate 的原生 dict。
"""

from __future__ import annotations

import re

from robin.models import Category
from robin.utils import truncate

# ---------------------------------------------------------------- 分类规则
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("funding_ma", ["融资", "收购", "并购", "ipo", "估值", "募资", "funding", "acquisition", "acquires", "raises", "merger", "buyout"]),
    ("model_release", ["大模型", "新模型", "模型发布", "基准", "刷榜", "benchmark", "gpt-", "claude", "gemini", "llama", "qwen", "deepseek-v", "kimi", "unveils", "releases model", "model release", "foundation model"]),
    ("policy", ["监管", "法案", "政策", "审查", "出口管制", "罚款", "反垄断", "regulation", "regulator", "lawsuit", "antitrust", "ban", "compliance"]),
    ("open_source", ["开源", "open source", "open-source", "open sourced", "apache", "mit license", "weights"]),
    ("research", ["论文", "研究", "arxiv", "paper", "study", "researchers"]),
    ("product", ["上线", "推出", "发布", "更新", "定价", "收费", "开放", "内测", "公测", "api", "launch", "launches", "rolls out", "shipping", "release", "beta", "pricing", "tool"]),
]

_COMPANY_TABLE: list[tuple[str, list[str]]] = [
    ("OpenAI", ["openai", "chatgpt", "gpt-5", "gpt-4", "o1", "sora", "sam altman", "奥特曼"]),
    ("Anthropic", ["anthropic", "claude", "dario"]),
    ("Google", ["google", "deepmind", "gemini", "alphabet"]),
    ("Meta", ["meta ", " meta", "llama", "zuckerberg"]),
    ("NVIDIA", ["nvidia", "英伟达", "cuda", "gb200", "b200", "黄仁勋"]),
    ("Microsoft", ["microsoft", "微软", "copilot", "azure ai"]),
    ("DeepSeek", ["deepseek", "深度求索"]),
    ("月之暗面", ["moonshot", "月之暗面", "kimi"]),
    ("智谱", ["智谱", "zhipu", "glm-", "chatglm"]),
    ("阿里", ["阿里", "alibaba", "qwen", "通义"]),
    ("腾讯", ["腾讯", "tencent", "混元", "hunyuan"]),
    ("字节跳动", ["字节", "bytedance", "豆包", "doubao", "seed"]),
    ("百度", ["百度", "baidu", "文心", "ernie"]),
    ("Mistral", ["mistral"]),
    ("xAI", [" xai", "grok", "马斯克", "musk"]),
    ("Manus", ["manus"]),
]

_AI_HINTS = [
    # 通用技术词
    "ai", "a.i.", "llm", "大模型", "模型", "人工智能", "智能", "gpt", "agent", "智能体",
    "算法", "机器学习", "深度学习", "ml", "neural", "transformer", "rag", "推理", "算力",
    # 头部公司/产品名（ASCII 走词边界，避免 training 里的 ai 之类误判）
    "openai", "anthropic", "claude", "gemini", "copilot", "nvidia", "英伟达",
    "deepseek", "llama", "qwen", "kimi", "mistral", "chatbot", "具身",
]


def _pick_category(blob: str) -> Category:
    for cat, kws in _CATEGORY_KEYWORDS:
        if any(k in blob for k in kws):
            return Category(cat)
    return Category.OTHER


def _pick_companies(blob: str) -> list[str]:
    found = []
    for name, kws in _COMPANY_TABLE:
        if any(k in blob for k in kws) and name not in found:
            found.append(name)
        if len(found) >= 3:
            break
    return found


def _is_ai(blob: str) -> bool:
    from robin.utils import keyword_hit

    return any(keyword_hit(blob, k) for k in _AI_HINTS)


# ---------------------------------------------------------------- handlers
def mock_classify(payload: dict) -> dict:
    items = payload.get("items", [])
    out = []
    for it in items:
        blob = f"{it.get('title', '')} {it.get('content', '')}".lower()
        is_ai = _is_ai(blob)
        out.append({
            "id": it["id"],
            "category": _pick_category(blob).value,
            "companies": _pick_companies(blob),
            "is_ai": is_ai,
        })
    return {"items": out}


def mock_score(payload: dict) -> dict:
    from robin.models import CATEGORY_LABELS

    out = []
    for it in payload.get("items", []):
        parts = []
        cat_label = CATEGORY_LABELS.get(it.get("category", "other"), "行业动态")
        parts.append(cat_label)
        companies = it.get("companies") or []
        if companies:
            parts.append(f"涉及{'、'.join(companies[:2])}")
        if it.get("points"):
            parts.append(f"热度{it['points']}")
        out.append({
            "id": it["id"],
            "importance": max(1, min(5, int(it.get("rule_score") or 3))),
            "reason": "规则评分校准：" + "，".join(parts),
        })
    return {"items": out}


def mock_summarize(payload: dict) -> dict:
    out = []
    for it in payload.get("items", []):
        content = re.sub(r"\s+", " ", it.get("content", "")).strip()
        first = re.split(r"[。！？!?]", content)[0] if content else ""
        base = first if len(first) >= 12 else it.get("title", "")
        out.append({"id": it["id"], "summary": truncate(base, 60)})
    return {"items": out}


_EPIGRAPH_POOL = {
    "model_release": "模型迭代一日千里，清晨一读，先人一步。",
    "funding_ma": "资本用真金白银投票，方向藏在新闻里。",
    "policy": "边界正在重画，规则值得每个人多看一眼。",
    "open_source": "开放的力量在于分享，生态因开源而茂盛。",
    "research": "每一篇论文，都可能是明天的产品。",
    "product": "产品落地，才是技术真正的考场。",
    "other": "信息过载的时代，挑选本身即是价值。",
}

_COMMENT_POOL = {
    "model_release": ["头部模型座次重排，开发者选型窗口再变。", "模型能力外溢，应用层成本曲线继续下移。", "竞争焦点从参数转向落地能力。"],
    "funding_ma": ["资本动向往往领先行业叙事半年。", "资源加速向头部聚集，赛道门槛抬升。", "并购是行业出清与整合的信号。"],
    "policy": ["合规成本将成为产品竞争力的一部分。", "监管框架落地速度影响商业化节奏。", "政策信号值得每个从业者纳入规划。"],
    "open_source": ["开源生态的飞轮再转一圈。", "开放权重正在改写竞争的边界。", "社区迭代速度再次快过闭源。"],
    "research": ["从论文到产品的时间差正在缩短。", "基础研究的突破往往先于此显现。", "值得关注其工程化复现的进展。"],
    "product": ["商业化路径逐渐清晰，落地质量是关键。", "产品化能力正成为新的护城河。", "用户侧反馈将决定其真实上限。"],
    "other": ["行业动态的拼图又多了一块。", "保持关注，趋势由细节累积。"],
}


def mock_editor(payload: dict) -> dict:
    cands = payload.get("candidates", [])
    max_n = int(payload.get("max_headlines", 5))
    cands = sorted(cands, key=lambda c: (-(c.get("importance") or 0), -(c.get("points") or 0)))
    headlines, seen_cat = [], {}
    for c in cands:
        cat = c.get("category", "other")
        pool = _COMMENT_POOL.get(cat) or _COMMENT_POOL["other"]
        idx = seen_cat.get(cat, 0)
        seen_cat[cat] = idx + 1
        headlines.append({"id": c["id"], "comment": truncate(pool[idx % len(pool)], 40)})
        if len(headlines) >= max_n:
            break
    top_cat = cands[0].get("category", "other") if cands else "other"
    return {"headlines": headlines, "epigraph": _EPIGRAPH_POOL.get(top_cat, _EPIGRAPH_POOL["other"])}


def mock_analyst(payload: dict) -> dict:
    it = payload.get("item", {})
    title = it.get("title", "该事件")
    summary = it.get("summary", "")
    companies = "、".join(it.get("companies") or []) or "相关厂商"
    background = (
        f"{title}。{summary} 从行业脉络看，{companies}近年在该方向持续投入，"
        f"本次事件并非孤立节点，而是过去数月技术迭代与市场竞争共同作用的结果；"
        f"同类动作此前已有先例，行业对相关进展保持了高度关注。"
        f"（mock 演示文本，真实运行时由 LLM 基于原文撰写）"
    )
    impact = (
        "短期看，这一消息将直接影响相关赛道的竞争节奏，同业厂商大概率加快跟进与响应；"
        "中长期看，其真正的影响取决于落地细节：产品化的质量、成本曲线的变化以及用户真实反馈。"
        "建议持续关注后续两周的跟进动作与公开数据。"
        "（mock 演示文本）"
    )
    return {"background": background, "impact": impact}


_PRODUCT_TOKEN_RE = re.compile(r"(?i)(v\d+|gpt-?\d[\w.]*|gb\d+|glm-?\d|llama\s?\d|claude\s?\d|kimi\s?k\d)")


def mock_dedup_judge(payload: dict) -> dict:
    """临界重复判定的 mock 近似：高相似度，或「同公司 + 同产品代号」即判同事件。

    真实链路由 LLM 做语义判断，这里只是无网络环境下的规则近似。
    """
    pairs = []
    for p in payload.get("pairs", []):
        a, b = (p.get("title_a") or "").lower(), (p.get("title_b") or "").lower()
        ratio = p.get("ratio", 0)
        same = ratio >= 87
        if not same and ratio >= 55:
            from robin.agents.mock_impl import _pick_companies

            co_a, co_b = set(_pick_companies(a)), set(_pick_companies(b))
            tok_a = set(_PRODUCT_TOKEN_RE.findall(a))
            tok_b = set(_PRODUCT_TOKEN_RE.findall(b))
            same = bool(co_a & co_b) and bool(tok_a & tok_b)
        pairs.append({"a": p["a"], "b": p["b"], "same": same})
    return {"pairs": pairs}


MOCK_HANDLERS = {
    "classifier": mock_classify,
    "scorer": mock_score,
    "summarizer": mock_summarize,
    "editor": mock_editor,
    "analyst": mock_analyst,
    "dedup": mock_dedup_judge,
}
