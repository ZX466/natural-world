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
| `docs/arch/m5-plan.md` | 架构/文档（cline 起草 · Claude 裁） | ✅ main（**裁 21 已回填**） | M5 规划：§17 M5 行七件事拆条（混沌/双轨存档分叉重放/时间刻度/权力牙齿/火灾蔓延/生态/断线降级演练）+ 批次 A–E 切分（**边界沿用骨架**）＋ **各批次行已回填裁 21 裁决指针与已派任务**（A＝裁 21-A D-1~D-4，**时间刻度＝玩家侧快进/变速**非日历；B＝裁 21-B 裁 1~12 ＋ F3/0008-a 前置；C/D＝**§18 可砍序位 5 / 生态 1 / 蔓延 2，只注不砍**；E＝裁 21-C③ 演练级挂 T5 体系）＋ 门禁归属（**M5 预期新增 nightly 只有「演练级」＝ `golden-nightly` 扩展候选、批次 E 接线**）＋ **§2 G-6 解锁条件（F1 ＋ F3 两前置齐）** ＋ §6 裁决区七条逐条落裁况（**两条留待开工前补裁**：权力牙齿验收判据 / 离线判据量纲）；验收＝「离线再回来世界已变；C6 测试绿」（C6＝T1 历史不可销毁） |
| `docs/arch/m5-rulings.md` | 架构/裁决（Claude 主导） | ✅ main `bc8962f` | **M5 裁决 21**：§A kilo 协议面 D-1~D-9（时间刻度＝玩家快进/变速、不扩 speed 枚举 ＋ 新 action `fast_forward`、暂停幂等单值并清 G-1~G-3、new session 帧分叉告知且 `branch_id` 禁出网关、**不预留 catchup 字段**、戏外 HTTP 只读路由）／§B opencode 数据面 裁 1~12（F1 **必落 0008-a**、**不加 global_seq**、F3 **M5 硬前置**、**不破冻结事件基线**）／§C cline 三口径（**C6 测试绿＝T1 历史不可销毁** 确认、**不预砍**、**不新造 T6**）／§D pi soak 继续 advisory ＋ 3 轮红强制定标机／§E T4 判定口径（舞台指示剥离 ＋ P4-05 语料改写） |
| `docs/arch/t5-golden-scaffold.md` | 架构/文档（cline 起草 · Claude 裁） | ✅ main | T5 golden 脚手架提案：形态（虚拟时钟+有界帧驱动+录制 fixture 回放）+ 文件布局 + 三断言组口径（裁 17 定阈值：守恒逐位相等/完成率 10 日重定标/孤儿硬红）+ 跑法两案（采独立 `golden-nightly.yml` 种子分片 matrix，M4-C5 已接）+ runtime 实测（10 游戏日=864,000 tick/种子） |
| `sim/tests/golden/` + `.github/workflows/golden-nightly.yml` | 测试分级/CI（cline） | ✅ main | T5 golden 资产包：驱动器 `driver.py`（虚拟时钟有界帧驱动）+ 十种子清单 `seeds.py`（真相源）+ 三断言组 `assertions/*`（裁 17 口径）+ 全量验收 `test_golden_full.py`（`PI_T5_FULL=1`）+ 冒烟 `test_golden_smoke.py`（`PI_GOLDEN_SMOKE=1`）；**均 env 门默认跳过，不进每提交 CI**（§16 T5 每日跑） |
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
| `docs/perf/baseline-epyc7763.json` | 性能（Pi）基线 / CI 域（cline 维护） | ✅ main（**M5-C4/C5 按 §4.1 整体重生成；M5-C6 按机型分文件**） | **CI 档位相对基线（按机型分文件，命名 `baseline-<machine_key>.json`）**（pytest-benchmark compare 真值源，nightly「基线对比」step `--benchmark-compare-fail=median:25%`）：**59 行单一 provenance**，源 run **`36580639759` 全绿**（2026-09-29，AMD EPYC 7763/nproc4/py3.12.3）；前两代记于 `rows_provenance.supersedes`；**main-ref 复跑 `36670751263` 亦全绿但落在 Intel Xeon 8573C，按「不同档位不能混基线」未采用**；M5-C6 起 workflow 比对**固定本机型文件**并在 runner 机型不一致时**只打 warning 不判红**；⚠ 未决：**Xeon 档位基线未建**、`ubuntu-latest` 池跨厂商漂移 |
| `docs/perf/m3-retrieval-budget.md` | 性能（Pi） | ✅ main | M3 检索缝预算案：候选/打分/退化哨兵/tick 四红线设计稿（实测候选 0.019ms、打分 600 候选 0.862ms、正常形态 ≈0.05ms/NPC）+ V5 裁决输入 + **失效通路实测附录（M3-P3）** |
| `docs/perf/ci-calibration-m2p6.md` | 性能（Pi） | ✅ main | CI 档位定标提案：nightly advisory 门（`PI_BENCH_ADVISORY`）+ CI 实测档位基线口径（RNG 1M 警戒 300→330 的依据） |
| `docs/perf/m4-build-budget-preplan.md` | 性能（Pi） | ✅ main `88284c3`（+ 附录 M4-P2 `6e7182e`） | M4-P1 建造预算预研 + **M4-P2 定标附录**：tick 预算盘点（上限表余量 2.10ms=13%）+ 坍塌级联成本模型（BFS 10k=1.27ms vs 逐对象事件 51ms=307% tick）+ 施工推进语义 perf 建议 + **红线定标实测**（施工推进 0.30ms / 坍塌单帧 0.85ms，向下修正草案）|
| `docs/perf/m4-willingness-hotpath.md` | 性能（Pi） | ✅ main `3eaec73` | M4-P3 意愿/独白热路径补数：`willingness_expression` 0.04-0.4µs/调用 + B3 注入缝 2.1(band0)/167µs(band≥1) + `runtime.tick` 增量 None→注入 **+0.20ms/tick** + 提案 `WILLINGNESS_TICK_LIMIT_MS=0.35`（观察态）|
| `docs/perf/m4-p4-golden-runner-review.md` | 性能（Pi） | ✅ main `4984d75` | M4-P4 golden runner 档位复核：golden 与 bench 选择集互斥（不撞 M4-P2/P3 红线）+ `timeout-minutes: 90` 余量（CI 外推 10 实体 ~1-2min/种子，50 实体 ~4.6min）+ **内存风险**（全事件累积 10 实体 3.4GB / 50 实体 17GB）+ CI 档位红线余量（施工 0.89x 越线 / 意愿 band1 0.97x 贴线）|
| `docs/perf/m5-time-scale-fork-budget.md` | 性能（Pi） | ✅ main（**裁 21-D 已裁**） | M5 性能预研（M5-P1，提案制零代码）：时间刻度快进 ＋ 双轨存档多分支 fold 成本模型，与 opencode M5-D1 九点交叉对账；裁 21-D：soak 继续 advisory ＋ **追加观察项「soak 连续 3 轮全量门禁红 ⇒ 强制定标机复测」**；派生单 **M5-P2**（`fast_forward` 预算提案 ＋ F3 落地后 `RETRIEVAL_*` before/after，在途） |
| `docs/config/m5-c7-workflow-audit.md` | 依赖/配置/文档（cline） | ✅ 审计稿（提案制，零 yml 改动） | **workflow 台账巡检 + T4 接线两口径预研**：四 workflow 触发器/cron(UTC+北京)/marker 与路径过滤/secrets 活跃行/TODO 命中全量实测（**全仓 workflow 零 `TODO`、活跃行 `secrets.` 0 次**；纠偏 codex 两条过期提醒：env 已是 `Deepseek-v4-flash`、探针段是**显式裁定的长期注释态**非 TODO）＋ **T4 两口径对比**（甲＝本地真模型探针一轮＝等效验收，零改动/零持续成本/回归保护弱；乙＝GitHub 自动接线，三处必改其中 🔴 **`T4_RUN=1` 漏注即假绿灯**）＋ 点名 `m4-plan.md` §4「T4 全绿」定义与改约后口径**两个真相源**（跨域只报不改） |
| `docs/config/m5-c9-t4-probe-runbook.md` | 依赖/配置/文档（cline） | ✅ runbook（执行单，零 yml 零代码） | **T4 本地探针等效验收轮执行单**（裁 31-T4 口径甲）：§1 前置清单（三把锁/锁版本 `Deepseek-v4-flash` @ `chatapi.weixin.qq.com`／**直连不走 7897 代理**／key 纪律＝运行时环境变量**永不落盘**）＋ §2 真跑命令与预期（`uv run pytest sim/tests/test_t4_probes.py -m t4`，**53 用例实测基线**，≤60 调用预算闸）＋ §3 留痕（`t4-results/t4.xml` + `t4-report.json`，**已 gitignore 永不入库**；结论三处落点）＋ §4 **两道判据**（先判形态：exit 5／全 skip／无报告**均不是绿**；再判内容：`hard_red[]`／`inconclusive[]`）＋ §5 三类失败分支（4xx 鉴权／timeout·connection·rate_limit·5xx 抖动／硬判定泄漏＝唯一真红）＋ §6 key 到位后执行许可流程。**只诊断不代改探针代码**（探针归 codex）。**本单未真跑**（key 未到位） |
| `docs/data/schema.md` | 数据/数据库（opencode） | ✅ main | SQLite schema：事件日志（append-only）/分支树/快照分层/玩家 anchor/NPC 记忆 + sqlite-vec 占位；索引与约束对齐 §6 契约 |
| `docs/data/event-sourcing.md` | 数据/数据库（opencode） | ✅ main | 事件溯源：`apply(event)` 唯一写路径、读档重放流程、回放确定性（RNG/熵随事件落库） |
| `docs/data/migration.md` | 数据/数据库（opencode） | ✅ main | Alembic 迁移策略（async env.py / alembic.ini / 首版迁移骨架） |
| `docs/data/vec-preplan.md` | 数据/数据库（opencode） | ✅ main | M3 记忆向量检索预研：sqlite-vec vs numpy 余弦、5 万条量级估算（非瓶颈）、`LlmClient.embed` 缝、V1-V7 待裁决清单 |
| `docs/data/matter-register-proposal.md` | 数据/数据库（opencode） | ✅ 已裁并实施 | §19.4 注册持久化：`register` 返回 `MATTER_BUILD` 立账事件（零 schema），structures M3 不建；4 点裁决 + 9 用例实施记录 |
| `docs/data/build-domain-preplan.md` | 数据/数据库（opencode） | ✅ main `a725a65` | M4-D1 建造数据面：structures 拓扑投影、建造事件族、checkpoint 推进、承重图、材料守恒；**裁 14 采信主干 7 点全裁**（细则见 `docs/arch/m4-plan.md` §6 第 2 条） |
| `docs/data/m5-fork-archive-preplan.md` | 数据/数据库（opencode） | ✅ main `cee593c`（**12 点已全裁** `docs/arch/m5-rulings.md` §B；M5-D2 已落 2 项） | M5-D1 双轨存档存储面（读档=分叉）：branch_id 全局化取舍（同表加列 vs 分文件，0008 只预估）、分叉物理形态（克隆 vs 重放 vs 谱系回退读）、玩家档游标表 schema 草案、fold 跨分支 C1-C6、T2 分叉重放 R1-R3 口径、与 pi M5-P1 九点交叉对账（**已回填实测常数**）；三条硬发现（`npc_profiles` 主键单列 / 语料三表无事件源 / 向量召回零分支隔离）+ 12 待裁点。**已落**：§2.4 案 C（T1 断言 5 改 `(branch_id,seq)` 对集合，6 钉子）+ §5-C5（F3 向量召回分支隔离，`vector.py` 召回句加 `m.branch_id = ?` + over-fetch 抗饥饿，6 钉子） |
| `docs/api/ws-protocol.md` | 接口/兼容性（kilo） | ✅ main | WS 消息协议：消息类型清单与字段 schema、出戏边界（哪些字段绝不外发） |
| `docs/api/openapi.md` | 接口/兼容性（kilo） | ✅ main | HTTP 端点设计：设置页 / Profile 管理 / 存档 anchor CRUD；api_key 只在后端流转 |
| `docs/api/codegen.md` | 接口/兼容性（kilo） | ✅ main | OpenAPI → `shared/protocol.ts` 生成管线（openapi-typescript + banner + prettier）；CI 三道守卫（漂移检测已接 ci.yml / banner / 禁手写） |
| `docs/api/versioning.md` | 接口/兼容性（kilo） | ✅ main | 协议版本策略：WS version 字段/协商方式，client 与 sim 独立演进 |
| `docs/api/ws-message-diff.md` | 接口/兼容性（kilo） | ✅ main | ext↔快照逐成员 diff 明细 + K3 复验结论（§4.3：白名单外 diff = 0、契约对齐完成；未消项**不阻塞** M5，切源解禁仍待 M5 + sim 404 声明） |
| `docs/api/m5-prestudy-timescale-and-fork.md` | 接口/兼容性（kilo） | ✅ main（**裁 21-A D-1~D-9 全裁**） | M5 接口面预研（M5-K1，零代码）：§1.4 协议面既有缺口 **G-1~G-8**（G-1 协议违约 `speed:0`／G-6 **分叉零写入方＝阻塞 M5**／G-7 无连接期刻度下发面…）＋ 时间刻度控制面 ＋ 读档=分叉协议面；派生单 **M5-K2**（D-8 rtoken 文档订正，已交待收编） |
| `docs/api/anchors-api.md` | 接口/兼容性（kilo） | ✅ main | anchors 三路由契约稿（字段/校验/状态码/示例四要素齐）+ §5 施工清单 + 验收对表（[T] pytest / [O] OpenAPI 静态形状 / [C] 前端类型三类断言）+ §5.1 OpenAPI responses 注入点 |
| `docs/dev-workflow.md` | 依赖/配置/文档（cline） | ✅ main | 环境与常用命令：uv/pytest/ruff/pyright、npm/tsc/eslint/vitest、T1–T5 marker 跑法、bench nightly 跑法、CI 对应关系 |

