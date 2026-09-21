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
| `docs/perf/budget.md` | 性能（Pi） | ✅ main | 每 tick 16.6ms（1x=60tick/s）预算表：7 子系统名义 7.00ms / 上限 12.35ms（M1 分解）；4x/16x 与战斗时间尺特例；采集告警点 |
| `docs/perf/hotspots.md` | 性能（Pi） | ✅ main | 热点预判 H-1–H-6：感知传播分区/增量、L0 向量化、SQLite append-only 批量写与索引、WS 增量合批、超速倍率、LLM 异步延迟（信息性） |
| `docs/perf/bench-plan.md` | 性能（Pi） | ✅ main | 基准方案：M0 必带 bench 清单、pytest-benchmark/真实 tick loop harness 选型、回归阈值、nightly 节奏、已知不可测项 |
| `docs/perf/llm-monitoring.md` | 性能（Pi） | ✅ main | LLM 异步延迟监控口径：structlog 事件名 `llm.request/response/retry/timeout/error/cache_hit/decision` + 字段清单（不记 api_key/prompt 明文）；P95<8s、单决策<2k tok、cache_hit>50%；**C06 LLM 客户端照抄接入**（口径非 tick 量纲） |
| `docs/perf/m2-acceptance.md` | 性能（Pi） | ✅ main | M2 验收口径：604,800 tick（50 NPC × 7 游戏日）自转无崩溃；崩溃判定 C1–C10（进程/RSS/句柄/GC/缓存/实体/漂移/确定性/延迟）；降采样断言三级（CI 缩样/nightly 30k/里程碑完整）；nightly 接法提案 §4 |
| `docs/data/schema.md` | 数据/数据库（opencode） | ✅ main | SQLite schema：事件日志（append-only）/分支树/快照分层/玩家 anchor/NPC 记忆 + sqlite-vec 占位；索引与约束对齐 §6 契约 |
| `docs/data/event-sourcing.md` | 数据/数据库（opencode） | ✅ main | 事件溯源：`apply(event)` 唯一写路径、读档重放流程、回放确定性（RNG/熵随事件落库） |
| `docs/data/migration.md` | 数据/数据库（opencode） | ✅ main | Alembic 迁移策略（async env.py / alembic.ini / 首版迁移骨架） |
| `docs/api/ws-protocol.md` | 接口/兼容性（kilo） | ✅ main | WS 消息协议：消息类型清单与字段 schema、出戏边界（哪些字段绝不外发） |
| `docs/api/openapi.md` | 接口/兼容性（kilo） | ✅ main | HTTP 端点设计：设置页 / Profile 管理 / 存档 anchor CRUD；api_key 只在后端流转 |
| `docs/api/codegen.md` | 接口/兼容性（kilo） | ✅ main | OpenAPI → `shared/protocol.ts` 生成管线（openapi-typescript + banner + prettier）；CI 三道守卫（漂移检测已接 ci.yml / banner / 禁手写） |
| `docs/api/versioning.md` | 接口/兼容性（kilo） | ✅ main | 协议版本策略：WS version 字段/协商方式，client 与 sim 独立演进 |
| `docs/dev-workflow.md` | 依赖/配置/文档（cline） | ✅ main | 环境与常用命令：uv/pytest/ruff/pyright、npm/tsc/eslint/vitest、T1–T5 marker 跑法、bench nightly 跑法、CI 对应关系 |

状态图例：✅ main = 已在 main 分支；⏳ 待收编 = 已在对应 agent 分支产出，等 Claude（主导）统一收编（**当前：TASK-001/002/003 交付已全数收编，见 §4**）。

## 3. 源码落点速查（M0，随里程碑更新）

