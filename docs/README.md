# docs 索引（临河镇）

> 本文件是设计文档的唯一入口。**2026-10-25 大整理**：M0–M6 的历史规划、审计、闭环、
> 预研与台账文档已删除，只保留仍在生效的活文档。删除内容可从 git 历史找回：
> `git log --diff-filter=D --name-only -- docs/`。
> 代码注释中的 `docs/api/m5-*`、`docs/security/m4-*` 等引用是历史出处，不再指向现存文件。
> 协议字段以 `shared/openapi.json` 与生成类型为准；数据字段以 ORM 模型与迁移为准。

## 1. 读顺序

| 顺序 | 读什么 | 为什么 |
|---|---|---|
| 1 | `../DESIGN.md` | 冻结基线 v2.1：六条约束 C1–C6、数据契约、测试分级、禁止事项 |
| 2 | `dev-workflow.md` | 环境、门禁命令、T1–T5、协议生成、Git 规范 |
| 3 | 所在域的文档（下表） | 对接时只读接口/边界段 |
| 4 | `../.orca/workflow.txt` + `../.orca/agent-registry.md` | 多 Agent 协作与域边界 |

## 2. 文档地图

### API / 协议

| 文档 | 内容 |
|---|---|
| `api/ws-protocol.md` | WebSocket 消息协议（出站/入站、字段、出戏边界） |
| `api/openapi.md` | HTTP 端点设计 |
| `api/anchors-api.md` | 玩家档锚点 HTTP 契约（字段/校验/状态码/错误形） |
| `api/versioning.md` | 协议版本策略 |
| `api/codegen.md` | OpenAPI → `shared/protocol.ts` 生成管线 |

### 架构 / 渲染

| 文档 | 内容 |
|---|---|
| `arch/voxel-execution-spec.md` | 等距体素 V0–V3 施工规格（**现行**） |
| `arch/voxel-transition-plan.md` | 体素转向方案与决策链（背景，冲突时以执行规格为准） |
| `arch/m7-render-art.md` | 渲染美术面（星露谷调性落地） |

### 数据

| 文档 | 内容 |
|---|---|
| `data/schema.md` | 数据库 schema 真相源 |
| `data/migration.md` | 迁移规范 |
| `data/event-sourcing.md` | 事件溯源设计 |

### 安全

| 文档 | 内容 |
|---|---|
| `security/threat-model.md` | 威胁模型 |
| `security/l1-whitelist.md` | L1 白名单与隐藏属性契约 |
| `security/self-unknown.md` | 自我未知规范（隐藏属性不可直陈） |
| `security/memory-scan.md` | 记忆写入禁词扫描与治理列 |
| `security/t1-sampling-10k.md` | T1 信息边界 10k 采样验收 |
| `security/t3-corpus.md` | T3 闸门对抗语料（**运行时真相源**，测试双向核对） |
| `security/t4-corpus.md` | T4 出戏探针语料（**运行时真相源**，测试双向核对） |
| `security/gameplay-integrity-audit-2026-10-21.md` | 最近一次玩法完整性审计 |

### 性能

| 文档 | 内容 |
|---|---|
| `perf/bench-plan.md` | 基准计划与 CI 口径 |
| `perf/budget.md` | 预算与红线口径 |
| `perf/hotspots.md` | 热点清单 |
| `perf/l1-spec.md` | L1 性能规格 |
| `perf/llm-monitoring.md` | LLM 成本/延迟监控口径 |
| `perf/baseline-epyc7763.json` | 定标机基线（**nightly 读取**） |
| `perf/runner.txt` | 定标机档位（**nightly 读取**） |

## 3. 文档纪律

- 不新建顶层文档；新增设计文档落在既有目录，并在此登记一行。
- 同一事实只写一处：决策写 DESIGN 或对应域文档，历史文档只作为输入。
- `t3-corpus.md`、`t4-corpus.md`、`perf/baseline-*.json`、`perf/runner.txt` 是机器读取的真相源，改动前先改测试/流程。
