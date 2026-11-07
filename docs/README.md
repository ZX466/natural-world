# docs 索引（临河镇）

> 本文件是现行文档入口。2026-11-07 清理已完成的施工计划与重复前端说明；有效规则保留在域文档，
> 历史步骤从 Git 查询，不再作为新任务。2026-10-25/26 已清理的 M0–M6 规划保持归档状态。
> 代码注释中的旧文档名是历史出处，不代表文件仍存在。
> 协议字段以 `shared/openapi.json` 与生成类型为准；数据字段以 ORM 模型与迁移为准。

## 1. 读顺序

| 顺序 | 读什么 | 为什么 |
|---|---|---|
| 1 | [设计基线](../DESIGN.md) | 冻结基线 v2.1：六条约束 C1–C6、数据契约、测试分级、禁止事项 |
| 2 | [开发流程](dev-workflow.md) | 环境、门禁、协议生成、清理与恢复、Git 规范 |
| 3 | 所在域的文档（下表） | 对接时只读接口/边界段 |
| 4 | [协作规则](../.orca/workflow.txt) + [注册表](../.orca/agent-registry.md) | 多 Agent 协作与域边界 |
| 5 | [工作树记忆](../.orca/memory.md) | 主树读 §0/§6，Codex 读 §7；当前任务还须核对本树 talking 与 Git |

## 2. 文档地图

### API / 协议

| 文档 | 内容 |
|---|---|
| [WS 协议](api/ws-protocol.md) | 出站/入站、字段、出戏边界 |
| [HTTP API](api/openapi.md) | HTTP 端点设计 |
| [锚点 API](api/anchors-api.md) | 玩家档锚点的字段、校验、状态码与错误形 |
| [版本策略](api/versioning.md) | 协议兼容规则与变更登记 |
| [类型生成](api/codegen.md) | OpenAPI → `shared/protocol.ts` 生成管线 |

### 架构 / 渲染

| 文档 | 内容 |
|---|---|
| [体素规格](arch/voxel-execution-spec.md) | 挖放、材料、可走面、拾取与渲染路线的现行规格 |
| [世界可辨认性与自生长](arch/world-liveliness-design.md) | 等距烘焙、NPC/材料/动作边界与完整 three.js 世界；`?terrain=three` 可选，默认 Phaser |
| [渲染美术](arch/m7-render-art.md) | 地图/美术来源、HTTP 地面和权威时钟等接口决策 |
| [离线补跑](arch/offline-progress.md) | 时间口径、上限、持久化与复跑证据 |
| [世界音效](arch/audio.md) | 默认静音、解锁、事件映射与亲听入口 |

### 数据

| 文档 | 内容 |
|---|---|
| [数据结构](data/schema.md) | 数据库 schema 真相源 |
| [迁移](data/migration.md) | 迁移规范 |
| [事件溯源](data/event-sourcing.md) | 世界事件、投影与快照边界 |

### 安全

| 文档 | 内容 |
|---|---|
| [威胁模型](security/threat-model.md) | 安全边界 |
| [L1 白名单](security/l1-whitelist.md) | L1 与隐藏属性契约 |
| [自我未知](security/self-unknown.md) | 隐藏属性不可直陈 |
| [记忆扫描](security/memory-scan.md) | 写入禁词扫描与治理列 |
| [T1 采样](security/t1-sampling-10k.md) | 信息边界 10k 采样验收 |
| [T3 语料](security/t3-corpus.md) | 运行时真相源，测试双向核对 |
| [T4 语料](security/t4-corpus.md) | 运行时真相源，测试双向核对 |

### 性能

| 文档 | 内容 |
|---|---|
| [基准方案](perf/bench-plan.md) | 基准计划与 CI 口径 |
| [性能预算](perf/budget.md) | 预算与红线口径 |
| [热点](perf/hotspots.md) | 性能热点清单 |
| [L1 性能](perf/l1-spec.md) | L1 性能规格 |
| [LLM 监控](perf/llm-monitoring.md) | 成本/延迟口径 |
| [定标基线](perf/baseline-epyc7763.json) | nightly 读取 |
| [定标机档位](perf/runner.txt) | nightly 读取 |

### 历史计划与审计

已完成的九份审计 `plan.md`、2026-11-05 主树施工计划和重复的 `client/README.md` 已退出工作树。
它们的有效内容按下表归位，执行步骤和旧门禁数字留在 Git 历史：

本地未跟踪的过期施工草稿与重复快照模板同时移除；审查结论、实测结果和复核脚本保留。

| 原内容 | 当前入口 |
|---|---|
| 前端目录说明 | [仓库 README](../README.md)；协议细节见类型生成 |
| 主树等距烘焙、气味与动作面施工 | 世界可辨认性与自生长 §3/§4/§6 |
| 体素绘制、逐层挖放、材料、土坎与移动 | 体素规格；协议演进见版本策略 |
| 快照治理、健康写入边界 | 事件溯源、数据结构 |
| 离线补跑与音效 | 离线补跑、世界音效 |

`.orca/audits/` 保留可复核的报告、JSON 结果与脚本；其中已跟踪摘要入库，运行日志与截图通常是本地文件。
最近实测入口为 `round23-2026-11-05/`、`round24-2026-11-06/`；不能把历史读数当作当前门禁。
临时私库可以重建，清理后重新实测应创建新库，不依赖残留 SQL 文件。
旧文件用 `git log --all -- <路径>` 找到历史版本，再用 `git show <提交号>:<路径>` 读取。

## 3. 文档纪律

- 不新建顶层文档；新增设计文档落在既有目录，并在此登记一行。
- 同一事实只写一处：决策写 DESIGN 或对应域文档，历史文档只作为输入。
- `t3-corpus.md`、`t4-corpus.md`、`perf/baseline-*.json`、`perf/runner.txt` 是机器读取的真相源，改动前先改测试/流程。
