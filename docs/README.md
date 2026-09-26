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
| `docs/arch/m3-plan.md` | 架构（Claude） | ✅ main | M3 规划整合稿：批次 A-D 切分（A 向量 / C 地图可并行，B 等 A 接口冻结，D 收尾）+ 安规钉子横切 + §6 待裁决队列；第五批续写批次 B 模块/文件级施工图与 B1 |
| `docs/arch/m4-plan.md` | 架构（Claude） | ✅ main | M4 规划：批次 A–D 切分 + 裁 14 六条裁决记录 + 门禁归属速查 + **「T4 全绿」定义**（锁定模型版本下 nightly 连续通过，非每次提交绿） |
| `docs/security/m1-checklist.md` | 安全/合规/风险（Codex） | ✅ main | M1 安全检查清单 27 项：K1–K8 密钥（Fernet/主密钥/日志脱敏/SSRF）、M1-A–I 出戏断言、O1–O6 LLM 输出边界、W1–W5 WS 白名单、G1–G4 通用 |
| `docs/security/threat-model.md` | 安全/合规/风险（Codex） | ✅ main | 轻量威胁模型：4 资产 / 10 威胁→缓解映射 / 出戏防线 5 层 / 非目标 / Top-5 技术安全风险 |
| `docs/security/t3-corpus.md` | 安全/合规/风险（Codex） | ✅ main | T3 出戏对抗样本集：分类攻击语料（元信息直问/诱导/存档意识/操纵感/时间戳探针/身体否定）；**期望响应形态 = 第一人称世界内回应，不是拒绝话术**；M1-C/D/E/I 的 fixture 来源 |
| `docs/security/memory-scan.md` | 安全/合规/风险（Codex） | ✅ main | 记忆写入前禁词扫描设计稿（架构域已批原则方向，M1 照此落地）：挂记忆写入路径、复用禁词表、命中改写优先拒写、append-only 用「标记无效+重写」补救 |
| `docs/security/m3-preplan.md` | 安全/合规/风险（Codex） | ✅ main | M3 安规预研：R1-R7 记忆/知识传播缝、C1-C13 建造输入面、X1-X8 triggered 扫描面 + §4 验收口径 |
| `docs/security/m3-evidence-chain.md` | 安全/合规/风险（Codex） | ✅ main | R5 证据链契约：witnessed（emerge 事件 + witnesses 双证据）/ told（链上衰减 0.9×0.6^n、下限 0.1、断链即失效）/ inferred（禁他人属性，无例外）三路判定 + E1 浮现事件提案 + knowledge 五列扩展 + §8 七条 T1 验收钉子 |
| `docs/security/t1-sampling-10k.md` | 安全/合规/风险（Codex） | ✅ main | T1 信息边界 10k 采样验收口径：采样对象/触发分布/判据（零直陈泄露 + 零误伤）+ 与 S1 双路径测试的关系（单测=逻辑覆盖，10k=规模化终验）；配套 `test_m2_t1_sampling_10k.py` |
| `docs/security/m3-closure-preaudit.md` | 安全/合规/风险（Codex） | ✅ 已收官 | M3 收官门预审：静态六钉子对表 + S4 10k 闭环核对 + 5 发现；§7 动态门于 2026-09-25 在 main 回填（全量 1076 passed / 0 failed）→ 宣告 M3 收官 |
| `docs/perf/budget.md` | 性能（Pi） | ✅ main | 每 tick 16.6ms（1x=60tick/s）预算表：7 子系统名义 7.00ms / 上限 12.35ms（M1 分解）；4x/16x 与战斗时间尺特例；采集告警点 |
| `docs/perf/hotspots.md` | 性能（Pi） | ✅ main | 热点预判 H-1–H-6：感知传播分区/增量、L0 向量化、SQLite append-only 批量写与索引、WS 增量合批、超速倍率、LLM 异步延迟（信息性） |
| `docs/perf/bench-plan.md` | 性能（Pi） | ✅ main | 基准方案：M0 必带 bench 清单、pytest-benchmark/真实 tick loop harness 选型、回归阈值、nightly 节奏、已知不可测项 |
| `docs/perf/llm-monitoring.md` | 性能（Pi） | ✅ main | LLM 异步延迟监控口径：structlog 事件名 `llm.request/response/retry/timeout/error/cache_hit/decision` + 字段清单（不记 api_key/prompt 明文）；P95<8s、单决策<2k tok、cache_hit>50%；**C06 LLM 客户端照抄接入**（口径非 tick 量纲） |
| `docs/perf/m2-acceptance.md` | 性能（Pi） | ✅ main | M2 验收口径：604,800 tick（50 NPC × 7 游戏日）自转无崩溃；崩溃判定 C1–C10（进程/RSS/句柄/GC/缓存/实体/漂移/确定性/延迟）；降采样断言三级（CI 缩样/nightly 30k/里程碑完整）；nightly 接法提案 §4 |
| `docs/perf/m2-p4-budget-preplan.md` | 性能（Pi） | ✅ main | 第三批预算预案：smell 拆表/flush 断言/cognition 上界 + §4 已落地 vs 待裁决分栏 |
| `docs/perf/l1-spec.md` | 性能（Pi） | ✅ main | L1 算法规格：原型↔实现对账 + 红线实测回填 + soak L1 feeder 两阶段 |
| `docs/perf/m3-retrieval-budget.md` | 性能（Pi） | ✅ main | M3 检索缝预算案：候选/打分/退化哨兵/tick 四红线设计稿（实测候选 0.019ms、打分 600 候选 0.862ms、正常形态 ≈0.05ms/NPC）+ V5 裁决输入 + baseline.json 8 步建立流程 |
| `docs/perf/ci-calibration-m2p6.md` | 性能（Pi） | ✅ main | CI 档位定标提案：nightly advisory 门（`PI_BENCH_ADVISORY`）+ CI 实测档位基线口径（RNG 1M 警戒 300→330 的依据） |
| `docs/perf/m4-build-budget-preplan.md` | 性能（Pi） | ✅ main `88284c3` | M4-P1 建造预算预研：现状 tick 预算盘点（上限表余量 2.10ms=13%）+ 坍塌级联成本模型实测（BFS 10k=1.27ms vs 逐对象事件 51ms=307% tick）+ 施工推进语义 perf 建议（支持 M4-D1 checkpoint）+ 红线草案框架 |
| `docs/data/schema.md` | 数据/数据库（opencode） | ✅ main | SQLite schema：事件日志（append-only）/分支树/快照分层/玩家 anchor/NPC 记忆 + sqlite-vec 占位；索引与约束对齐 §6 契约 |
| `docs/data/event-sourcing.md` | 数据/数据库（opencode） | ✅ main | 事件溯源：`apply(event)` 唯一写路径、读档重放流程、回放确定性（RNG/熵随事件落库） |
| `docs/data/migration.md` | 数据/数据库（opencode） | ✅ main | Alembic 迁移策略（async env.py / alembic.ini / 首版迁移骨架） |
| `docs/data/vec-preplan.md` | 数据/数据库（opencode） | ✅ main | M3 记忆向量检索预研：sqlite-vec vs numpy 余弦、5 万条量级估算（非瓶颈）、`LlmClient.embed` 缝、V1-V7 待裁决清单 |
| `docs/data/matter-register-proposal.md` | 数据/数据库（opencode） | ✅ 已裁并实施 | §19.4 注册持久化：`register` 返回 `MATTER_BUILD` 立账事件（零 schema），structures M3 不建；4 点裁决 + 9 用例实施记录 |
| `docs/data/build-domain-preplan.md` | 数据/数据库（opencode） | ✅ main `a725a65` | M4-D1 建造数据面：structures 拓扑投影、建造事件族、checkpoint 推进、承重图、材料守恒；**裁 14 采信主干 7 点全裁**（细则见 `docs/arch/m4-plan.md` §6 第 2 条） |
| `docs/api/ws-protocol.md` | 接口/兼容性（kilo） | ✅ main | WS 消息协议：消息类型清单与字段 schema、出戏边界（哪些字段绝不外发） |
| `docs/api/openapi.md` | 接口/兼容性（kilo） | ✅ main | HTTP 端点设计：设置页 / Profile 管理 / 存档 anchor CRUD；api_key 只在后端流转 |
| `docs/api/codegen.md` | 接口/兼容性（kilo） | ✅ main | OpenAPI → `shared/protocol.ts` 生成管线（openapi-typescript + banner + prettier）；CI 三道守卫（漂移检测已接 ci.yml / banner / 禁手写） |
| `docs/api/versioning.md` | 接口/兼容性（kilo） | ✅ main | 协议版本策略：WS version 字段/协商方式，client 与 sim 独立演进 |
| `docs/api/ws-message-diff.md` | 接口/兼容性（kilo） | ✅ main | ext↔快照逐成员 diff 明细 + K3 复验结论（§4.3：白名单外 diff = 0、契约对齐完成；未消项**不阻塞** M5，切源解禁仍待 M5 + sim 404 声明） |
| `docs/api/anchors-api.md` | 接口/兼容性（kilo） | ✅ main | anchors 三路由契约稿（字段/校验/状态码/示例四要素齐）+ §5 施工清单 + 验收对表（[T] pytest / [O] OpenAPI 静态形状 / [C] 前端类型三类断言）+ §5.1 OpenAPI responses 注入点 |
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

