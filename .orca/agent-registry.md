# Agent 注册表（.orca/agent-registry.md）

> 每个能力域只指定一个推荐 Agent，不重复分配。未覆盖能力保持空白，后续按需补充。
> **注册表内容仅由用户决定，任何 agent 不得随意更改。**

| 能力域 | 推荐 Agent | 评审 Agent |
|--------|-----------|-----------|
| 架构 / 代码质量 / 逻辑 / 测试 | **Claude** | Codex |
| 依赖 / 配置 / 文档 | **Claude** | Codex |
| 安全 / 合规 / 风险 | **Codex** | Claude |
| 性能 | **Claude** | Codex |
| 数据 / 数据库 | **Claude** | Codex |
| 接口 / 兼容性 | **Claude** | Codex |
| 前端 / 体验 / 发布 / 运维 | **Claude** | Codex |

## Agent → 工作树对应

| Agent | 工作树路径 | 分支 |
|-------|-----------|------|
| Claude（主导/组织） | E:/zxdevelop/project7（主工作树） | main |
| codex | E:/zxdevelop/.orca/worktrees/project7/codex | codex |

> **2026-10-20 用户裁定：六树 → 两树**（cline / kilo / opencode / pi 移除）。
> 本表已按该裁定收敛；四个历史树的目录与分支均不存在，勿再补回。