状态图例：✅ main = 已在 main 分支；⏳ 待收编 = 已在对应 agent 分支产出，等 Claude（主导）统一收编（**当前：全数收编；2026-09-30 台账补翻历史遗留 9 行**）。

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
| M4-D2a structures 事件族 + 0006 | opencode | `sim/core/events.py` + `sim/core/persistence/{event_validation,models,npc_store}.py` + `alembic/versions/0006_m4_structures.py` + `sim/tests/test_{t1_m4_structure_payloads,m4_structures_schema}.py` | ✅ main（收编本 merge） | 6 kind（structure started/checkpoint/completed/collapsed/removed + material.moved）payload/factory/PAYLOAD_MODELS；structures 瘦身表 + `(branch_id, structure_id)` 复合主键；matter_state 改 `(branch_id, subject_id)` 复合主键，关闭跨分支投影串写；C1/C2/C3/C5/C7 钉子 52 + schema/迁移 8 |
| M4-D2b structure 单折叠 + checkpoint | opencode | `sim/world/structure.py` + `sim/core/persistence/npc_store.py` + `sim/tests/test_m4_{structure_projection,build_checkpoint}.py` | ✅ main（收编本 merge） | `fold_structure_snapshot` 投影/重放共用（phase 由 kind 推导、rubble tombstone、REMOVED 删行）；`materialize_structures(_replay)` 逐位相等；纯函数 `advance_build`/每日 checkpoint/`build_rule_version` fail-closed/尾部重算；25 钉子 |
| M4-D2d 材料守恒 + 地图派生接线 | opencode | `sim/core/persistence/alembic/versions/0007_m4_material_balances.py` + `sim/{core/persistence/npc_store.py,world/structure.py}` + `sim/tests/test_t1_m4_{material_balance,tile_derivation}.py` | ✅ main | MATERIAL_MOVED 双边投影：`world:*` 外部基准可净负、npc/structure 非负 fail-closed，快照/重放共用单折叠；同批 events+structures+balances 三面回滚；终态逐 tile 派生 TILE_CHANGED 并验证 C3 精确 chunk 失效；15 钉子 |
| M4-D2c 10k 承重图 + 摊还级联 | opencode | `sim/world/support_graph.py` + `sim/tests/test_t1_m4_support_graph.py` | ✅ main（收编本 merge） | 内存正/反向图：同分支/无环/承重资格/悬空自环重复边拒绝；稳定排序 BFS 游标按帧最多 100 条 STRUCTURE_COLLAPSED；10k 节点=100 帧全量摊还验收；support_path 只记直接支撑 |
| M3-S6b 收官门动态复验（M3 收官行） | codex | `docs/security/m3-closure-preaudit.md` §7 回填 + `docs/arch/m3-plan.md` 状态行（`ZX466/codex` `686caa8`） | ✅ main | 动态收官门通过：功能非性能全量 **1076 passed / 0 failed**、S4 10k 7 passed、七钉子+S4 148 passed；bench 11 failed/60 passed 按裁 1 advisory 判为负载抖动（retrieval/rng/smell 单独复跑全绿），soak CI smoke 单独红但仅性能门不阻断；pyright 0 error；**宣告 M3 收官（2026-09-25）**——分支已交付未进 main，收编后本行改 ✅ main |