## 5. M2 / M3 / M5 交付台账（2026-09-25 盘点）

M2 范围与量化验收 = `DESIGN.md` §17 M2 行：**NPC 底座 + L1 效用 AI（兼 LLM 断线兜底）+ 非理性框架 + 物质熵增 + 嗅觉风向 + 语言判定 + 自我未知**。

- **量化验收（只认这两条；DESIGN §16「验收只认上表」同纪律）**：
  1. 50 NPC × 7 游戏日自转无崩溃；
  2. T1 信息边界 10k 采样通过。
- **本阶段不做**：记忆传播、建造（DESIGN §17 M2 行「本阶段不做」）。
- **量纲提醒（写 M2 验收脚本前先看）**：DESIGN §10 锁定「1 tick = 1 游戏秒」⇒ 7 游戏日 = **604,800 tick**。完整跑**不进每提交 CI**（ci.yml 的 M2 占位步骤 `timeout-minutes: 15` 即这道护栏），完整跑与 M2 红线一律接 `nightly-bench.yml`（接入点注释已留）。

### 5.1 M2 交付状态（第一至九轮）

| 路 | Agent | 交付物（提交） | 状态 | 实测 / 结论 |
|---|---|---|---|---|
| M2-A1 架构稿 | Claude | `docs/arch/m2-npc-cognition.md`（NPC 底座/L1 效用/非理性/物质熵增/嗅觉+风场接口/语言判定 + 实施顺序与分工） | ✅ main `3ab8c71` | 两项配置裁决同批落地（`.gitattributes` + `.gitignore` 的 `.github` 例外） |
| M2-A2 第一批 | Claude | `sim/npc/{model,needs,body,actions}.py` + EventKind 扩 6 类 + `sim/tests/test_m2_npc_base.py` | ✅ main `76f1ba3` | 26 用例；636 passed / 55 skipped；CI M2 命名步骤已实跑 |
| M2-S1 自我未知安全边界 | codex | `docs/security/self-unknown.md` + `sim/npc/hidden.py` + gate/memory_scan 扩展 + `sim/tests/test_t1_self_unknown.py` | ✅ main `8d254cb` | 28 用例（未触发零泄露 / 触发正常浮现双路径）；自带 ci.yml 文件路径门禁 |
| M2-P1 性能预算 | pi | `docs/perf/{budget,bench-plan,hotspots}.md` + `thresholds.py` 5 常量 + `test_bench_l1_utility.py` / `test_bench_smell.py` | ✅ main `e42b979` | bench 29 passed；暖态中位 L1 向量化 ~0.02ms/tick、嗅觉 ~0.01ms；红线 L1 6.0 / 单 NPC 0.12 / 断线兜底 0.20 / 嗅觉 0.15ms |
| M2-D1 数据层 | opencode | `docs/data/schema.md` §12-14 + `0004_m2_npc_attributes` + `models.py` + `sim/tests/test_persistence_m2.py` | ✅ main `4934ec1` | 11 用例；alembic 零漂移；`npc_memory_vec` 仍锁 M3 |
| K04 WS 类型生成 | kilo | `client/src/net/__tests__/protocol-types.test.ts` + `docs/api/ws-protocol.md` §3.1 | ✅ main `8dd8355` | `gen:protocol --check` / typecheck / lint / vitest 13 / build 全绿 |
| M2-C2 风场 + 门禁填实 + 重签出（本域） | cline | `sim/world/weather.py` + `sim/tests/test_m2_weather.py` + ci.yml M2 步骤填实 + `docs/dev-workflow.md` §7 重签出操作 | ✅ 已收编 | 31 用例；纯函数可重放（同 (rng,tick) 同风）+ 每日天气注入点 `daily_reseed_due`；六树重签出后 `w/crlf` 全 0、prettier/gen-protocol 假红消失 |
| M2-S2 L1 动作白名单 + HiddenState | codex | `docs/security/l1-whitelist.md` + `sim/npc/contract.py` + `sim/tests/test_t1_l1_whitelist.py` | ✅ 已收编 | 29 用例（白名单锁定/payload 键/升格传递/降格写回）；自带 T1 文件路径门禁 |
| M2-D2 LOD 事件持久化 | opencode | `sim/core/persistence/npc_store.py`（materialize/flush_tick/writeback）+ `store.py` 投影缝 + `sim/tests/test_m2_runtime_store.py` + schema.md §14/15 | ✅ 已收编 | 15 用例；651 passed / 55 skipped；alembic 零漂移 |
| M2-P2 长跑验收口径 + 预压测 | pi | `docs/perf/m2-acceptance.md`（C1-C10）+ `sim/tests/bench/soak.py` + `test_bench_soak.py` + thresholds 5 SOAK_* | ✅ 已收编 | 100k tick 实测均值无漂移（1.86→1.86ms）、RSS/句柄/GC 有界；三级降采样；nightly 接法=方案 A（已裁，`c49b0b3`） |
| M2-K1 复核 | kilo | language 叙事边界复核 4 条意见（memory.md ⑥节） | ✅ 已收编 | 全部采纳进架构稿 §5.2；openapi_ext 复核转 M2-K2 |
| M2-A2 第二批 | Claude | `sim/npc/{schedule,utility,runtime}.py` + `sim/world/matter.py` + `sim/perception/smell.py` + openapi_ext WsMessage 改写 | ✅ main `59ffd86` | 44 用例；768 passed / 55 skipped；client 五项验收绿 |
| M2-C3 口径校验 | cline | 纯校验报告（未改仓库文件） | ✅ 已回执 | P0=README §5 冲突标记（Claude 已修）；P1/P2 五处口径过期（codex 代修 `86d5d1e`）；一致项全绿 |
| M2-S3 M2-D2 安评 | codex | `docs/security/m2-d2-review.md` + 3 条补充测试（`ZX466/codex` `86d5d1e`） | ✅ main `3c79465` | 结论=通过：0 CRITICAL/HIGH、2 MEDIUM（归 opencode）、2 观察 |
| M2-D3 记忆检索缝 | opencode | 读侧检索打分 + redact_sensitive + codex 两条 MEDIUM 修复（`ZX466/opencode` `cc29687`） | ✅ main `25e9b2d` | 9 文件 +988 行；npc_memory_vec 仍锁 M3 |
| M2-P3 L1 规格 + feeder | pi | `docs/perf/l1-spec.md` + `soak.py::make_l1_feeder`（`ZX466/pi` `a5c05ed`） | ✅ main `7d63210` | 实测 0.206-0.747ms（余量 8-29×）；p99 硬门禁改信息性守护（口径已随收编确认） |
| M2-K2 openapi 复核 | kilo | 复核回执（无仓库文件）；返工验收清单转 M2-K3 → `docs/api/ws-message-diff.md`（见下方 M2-K3 清单行） | ✅ 已回执 | `59ffd86` 改写复核 + 接口三查；6 类问题（含 P0「切源丢 21 schema」）全采信，裁决=切源暂缓（`docs/api/codegen.md` §4.1，cline M2-C4 落档） |
| M2-A2 第三批 | Claude | smell/weather 接感知步 + NpcRuntime 物化 HiddenState + cognition 六偏差骨架 + language 叙事降质 | ✅ main `19de630` | 四件全部落 main；840 passed / 55 skipped |
| M2-C4 切源暂缓声明（本域） | cline | `docs/api/codegen.md` §4.1「切源暂缓」+ `tools/gen-protocol.ts` 头注 | ✅ main `525f970` | 原因=kilo K2 P0（`--src` 切真实源丢 21 个 HTTP 子结构 schema）；解除条件=sim 补 `response_model`（照 K3 清单）+ openapi_ext 返工，两项齐备经 Claude 裁决；nightly 基线评估=产物不全不动 |
| M2-S4 T1 信息边界 10k 采样 | codex | `docs/security/t1-sampling-10k.md` + `sim/tests/test_m2_t1_sampling_10k.py` | ✅ main `38a7f63` | 4 场景 × 2,500 = **10,000 采样**（假 LLM 词面拼装、分流 RNG 可重放、零网络）；判据=零直陈泄露 + 零误伤；7 用例 1.1s 全绿、全量 862 passed；复用 S1 工具链零改动，`test_m2_` 前缀自动进 CI glob |
| M2-D4 matter 对账 + memory 契约 | opencode | `docs/data/schema.md` §17（Matter 三方投影对账）+ `sim/npc/memory.py` 契约 + 对账锁定测试 | ✅ main `e77d25c` | integrity/decay_rate/is_rubble ↔ `matter_state` 列 ↔ MatterPayload 三方一致表；§17.2 缺口 `decay_rate` 无事件承载 → 方案 A 当时待裁、后由 `653d395` 落地 |
| M2-P4 第三批预算预案 | pi | `docs/perf/m2-p4-budget-preplan.md` | ✅ main `1813cbb` | smell 接线拆表 / `flush_tick` 异步不进 tick 断言 / cognition 骨架成本上界建议；§4 分「已落地 vs 待裁决」两栏（阈值真相源仍 `thresholds.py`） |
| M2-K3 返工验收清单 | kilo | `docs/api/ws-message-diff.md` | ✅ main `d7f066f` | 22 个缺失 schema 清单（标来源路由）+ 61 处字段级差异（ADD 22 / DEL 10 / MOD 29）+ 4 处 WS channel 错值 + subject 等整字段删除 + nullable→oneOf-null 三种正确形样例 |
| M2-C5 nightly 红灯修复（本域） | cline | `.github/workflows/nightly-bench.yml`（`mkdir -p perf` + 上传 `if: always()` + `runner.txt` 归档） | ✅ main `dd8e253` | 根因=`perf/` 目录不入库 → pytest-benchmark 收尾 `save_json` 抛 `FileNotFoundError`（4/4 跑必现）；3 次 dispatch 实证：FileNotFoundError 消失、artifact 首次非 0（含 CI 档位 `runner.txt`：ubuntu-latest / nproc 4 / AMD EPYC 9V74）；残留微基准边缘越线（每轮集合不同、超 2–9%）=runner 负载抖动，非管道问题，移交裁决（`PI_BENCH_ADVISORY` 已批、落地归 pi） |
| M2-S5 M3 安规预研 | codex | `docs/security/m3-preplan.md` | ✅ main `3c69158` | R1-R7 记忆/知识传播缝、C1-C13 建造输入面、X1-X8 triggered 扫描面 + §4 验收口径（零代码） |
| M2-D5 M3 数据预研 | opencode | `docs/data/vec-preplan.md` + `docs/data/schema.md` §19 | ✅ main `ee70aad` | sqlite-vec vs numpy 余弦方案 + 5 万条量级估算（非瓶颈）+ `LlmClient.embed` 缝 + V1-V7 待裁决；`materialize_matter` 契约入 schema §19 |
| M2-P5 嗅觉接线预算落地 | pi | `thresholds.py::SMELL_WIRED_TICK_LIMIT_MS=1.0` + `test_bench_smell.py` 接线版三用例 | ✅ main `7cfe842` | 接线版红线 1.0ms；复测 50 源 0.116ms（余量 ~8.6×） |
| M2-K3 复验 | kilo | `docs/api/ws-message-diff.md` §4.3 复验结论 + 快照侧对齐回写（`ce68e5a`） | ✅ main `e10c6cd` | 判据达成：白名单外结构 diff = **0**（五项全绿：`MISSING in ext` ≤5 / 逐字段 44+8 required 归零 / 4 处 channel 错值归零 / nullable 归零 / paths `{id}`→`{profile_id}`）；未消项不阻塞 M5，切源解禁仍待 M5 + sim 404 声明 |
| M2-A2 第四批 | Claude | `docs/arch/m3-plan.md`（M3 规划整合稿） | ✅ main `805166e` | 三份 M3 预研的整合骨架：批次 A-D 切分（A 向量 / C 地图可并行，B 等 A 接口冻结，D 收尾）+ 安规钉子横切（M3-S1 两枚 RED 先于一切实现）+ §6 待裁决队列 + M3 量化验收逐条对照落点 |
| M2-C6 README 补表（本域） | cline | `docs/README.md`（§2 文档地图 +5 行 / §5 第五轮 +5 行 + 5 处过期状态校正） | ✅ main `4470fd0` | 表列数一致性 + 无冲突标记双检通过；摘要口径微调被采信（裁 6：ws-message-diff 按文档原文写「未消项不阻塞 M5」）；缺行 gap 已转 C7 本单补齐 |
| M2-D6 vec 裁决栏 | opencode | `docs/data/vec-preplan.md` §7 裁决栏 + `docs/data/schema.md` §19「注册≠落库」核对 | ✅ main `414acb5` | V1/V4/V6 采结（A 主 B 降级 / vec 表为准、BLOB 仅写缓存 / 召回端治理过滤红线归 codex R2）；V2/V3/V5/V7 挂起（改 schema 须提案、S1 敏感须 codex 复核）；纯文档零迁移，alembic 零漂移（收编 `8470f3b`） |
| M2-P6 advisory 门 | pi | `sim/tests/bench/harness.py`（`PI_BENCH_ADVISORY`）+ `thresholds.py` RNG 330 + `test_bench_advisory_gate.py` + `docs/perf/ci-calibration-m2p6.md` | ✅ main `8fd9a17` | 落地裁 1：nightly 置 `PI_BENCH_ADVISORY=1`（越线只 structlog warning 不红、采集零改动）；裁 2：RNG 1M 警戒 300→**330ms**（CI 档位实测）；附 CI 档位定标提案（收编 `3c20b7c`） |
| M2-C7 README §5 补齐（本域） | cline | `docs/README.md`（§5 +11 行：第四轮 / A2 第四批 / 第六轮 + K2 状态消重） | ✅ main `0eff1e9` | §5 表 36 行×5 列一致、无冲突标记、11 个 commit 逐一 `merge-base --is-ancestor` 实测；已知缺行清零 |
| M2-A2 第五批 | Claude | `docs/arch/m3-plan.md` 批次 B 架构细化 + B1 双列口径落地（`memory_store.py` 双实现 + `memory_scan.py`） | ✅ main `3bf49be` | B1 = `iter_visible` 双列口径（`superseded_by` / `invalid_reason` 任一非空即检索不可见，修 R3 的 S5 旁路），TDD 先 RED 后 GREEN；批次 B 模块/文件级施工图（传播=复制写等） |
| M2-A2 第六批 | Claude | `sim/core/events.py`（`NPC_HIDDEN_EMERGE` + `HiddenEmergePayload`）+ `sim/npc/evidence.py`（`judge_third_party_hidden`）+ `sim/npc/propagation.py`（`retell()` 复制写） | ✅ main `1ae9e54` | 把 codex M3-S3 的 **26 RED 全部转绿（26/26）** + retell 复制写 4 用例；结构化拒绝 reason 无词面（X4 修订：descriptor/label/triggered 永不入事件） |