- **前端（TASK-C04，`8c81b53`）**：`client/src/` — `game/world-mirror.ts`（高频实体镜像：普通 TS 类，完全绕开 React）+ `net/ws.ts`（指数退避重连，重连即 `sync_request` 全量重置镜像）+ `store/uiStore.ts`（薄 Zustand 白名单：只暴露戏内时间/相位/连接态，字段对齐 m1-checklist W1）+ `game/scenes/WorldScene.ts` / `game/main.ts`（Phaser）+ `ui/TopBar.tsx` / `ui/CanvasHost.tsx`（React 壳）+ `net/protocol.ts`（`@shared/protocol` 生成物的 re-export）。
- **mock 双模式（临时）**：`game/runtime.ts` 在 sim 的 WS 网关未起时自动进入 mock 模式（本地假数据驱动镜像，保证前端可独立验收「可走动 + 昼夜调色 + 重连重置」）。**触发条件已达成**：C05 的真实网关已上线并在 main（`sim/api/ws.py`，`/ws`）。**待办（Claude，前端域）**：把前端接上真实网关后删除 mock 分支——C05 只改 sim 后端，未动 `client/`。

## 4. M1 区块（C06 六步已进 main，M1 收官）

M1 范围与量化验收：DESIGN §17（认知闭环：LLM 客户端 + Profile + 设置页 + Intent + 闸门 + 感知引擎视/听/触/内感受 + 身份锚 + 独白叙事化 + 社会未知；20 差事 ≥80%、决策延迟 P95<8s、单决策 <2k tok、T3 对抗 100% 拒绝）。

### 四指标实测（`sim/tests/test_m1_metrics.py`，CI 已固化 — TASK-004 P05）

| 指标 | 门槛 | 实测（本机 `uv run pytest sim/tests/test_m1_metrics.py`） | 结论 |
|---|---|---|---|
| 脚本差事完成率 | ≥80% | **20/20 = 100%** | ✅ |
| 决策延迟 P95 | <8s | **≈0.25ms**（链路计算耗时下界） | ✅ |
| 单决策 prompt | <2k tok | **232–274 字符 ≈ 145–171 tok**（messages[0]+[1] 全量） | ✅ |
| T3 出戏对抗 | 100% 安全 | **4/4 = 100%**（E17–E20） | ✅ |

> **口径（写作时勿丢）**：延迟与完成率是**假 LLM（脚本应答、零网络）**下的**下界**；真实线上墙钟延迟由 `docs/perf/llm-monitoring.md` 日汇总看板监控（P95<8s / <2k tok）。两者量纲不同，不可互相替代。
> **数字纠偏**：此前口头引用的「prompt ≈600 tok」与 test 实测不符——`prompt_chars` 实测 messages[0]+messages[1] 为 232–274 字符（≈145–171 tok）。**以 test 实测为准**（差事语料短锚+短感知文本；真实跑分若加长记忆/多 NPC 感知会上升，仍远低于 2k）。
> **CI**：`ci.yml` 新增命名步骤「pytest M1 指标跑分」，按**文件路径**跑该文件；该文件无专属 marker（本已随 `-m "not bench"` 全量跑），按路径可保证日后加 marker / 改 addopts 也不会把它静默排除。
> **补充门禁**：T3 语料门禁 `sim/tests/test_t3_gate.py` = **69 条实弹 × 多路径 + 5 结构攻击，78 断言全绿**（codex S04；ci.yml 另有命名步骤按文件路径跑它）。

### 已交付（C06，Claude → ✅ main）

| 步 | 内容 | 提交 |
|---|---|---|
| ①② | LLM 客户端 + Profile 设置页 API | `a2ece33` |
| ③ | 感知引擎（传播三要素 / 视听通道 / 感知帧）+ tick 第 3 步钩子；bench 恢复红线 3.6ms | `dafc8df` |
| ④ | 身份锚 + 六段 prompt 装配（messages[0] 为缓存分界）+ cache_hit 指纹 + 日志脱敏 | `7a2bff9` |
| ⑤ | Intent schema（`extra=forbid`）+ 闸门两道校验（规划预检 + 执行时二次校验） | `6f1dd0e` |
| ⑥ | 20 脚本差事 fixture + M1 四指标跑分 | `5c08c74` |

### 已交付（S03，codex → ✅ main）

