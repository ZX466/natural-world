# docs 索引（临河镇）

> 本文件是设计文档的唯一入口。**2026-10-25/26 大整理**：M0–M6 的规划、审计、闭环、
> 预研与台账文档已删除，`voxel-transition-plan.md` 已并入执行规格，只保留仍在生效的
> 活文档。删除内容可从 git 历史找回：`git log --diff-filter=D --name-only -- docs/`。
> 代码注释里出现的已删文档名是历史出处，不代表文件仍存在。
> 协议字段以 `shared/openapi.json` 与生成类型为准；数据字段以 ORM 模型与迁移为准。

## 1. 读顺序

| 顺序 | 读什么 | 为什么 |
|---|---|---|
| 1 | `../DESIGN.md` | 冻结基线 v2.1：六条约束 C1–C6、数据契约、测试分级、禁止事项 |
| 2 | `dev-workflow.md` | 环境、门禁命令、T1–T5、协议生成、Git 规范 |
| 3 | 所在域的文档（下表） | 对接时只读接口/边界段 |
| 4 | `../.orca/workflow.txt` + `../.orca/agent-registry.md` | 多 Agent 协作与域边界 |
| 5 | `../.orca/memory.md` §0 | 当前 HEAD / 协议版本 / 门禁数字 / 待人工验收 |

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
| `arch/voxel-execution-spec.md` | 等距体素 V0–V3 施工规格 + 决策链（**已收官**，历史执行真相源；§0 行号已漂移，按符号名 grep） |
| `arch/world-liveliness-design.md` | 世界可辨认性与自生长（2026-11-05 用户验收驱动；A 等距烘焙 / B 后端五项 / C three.js 自由视角世界已于 2026-11-06 实现，**2026-11-07 验收后成为默认**，`?terrain=phaser` 回滚） |
| `arch/m7-render-art.md` | M7 渲染面**裁决留档**：只剩仍生效的 R2/R3/R8 三条，施工细节已随管线退役压缩 |
| `arch/character-model-3d-plan.md` | 人物 3D 化的**实际形态**与后续档位（默认已启用，`?avatar3d=0` 回滚；当初的分档估算已归档） |
| `arch/offline-progress.md` | 停服补跑的时间口径、上限（默认一游戏小时，`LZ_OFFLINE_CATCHUP_MAX_TICKS` 可调）、持久化与可复跑证据 |
| `arch/audio.md` | 世界音效的默认静音、交互解锁、事件映射与亲听入口 |
| `../vendor/linhe-lre-sdk/README.md` | 外部 LRE-DT100 试车台 SDK 原件清单、接线边界与已知不符之处（**接线状态以该文件为准**） |

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

### 轮次审计（`../.orca/audits/`，入库）

按轮次归档的施工证据（`plan.md` + `acceptance.json`，含真实地图探针数值与截图），
共 20 个目录，按日期命名。**不是设计真相源**——只用于复现某一轮的实测口径。
近期几轮：`walk-verify-2026-11-08/`（走跑/跳跃实机读数）、
`three-acceptance-2026-11-07/`（three.js 默认渲染验收）、
`acceptance-2026-11-04/`（浏览器实机 7 项 + 两条缺陷现场；`retell-after.cjs` 可复跑）、
`snapshot-governance-2026-10-31/`（热保留 3946→9 行、events 零删除；`measure.py` 可复跑）。
找某一轮先 `ls .orca/audits/`，不要在本文件里找全表。

`.orca/audits/motion-smoothness-2026-11-07/` 只留 `REPORT.md`（本地 ignored，不入库）：
移动连贯性的根因数值、三种方案被否的实测读数、最终方案与已知遗留。

## 3. 文档纪律

- 不新建顶层文档；新增设计文档落在既有目录，并在此登记一行。
- 同一事实只写一处：决策写 DESIGN 或对应域文档，历史文档只作为输入。
- `t3-corpus.md`、`t4-corpus.md`、`perf/baseline-*.json`、`perf/runner.txt` 是机器读取的真相源，改动前先改测试/流程。
- **执行计划不长期保留**：一次性的实施计划在该轮收编后删除，结论并入本域文档或
  `.orca/memory.md`。考古走 `git log`。`world-liveliness-design.md` 是该轮的设计真相源，
  计划只是它的执行单。
- **文档写完即回写**：实施完成后把「待决方案」改写成「实际形态」，删掉已退役的分支。
  保留死内容会让下一个读者（包括 AI）按已删除的路径施工——`m7-render-art.md` 与
  `character-model-3d-plan.md` 都是这样压缩的。
