# 🐦 知更 Robin

> 一群 AI 知更鸟，每天清晨为你报晓 AI 世界。

**知更 Robin** 是一个**多 Agent 协作的 AI 行业每日早报系统**：每天自动从多个渠道抓取 AI 领域资讯，由 9 个各司其职的 Agent（LangGraph 状态图编排）完成采集 → 提纯 → 撰写 → 出版，生成一份「晨光纸感」风格的早报页面，并可自动推送飞书。

![知更早报效果预览](docs/assets/brief-preview.png)

## ✨ 它解决什么问题

AI 从业者每天要花 30+ 分钟刷资讯，而真正值得看的大事件每天只有几条。知更用一条 Agent 流水线替你完成「刷 → 筛 → 读 → 判断」：

- **60 秒读完**：3~5 条头条 + 8~15 条一句话快讯 + 1~2 篇深度解读
- **有观点**：每条头条附「为什么重要」编辑点评，重大事件给「背景 + 影响」深度解读
- **可信**：摘要严格基于原文生成，每条保留来源与原文链接，重要性评分附带评分理由
- **可观测**：每次运行产出运行报告 —— 采集 N → 去重 M → 入报 K 的完整漏斗、各 Agent 耗时与 LLM token 消耗

## 🏗️ 架构一览

```
                   ┌─────────────────────────────────────────┐
                   │        LangGraph 状态图（blackboard）     │
  sources.yaml     │                                         │
  ┌──────────┐     │  START ──(Send 并行 fan-out)──► fetch_source ×N
  │ 机器之心  │     │                                    │    │
  │ 量子位    │────►│  dedup（四层去重）──不足──► relax 重采   │
  │ 36氪     │     │    │ 充足                            │    │
  │ TechCrunch│    │  classify（分类打标）                     │
  │ HN/ArXiv │     │    │                                 │    │
  │ GitHub   │     │  score（规则引擎 + LLM 校准评分）          │
  └──────────┘     │    │                                 │    │
                   │  summarize（一句话摘要）                   │
                   │    ├──────────► analyst（深度解读）──┐     │
                   │    └─► editor（头条+点评+微语）       │     │
                   │          └─► quicknews（快讯）─────┤     │
                   │                      publish（出版）◄     │
                   └─────────────────────────────────────────┘
                                │
              brief.html + brief.md + run_report.json + 飞书推送
```

9 个 Agent：采集记者 / 去重管理员 / 分类编辑 / 评分编辑 / 摘要主笔 / 头条编辑 / 深度评论员 / 快讯编辑 / 出版发行。

## 🚀 快速开始

```bash
# 1. 创建环境（uv + Python 3.12）
uv venv --python 3.12
uv pip install -r requirements-dev.txt
uv pip install -e . --no-deps

# 2. 离线演示：无需 API Key，一键生成示例早报
robin demo

# 3. 配置真实 LLM（默认 DeepSeek，任何 OpenAI 兼容端点均可）
robin init          # 生成 .env，填入 ROBIN_LLM_API_KEY
robin run           # 真实抓取 + LLM 生成今日早报

# 4. 每天 08:30 自动出版并推送飞书
robin schedule --at 08:30
```

打开 `output/<日期>/brief.html` 即是当日早报。

## 📦 每次运行的产物

| 文件 | 说明 |
|---|---|
| `output/<日期>/brief.html` | **主产物**：晨光纸感版早报页面（移动端优先，可直接浏览器打开） |
| `output/<日期>/brief.md` | Markdown 版，便于粘贴进飞书文档/邮件 |
| `output/<日期>/run_report.json` | 运行报告：漏斗统计、各 Agent 耗时、LLM token 用量、来源错误 |
| `data/robin.db` | SQLite 归档：文章库 / 历史日报 / 运行记录（`robin archive` 查看） |

## 🧪 质量

```bash
pytest            # 33 个测试：源适配器/去重/评分/渲染/端到端全链路
ruff check src    # 代码规范
```

测试策略：真实源结构录制成 fixtures（离线可复现）+ MockLLMClient（确定性伪智能），
端到端测试跑的是与生产完全相同的流水线，只替换网络与 LLM 两个边界。

## 🧭 更多文档

| 文档 | 内容 |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | 版本记录（每版新增/变更/修复） |
| [docs/01-项目概述.md](docs/01-项目概述.md) | 命名故事、产品哲学、功能清单 |
| [docs/02-系统架构.md](docs/02-系统架构.md) | 分层架构、数据流、技术选型对比 |
| [docs/03-多Agent设计详解.md](docs/03-多Agent设计详解.md) | 每个 Agent 的职责、输入输出、Prompt 设计 |
| [docs/04-数据模型与状态机.md](docs/04-数据模型与状态机.md) | 表结构、BriefState、图拓扑、容错降级 |
| [docs/05-运行与部署指南.md](docs/05-运行与部署指南.md) | Key 配置、CLI、定时、飞书机器人、Docker |
| [docs/06-简历与面试指南.md](docs/06-简历与面试指南.md) | STAR 简历条目 + 20+ 面试深挖题 |
| [docs/07-Roadmap.md](docs/07-Roadmap.md) | 后续演进方向 |
| [docs/08-开发日志.md](docs/08-开发日志.md) | 设计决策与踩坑记录 |

## 📄 License

MIT