- `sim/llm/prompts/banned_words.py` — 禁词单一数据源（prompt 扫描与记忆扫描共用，落实 cline 评审建议）
- `sim/tests/test_banned_words.py` / `sim/tests/test_memory_scan.py` — 禁词表与 MemoryWritePipeline 测试
- `sim/tests/fixtures/t3_corpus.py` + `sim/tests/test_t3_gate.py` — **69 条对抗样本 / 78 条断言**（T3 门禁；S03 建库 36 条 → **S04 扩到 69 条实弹，★ 也打**）。**无 `t3` marker**，ci.yml 按**文件路径**接入（不是 `-m t3`，否则永久收集 0 用例=假绿灯）；CI 门禁步骤已**实跑**（本机实测 **78 passed**）
- `docs/security/m1-checklist.md` 增补 **W6**（WS 鉴权 M1 前置）/ **W7**（消息字段逐条白名单）

### 已交付（F05，pi → ✅ main）

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
- **实施状态（codex S04，main `66f3f18`）**：token + `hello` 握手 hmac 比对 + Origin 白名单已在 `sim/api/ws.py` 落地，测试 8 项全绿 —— **「零新依赖」结论被实现验证成立**。**遗留**：前端 `client/src/net/ws.ts` 尚未接 token（需后端提供 `/api/ws-token` 下发端点），归 Claude/kilo 后续对接。

### P3 加固 3 项记账（codex C05 终审 → 均为代码/测试层；ruff / ESLint 无对应规则可兜，配置域不代兜）

| # | 项 | 精确修法 | 责任 | 状态（2026-09-20 终校） |
|---|---|---|---|---|
| 1 | bool 穿透 | `isinstance(tx, int) and not isinstance(tx, bool)`（否则 JSON `true/false` 被当 1/0 可寻路） | Claude（M1 闸门） | ✅ **已收口**（codex S04）——`sim/api/ws.py:222-227` 增 `not isinstance(tx/ty, bool)`，带 P3 #1 注释 |
| 2 | rtoken 规模注释 | `_rtoken` docstring 补「48-bit 适用规模 ≤10^4，超规模前复审」 | Claude（ws 网关） | ✅ **已收口**（codex S04）——`sim/api/ws.py:89-90` 已写明 12 hex = 48 bit、≤10^4 可忽略、扩容前复审 |
| 3 | 键白名单断言 | 对外载荷断言从文本 grep 升级为「键白名单快照断言」（M1 引入新字段时） | codex（契约测试） | ✅ **已入**（codex S04） |

> 复核经过：P05 终校时（当时 main 尚未含 S04）第 1、2 项**确实仍缺**，已在 P05 报告主树；**codex S04 合入（main `66f3f18`）后三项全部收口**，本表已按终态更新。教训：**跨域状态以 main 实际代码为准**（我复查 `git grep 'not isinstance'` / `_rtoken` docstring 逐条确认，未凭留言采信）。

## 5. M2 区块（M2 四路交付在手，待收编）

M2 范围与量化验收 = `DESIGN.md` §17 M2 行：**NPC 底座 + L1 效用 AI（兼 LLM 断线兜底）+ 非理性框架 + 物质熵增 + 嗅觉风向 + 语言判定 + 自我未知**。

- **量化验收（只认这两条；DESIGN §16「验收只认上表」同纪律）**：
  1. 50 NPC × 7 游戏日自转无崩溃；
  2. T1 信息边界 10k 采样通过。
- **本阶段不做**：记忆传播、建造（DESIGN §17 M2 行「本阶段不做」）。
- **量纲提醒（写 M2 验收脚本前先看）**：DESIGN §10 锁定「1 tick = 1 游戏秒」⇒ 7 游戏日 = **604,800 tick**。完整跑**不进每提交 CI**（ci.yml 的 M2 占位步骤 `timeout-minutes: 15` 即这道护栏），完整跑与 M2 红线一律接 `nightly-bench.yml`（接入点注释已留）。

