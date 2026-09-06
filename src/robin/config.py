"""配置系统：环境变量（.env / ROBIN_ 前缀）+ 数据源 YAML。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SOURCES_PATH = Path("config/sources.yaml")


class Settings(BaseSettings):
    """全局运行配置。所有路径相对项目根（即运行 CLI 时的工作目录）。"""

    model_config = SettingsConfigDict(env_prefix="ROBIN_", env_file=".env", extra="ignore")

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.3
    llm_max_retries: int = 3

    # 飞书推送（留空则跳过）
    feishu_webhook_url: str = ""
    feishu_secret: str = ""

    # 存储 / 输出
    db_path: str = "data/robin.db"
    output_dir: str = "output"
    checkpoint_path: str = "data/checkpoints.sqlite"

    # 流水线参数
    min_articles: int = Field(default=10, description="采集+去重后少于该条数则触发宽松重采")
    collect_window_hours: int = 30
    relaxed_window_hours: int = 72
    timezone: str = "Asia/Shanghai"
    agent_count: int = 9

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_api_key) and "your-" not in self.llm_api_key


class SourceCfg(BaseModel):
    """单个数据源的配置（对应 sources.yaml 里的一行）。"""

    id: str
    name: str
    type: str  # rss | hackernews | arxiv | github_trending
    url: str = ""
    query: str = ""
    min_points: int = 40
    categories: list[str] = Field(default_factory=list)
    max_results: int = 20
    language: str = ""
    ai_keywords: list[str] = Field(default_factory=list)
    weight: int = 3
    lang: str = "en"
    enabled: bool = True
    headline_eligible: bool = Field(default=True, description="该源条目是否可进入今日头条（False 则只进快讯）")
    window_hours: int | None = None


def load_sources(path: Path | str = DEFAULT_SOURCES_PATH) -> list[SourceCfg]:
    """解析 sources.yaml；文件缺失或为空时返回空列表（流水线仍可运行）。"""
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return [SourceCfg(**item) for item in data.get("sources", []) if item.get("enabled", True)]
