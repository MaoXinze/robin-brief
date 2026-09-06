"""去重管理员 Agent：四层去重 —— URL 精确 / 标题精确 / 模糊聚类 / 历史库。

模糊比对使用 partial_ratio（中文标题归一后无空格分词，token 类算法不适用）：
- ≥92 直接判重；82~92 进入 LLM 临界裁决；<82 保留
- 无 LLM（单元测试）时用 87 分阈值近似
- 历史库比对近 3 天已报道条目（≥93 判重）
"""

from __future__ import annotations

import logging

from rapidfuzz import fuzz, process

from robin.agents._common import call_llm
from robin.agents.schemas import DupJudgeBatch
from robin.config import Settings
from robin.llm import LLMClient
from robin.models import Article
from robin.utils import norm_title

logger = logging.getLogger(__name__)

FUZZY_HARD = 92        # ≥ 视为重复
FUZZY_SOFT = 82        # 进入 LLM 裁决区间
FUZZY_FALLBACK = 87    # 无 LLM 时的近似阈值
FUZZY_HISTORY = 93     # 与近 3 天历史比对阈值


def _priority(a: Article) -> tuple:
    return (-a.source_weight, -(a.points or 0), -(a.published_at or a.fetched_at).timestamp() if (a.published_at or a.fetched_at) else 0)


def dedup_articles(
    articles: list[Article],
    history_norms: set[str] | None = None,
    llm: LLMClient | None = None,
) -> tuple[list[Article], dict[str, int]]:
    """返回 (去重后条目, 漏斗统计)。单元测试直接调用本函数。"""
    history_norms = history_norms or set()
    stats = {"collected": len(articles), "after_url": 0, "after_title": 0,
             "after_fuzzy": 0, "after_history": 0, "kept": 0}

    ordered = sorted([a for a in articles if a.title], key=_priority)

    # 第 1 层：规范化 URL 精确去重（article.id 即规范化 URL 哈希）
    seen_ids: set[str] = set()
    lvl1 = []
    for a in ordered:
        if a.id in seen_ids:
            continue
        seen_ids.add(a.id)
        lvl1.append(a)
    stats["after_url"] = len(lvl1)

    # 第 2 层：标题归一精确去重
    seen_titles: set[str] = set()
    lvl2 = []
    for a in lvl1:
        tnorm = norm_title(a.title)
        if tnorm and tnorm in seen_titles:
            continue
        if tnorm:
            seen_titles.add(tnorm)
        lvl2.append(a)
    stats["after_title"] = len(lvl2)

    # 第 3 层：模糊聚类 + LLM 临界裁决
    kept: list[Article] = []
    kept_norms: list[str] = []
    borderline: list[tuple[Article, Article, int]] = []
    hard_dups = 0
    for a in lvl2:
        tnorm = norm_title(a.title)
        best_idx = None
        best_score = 0
        if kept_norms and tnorm:
            match = process.extractOne(tnorm, kept_norms, scorer=fuzz.partial_ratio)
            if match:
                best_score = int(match[1])
                best_idx = int(match[2])
        if best_score >= FUZZY_HARD:
            hard_dups += 1
            continue
        if FUZZY_SOFT <= best_score < FUZZY_HARD and best_idx is not None:
            borderline.append((a, kept[best_idx], best_score))
            continue
        kept.append(a)
        kept_norms.append(tnorm)
    stats["after_fuzzy"] = len(lvl2) - hard_dups

    if borderline:
        judged = _judge_pairs(borderline, llm)
        for cand, _champ, _r in judged:
            kept.append(cand)

    # 第 4 层：近 3 天历史库
    final: list[Article] = []
    if history_norms:
        hist_list = list(history_norms)
        for a in kept:
            tnorm = norm_title(a.title)
            if tnorm and tnorm in history_norms:
                continue
            if tnorm and hist_list:
                hit = process.extractOne(tnorm, hist_list, scorer=fuzz.partial_ratio,
                                         score_cutoff=FUZZY_HISTORY)
                if hit:
                    continue
            final.append(a)
    else:
        final = kept
    stats["after_history"] = len(final)
    stats["kept"] = len(final)
    return final, stats


def _judge_pairs(
    pairs: list[tuple[Article, Article, int]], llm: LLMClient | None
) -> list[Article]:
    """临界对的最终裁决：LLM 判同事件的并入（丢弃候选），否则保留。"""
    if llm is None:
        return [cand for cand, _champ, r in pairs if r < FUZZY_FALLBACK]
    payload = {
        "pairs": [
            {"a": cand.id, "b": champ.id, "ratio": r, "title_a": cand.title, "title_b": champ.title}
            for cand, champ, r in pairs
        ]
    }
    try:
        batch: DupJudgeBatch = call_llm(llm, "dedup", DupJudgeBatch, "dedup", payload=payload)
        same_ids = {p.a for p in batch.pairs if p.same}
        return [cand for cand, _champ, _r in pairs if cand.id not in same_ids]
    except Exception as e:
        logger.warning("[去重] LLM 裁决失败，退回阈值近似: %s", e)
        return [cand for cand, _champ, r in pairs if r < FUZZY_FALLBACK]


def make_dedup_agent(llm: LLMClient | None, settings: Settings):
    """图节点工厂：注入 LLM 与配置。"""

    def dedup_agent(state: dict) -> dict:
        history = set(state.get("history_norms") or [])
        kept, stats = dedup_articles(state["articles"], history, llm=llm)
        logger.info("[去重] %s -> %s 条 %s", stats["collected"], stats["kept"], {
            k: v for k, v in stats.items() if k != "collected"
        })
        return {"deduped": kept, "dedup_stats": stats}

    return dedup_agent