### 5.2 M3 交付状态（第七轮起；批次 A/B/C/D 全收口）

| 路 | Agent | 交付物（提交） | 状态 | 实测 / 结论 |
|---|---|---|---|---|
| M3-S1 安全钉子（两枚 T1 RED） | codex | `sim/tests/test_t1_m3_vec_governance.py`（R2）+ `sim/tests/test_t1_m3_matter_bounds.py`（C2） | ✅ main `2daa644` | 先红后绿钉子：R2 召回治理（`superseded_by`/`invalid_reason` 非空不得进向量候选、supersede 级联即时）5 用例 + C2 MatterPayload 域约束 29 用例；失败指纹=ImportError `VecCandidateSource`；随批次 A4/C4 转绿（收编 `7328dfc`） |
| M3-S2 R5 证据链契约稿 | codex | `docs/security/m3-evidence-chain.md`（152 行） | ✅ main `d81cf11` | 三路判定：witnessed（emerge 事件 + witnesses 双证据）/ told（0.9×0.6^n 衰减、下限 0.1、链须完整）/ inferred（禁他人属性，无例外）；自我披露作链根特例；+ E1 提案（extra=forbid、attr_ids 走 delta）+ knowledge 五列 + §8 七条 T1 钉子（收编 `cf7fa8a`，裁 8 采） |
| M3-D1 向量缝接口 + C2 域约束 | opencode | MatterPayload 域约束（C2 钉子 29/29 转绿）+ `VectorIndex` 接口草案（SqliteVec / NumpyCosine 双实现，A3） | ✅ main `4da190d` | C2 钉子全绿；R2 治理钉子余 3 RED 留 A4 收口（收编 `d7178fe`） |
| M3-P1 检索缝预算案 | pi | `docs/perf/m3-retrieval-budget.md` + `bench-plan.md` / `budget.md` / `llm-monitoring.md` + embed 监控事件族 | ✅ main `1d09581` | 实测（本机多轮中位）：候选 0.019ms/NPC、打分 600 候选 0.862ms、正常形态（k=20）≈0.05ms/NPC；红线提案 2 项随 A4 落地；附 baseline.json 8 步建立流程（收编 `fbd4e71`：裁 7 采红线 4 项 + V5） |
| M3-D2 批次 A 收口（A4 + C1） | opencode | `sim/core/persistence/{vector,npc_store}.py` + `sim/tests/bench/thresholds.py` | ✅ main `caddcdd` | A4 治理 JOIN 收口（R2 3 RED→0：召回 SQL 内联 JOIN + `superseded_by IS NULL AND invalid_reason IS NULL` push-down，保留 rowid 候选身份）；裁 7 四红线进 `thresholds.py`；C1 `materialize_matter` 照抄 schema §19；门禁 923 passed / ruff / pyright 0 error / alembic 零漂移（收编 `e2f8863`） |
| M3-P2① 检索缝四红线 bench | pi | `sim/tests/bench/test_bench_retrieval.py`（364 行，8 用例）+ `thresholds.py` | ✅ main `48db6cf` | 四红线实测对账：候选 0.233ms（余量 1.29× 偏紧）/ 打分 0.057ms（5.3×）/ 退化哨兵 0.970ms（2.06×）/ tick 常态 2.9ms（④ 拆常态 + 退化两口径）；附 R2 最小自证契约用例 |
| M3-S3 E1 验收钉子（26 RED） | codex | `sim/tests/test_t1_m3_hidden_emerge.py`（486 行） | ✅ main `56a6fa4` | 12 用例 E1 事件形状（kind 注册 / `HiddenEmergePayload` extra=forbid / 工厂 witnesses 形 / 二阶 RED 防「未注册」误点绿）+ 2 用例 delta 语义（`triggered_now - triggered_prev`、无 delta 不发事件）+ 证据链三路判定，**26 用例全 RED**，实现归 A2 第六批（收编 `5596537`） |
| M3-D4 knowledge 治理七列（B3 实施） | opencode | `0005_m3_knowledge_governance`（add_column×7 + 索引×3 + CHECK×3，CHECK 走 `op.batch_alter_table`）+ `sim/core/persistence/knowledge_store.py` + `sim/llm/memory_scan.py`（`decide()` 抽出为唯一判梯）+ `sim/tests/test_t1_m3_knowledge_cascade.py`（20 用例） | ✅ main `30dd087` | 裁 10 全采：继承失效不继承替代（沿 `source_knowledge_id` 广度递归、表内无替代指针、已失效行幂等仍下钻、全 SQL 带 `branch_id`）；X7 写入门=记忆/知识共用 `decide()`，知识表不可能成扫描旁路；`evidence_seq` 复用 M2-D3 `seq_by_index` 投影缝回填；门禁 995 passed / 55 skipped、ruff ok、pyright 0 error、alembic 零漂移 |
| M3-C3 chunk 失效通路 + §19.4 提案 | opencode | `sim/world/{map,pathfinding}.py` + `sim/tests/test_m3_chunk_invalidation.py` + `docs/data/matter-register-proposal.md` | ✅ main `5724aa7` | `TileMap` PrivateAttr 脏集（mark/drain/`with_collision` 不可变换图）+ `event_tile_position`（TILE_CHANGED 全量、MATTER 仅 x/y≥0、-1 哨兵不标）+ `Pathfinder.observe_events`/`observe_map` 精确失效；24 用例钉死「剔 1 留 1 / 未定位 no-op / 封格绕行 / 全封不可达」；提案主张 MATTER_BUILD 立账否 structures 注册主路径（全量 1081 passed / ruff / pyright 0） |
| M3-§19.4 注册持久化裁决 | Claude | `docs/data/matter-register-proposal.md`（提案→已裁）+ `docs/data/schema.md` §19.4 + `docs/arch/m3-plan.md` §6 同步 | ✅ main `16f2983` | 四点全采：①采 A 否 A'（零新 kind，`register` 产 `MATTER_BUILD` 立账）②采「返回事件不注入 EventSink」③structures M3 不建、留给 M4 ④x/y 默认 -1（与 C3 `event_tile_position` 哨兵天然衔接）；依据=主树实证 `_project_matter` 首事件即建行、折叠按 `durability` 而非 `amount`；实施放行 opencode（M3-C3 后续件） |
| M3-S6 收官门静态预审 | codex | `docs/security/m3-closure-preaudit.md`（`700015a`） | ✅ main `700015a` | 六钉子逐条对表 + S4 10k 闭环核对 + **5 发现**待裁（动态门结论见下行 M3-S6b） |
| M3-S6b 收官门动态复验（M3 收官行） | codex | `docs/security/m3-closure-preaudit.md` §7 回填 + `docs/arch/m3-plan.md` 状态行（`ZX466/codex` `686caa8`） | ⏳ 待收编 | 动态收官门通过：功能非性能全量 **1076 passed / 0 failed**、S4 10k 7 passed、七钉子+S4 148 passed；bench 11 failed/60 passed 按裁 1 advisory 判为负载抖动（retrieval/rng/smell 单独复跑全绿），soak CI smoke 单独红但仅性能门不阻断；pyright 0 error；**宣告 M3 收官（2026-09-25）**——分支已交付未进 main，收编后本行改 ✅ main |

