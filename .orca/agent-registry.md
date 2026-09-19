# Agent 注册表（.orca/agent-registry.md）

> 每个能力域只指定一个推荐 Agent，不重复分配。未覆盖能力保持空白，后续按需补充。
> **注册表内容仅由用户决定，任何 agent 不得随意更改。**

| 能力域 | 推荐 Agent | 评审 Agent |
|--------|-----------|-----------|
| 架构 / 代码质量 / 逻辑 / 测试 | **Claude** | Codex |
| 依赖 / 配置 / 文档 | **cline** | Claude |
| 安全 / 合规 / 风险 | **Codex** | cline |
| 性能 | **Pi** | cline |
| 数据 / 数据库 | **opencode** | Codex |
| 接口 / 兼容性 | **kilo** | Claude |
| 前端 / 体验 / 发布 / 运维 | **Claude** | codex |

## Agent → 工作树对应

| Agent | 工作树路径 | 分支 |
|-------|-----------|------|
| Claude（主导/组织） | E:/zxdevelop/project7（主工作树） | main |
| cline | E:/zxdevelop/.orca/worktrees/project7/cline | ZX466/cline |
| codex | E:/zxdevelop/.orca/worktrees/project7/codex | ZX466/codex |
| kilo | E:/zxdevelop/.orca/worktrees/project7/kilo | ZX466/kilo |
| opencode | E:/zxdevelop/.orca/worktrees/project7/opencode | ZX466/opencode |
| pi | E:/zxdevelop/.orca/worktrees/project7/pi | ZX466/pi |
