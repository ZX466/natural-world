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
| `docs/security/m1-checklist.md` | 安全/合规/风险（Codex） | ✅ main | M1 安全检查清单 27 项：K1–K8 密钥（Fernet/主密钥/日志脱敏/SSRF）、M1-A–I 出戏断言、O1–O6 LLM 输出边界、W1–W5 WS 白名单、G1–G4 通用 |
| `docs/security/threat-model.md` | 安全/合规/风险（Codex） | ✅ main | 轻量威胁模型：4 资产 / 10 威胁→缓解映射 / 出戏防线 5 层 / 非目标 / Top-5 技术安全风险 |
| `docs/security/t3-corpus.md` | 安全/合规/风险（Codex） | ✅ main | T3 出戏对抗样本集：分类攻击语料（元信息直问/诱导/存档意识/操纵感/时间戳探针/身体否定）；**期望响应形态 = 第一人称世界内回应，不是拒绝话术**；M1-C/D/E/I 的 fixture 来源 |
| `docs/security/memory-scan.md` | 安全/合规/风险（Codex） | ✅ main | 记忆写入前禁词扫描设计稿（架构域已批原则方向，M1 照此落地）：挂记忆写入路径、复用禁词表、命中改写优先拒写、append-only 用「标记无效+重写」补救 |
| `docs/perf/budget.md` | 性能（Pi） | ✅ main（M1 分解在 ZX466/pi） | 每 tick 16.6ms（1x=60tick/s）预算表：7 子系统名义 7.00ms / 上限 12.35ms（M1 分解）；4x/16x 与战斗时间尺特例；采集告警点 |
| `docs/perf/hotspots.md` | 性能（Pi） | ✅ main | 热点预判 H-1–H-6：感知传播分区/增量、L0 向量化、SQLite append-only 批量写与索引、WS 增量合批、超速倍率、LLM 异步延迟（信息性） |
| `docs/perf/bench-plan.md` | 性能（Pi） | ✅ main | 基准方案：M0 必带 bench 清单、pytest-benchmark/真实 tick loop harness 选型、回归阈值、nightly 节奏、已知不可测项 |
| `docs/perf/llm-monitoring.md` | 性能（Pi） | 🆕 ZX466/pi（F05，待收编） | LLM 异步延迟监控口径：structlog 事件名 `llm.request/response/retry/timeout/error/cache_hit/decision` + 字段清单（不记 api_key/prompt 明文）；P95<8s、单决策<2k tok、cache_hit>50%；**C06 LLM 客户端照抄接入** |
| `docs/data/schema.md` | 数据/数据库（opencode） | ✅ main | SQLite schema：事件日志（append-only）/分支树/快照分层/玩家 anchor/NPC 记忆 + sqlite-vec 占位；索引与约束对齐 §6 契约 |
| `docs/data/event-sourcing.md` | 数据/数据库（opencode） | ✅ main | 事件溯源：`apply(event)` 唯一写路径、读档重放流程、回放确定性（RNG/熵随事件落库） |
| `docs/data/migration.md` | 数据/数据库（opencode） | ✅ main | Alembic 迁移策略（async env.py / alembic.ini / 首版迁移骨架） |
| `docs/api/ws-protocol.md` | 接口/兼容性（kilo） | ✅ main | WS 消息协议：消息类型清单与字段 schema、出戏边界（哪些字段绝不外发） |
| `docs/api/openapi.md` | 接口/兼容性（kilo） | ✅ main | HTTP 端点设计：设置页 / Profile 管理 / 存档 anchor CRUD；api_key 只在后端流转 |
| `docs/api/codegen.md` | 接口/兼容性（kilo） | ✅ main | OpenAPI → `shared/protocol.ts` 生成管线（openapi-typescript + banner + prettier）；CI 三道守卫（漂移检测已接 ci.yml / banner / 禁手写） |
| `docs/api/versioning.md` | 接口/兼容性（kilo） | ✅ main | 协议版本策略：WS version 字段/协商方式，client 与 sim 独立演进 |
| `docs/dev-workflow.md` | 依赖/配置/文档（cline） | ✅ main | 环境与常用命令：uv/pytest/ruff/pyright、npm/tsc/eslint/vitest、T1–T5 marker 跑法、bench nightly 跑法、CI 对应关系 |

状态图例：✅ main = 已在 main 分支；⏳ 待收编 = 已在对应 agent 分支产出，等 Claude（主导）统一收编（**当前：TASK-001/002 交付已全数收编；TASK-003 的 codex S03 交付仍在 `ZX466/codex`，见 §4**）。

## 3. 源码落点速查（M0，随里程碑更新）

- **前端（TASK-C04，`8c81b53`）**：`client/src/` — `game/world-mirror.ts`（高频实体镜像：普通 TS 类，完全绕开 React）+ `net/ws.ts`（指数退避重连，重连即 `sync_request` 全量重置镜像）+ `store/uiStore.ts`（薄 Zustand 白名单：只暴露戏内时间/相位/连接态，字段对齐 m1-checklist W1）+ `game/scenes/WorldScene.ts` / `game/main.ts`（Phaser）+ `ui/TopBar.tsx` / `ui/CanvasHost.tsx`（React 壳）+ `net/protocol.ts`（`@shared/protocol` 生成物的 re-export）。
- **mock 双模式（临时）**：`game/runtime.ts` 在 sim 的 WS 网关未起时自动进入 mock 模式（本地假数据驱动镜像，保证前端可独立验收「可走动 + 昼夜调色 + 重连重置」）。**触发条件已达成**：C05 的真实网关已上线并在 main（`sim/api/ws.py`，`/ws`）。**待办（Claude，前端域）**：把前端接上真实网关后删除 mock 分支——C05 只改 sim 后端，未动 `client/`。

