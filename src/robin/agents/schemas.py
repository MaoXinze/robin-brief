"""各 Agent 的结构化输出 Schema（pydantic 校验 + 重试的契约）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from robin.models import Category


class ClassifyItem(BaseModel):
    id: str
    category: Category = Category.OTHER
    companies: list[str] = Field(default_factory=list)
    is_ai: bool = True


class ClassificationBatch(BaseModel):
    items: list[ClassifyItem] = Field(default_factory=list)


class ScoreItem(BaseModel):
    id: str
    importance: int = Field(ge=1, le=5)
    reason: str = ""


class ScoreBatch(BaseModel):
    items: list[ScoreItem] = Field(default_factory=list)


class SummaryItem(BaseModel):
    id: str
    summary: str


class SummaryBatch(BaseModel):
    items: list[SummaryItem] = Field(default_factory=list)


class HeadlinePick(BaseModel):
    id: str
    comment: str = ""


class EditorialPlan(BaseModel):
    headlines: list[HeadlinePick] = Field(default_factory=list)
    epigraph: str = ""


class AnalysisOut(BaseModel):
    background: str
    impact: str


class DupPair(BaseModel):
    a: str
    b: str
    same: bool = False


class DupJudgeBatch(BaseModel):
    pairs: list[DupPair] = Field(default_factory=list)
