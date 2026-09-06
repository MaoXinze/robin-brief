"""Agent 层：流水线每个节点的工厂函数（依赖注入：LLM 客户端 / 配置 / 数据库）。"""

from robin.agents.analyst import make_analyze_agent
from robin.agents.classifier import make_classify_agent
from robin.agents.collector import dispatch_collect, make_fetch_source, relax_refetch
from robin.agents.dedup import make_dedup_agent
from robin.agents.editor import make_edit_agent
from robin.agents.publisher import make_publisher_node
from robin.agents.quicknews import make_quicknews_agent
from robin.agents.scorer import make_score_agent
from robin.agents.summarizer import make_summarize_agent

__all__ = [
    "dispatch_collect", "make_fetch_source", "relax_refetch",
    "make_dedup_agent", "make_classify_agent", "make_score_agent",
    "make_summarize_agent", "make_edit_agent", "make_analyze_agent",
    "make_quicknews_agent", "make_publisher_node",
]
