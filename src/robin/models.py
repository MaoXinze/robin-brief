"""数据模型：流水线各阶段的实体定义。

设计说明：
- Article        —— 采集层的原始条目（来源、标题、链接、正文、时间）
- EnrichedArticle —— 在 Article 基础上叠加 分类/公司/评分/摘要 字段，
  由分类、评分、摘要三个 Agent 依次 model_copy(update=...) 产出新实例，
  保证每个阶段的产物不可变、可追溯（可信度优先原则）。
- BriefDocument  —— 出版层的结构化日报，是渲染层的唯一输入（内容与呈现分离）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Category(StrEnum):
    """新闻分类（分类编辑 Agent 的标签体系）。"""

    MODEL_RELEASE = "model_release"      # 模型发布
    FUNDING_MA = "funding_ma"            # 融资并购
    PRODUCT = "product"                  # 产品动态
    POLICY = "policy"                    # 政策监管
    OPEN_SOURCE = "open_source"          # 开源动态
    RESEARCH = "research"                # 研究论文
    OTHER = "other"                      # 其他


CATEGORY_LABELS: dict[str, str] = {
    Category.MODEL_RELEASE: "模型发布",
    Category.FUNDING_MA: "融资并购",
    Category.PRODUCT: "产品动态",
    Category.POLICY: "政策监管",
    Category.OPEN_SOURCE: "开源动态",
    Category.RESEARCH: "研究论文",
    Category.OTHER: "行业动态",
}


class Article(BaseModel):
    """采集层产出的原始文章条目。"""

    id: str = Field(description="全文唯一 ID（规范化 URL 的哈希）")
    source_id: str
    source_name: str
    source_weight: int = Field(default=3, description="来源权重（去重优先级/评分参考）")
    url: str
    title: str
    content: str = ""
    author: str = ""
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    points: int | None = Field(default=None, description="社区热度（如 HN points），无则 None")


class EnrichedArticle(Article):
    """分类/评分/摘要 Agent 依次填充后的文章。"""

    category: Category = Category.OTHER
    companies: list[str] = Field(default_factory=list)
    importance: int = Field(default=0, ge=0, le=5, description="重要性 1~5 星，0=未评分")
    score_reason: str = ""
    summary: str = ""
    is_ai: bool = True


class HeadlineView(BaseModel):
    """日报「今日头条」板块的单条视图。"""

    title: str
    summary: str
    comment: str = Field(description="头条编辑的一句点评：为什么重要")
    url: str
    source_name: str
    category: Category
    companies: list[str] = Field(default_factory=list)
    importance: int
    score_reason: str = ""


class QuickNewsView(BaseModel):
    """日报「一句话快讯」板块的单条视图。"""

    text: str
    url: str
    source_name: str
    category: Category


class AnalysisView(BaseModel):
    """日报「深度解读」板块的单条视图。"""

    title: str
    url: str
    source_name: str
    background: str = Field(description="事件背景")
    impact: str = Field(description="影响分析")


class YesterdayView(BaseModel):
    """「昨日回顾」单行视图。"""

    date: str
    title: str
    url: str = ""


class BriefDocument(BaseModel):
    """结构化日报 —— 渲染层的唯一输入（内容与呈现分离）。"""

    run_date: str = Field(description="YYYY-MM-DD")
    weekday_cn: str
    lunar_str: str = ""
    agent_count: int = 9
    epigraph: str = Field(default="", description="今日微语")
    headlines: list[HeadlineView] = Field(default_factory=list)
    quick_news: list[QuickNewsView] = Field(default_factory=list)
    analysis: list[AnalysisView] = Field(default_factory=list)
    yesterday: YesterdayView | None = None
    sources_used: list[str] = Field(default_factory=list)
    funnel: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime | None = None
    is_demo: bool = Field(default=False, description="mock 模式产出的演示版")


class RunReport(BaseModel):
    """单次运行报告（可观测性产物）。"""

    run_date: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_s: float = 0.0
    mock: bool = False
    status: str = "ok"  # ok | degraded | failed
    funnel: dict[str, int] = Field(default_factory=dict)
    agent_stats: dict[str, dict] = Field(default_factory=dict)
    source_errors: list[dict] = Field(default_factory=list)
    llm_usage: dict[str, int] = Field(default_factory=dict)
    output_files: dict[str, str] = Field(default_factory=dict)
