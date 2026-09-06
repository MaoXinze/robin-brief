# 版本记录（CHANGELOG）

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)（主版本.次版本.修订号）与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

- **主版本**：不兼容的架构/接口变更（如更换编排框架、存储引擎）
- **次版本**：向后兼容的新功能（如新增数据源、新增推送渠道）
- **修订号**：bug 修复与小的体验改进

---

## [v0.1.0] · 创刊号 — 2026-09-06

> 项目首个完整可用版本：多 Agent 流水线闭环（采集 → 提纯 → 撰写 → 出版 → 推送），
> 含全套测试、文档与容器化方案。

### 新增

**核心流水线（LangGraph 状态图编排，9 个 Agent）**
- 采集记者：Send API 动态并行 fan-out，单源失败错误隔离不阻塞整体；条数不足自动"宽松重采"（条件边循环，时间窗 30h→72h、阈值减半，仅触发一次）
- 去重管理员：四层漏斗（URL 归一 → 标题归一 → rapidfuzz 模糊聚类 → 近 3 天历史库），模糊区间 82~92 分的临界对交 LLM 语义裁决
- 分类编辑：7 类标签体系 + 涉及公司识别 + 非 AI 内容过滤
- 评分编辑：规则引擎（公司权重 × 事件类型 × 时效 + 有上限的热度加成）主导，LLM 仅 ±1 星校准并输出评分理由
- 摘要主笔：一句话中文摘要（≤60 字），严格基于原文（幻觉防线之一）
- 头条编辑：Top 3~5 头条 +「为什么重要」点评 + 今日微语；评分直选降级保证
- 深度评论员：1~2 个重大事件的「背景 + 影响」解读
- 快讯编辑：复用摘要产物零 LLM 成本，头条自动排除
- 出版发行：渲染双格式 → SQLite 归档 → 飞书推送；`stage_done` 完成标志做幂等守卫

**数据源（6 类适配器，配置化 sources.yaml）**
- RSS 通用适配器（机器之心 / 量子位 / 36氪 / TechCrunch / VentureBeat / OpenAI 博客）
- Hacker News（Algolia API，热度阈值过滤，宽松模式自动减半）
- arXiv（cs.AI / cs.CL，官方 Atom API）
- GitHub Trending（AI 关键词过滤，`headline_eligible` 控制只进快讯）
- 来源权重体系：影响去重保留策略与评分

**产物与交付**
- 「晨光纸感版」早报 HTML（单栏 680px 移动优先，无外部资源依赖，打印样式）+ Markdown 版
- `run_report.json` 运行报告：完整漏斗 / 各 Agent 耗时 / LLM token 用量 / 来源错误
- SQLite 归档（文章库 / 日报 / 运行记录）+「昨日回顾」连续阅读设计
- 飞书自定义机器人推送（交互卡片 + HMAC 加签）

**工程化**
- CLI：`robin run / demo / schedule / archive / init / version`
- `robin demo`：内置样例数据 + MockLLM 的全离线演示（无需 API Key 与网络）
- MockLLMClient：确定性规则式伪智能，与真实链路共用同一 pydantic 校验
- pytest 34 个用例（适配器解析 / 去重 / 评分 / 渲染 / 端到端全链路 / 异步检查点回归），离线 1.5s 跑完
- 结构化输出契约：pydantic Schema 校验 + 错误回示重试 + 三段式降级
- Dockerfile + .dockerignore，容器内实跑验证通过
- 全套中文文档：README + docs/01~08（含简历与面试指南）

### 修复

- 异步图 + 同步检查点：`ainvoke` 驱动下同步 `SqliteSaver` 抛 `NotImplementedError`，改用 `AsyncSqliteSaver`（aiosqlite）并新增回归测试
- SQLite 跨线程使用（LangGraph 线程池执行同步节点）：`check_same_thread=False` + 写锁
- LangGraph Send 必须挂在条件边上（普通节点返回 Send 列表抛 InvalidUpdateError）
- 中文标题归一后无空格分词，token 类相似度失效 → 模糊比对改用 `partial_ratio` 并重标定阈值
- URL 归一化对无查询参数的 URL 拼接 `None` 字符串导致同 URL 双哈希
- mock 客户端收到整段提示词导致 JSON 解析空转 → 载荷与规则分离（`<input>` 标签约定）
- 热度加成无上限导致高星仓库挤掉行业大事 → 加成上限 0.25 + `headline_eligible` 机制
- 摘要与标题同文时不再重复展示；英文截断改为词边界回退

### 已知限制（→ Roadmap）

- 质量评测依赖人工抽查，未建立标注评测集
- 定时依赖本机常驻进程，未接入 GitHub Actions
- 无 HTTP API 层（外部 App/小程序接入需先补 FastAPI）
- 财新（付费墙）与 X API（收费）未接入

---

<!-- 以下为新版本的记录模板（发布时删除本注释）
## [v0.2.0] · YYYY-MM-DD

### 新增
- （功能 + 一句话说明 + 动机）

### 变更
- （行为调整 + 影响面）

### 修复
- （bug + 根因 + 修法）

### 移除
- （弃用项）
-->
