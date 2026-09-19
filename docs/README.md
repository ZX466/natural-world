# docs 索引（临河镇）

> 本文件是设计文档的唯一入口。**能力域归属以 `.orca/agent-registry.md` 为准**（该表只由用户决定）。
> 不要新建顶层文档、不要复制粘贴内容；新增设计文档请落在既有目录下并在此登记一行。

## 1. 读顺序（新人/新对话按此顺序）

| 顺序 | 读什么 | 为什么 |
|---|---|---|
| 1 | `DESIGN.md`（仓库根，v2.1 冻结基线） | 先读 §0 修订摘要、§2 六条约束、§4 技术栈、§5 目录、§19 禁止事项。**这是唯一基线**，其他文档都是它的展开 |
| 2 | `docs/arch/m0-core.md`、`docs/arch/m0-client.md` | M0 要落地的东西：确定性内核与前端渲染闭环 |
| 3 | 你所在域的文档（下表 §data / §api / §security / §perf） | 需要对接别域时，只读它的「接口/边界」段 |
| 4 | `docs/dev-workflow.md` | 环境与常用命令（uv / pytest / ruff / pyright / npm / vitest） |
| 5 | `.orca/workflow.txt` + `.orca/agent-registry.md` | 多 Agent 协作与域边界 |

## 2. 文档地图

| 文档 | 能力域（owner） | 状态 | 一句话内容 |
|---|---|---|---|
| `DESIGN.md` | 架构（Claude） | ✅ main | 冻结基线 v2.1：六条约束 C1–C6（含守卫测试与里程碑）、架构、数据契约、感知/认知/战斗/存档/测试分级 T1–T5、里程碑 M0–M6、禁止事项 |
| `docs/arch/m0-core.md` | 架构（Claude） | ✅ main | M0 内核：clock（TimeScale/累加器）/ rng（分流 PCG64）/ entropy（注入走 apply）/ events（EventBus 唯一写路径）/ tick loop（异步驱动 + 同步确定性 tick + 固定执行序）/ map（chunk）/ pathfinding（A* + chunk 失效）/ EventStore Protocol 边界 |
| `docs/arch/m0-client.md` | 前端/体验（Claude） | ✅ main | M0 渲染闭环：Phaser(canvas 世界) 与 React(canvas 外 UI) 经 Zustand store 单桥、对象池、插值、摄像机；M0 边界与出戏字段禁令 |
| `docs/security/m1-checklist.md` | 安全/合规/风险（Codex） | ⏳ 待收编（codex 分支） | M1 安全检查清单 27 项：K1–K8 密钥（Fernet/主密钥/日志脱敏/SSRF）、M1-A–I 出戏断言、O1–O6 LLM 输出边界、W1–W5 WS 白名单、G1–G4 通用 |
| `docs/security/threat-model.md` | 安全/合规/风险（Codex） | ⏳ 待收编（codex 分支） | 轻量威胁模型：4 资产 / 10 威胁→缓解映射 / 出戏防线 5 层 / 非目标 / Top-5 技术安全风险 |
| `docs/perf/budget.md` | 性能（Pi） | ⏳ 待收编（pi 分支） | 每 tick 16.6ms（1x=60tick/s）预算表：7 子系统名义 6.95ms / 上限 12.15ms；4x/16x 与战斗时间尺特例；采集告警点 |
| `docs/perf/hotspots.md` | 性能（Pi） | ⏳ 待收编（pi 分支） | 热点预判 H-1–H-6：感知传播分区/增量、L0 向量化、SQLite append-only 批量写与索引、WS 增量合批、超速倍率、LLM 异步延迟（信息性） |
| `docs/perf/bench-plan.md` | 性能（Pi） | ⏳ 待收编（pi 分支） | 基准方案：M0 必带 bench 清单、pytest-benchmark/真实 tick loop harness 选型、回归阈值、nightly 节奏、已知不可测项 |
| `docs/data/schema.md` | 数据/数据库（opencode） | ✅ main | SQLite schema：事件日志（append-only）/分支树/快照分层/玩家 anchor/NPC 记忆 + sqlite-vec 占位；索引与约束对齐 §6 契约 |
| `docs/data/event-sourcing.md` | 数据/数据库（opencode） | ✅ main | 事件溯源：`apply(event)` 唯一写路径、读档重放流程、回放确定性（RNG/熵随事件落库） |
| `docs/data/migration.md` | 数据/数据库（opencode） | ✅ main | Alembic 迁移策略（async env.py / alembic.ini / 首版迁移骨架） |
| `docs/api/ws-protocol.md` | 接口/兼容性（kilo） | ⏳ 待收编（kilo 分支） | WS 消息协议：消息类型清单与字段 schema、出戏边界（哪些字段绝不外发） |
| `docs/api/openapi.md` | 接口/兼容性（kilo） | ⏳ 待收编（kilo 分支） | HTTP 端点设计：设置页 / Profile 管理 / 存档 anchor CRUD；api_key 只在后端流转 |
| `docs/api/codegen.md` | 接口/兼容性（kilo） | ⏳ 待收编（kilo 分支） | OpenAPI → `shared/protocol.ts` 生成管线（openapi-typescript）、CI 三道守卫（漂移/banner/禁手写） |
| `docs/api/versioning.md` | 接口/兼容性（kilo） | ⏳ 待收编（kilo 分支） | 协议版本策略：WS version 字段/协商方式，client 与 sim 独立演进 |
| `docs/dev-workflow.md` | 依赖/配置/文档（cline） | ✅ main | 环境与常用命令：uv/pytest/ruff/pyright、npm/tsc/eslint/vitest、T1–T5 marker 跑法、bench nightly 跑法、CI 对应关系 |

状态图例：✅ main = 已在 main 分支；⏳ 待收编 = 已在对应 agent 分支产出，等 Claude（主导）统一收编。

## 3. 跨域接口对接点（改了要同时通知对方）

| 接口 | 提供方 → 消费方 | 契约落点 |
|---|---|---|
| 事件/快照存储 | 数据（opencode）→ 内核（Claude） | `EventStore` Protocol（`docs/arch/m0-core.md` §8）↔ `docs/data/schema.md`；实现：`sim/core/persistence/`（已进 main） |
| WS 消息 schema | 接口（kilo）→ 前端（Claude） | `docs/api/ws-protocol.md` → `shared/protocol.ts`（生成物） |
| 禁词表 | 安全（Codex）→ 认知层（Claude） | `docs/security/m1-checklist.md` M1-A/B/D ↔ prompt 装配唯一出口 |
| tick 预算 | 性能（Pi）→ 内核（Claude） | `docs/perf/budget.md` §1 ↔ `docs/arch/m0-core.md` §5 固定执行序 |
| 依赖与 CI | 配置（cline）→ 全员 | `pyproject.toml` / `uv.lock` / `client/package.json` / `.github/workflows/` |

## 4. 约束提醒（写文档时最容易破的两条）

- `DESIGN.md` §18：**本文档为冻结基线**，新想法先进「MVP 后清单」，不回写里程碑——改基线要走 v2.x 修订记录。
- `DESIGN.md` §19 禁止事项与 §10 界面双层铁律是**文档也必须遵守**的：设计文档里不要引入「把结构化世界状态喂给 LLM」「戏内界面出元信息」这类写法。