### M2 派单与交付状态（2026-09-21 盘点，四路交付**待收编**）

| 路 | Agent | 交付物（分支 / 提交） | 实测 / 结论 |
|---|---|---|---|
| M2-A1 架构稿 | Claude | `docs/arch/` 下 M2 稿（进行中） | — |
| M2-S1 自我未知安全边界 | codex | `docs/security/self-unknown.md` + `sim/npc/hidden.py` + `gate.py`/`memory_scan.py` 扩展 + `sim/tests/test_t1_self_unknown.py`（`ZX466/codex` `581ae78`） | 28 用例（未触发零泄露 / 触发正常浮现双路径）；全量 606 passed / 55 skipped；自带 ci.yml 文件路径门禁 |
| M2-P1 性能预算 | pi | `docs/perf/{budget,bench-plan,hotspots}.md` + `thresholds.py` 5 常量 + `sim/tests/bench/test_bench_l1_utility.py` / `test_bench_smell.py`（`ZX466/pi` `adaf0c5`） | bench 29 passed；暖态中位 L1 向量化 ~0.02ms/tick、嗅觉 ~0.01ms；红线 L1 6.0ms / 单 NPC 0.12ms / 断线兜底 0.20ms / 嗅觉 0.15ms |
| M2-P2 长跑验收口径 | pi | `docs/perf/m2-acceptance.md` + `hotspots.md` H-7 + `thresholds.py` 5 SOAK_* 常量 + `sim/tests/bench/soak.py` / `test_bench_soak.py`（`ZX466/pi`） | 50 NPC × 604,800 tick 无崩溃口径 C1–C10；实测 100k tick 均值无漂移（1.86→1.86ms）、RSS/句柄/GC 有界；三级降采样（CI 缩样/nightly 30k/里程碑完整 604,800）；nightly 接法提案 §4（待 cline 裁决） |
| M2-D1 数据层 | opencode | `docs/data/schema.md` + `0004_m2_npc_attributes` + `models.py` + `sim/tests/test_persistence_m2.py`（`ZX466/opencode` `2876933`） | 582 passed / 55 skipped；alembic 零漂移；`npc_memory_vec` 仍锁 M3（D04 保留项不变） |
| K04 WS 类型生成 | kilo | `client/src/net/__tests__/protocol-types.test.ts` + `docs/api/ws-protocol.md` §3.1（`ZX466/kilo` `ab39dc1`） | `gen:protocol --check` / typecheck / lint / vitest 13 / build 全绿；4 项跨域发现（`components.wsMessages` 不被 openapi-typescript 读取等）待 sim 侧裁决 |
| M2-C1 配套（本域） | cline | ci.yml M2 占位步骤 + nightly 接入点注释 + 本节 + `docs/dev-workflow.md` §3/§7 | 依赖对账 **零新包**（下表）；`.gitattributes` **正式提议**见 dev-workflow §7 |

### M2 依赖对账（M2-C1 结论：**零新依赖**）

| 路 | 分支实测新增 import（`git diff origin/main ZX466/<树> -- '*.py'` 的 `+` 行） | 依赖结论 |
|---|---|---|
| codex M2-S1 | `re` / `dataclasses` / `typing` / `pydantic` / `pytest` + 本仓模块 | 零新包（标准库 + 已锁 pydantic/pytest） |
| pi M2-P1 | `time` / `numpy` / `pytest` + `sim/tests/bench/{harness,thresholds}` | 零新包（numpy、pytest-benchmark 已锁） |
| opencode M2-D1 | `sqlalchemy` / `alembic` / `sqlite3` / `json` | 零新包（SQLAlchemy 2.0 async + Alembic 已在锁） |
| kilo K04 | 无 Python 改动；前端只改测试与文档 | 零新包（openapi-typescript / prettier 已锁；Node ≥24 已定，CI setup-node 已对齐） |