### 5.3 M4 交付状态（进行中 · 批次 A/B/C/D 按裁 14 切分）

| 路 | Agent | 交付物（提交） | 状态 | 实测 / 结论 |
|---|---|---|---|---|
| M4-C1 计划骨架 + M4-C2 T4 nightly 接线（本域） | cline | `docs/arch/m4-plan.md`（136 行骨架→裁 14 填实）+ `.github/workflows/t4-nightly.yml` + `pytest.ini` `t4` marker | ✅ main `4b19f31`（C1）＋ C2 本轮交付待收编 | 裁 14 六条落档（批次边界照切 / 看板落前端 / 运气只进事件流 / D 批担 T5…）；**T4 接线骨架**：锁 `claude-sonnet-5`（模型 id 硬编码 workflow env，不进代码）、secret `T4_MODEL_API_KEY`、cron UTC 19:30（与 nightly-bench UTC 18:00 错开）、**仅 schedule/dispatch 不进每提交 CI**（§16 铁律）、探针步骤留 TODO 指向 M4-S1；`t4` marker 补注册（`--strict-markers` 要求先注册） |
| M4-D1 建造域数据面预研 | opencode | `docs/data/build-domain-preplan.md` | ✅ main `a725a65` | structures 拓扑投影瘦身 + 建造事件族 + checkpoint 推进 + 承重图 + 材料守恒；**裁 14 采信主干 7 点全裁**（细则见 `m4-plan.md` §6 第 2 条，含 pi M4-P1 摊还硬约束交叉对账） |
| M4-P1 建造预算预研 | pi | `docs/perf/m4-build-budget-preplan.md` | ✅ main `88284c3` | tick 预算盘点（余量 2.10ms=13%）+ 坍塌 BFS 成本模型（BFS 10k=1.27ms vs 逐对象事件 51ms=307% tick）+ 施工推进语义 perf 建议 + 红线草案框架 |
| M4-B2 意愿冲突度管线 v0 | Claude | `sim/agent/will.py` + `sim/tests/test_m4_willingness.py` | ✅ main `5a8c1b9` | w₁–w₄ 加权和（初版均分 0.25）+ 四档表现（0.3/0.6/0.8）+ 12 钉子；抱怨词面全自我怀疑族（§19 禁被操纵感）；frozen `WillingnessVerdict` + 模板确定性（C5）；「但最终都执行」由类型层保证（不回写效用分数） |
| M4-S1 三面词面边界 + T4 探针集提案 | codex | 念头/意愿/运气三面词面边界 + T4 探针集提案（`ZX466/codex` `346dfa1`） | ⏳ 待收编 | **T4 接线唯一缺口**：探针集收编后由 cline 把探针步骤接进 `t4-nightly.yml`（接线约定五条已写在 workflow 注释） |
| M4-D2 建造数据面施工 | opencode | 基于 D1 预研的施工件（在途） | ⏳ 在途 | 裁 14 第 2 条七点细则施工；同轮修正 `(branch_id, structure_id)` 复合主键 + matter identity 对账 = 首个迁移件 |