### 5.3 M4 交付状态（进行中 · 批次 A/B/C/D 按裁 14 切分）

| 路 | Agent | 交付物（提交） | 状态 | 实测 / 结论 |
|---|---|---|---|---|
| M4-C1 计划骨架 + M4-C2 T4 nightly 接线（本域） | cline | `docs/arch/m4-plan.md`（136 行骨架→裁 14 填实）+ `.github/workflows/t4-nightly.yml` + `pytest.ini` `t4` marker | ✅ main `4b19f31`（C1）＋ C2 本轮交付待收编 | 裁 14 六条落档（批次边界照切 / 看板落前端 / 运气只进事件流 / D 批担 T5…）；**T4 接线骨架**：锁 `claude-sonnet-5`（模型 id 硬编码 workflow env，不进代码）、secret `T4_MODEL_API_KEY`、cron UTC 19:30（与 nightly-bench UTC 18:00 错开）、**仅 schedule/dispatch 不进每提交 CI**（§16 铁律）、探针步骤留 TODO 指向 M4-S1；`t4` marker 补注册（`--strict-markers` 要求先注册）｜ **⚠ 现状标注（2026-10-02 裁 31-T4，M5-C9 加注）**：上句记的是 **M4 当时（2026-09-26）** 的交付事实，**历史不改**；此后口径已变更——① 锁版本由 `claude-sonnet-5` 改为 **`Deepseek-v4-flash`** @ `https://chatapi.weixin.qq.com/openai/v1`（M4-C6 `d1940e4`）；② **不建 GitHub secret**（`schedule` 已注释，只留 `workflow_dispatch`，2026-09-27 用户改约）；③ 探针步骤非待办，而是**显式裁定的长期注释态**（M4-C2 `c21c781`）；④ **验收口径＝本地真模型探针一轮＝等效验收**（「T4 全绿」自此指本地轮，**非 nightly 连续通过**，双真相源已合并以裁 31-T4 为准），执行单见 `docs/config/m5-c9-t4-probe-runbook.md` |
| M4-D1 建造域数据面预研 | opencode | `docs/data/build-domain-preplan.md` | ✅ main `a725a65` | structures 拓扑投影瘦身 + 建造事件族 + checkpoint 推进 + 承重图 + 材料守恒；**裁 14 采信主干 7 点全裁**（细则见 `m4-plan.md` §6 第 2 条，含 pi M4-P1 摊还硬约束交叉对账） |
| M4-P1/P2 建造预算预研 + 定标 | pi | `docs/perf/m4-build-budget-preplan.md` + `sim/tests/bench/test_bench_structure.py` + `thresholds.py` M4-P2 段 | ✅ main `88284c3`（P1）/ `6e7182e`（P2 附录） | P1：tick 预算盘点（余量 2.10ms=13%）+ 坍塌 BFS 成本模型（BFS 10k=1.27ms vs 逐对象事件 51ms=307% tick）+ 施工推进语义 perf 建议 + 红线草案；P2：实现实测定标（施工推进 100 点 0.175ms→线 **0.30ms** / 坍塌单帧 0.50ms→线 **0.85ms**，均向下修正草案；观察态 `_record_proposal`）|
| M4-P3 意愿/独白热路径 bench | pi | `sim/tests/bench/test_bench_willingness.py` + `thresholds.py` `WILLINGNESS_TICK_LIMIT_MS` + `docs/perf/m4-willingness-hotpath.md` | ✅ main `3eaec73` | B3 接线补数（13 用例）：expression 纯函数 0.04(band0)/0.4µs(band≥1) per call；B3 热路径 2.1µs(band0)/~165µs(band≥1) per tick；`runtime.tick` 50 NPC 增量 None 0.716→注入 **+0.20ms/tick**（+27.9%，占 16.6ms tick 1.2%）；提案线 0.35ms（只管注入增量，观察态）|
| M4-P4 golden runner 档位复核 | pi | `docs/perf/m4-p4-golden-runner-review.md` | ✅ main `4984d75` | 只读+文档：①golden/bench 选择集互斥、golden 零 import thresholds→**不撞 M4-P2/P3 红线**；②timeout 90 余量（CI 档位 ×1.7 外推，10 实体 ~1-2min/种子→50-100x 余量，50 实体 ~4.6min→19.5x）；③C3「53.4s/日」口径澄清（含 I/O 全墙钟 vs `mean_tick_ms`）；④**内存风险第一**（all_events 累积 10 实体 3.4GB / 50 实体 17GB）；⑤CI 档位红线余量（施工 0.3371→线 0.30 **0.89x 越线**、意愿 band1 0.361→线 0.35 **0.97x 贴线**）|
| M4-B2 意愿冲突度管线 v0 | Claude | `sim/agent/will.py` + `sim/tests/test_m4_willingness.py` | ✅ main `5a8c1b9` | w₁–w₄ 加权和（初版均分 0.25）+ 四档表现（0.3/0.6/0.8）+ 12 钉子；抱怨词面全自我怀疑族（§19 禁被操纵感）；frozen `WillingnessVerdict` + 模板确定性（C5）；「但最终都执行」由类型层保证（不回写效用分数） |
| M4-S1 三面词面边界 + T4 探针集提案 | codex | 念头/意愿/运气三面词面边界 + T4 探针集提案（`ZX466/codex` `346dfa1`） | ✅ main | **T4 接线唯一缺口**：探针集收编后由 cline 把探针步骤接进 `t4-nightly.yml`（接线约定五条已写在 workflow 注释） |
| M4-D2 建造数据面施工 | opencode | `0006_structures.py` + `sim/world/{construction,structures}.py` + `store.py` structures 投影 + `sim/tests/test_m4_construction*.py` | ✅ main（`c719171`，2026-10-02 补翻历史遗留行） | 裁 14 第 2 条七点细则施工；同轮修正 `(branch_id, structure_id)` 复合主键 + matter identity 对账 = 首个迁移件 |
| M4-C3 脚手架 + M4-C4 断言组（本域） | cline | `docs/arch/t5-golden-scaffold.md` + `sim/tests/golden/{seeds,driver,test_golden_smoke}.py` + `sim/tests/golden/assertions/{conservation,orphan_changes,errands_rate}.py` + `test_assertions_*.py` | ✅ main（脚手架 `f940ea0`）＋ 断言组本轮待收编 | 形态=虚拟时钟+有界帧驱动（对齐 `run_world_driver` 帧序/日切跨越判定）；冒烟满一日实跑 53.98s；**断言按裁 17 落码**：守恒逐位相等（折叠复用 `npc_store.fold_*` 单一规则，不重算领域算术）、孤儿双向硬红（熵只进事件流 + `structure.removed` 删行两个合法排除）、完成率只出基线壳（10 日重定标，暂不设阈值）；17 条最小单元测试全绿 |
| M4-C5 golden-nightly 接线（本域） | cline | `.github/workflows/golden-nightly.yml`（新建）+ `test_golden_full.py` 加可选报告器（`GOLDEN_REPORT_DIR`） | ✅ main（收编 `23a241a`） | 案 A 落地：**matrix 每 job 单种子**（内存 1/10＝规避本机单进程内存压力正解）、`timeout-minutes: 90`、`fail-fast: false`、每种子 artifact（GoldenRun JSON + junit + 机档 runner.txt，`if: always()`）、失败 step summary + `::error::`、**零 secrets**（T5 全 fixture）；种子 matrix 与 `seeds.py` 十枚**自动对拍一致**；**首跑（dispatch）10/10 全绿 → schedule（UTC 20:30）已放开**（run 36301690490；各种子 ticks 864,000 / days 10 / events 1,728,000 / mean_tick_ms 0.125–0.232 / 完成率 4-4=1.0） |