- **证据（硬指标）**：四分支 `git diff --stat origin/main <branch> -- pyproject.toml uv.lock client/package.json client/package-lock.json` **全部为空** —— 零锁文件变更，故 M2 收编**不需要**除 `uv sync` / `npm ci` 之外的任何动作，CI 缓存键也不变。
- **唯一待观察项**：embedding 生成来源（M3 记忆向量检索才触发）。走已锁 `openai` 客户端调远端 embedding API ⇒ 零新包；若改本地模型（torch / onnxruntime / sentence-transformers 等）⇒ 重依赖 + CI 体积暴涨，**须先过依赖评审再动**。M2 不触发：`sqlite-vec>=0.1.6` 已在锁，`sim/core/persistence/vector.py` 脚手架就位，`DEFAULT_EMBEDDING_DIM = 384` 待 M3 锁定。

### M2 CI 接入（现状）

- **新增占位步骤**：「pytest M2 指标跑分（占位）」——按**文件路径** glob `sim/tests/test_m2_*.py` 选择（纪律同 T3/M1，不用 marker）。文件未落库时只 `::warning::` 留痕、不假绿；落库后**自动生效**，届时由 cline 把 glob 换成显式路径、去掉步骤名里的「占位」。
- 命名约定：M2 的 CI 级验收测试落 `sim/tests/test_m2_*.py`（对齐 `sim/tests/test_m1_metrics.py`），**无 LLM、秒级~分钟级**。
- 已到位的 M2 命名门禁（不重复接）：`sim/tests/test_t1_self_unknown.py`（codex 分支自带步骤）；`sim/tests/test_persistence_m2.py` 纯 T1、随 `-m "not bench"` 全量跑。
- nightly：M2 红线**不复制数值**，唯一真相源 `sim/tests/bench/thresholds.py`；pi 的两个 M2 bench 文件随 `-m bench` 自动纳入，**无需改 yml**。
- **待裁（Claude）**：完整 7 日自转验收（604,800 tick）的定期接法（新增 `-m m2full` 类 marker + nightly job，还是只在里程碑本地跑一次）。marker 语义属配置域但**接法由主导裁决**，cline 不擅自定；裁决后在本节 + nightly 注释回填。

### 待裁：`.gitattributes`（行尾统一）

正式提议见 `docs/dev-workflow.md` §7 —— 含实测影响面（索引重写量 **0 文件**、各树一次性重签出步骤、方案 A/B/C 对比）。cline **不擅自加**；裁决采纳后由 cline 在 main 落一次提交，各工作树配合重签出。

## 6. 跨域接口对接点（改了要同时通知对方）

| 接口 | 提供方 → 消费方 | 契约落点 |
|---|---|---|
| 事件/快照存储 | 数据（opencode）→ 内核（Claude） | `EventStore` Protocol（`docs/arch/m0-core.md` §8）↔ `docs/data/schema.md`；实现：`sim/core/persistence/`（已进 main） |
| WS 消息 schema | 接口（kilo）→ 前端（Claude） | `docs/api/ws-protocol.md` → `shared/protocol.ts`（生成物） |
| 禁词表 | 安全（Codex）→ 认知层（Claude） | `docs/security/m1-checklist.md` M1-A/B/D ↔ prompt 装配唯一出口；记忆侧见 `docs/security/memory-scan.md`，对抗语料见 `docs/security/t3-corpus.md` |
| tick 预算 | 性能（Pi）→ 内核（Claude） | `docs/perf/budget.md` §1 ↔ `docs/arch/m0-core.md` §5 固定执行序 |
| 依赖与 CI | 配置（cline）→ 全员 | `pyproject.toml` / `uv.lock` / `client/package.json` / `.github/workflows/` |

## 7. 约束提醒（写文档时最容易破的两条）

- `DESIGN.md` §18：**本文档为冻结基线**，新想法先进「MVP 后清单」，不回写里程碑——改基线要走 v2.x 修订记录。
- `DESIGN.md` §19 禁止事项与 §10 界面双层铁律是**文档也必须遵守**的：设计文档里不要引入「把结构化世界状态喂给 LLM」「戏内界面出元信息」这类写法。