### 5.4 M5 预备（接口锚点，零代码契约先行）

| 路 | Agent | 交付物（提交） | 状态 | 实测 / 结论 |
|---|---|---|---|---|
| M5-K1 anchors 契约稿 | kilo | `docs/api/anchors-api.md`（306 行，零代码） | ✅ main `b849025` | 三路由契约四要素齐：GET 列表空库 `[]` 非 404 / POST 仅 `name`（游标由服务端从会话取）/ PATCH `name` 必填非可空 / DELETE protected 时 409；+ §5 施工清单与 sim 404 handler 提案（收编 `db46b9e`） |
| M5-K2 anchors 路径参数归一 | kilo | `shared/openapi.json` + `shared/protocol.ts` + `docs/api/{anchors-api,openapi}.md` + 前端 K03 #5 | ✅ main `5cf58c9` | `{id}`→`{anchor_id}` 三处同步（K03 惯例），旧模板从 paths 消失；§6 四项待决议提案（protected 并发 `asyncio.Lock` 等）（收编 `372153a`，四提案全采=裁 9） |
| M5-K3 anchors 验收对表 | kilo | `docs/api/anchors-api.md`（§5 施工清单 + 验收对表、§5.1 responses 注入点）+ `tools/gen-protocol.ts` 头注登记 | ✅ main `c25b979` | 7 项逐条补验收标准并标三类断言 `[T]` pytest / `[O]` OpenAPI 静态形状 / `[C]` 前端类型；覆盖空库 `[]` 非 404、越权字段 422、出戏字段不回传等易错点；注入点 = `openapi_ext.py::custom_openapi()` L445（须在 get_openapi 之后、strip 之前）（收编 `32ef4fe`） |
| M3-C3 chunk 失效通路 + §19.4 后续件 | opencode | `sim/world/{map,pathfinding,matter}.py` + `sim/tests/test_m3_{chunk_invalidation,matter_register}.py` + `docs/data/matter-register-proposal.md` | ✅ main `29f9d6c`（收编本 merge） | `TileMap` PrivateAttr 脏集 + `Pathfinder.observe_events`/`observe_map` 精确失效（24 钉子）；`register` 返回 `MATTER_BUILD` 立账事件（amount=0、durability=integrity、x/y=-1），flush_tick 快照/flush_events 重放冷启均不丢、逐位相等（9 钉子）；零 schema、零生产调用方 |