## 4. M1 区块（TASK-003 进行中）

M1 范围与量化验收：DESIGN §17（认知闭环：LLM 客户端 + Profile + 设置页 + Intent + 闸门 + 感知引擎视/听/触/内感受 + 身份锚 + 独白叙事化 + 社会未知；20 差事 ≥80%、决策延迟 P95<8s、单决策 <2k tok、T3 对抗 100% 拒绝）。

### 已交付（S03，codex —— 分支 `ZX466/codex`，待收编进 main）

- `sim/llm/prompts/banned_words.py` — 禁词单一数据源（prompt 扫描与记忆扫描共用，落实 cline 评审建议）
- `sim/tests/test_banned_words.py` / `sim/tests/test_memory_scan.py` — 禁词表与 MemoryWritePipeline 测试
- `sim/tests/fixtures/t3_corpus.py` + `sim/tests/test_t3_gate.py` — 36 条对抗样本断言 / 45 条断言（T3 门禁）。**无 `t3` marker**，ci.yml 按**文件路径**接入（不是 `-m t3`）；文件未收编前该步骤自适应跳过，收编后自动生效
- `docs/security/m1-checklist.md` 增补 **W6**（WS 鉴权 M1 前置）/ **W7**（消息字段逐条白名单）

### 已交付（F05，pi —— 分支 `ZX466/pi`，待收编进 main）

- `docs/perf/llm-monitoring.md` — LLM 异步延迟监控口径（structlog 事件名 `llm.request/response/retry/timeout/error/cache_hit/decision` + 字段清单；不记 api_key/prompt 明文）。**C06 LLM 客户端照抄接入**
- `sim/tests/bench/test_bench_perception.py` — 感知传播基准脚手架（5 用例）。实测：朴素 O(N²) 9.1ms / 半径剪枝参考 4.64ms / 听觉 0.093ms → 3ms 上限确证 H-1「必须增量可见集」
- `docs/perf/budget.md` M1 分解：感知启用、LLM 预取调度进 tick（0.05/0.20ms，异步推理不进）；合计名义 7.00 / 上限 12.35 ≤16.6 ✓
- **cline 评审结论：通过**（3 项非阻断建议：① `_vision_partitioned_v2` 实为「半径剪枝参考」非空间分区，命名待正；② `RNG_TICK_LIMIT_MS=0.10` 逐调用口径偏紧，建议放宽或改向量化；③ `test_bench_rng.py` 头注释 100ms 待同步 300ms）

### 占位（待产出）

- arch 域 M1 设计文档，落点 docs/arch/m1-core.md（待 Claude）——产出后在此登记并在 §2 文档地图加行

### W6 鉴权依赖核（cline 结论：零新依赖）

- token 生成：标准库 `secrets`（token_urlsafe）；校验/摘要：标准库 `hmac` + `hashlib`（或已锁的 `cryptography` Fernet/HMAC）
- 握手校验 Origin/Host（防 DNS rebinding / localhost CSRF）：uvicorn/starlette 原生支持（已锁）；绑定保持默认 127.0.0.1 即满足「禁 0.0.0.0」
- 前端：原生 WebSocket/fetch，token 由后端同源 HTTP 下发，不落 localStorage 之外的位置
- **结论：Python 无新包、npm 无新包** —— M1 实现按此清单走，无需再过依赖评审

### P3 加固 3 项记账（codex C05 终审 → 均为代码/测试层；ruff / ESLint 无对应规则可兜，配置域不代兜）

| # | 项 | 精确修法 | 责任 |
|---|---|---|---|
| 1 | bool 穿透 | `isinstance(tx, int) and not isinstance(tx, bool)`（否则 JSON `true/false` 被当 1/0 可寻路） | Claude（M1 闸门） |
| 2 | rtoken 规模注释 | `_rtoken` docstring 补「48-bit 适用规模 ≤10^4，超规模前复审」 | Claude（ws 网关） |
| 3 | 键白名单断言 | 对外载荷断言从文本 grep 升级为「键白名单快照断言」（M1 引入新字段时） | codex（契约测试） |

## 5. 跨域接口对接点（改了要同时通知对方）

| 接口 | 提供方 → 消费方 | 契约落点 |
|---|---|---|
| 事件/快照存储 | 数据（opencode）→ 内核（Claude） | `EventStore` Protocol（`docs/arch/m0-core.md` §8）↔ `docs/data/schema.md`；实现：`sim/core/persistence/`（已进 main） |
| WS 消息 schema | 接口（kilo）→ 前端（Claude） | `docs/api/ws-protocol.md` → `shared/protocol.ts`（生成物） |
| 禁词表 | 安全（Codex）→ 认知层（Claude） | `docs/security/m1-checklist.md` M1-A/B/D ↔ prompt 装配唯一出口；记忆侧见 `docs/security/memory-scan.md`，对抗语料见 `docs/security/t3-corpus.md` |
| tick 预算 | 性能（Pi）→ 内核（Claude） | `docs/perf/budget.md` §1 ↔ `docs/arch/m0-core.md` §5 固定执行序 |
| 依赖与 CI | 配置（cline）→ 全员 | `pyproject.toml` / `uv.lock` / `client/package.json` / `.github/workflows/` |

## 6. 约束提醒（写文档时最容易破的两条）

- `DESIGN.md` §18：**本文档为冻结基线**，新想法先进「MVP 后清单」，不回写里程碑——改基线要走 v2.x 修订记录。
- `DESIGN.md` §19 禁止事项与 §10 界面双层铁律是**文档也必须遵守**的：设计文档里不要引入「把结构化世界状态喂给 LLM」「戏内界面出元信息」这类写法。