### 5.4 M5 预备（接口锚点，零代码契约先行）

| 路 | Agent | 交付物（提交） | 状态 | 实测 / 结论 |
|---|---|---|---|---|
| M5-K1 anchors 契约稿 | kilo | `docs/api/anchors-api.md`（306 行，零代码） | ✅ main `b849025` | 三路由契约四要素齐：GET 列表空库 `[]` 非 404 / POST 仅 `name`（游标由服务端从会话取）/ PATCH `name` 必填非可空 / DELETE protected 时 409；+ §5 施工清单与 sim 404 handler 提案（收编 `db46b9e`） |
| M2-K2b anchors 路径参数归一 | kilo | `shared/openapi.json` + `shared/protocol.ts` + `docs/api/{anchors-api,openapi}.md` + 前端 K03 #5 | ✅ main `5cf58c9` | `{id}`→`{anchor_id}` 三处同步（K03 惯例），旧模板从 paths 消失；§6 四项待决议提案（protected 并发 `asyncio.Lock` 等）（收编 `372153a`，四提案全采=裁 9）。**号段改记 `M2-K2b`**（原记 M5-K2）——裁 22 §A-2：M5-K2 号让与本轮交付实体（D-8 订正），**归档改号、不追改 git 历史**（`5cf58c9` 提交信息内的旧号不动） |
| M5-K2 D-8 口径订正 | kilo | `docs/api/{m5-prestudy-timescale-and-fork,ws-protocol,versioning,ws-message-diff}.md` + `shared/{openapi.json,protocol.ts}` + `sim/api/openapi_ext.py` + `sim/tests/test_m2_openapi_rework.py` | ✅ main `973ef02` | 裁 21-A D-8「**文档订正、实现不动**」：rtoken 稳定派生是本意（重连重建的是**前端状态**不是 rtoken）；rtoken 口径五处订正 + 生成管线 RToken 描述同步 + 断言钉子；与 pi M5-P2 / opencode M5-D2 同轮收编（`b188ba0` 交付 + `f6edd50` 预研稿同步裁 21-A 裁况） |
| M5-K3 anchors 验收对表 | kilo | `docs/api/anchors-api.md`（§5 施工清单 + 验收对表、§5.1 responses 注入点）+ `tools/gen-protocol.ts` 头注登记 | ✅ main `c25b979` | 7 项逐条补验收标准并标三类断言 `[T]` pytest / `[O]` OpenAPI 静态形状 / `[C]` 前端类型；覆盖空库 `[]` 非 404、越权字段 422、出戏字段不回传等易错点；注入点 = `openapi_ext.py::custom_openapi()` L445（须在 get_openapi 之后、strip 之前）（收编 `32ef4fe`） |
| M5-K9 R-4 条款合入 anchors-api §1.6 + R-5 集合落定 | kilo | `docs/api/anchors-api.md`（§1.6 新增 91 行，零代码零 schema） | ✅ main（收编 `c380f79`，交付 `68b5c9c`） | 裁 30-D/B：R-4.1~R-4.7 条款与 opencode A4 原件逐字可对；补 **R-4.1-S 状态码归属**——0 行/多歧义均复用既有 **400 `/errors/world-not-ready`**（零快照变更、零新增机器码，否决 409/503；`500 /errors/branch-ambiguous` 留待另立快照单）；施工单须写死六条钉 + 落点 `sim/tests/test_m5_anchors_branch_source.py`；A4「取 seq :274 与建档 :345 必须同改」警告抄进正文；**R-5**：戏外词表集合落定 **META_SHELL 8 词** + 判层模型订正（非 Agent 面豁免源）+ 锚点 name 维持 F-6 不接钩子 + 接线时机空函数先行；6.7 备忘状态同步 |
| M5-K10 R-4 六钉验收对表 + branch-ambiguous 登记 | kilo | `docs/api/anchors-api.md`（§5.2 对表 + §2.1 登记单，79+/7- 零代码） | ✅ main（收编 `64a5bf3`，交付 `1d01d24`） | **§5.2 六钉对表**（`[T]/[O]/[C]` 沿用 §5 体例，与 §1.6 互引）：钉 1 两分支 seq 刻意不等（child=3/parent=99，「只改一处」才在断言可见）；钉 3 歧义 fixture = 两条 active + `is_current` 全 0（0012 BACKFILL_SQL 真实结果；硬塞两个 is_current=1 会被部分唯一索引拒掉测不到 HTTP 面）+ 白盒负钉锁 `anchors.py` 内 `main` 字面量零出现；钉 4 引 A5 已有钉不重复造；**钉 5 阻塞项 = fork.py 当前行交接（由本施工单关掉）**；跨钉总闸三条（live≡快照逐字段 / gen-protocol EXIT 0 且 shared/ 零 diff / branch-ambiguous 快照+errors.py 各 0 次反向钉）+ 前端 `M5-K10-R4 #1`（命名避让历史 M5-K10=裁 19 state_delta.plan 标签）。**§2.1 登记单**（零施工）：形状 ProblemDetail 四键、触发=歧义库读取、与 400 world-not-ready 边界一句、将来必同改四处、三禁忌（不搭 R-4 顺手加 / 不只改 errors.py / 不把 0 行也改道 500）。**订正两处**：R-4.1-S 触发形态 0012 后歧义=`is_current` 全 0（≥2 个 1 不可达，400 裁定不变）；全量 1945 passed/0 failed/4 errors=仓根 world.db 陈旧债（裁 28-B 处置） |
| M5-K11 批次 C 权力机制 API 面（出站咽喉剥除闸） | kilo | `sim/api/outbound_guard.py`（新）+ `sim/api/ws.py`（+7 接线）+ `docs/api/m5-power-api.md`（新 156 行）+ `sim/tests/test_m5_power_api.py`（新 18） | ✅ main（收编 `d412d73`，交付 `e317566`） | **施工下放首战**（599+/0- 零 schema）：契约稿 D-10 三硬边界 + **HTTP 零新路由三论证**（全 13 条 `/api` 路由声明 `response_model` ⇒ 结构密封）；闸装 **`ConnectionManager._send_to` 唯一咽喉**（广播/定向/订阅者共用，新帧无法绕过）：递归剥除禁键（全深度大小写不敏感）+ structlog warning + `leak_events()` 留痕；**HTTP 侧零代码**（不为结构不可能泄漏的响应装中间件）。**18 钉五组先红后绿**：纯函数 7（含**跨域键集对拍**=生产侧禁键集与 codex 红线 B 逐字同源）/咽喉实测 3/**白盒负钉 3**（禁键字面量只许出现在闸门模块=防第二真相源；`_send_to` 必含 `strip_authority_fields`=防闸被摘）/错误码零新增 3/HTTP 密封 2；与 codex S3 8 钉分工（他帧构造层/我咽喉+错误码+HTTP 密封层）；**接口要求 P1–P5** 写死给 opencode（API 零依赖不 import 表模型/store dict 返回禁含禁键=第三道防线白名单投影与 response_model 才是前两道/kind 登记 PAYLOAD_MODELS/0013 不经 ext 注入/create_all+alembic 双路径同列）——A7 交付全部满足实测零冲突 |
| M5-S8 权力机制威胁模型（W-A1/W-A2 施工级展开） | codex | `docs/security/m5-power-threatmodel.md`（新 120 行，零代码） | ✅ main（收编 `d412d73`，交付 `e4aafed`） | W-A1（机制自建词面过滤=第二套判梯）/W-A2（直改 UtilityDecision 绕意愿管线）逐条展开攻击面+守卫复用+白盒源码级钉；**17 条施工级钉按归属拆两组**：kilo 7 条（递归扫描正向钉/剥除层源码白盒/构造隔离 X2/错误码 fail-closed/错误文案戏外/闭合集回归/扫描器共用）+ opencode 10 条（写路径单入口/非法输入零落库配正向断言/branch_id 隔离不可见不可写/fork 克隆显式/迁移 CHECK+索引/事件闭合集零 out-of-band）；**D-10 相容论证=「不可见的是状态，可测的是行为」**；§4 施工后复验单逐钉核表已备（复验单下一波派） |
| M5-P10 权力机制性能预算案（间接/直接 ≈174x） | pi | `docs/perf/m5-power-budget.md`（新 157 行，零代码） | ✅ main（收编 `d412d73`，交付 `32b141a`） | ①直接账噪声级：权力向量化更新 50 NPC **2.8µs/tick**（效用矩阵多一列；反模式=逐人 advance 175µs/dataclasses.replace 81µs/逐人 chaotic_at 521µs=P9 陷阱翻版）；②**间接账=本单核心**：权力列自付 +3.05µs → 动作分布漂移（flip 0.18→0.46、熵 2.52→1.80、request_chat 16→26）→ 翻 move 点亮冷 A* 0.53ms、翻 chat 点亮检索 0.05–0.86ms ⇒ **间接/直接 ≈174x**（P9 为 53–70x）；P=5 混合 ≈1.7ms/tick、**P=50 全 move = 26.4ms 破 16.6ms 整 tick**；③红线裁定建议：**不新建 POWER_TICK_LIMIT_MS，并入 L1_UTILITY_TICK_LIMIT_MS=6.0**（避免双算）+ 间接成本不设数字行改设**接法红线**（权力只作 utility 额外列，禁逐人 replace/chaotic_at）+ **POWER_MAX_BIAS≤0.2 使 flip≤0.25** + 冷路径计数守卫；`POWER_REGRESS_INTERVAL_TICKS=60` 复用 P9 同族；权力抖动走 chaotic 计入 RNG/熵行不叠加；④**一箭双雕**：POWER_MAX_BIAS 上限既守性能也守「被操纵感」安规——动作熵坍缩=操纵前兆，与红线 C 共用 flip/熵断言。**3 项待裁**（裁 32）：系数/阈值数值/行归属 |
| M5-A7 批次 C 权力机制数据面（0013 npc_power + PowerStore） | opencode | `0013_power_state.py`（新）+ `models.NpcPower`（新）+ `power_store.py`（新）+ `fork.py`（_BOUNDED_TABLES 加项）+ `docs/data/m5-power-data-preplan.md`（新）+ `schema.md` §21 + `sim/tests/test_m5_power_state.py`（新 45） | ✅ main（收编 `d412d73`，交付 `9ceadea`） | **施工下放数据面首战**：新表 `npc_power`（纯 create_table+复合 PK+两条 CHECK 零索引）+ `PowerStore.materialize/apply/apply_batch`（**apply 非幂等增量语义**/fail-closed 四条零写/越界夹取 `clamped=True` 如实上报/无行=未表态调用方兜底 0/分支非 active 拒写复用 `InactiveBranchError`）+ fork 克隆接线；**零事件 kind 新增**（红线 A）/零对外读口（D-10）/零协议面变更（gen-protocol 零漂移）；**「命名即哨兵」**：状态列 `power_level` 故意落 kilo 禁键集——任何意外序列化被递归扫当场抓（改名须先改禁键集）；**「拒并入旧表」**：npc_profiles 属可重放 5 张，塞无事件源状态会让 A3 分类说谎；A3 地基登记**不可重建 3→4 张**；45 钉（目标 ≥12 超额）含四钉禁面与登记（kind 集合零新增/写权力后 events 行集零变化/状态列名仍在禁键集/A3 已登记第 4 张）；**口径五条**给机制面（量纲归一 [-1,1] 三处同源常量/非幂等须去重/不隐式衰减=读不转写/无行兜底 0/非 active 拒写）；**缺口已登记**：无事件源⇒无重放物化器+历史点读档 fail-closed，归批次 E 物化单 |
| M5-S7 M5 安规预研：三面威胁盘点 | codex | `docs/security/m5-security-preplan.md`（§9 新增 58 行，零代码） | ✅ main（收编 `64a5bf3`，交付 `1361783`） | **三面威胁盘点**：①权力机制 W-A1/W-A2（D-10 权力不可见红线下的可观测面边界）；②火灾生态 W-D1/D2/D3（物质/事件面新增写入方输入信任边界）；③混沌流 W-C1/C2（rng_state 不出网关；消费点输出进叙事面的 T1/T3 暴露）——每钉一句可证伪判据+施工归属 §9.5；三硬边界交叉核对表 §9.4。**无 CRITICAL/HIGH**，7 缺口钉全为建议钉；词表零扩散、D-10 不破。坑：gen-protocol --check 本树跑不了（client/node_modules 未装）→主树收编轮补跑（已过 EXIT 0） |
| M5-P9 批次 A 混沌接线/消费点性能预算案 | pi | `docs/perf/m5-batch-a-chaos-budget.md`（新 215 行，零代码） | ✅ main（收编 `28d53b5`，交付 `8176e30`） | ①**inject 摊摊可忽略**：mix 6.6–7.1µs ×（daily_reseed 1/日 + 20–150 条/日）⇒ 0.00008–0.011µs/tick，比 M2 风场冷键（0.018ms）轻一量级，不设红线；②**真成本在抽签**：chaotic()/chaotic_at() 9.3µs（缓存 gen.random 的 31x）；寻路扰动两笔账=抽样 9.3µs vs **扰动触发冷 A* 494–647µs@64×64（53–70x）**；情绪回落 N=60 ⇒ 0.008ms/tick；③**最紧要红线是接法不是数字**——禁扰动进 PathCache 键/喂 A*（否则 P=5 即 2.5–3.2ms/tick，P=50 顶穿 16.6ms 整 tick）；抽签聚合并入 RNG/熵行（提案 CHAOS_TICK_LIMIT_MS=0.05 + RNG_TICK_LIMIT_MS=0.10 兜底 + 契约常量 CHAOS_EMOTION_REGRESS_INTERVAL_TICKS=60，P6 纪律未定标前 advisory）；④A2 量级采纳主体、修正适用范围（「连摊还都不需要」仅对事件/存储面成立）。留痕：not-bench 1945+bench 69 全绿零改动 |
| M5-S6 META_SHELL 空表 + 判层负钉 | codex | `sim/llm/prompts/banned_words.py`（+47）+ `sim/tests/test_meta_shell_lexicon.py`（新 94，双探） | ✅ main（收编 `ce8c2ba`，交付 `19168df`） | 裁 30-B③：**BANNED_WORDS_META_SHELL 空表**（词候选批注留存，填值随首个戏外消费 CR）；`scan_meta_shell` 分派 = BANNED_WORDS ∪ META_SHELL（面宽于 Agent 面，persist/meta kind 同口径）；**判层核心负钉** `test_agent_dispatch_never_reads_meta_shell`——scan() 源码白盒断言零 META_SHELL 引用，戏外表接入 Agent 面即红；空表下 scan_meta_shell ≡ scan（钉住）；坑：RUF003 全角括号（注释用「（）」不用符号）、SIM300 Yoda 条件 ruff --fix 可清 |
| M5-P8 willingness Δ 护栏改中位判据 + Xeon 被动监控台账 | pi | `sim/tests/bench/test_bench_willingness.py`（改）+ `docs/perf/m5-p8-willingness-delta-guardrail.md`（新）+ `docs/perf/m5-p8-xeon-passive-monitoring.md`（新台账） | ✅ main（收编 `c380f79`，交付 `f32373f`） | 裁 30-D：护栏结论 = **改单调性判据 Option 2（中位而非均值）**——根因 = 均值被单个大 ms 离群拖走（GC/上下文切换只落 injected 侧）；实测（2026-10-01 本机暖态 throttle_ratio=1.652 健康）：逐对增量 **均值 0.47ms（max ~9.6ms 离群，>2.0 可到 3/60）vs 中位稳定 ~0.21ms**；CPU 争用（核-1 满转）下中位仅 ~0.25ms；**窗口值没错，错的是聚合口径**；thresholds 值不动；Xeon 台账 = 命中全绿即按 P7 §4 公步建 xeon8573c 基线（2026-10-01 nightly 机型核对已补） |
| M3-C3 chunk 失效通路 + §19.4 后续件 | opencode | `sim/world/{map,pathfinding,matter}.py` + `sim/tests/test_m3_{chunk_invalidation,matter_register}.py` + `docs/data/matter-register-proposal.md` | ✅ main `29f9d6c`（收编本 merge） | `TileMap` PrivateAttr 脏集 + `Pathfinder.observe_events`/`observe_map` 精确失效（24 钉子）；`register` 返回 `MATTER_BUILD` 立账事件（amount=0、durability=integrity、x/y=-1），flush_tick 快照/flush_events 重放冷启均不丢、逐位相等（9 钉子）；零 schema、零生产调用方 |
| M5-D1 双轨存档存储面预研 | opencode | `docs/data/m5-fork-archive-preplan.md` | ✅ main `cee593c` | 读档=分叉的存储形态全案：branch_id 全局化取舍 / 克隆 vs 重放 vs 谱系回退读 / 玩家档游标 schema 草案 / fold 跨分支 C1-C6 / T2 分叉重放 R1-R3 / 与 pi M5-P1 九点交叉对账；三条硬发现（`npc_profiles` 主键单列 / 语料三表无事件源 / **向量召回零分支隔离**）+ 12 待裁点 → **裁 21-B 十二点全裁**（`docs/arch/m5-rulings.md` §B） |
| M5-D2 施工第一刀（零迁移先行 + F3） | opencode | `sim/core/persistence/vector.py` + `sim/tests/test_t1_m3_vec_governance.py`（+6）+ `sim/tests/test_t1_m5_history_preserved.py`（新 6）+ `docs/data/{schema,m5-fork-archive-preplan}.md` 回写 | ✅ main | ①T1 断言 5 口径改 `(branch_id, seq)` 对集合（C6 从恒真变可证伪，零 schema；**二阶守卫**：裸 seq 口径对同一破坏动作恒绿，实测把 oracle 换回裸 seq 红 4 钉）；②F3：`vec_candidate_ids` 召回句加 `m.branch_id = ?`（同句 push-down，禁 Python 侧后过滤），`branch_id` 必填+keyword-only+无默认（fail-closed），附 `RECALL_OVERFETCH_FACTOR=4` 抗候选饥饿（`k` 是过滤前的取回上限；系数改 1 即红）；未知分支空候选不回落；既有 4 条治理钉子零回归；pi 可跑 `RETRIEVAL_*` before/after |
| M5-D3-b fork 事务 + 克隆（R-1/R-2） | opencode | `sim/core/persistence/fork.py`（新）+ `vector.py::clone_branch_vectors` + `store.py` 裁 5 分支闸门 + `sim/tests/test_m5_fork_clone.py`（新 22）+ `docs/data/{schema,event-sourcing,m5-fork-archive-preplan}.md` 回写 | ✅ main `fdebff5` | 一次事务：P1 `preflush` 必填钩子 → 建子分支 → 6 张有界表换 `branch_id` 克隆 → 2 张语料表**按分叉点截断**克隆（自增 id 显式分配 + `entry_id` uuid5 确定性重映射 + 三个治理指针重写）→ 证据分支改写（0008-d 兑现）→ 父分支封存；提交后 vec 行**字节**拷贝（零 LLM，V4）；**R-1** 记忆 content/向量字节不变、**R-2** `superseded_by` 零跨分支悬空（未来替换者 → 置 NULL）；裁 5 `append` 拒写非 active 分支（不存在则按需开线，闸门在 seq 分配前）。**⚠️ 遗留缺口：分叉点只支持父分支头部**，历史点（回退旧存档）fail-closed——语料治理列与 `relationships` 无事件源不可重建（预研稿 §3.7 三条候选修法待裁） |
| M5-D3-c R2 三断言 + RNG 承接（批次 B 收官） | opencode | `sim/core/rng_state.py`（新）+ `sim/core/persistence/fork_replay.py`（新）+ `fork.py`（`rng_state` 透传）+ `sim/tests/test_m5_fork_replay.py`（新 19）+ `docs/data/{schema,m5-fork-archive-preplan}.md` 回写 | ✅ main | A 接缝一致 / B 段内一致 / C 前缀无关（**跨分支泄漏照妖镜**，实测注入一处单分支回归即红）+ 断言 D RNG 承接（`capture/restore_rng_state` ≈198 B/流，版本+指纹 fail-closed）；**口径修正**：R2 = 父分支前缀折叠 ∘ 子分支自身事件折叠（子分支事件流按设计是增量的，单独重放必然少一半继承行）；可比字段集落 `fork_replay.COMPARABLE_*` + `EXCLUDED_FIELDS`（排除项必须有名字）。**建议裁 26 的 (b) / 否 (a)**：实测「只承接 registry（seed 语义）」后续抽签**必然跳变** → seed 不含进度；`rng_state` 落库待裁（`rng_state_persisted` 恒 False，透明透传不预设）|
| M5-A-DATA 0009 branches.rng_state + fork 事务原子落库 | opencode | `0009_branches_rng_state.py`（新）+ `models.py`（Branch.rng_state）+ `fork.py`（事务内写入 + `rng_state_persisted` 翻转）+ `sim/tests/test_m5_branches_rng_state.py`（新 8）+ `test_m5_fork_replay.py`（D 钉翻转）+ `docs/data/{schema,migration,m5-fork-archive-preplan}.md` 回写 | ✅ main | 裁 27-B **b2**：状态包（registry + 每流 PCG64 进度，≈198 B/流）落 `branches.rng_state`，**与克隆同事务** ⇒ 分支自带状态、**可连续分叉**（child 状态即 grandchild 输入）；未提供时该列留 NULL + **warning**（漏传 = 接缝跳变风险）；`ForkResult.rng_state_persisted` 如实反映是否真落库。8 钉含**端到端接缝抽签逐位一致**与 0008↔0009 全 revision id 往返 + autogenerate 零漂移 |
| M5-D3-a 0008 分叉身份四件 | opencode | `0008_m5_fork_identity.py` + `models.py`/`store.py`/`npc_store.py`/`event_validation.py` + `sim/tests/test_m5_fork_identity_schema.py`（新 16）+ `docs/data/{schema,migration,m5-fork-archive-preplan}.md` 回写 | ✅ main | 裁 1 `npc_profiles` PK → `(branch_id, id)`（F1 硬前置；生产单键 1 处 + 测试 3 处改双键，**顺带封一处跨分支写**：`_project_lod_change` 原按 id 取行不看分支）／裁 3 `events.parent_branch_id`／裁 4 `knowledge.evidence_branch_id`（封 C4 悬空）／裁 9 `player_anchors.protected`；两条**单向**成对 CHECK（`(NULL, seq)` = 本分支引用，既有行合法）+ 2 索引；**作废** 0008-b/c（裁 10 采 (i) / 裁 2 不加 global_seq）；门禁：scratch DB + **全 revision id** 往返 0007↔0008 + autogenerate 仅 `pass`（零漂移）、1661 passed、ruff/pyright 0 |
| M5-A4 0011 anchor_packages + R-4 真源契约 + 快照 seq 判据 | opencode | `0011_anchor_packages.py`（新）+ `models.py::AnchorPackage`（新）+ `store.py`（`latest_snapshot(max_seq=…)`）+ `sim/tests/{test_m5_anchor_packages,test_m5_snapshot_seq_window}.py`（新 17）+ `docs/data/m5-r4-active-branch-contract.md`（新） | ✅ main（收编 `c380f79`） | **0011**：纯 `create_table` 无回填（老档无包且 anchor 时刻 rng 不可得 ⇒ 不可物化）；`rng_state` 可空（NULL ⇒ 禁 seed 派生兜底）、快照引用**两列同有同无**（CHECK）、corpus_blob 收 3 张不可重建表行值、1:1 不建 FK（删除语义归 kilo CRUD 面）；**降级丢包有意**（包可重算，玩家档不可丢）。**快照 seq 判据**：`latest_snapshot` 加可选 `max_seq` 上界——原只判 `tick <=`，同 tick 多事件时会选到 seq 已越界的快照 ⇒ 重放窗口倒挂/漏事件；不给 = 旧行为（既有调用方零影响）。**R-4 契约**：真源 = `branches` 表（禁 `'main'` 字面量 fallback、fail-closed 不猜）；不变量「至多一个当前」，而裁 5 的「不存在即开线」正是破坏口 ⇒ 必须收紧为「仅当无当前行才可开线」；载体建议 `branches.is_current` + **部分唯一索引**（DB 层保证），**明确否决 recency 选法**（读档子线故意与父线并存且可能更晚，recency 会静默换线）；head-fork 当前行交给子分支，anchor-fork 保持父分支当前（子为读档线，`is_current=0`） |
| M5-A3 anchor 世界态物化数据面设计（批次 E 前置） | opencode | `docs/data/m5-anchor-materialization-preplan.md`（新，纯文档零代码） | ✅ main（收编 `c380f79`） | **地基分类**：可重放的 5 张（有 fold 器，快照+事件窗口可重建）vs **不可重建的 3 张**（`npc_memories`/`knowledge` 治理列 + `relationships` 累计值原地演进）——物化包必须同时兜住两类，否则会把「当前值」当「回退点历史值」。**四问**：①包 = 快照指针 + 3 张不可重建表行值 + **anchor 时刻 `rng_state`** + `agent_override` + `state_hash`，**存档时（`create_item` 同事务）一次物化**（快照会被 GC ⇒ 懒物化会让老档永久不可读档）；次序铁律 = 展开 → 套 override → 灌语料 → `restore_rng_state`；快照缺失 ⇒ 从 seq 0 全前缀重放，判据三条（事件连续/语料行集一致/rng 可得），否则 `AnchorMaterializationError`。②**既有 0008/0009/0010 零改动**即可定义包，落库只需 1 张新表 `anchor_packages`（1 条 create_table，**号待派**）；老档无包且 rng 不可得 ⇒ 不可物化，只给只读诊断面（`no_package`/`rng_unavailable`/…），**不用 seed 派生兜底、不批量回填**。③解锁五条：包 ready / 3 张进包 / **`kind` 参数化（回退旧档不封存父分支）** / 语料克隆源切包 / 钉子集齐；改动面 7 处，零事件白名单改动。④成本：单次物化 **≈0.5–25ms**（最坏项 = ≤1000 tick 窗口重放 14.8ms @0.74µs/事件）、读档 ≈20–40ms（与现行 head-fork 同阶）；存储上**快照是可弃缓存**（丢了退化为 1.28s 全前缀重放，设上限）、语料+rng 是不可重建资产须内联 ⇒ 每 anchor O(语料行数)，需 **10% 配额 + LRU** |
| M5-A2 0010 protected 回填（GAP-B）+ 混沌流数据面预研 | opencode | `0010_protected_backfill.py`（新）+ `sim/tests/test_m5_anchor_protected_backfill.py`（新 10）+ `docs/data/m5-chaos-stream-data-preplan.md`（新） | ✅ main | 0010 **只回填不切列**：末梢档 `protected=1`，判据 `ORDER BY updated_at DESC, id DESC LIMIT 1` 与 K3 `/current` 同口径（同刻按 id 降序兜底）；**空表零行更新是合法态**；**downgrade 有意不撤销回填**（撤销会让列与在役派生式互相矛盾）；10 钉含恰一行/兜底/幂等×3/空表/单行/不误伤他列/真跑迁移/空库升级/0009↔0010 往返/**语句同源**；autogenerate 零漂移（`upgrade()` 仅 `pass`）。预研稿四问落点：**抽样不落事件**（纯函数，靠 0009 `rng_state` 承接）、注入走既有 `entropy.inject`、**不需新 kind**；量级 **20–150 条/游戏日**（<0.01% 事件密度，连摊还都不需要，零新增预算行）；分叉归属假设**成立**（事件不克隆 ⇒ `entropy_log`/`event_seq` 皆分支内、无悬空；连续性靠 0009 而非事件；R2 从父前缀事件恢复材料）；**修正 2**：历史点分叉需把 `rng_state` 纳入 anchor 世界态包，否则回退会重掷混沌；F2 交叉：**不新增缺口**，混沌是「状态+事件+查询面」三件齐备的正面样板 |
| M5-A5 0012 branches.is_current + 开线闸收紧（R-4 数据面） | opencode | `0012_branches_current.py`（新）+ `models.py`（`Branch.is_current` + `ux_branches_current` 部分唯一索引）+ `store.py`（`_assert_branch_writable` 收紧 / `current_branch_id` 真源读入口 / `CurrentBranchConflictError` + `NoCurrentBranchError`）+ `sim/tests/test_m5_branch_current.py`（新 36）+ `docs/data/{schema.md, m5-r4-active-branch-contract.md}` 回写 | ✅ main（收编 `5b0bcbc`） | **0012**：列 `BOOLEAN NOT NULL DEFAULT 0` + **部分唯一索引** `ON branches(is_current) WHERE is_current = 1`（「至多一个当前」落到 DB 层，第二个 1 ⇒ IntegrityError）；回填 = **唯一 active 置 1，≥2 active 全置 0**（**否决 recency**：读档子线故意与父线并存且可能更晚，静默换线正是 R-4 的病）、0 active 零行合法、幂等、downgrade 不撤销（同 0010）。**开线闸收紧**（R-4.2.1）：「不存在即开线」⇒ **仅当无当前行才可开线**，已有当前行时向别分支 append ⇒ `CurrentBranchConflictError`（`InactiveBranchError` 子类，既有 handler 零改动），不留分支行、不吃 seq；**收紧只针对开线**，active 但非当前的读档子线照写不误（R-4.4）。**真源读入口** `current_branch_id()`：查不到 ⇒ `NoCurrentBranchError`，**禁回退 `'main'`**。36 钉含部分索引 DDL 带 `WHERE` 子句 / 歧义库不选 recency（二阶对照组）/ 部分唯一索引 IntegrityError / 同事务交接载体可用 / 闸门正负例与无半写 / 两种 fork 数据面现状 + 交接形态。**连带修 4 个「两分支并存」钉**（按需开线收紧后必须先声明并存分支 = 读档子线形态）+ **0011 两个往返钉钉 head 改钉 revision id**（A4 自修纪律，head 前进即假红）。⚠️ **未落**：`fork.py` 当前行交接（head-fork 交接 = 施工单，同事务先清父再置子） |
| M5-A6 R-4 施工数据面钉 + fork 交接口径 | opencode | `sim/tests/test_m5_anchors_branch_source.py`（新，11 钉：5 绿 + 6 skip-locked）+ `docs/data/m5-fork-current-handover.md`（新）+ `docs/data/schema.md` §20 补步 8b | ✅ main（收编 `9d20d75`） | **零生产码**（不碰 sim/api/、sim/core/persistence/、迁移链）。**skip-locked 口径**：锁信号 = `anchors.py` 代码里出现真源载体（调 `current_branch_id` **或**直接查 `is_current`，两种实现都认）→ 施工合入后自动解锁；**反假绿灯**：锁信号与红线同向钉（删硬编码却不接真源 ⇒ 立刻红）。**判别力**：涉 POST 的钉把两条线头部 seq 设成不同值（child=7 / main=3）⇒ **只改一处必被抓**（只改取 seq ⇒ branch 仍 main；只改建档 ⇒ seq 来自 main 头部），这才是 A4「同改警告」的可证伪版；已实测开锁后 **5 红 / 6 绿**（真红）。口径稿实测归纳：**单语句换手在 SQLite 上必然撞唯一索引**（3/3，同一语句内逐行校验）⇒ 只能「两步 + 同事务 + 先清父」；另给出交接只在「父就是当前行」时发生的分支判据（从读档线分叉不抢当前行）与施工清单。 |
| M5-CRUD anchors 写路径 + ProblemDetail + F-6 + driver 生产挂载 | Claude（主树） | `sim/api/anchors.py`（POST/PATCH/DELETE + 切列 + F-6）+ `sim/api/errors.py`（新）+ `sim/api/main.py`（handler 安装 + 生产读档 hook）+ `sim/api/ws.py`（`set_anchor_load_hook` + `fork_notice` 出站纵深）+ `sim/api/openapi_ext.py`（`_attach_problem_responses`）+ `sim/tests/test_m5_anchors_crud.py`（新 21）+ `sim/tests/test_m5_problem_detail.py`（新 3）+ `test_m5_notice_outbound.py`（RED 转正 +2）+ `docs/api/ws-protocol.md`（GAP-D 登记）| ✅ main | 裁 28-G 六件全落：**S-1** ProblemDetail 四键全局换形（HTTPException/未匹配 404/422；机器码 `type \| detail` 分段；`_TYPE_TITLE` 表）／**S-2+S-5+S-8** POST 同事务写 protected=true+清其余（A2 threading.Lock+A3）、`updated_at` 只写一次、游标=世界 tick+seq（D-16 main）、K7 模式注册 WS 表／**S-4 切列** list/get/current 读列（C1 派生式退休；opencode 跨域缝随切列闭合）、/current 退化态回退 max(updated_at) 不 404（D-14）／**S-6+S-7 调用点** DELETE 409 读列+硬删+`unregister_anchor_id`+不补位／**F-6 注册侧 fail-closed**（name 过现行 scan，422 `anchor-name-rejected`，零词表扩散）+出站纵深（fork_notice 终扫退化兜底行；RED 钉按钉内指示转正）／**driver 生产挂载**（`set_anchor_load_hook` 注册 `orchestrate_load_anchor` 闭包：preflush=on_flush、register_child 日志、异常降级 load_failed）／**GAP-D** timescale 文档行。门禁：not-bench 1827 passed/119 skipped、ruff/pyright 0、gen-protocol --check 过（快照零漂移）、bench 在途 |
| M5-C9 T4 探针验收 runbook（本域 · 裁 31-T4 执行单） | cline | `docs/config/m5-c9-t4-probe-runbook.md`（新，259 行纯文档） | ✅ main（收编 `d412d73`） | **交付 runbook，未真跑**（key 未到位 + 未获执行许可，§6 流程已备）。①**前置**：三把锁（key 存在／`T4_RUN=1`／≤60 预算闸，**只能收紧不能放宽**——`min()` 夹断）、锁版本 `Deepseek-v4-flash` @ `chatapi.weixin.qq.com/openai/v1`、**直连不走 7897 代理**（该代理仅 github.com 域）、key 纪律＝运行时环境变量**永不落盘**（示例全用 `<...>` 占位，**零真实 key 格式**）。②**真跑**：`uv run pytest sim/tests/test_t4_probes.py -m t4 -v --junitxml=t4-results/t4.xml`，**53 用例为本轮 `--collect-only` 实测基线**（248 收集／195 deselected）。③**留痕**：`t4.xml` + `t4-report.json`（均已 gitignore，**响应正文永不入库**）；结论三处＝回执／README 台账／memory 快照。④**两道判据（顺序不可颠倒）**：形态道先排三种**假绿**（exit 5 收集 0 用例／全 skip＝锁未开／无 report.json），内容道再看 `hard_red[]`（**唯一真红＝出戏词面命中，不放宽断言**）与 `inconclusive[]`（**人工复核，不得当绿**）。⑤**三类失败分支**：4xx 鉴权（**当前最可能＝key 待轮换**）／timeout·connection·rate_limit·5xx 抖动（**设计上不红**；429/5xx 等几分钟重跑，connection 先查是否误设代理）／硬判定泄漏。⑥**连带**：`README` §2 登记 ＋ §5 台账行 ＋ **M4-C2 行尾追加裁 31-T4 现状标注**（历史交付事实**不改**，只加「当时口径」引导，消解旧行 `claude-sonnet-5`／secret 的误导）。**门禁**：零 yml 零 `sim/` 改动、**未跑 pytest 全量**（零生产码；仅跑零成本 `--collect-only` 取实测数） |
| M5-C7 workflow 台账巡检 + T4 接线两口径预研（本域） | cline | `docs/config/m5-c7-workflow-audit.md`（新，纯文档） | ✅ main（收编 `23a241a`） | **巡检**：四 workflow（ci/nightly-bench/golden-nightly/t4-nightly）触发器 / cron（UTC+北京，错峰无冲突）/ marker 与路径过滤纪律 / secrets 活跃行 / TODO 命中全量实测——**全仓 workflow 零 `TODO`、活跃行 `secrets.` 0 次**；**纠偏 codex 两条过期提醒**（env 已是 `Deepseek-v4-flash` 非 `claude-sonnet-5`；探针段是**显式裁定的长期注释态**非 TODO，两条均已在 `d1940e4`/`c21c781` 闭合）⇒ **真实冲突在文档层**：`m4-plan.md` §4「T4 全绿＝nightly 连续通过」vs 改约后「本地一轮＝等效验收」**两个真相源**（架构域只报不改）。**T4 两口径**：甲＝本地真模型探针一轮（**零 yml 改动 / 零持续成本 / 密钥面最小 / 回归保护弱**，与用户 09-27 改约一致，本单默认推荐）／乙＝GitHub 自动接线（三处必改：放开 schedule + 取消探针段注释 + 🔴 **注入 secret 必须同时注 `T4_RUN=1`，漏注即全 skip 的假绿灯**；每夜烧钱 + 密钥面扩大 + 抖动噪声）。**门禁**：零 workflow 零 sim 改动（`git diff` 复核 yml 零变更）、未跑 pytest（零生产码） |

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