### M2 依赖对账（M2-C1 结论：**零新依赖**）

| 路 | 分支实测新增 import（`git diff origin/main ZX466/<树> -- '*.py'` 的 `+` 行） | 依赖结论 |
|---|---|---|
| codex M2-S1 | `re` / `dataclasses` / `typing` / `pydantic` / `pytest` + 本仓模块 | 零新包（标准库 + 已锁 pydantic/pytest） |
| pi M2-P1 | `time` / `numpy` / `pytest` + `sim/tests/bench/{harness,thresholds}` | 零新包（numpy、pytest-benchmark 已锁） |
| opencode M2-D1 | `sqlalchemy` / `alembic` / `sqlite3` / `json` | 零新包（SQLAlchemy 2.0 async + Alembic 已在锁） |
| kilo K04 | 无 Python 改动；前端只改测试与文档 | 零新包（openapi-typescript / prettier 已锁；Node ≥24 已定，CI setup-node 已对齐） |

- **证据（硬指标）**：四分支 `git diff --stat origin/main <branch> -- pyproject.toml uv.lock client/package.json client/package-lock.json` **全部为空** —— 零锁文件变更，故 M2 收编**不需要**除 `uv sync` / `npm ci` 之外的任何动作，CI 缓存键也不变。
- **M2-C2 追加（风场，2026-09-21）**：`sim/world/weather.py` 只用标准库 `hashlib`/`math`/`dataclasses`/`typing` + 已锁 `numpy`（经 `sim.core.rng`/`sim.core.calendar`），**仍为零新依赖**；`.github/workflows/*` 与 `docs/` 改动不涉依赖。
- **唯一待观察项**：embedding 生成来源（M3 记忆向量检索才触发）。走已锁 `openai` 客户端调远端 embedding API ⇒ 零新包；若改本地模型（torch / onnxruntime / sentence-transformers 等）⇒ 重依赖 + CI 体积暴涨，**须先过依赖评审再动**。M2 不触发：`sqlite-vec>=0.1.6` 已在锁，`sim/core/persistence/vector.py` 脚手架就位，`DEFAULT_EMBEDDING_DIM = 384` 待 M3 锁定。

### M2 CI 接入（现状）

- **命名门禁（M2-C1 立占位 → M2-C2 填实）**：「pytest M2 验收测试」按**文件路径** glob `sim/tests/test_m2_*.py` 选择（纪律同 T3/M1，不用 marker）。**命名约定即契约**：新 M2 验收测试落到该前缀即自动纳入门禁；现役 `test_m2_npc_base.py`（架构域）+ `test_m2_weather.py`（配置域，31 用例）。落地要求：无 LLM、秒级~分钟级；步骤内 `-m "not bench"` + `timeout-minutes: 15` 双护栏。
- 已由他域单独接入的 M2 门禁（不重复接）：`sim/tests/test_t1_self_unknown.py`（codex 自带步骤）；`sim/tests/test_persistence_m2.py` 纯 T1、随 `-m "not bench"` 全量跑。
- nightly：M2 红线**不复制数值**，唯一真相源 `sim/tests/bench/thresholds.py`；pi 的两个 M2 bench 文件随 `-m bench` 自动纳入，**无需改 yml**。
- **待裁（Claude）**：完整 7 日自转验收（604,800 tick）的定期接法（新增 `-m m2full` 类 marker + nightly job，还是只在里程碑本地跑一次）。marker 语义属配置域但**接法由主导裁决**，cline 不擅自定；裁决后在本节 + nightly 注释回填。

### `.gitattributes`（行尾统一）—— 已落地

裁决采纳方案 A（main `3ab8c71`）：`.gitattributes` = `* text=auto eol=lf`；`.gitignore` 同批补 `!.github/`（`.orca/` 下**新增**文件仍需 `git add -f`）。**重签出操作手册见 `docs/dev-workflow.md` §7**（每树一次：`git rm -r --cached . && git reset --hard`；`git checkout-index -f -a` 实测无效）。M2-C2 已按该手册完成六树重签出。

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
