# memory.md — 主树记忆（Claude）

> **历史全文已归档**：`.orca/archive/memory-2026-10-21-full.md`（492KB，含 M0–M6 各轮快照、
> 各 agent 树历史、claude/codex/pi/kilo 分节）。**该目录被 `.gitignore:68`（`.*/`）忽略，
> 只在本地存在**；换机器/新克隆时没有它，需要历史就查 git history（`git log -p -- .orca/memory.md`）。
> 本文件只保留**当前有效**的部分。

<!-- ===== 新对话快速恢复卡（2026-10-21 P 单收口）===== -->

## 0. 本会话状态

- **HEAD**：`fe2e709`（merge codex：DA-05P + DA-05 建筑表现）
- **已收编**：DA-03 `d5c2931`／DA-04 `ecc9a14`／DA-05 `4518515`（merge `fe2e709`）
- **在飞**：**DA-06 / DA-07 / DA-08 三组同波派发**（2026-10-22，基准 `f7add60`）；06/08 可直接做，07 需先回执失能事件策略待核准
- **DA-05 遗留**：Phaser 真实渲染（遮挡/层级）仍未经人眼验收，只有 mock Graphics 单测
- **未决**：是否推送双远程（按纪律不推，收编前以现测为准）
- **协议**：1.11（真相源 `sim/api/ws.py::_PROTOCOL_VERSION`，前端 `client/src/net/ws.ts` 同源）
- **工作树：两棵**（2026-10-21 用户重申，长期有效）
  - 主树 `E:/zxdevelop/project7` → 分支 `main`（Claude）
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex` → 分支 `codex`（HEAD 随其提交推进，收编前以实际 `git log` 为准）
- **远程**：本地领先 `gitee/main`，按纪律不推

## 1. 里程碑

**M0–M6 全部收官**（M6 于 2026-10-05，G1–G4 全 ✅）；**M7 渲染面**已落（地图/时钟/视角/昼夜）。
代码侧整体完成，剩余是收口型缺口。

## 2. 门禁（2026-10-22 DA-05 收编后实测）

| 项 | 结果 |
|---|---|
| sim 全量 pytest（`-m "not bench"`） | **2871 passed** / 121 skipped / 72 deselected，**0 failed**（317s） |
| ruff check / ruff format | clean / 353 文件已格式化 |
| pyright sim/ | 0 errors, 0 warnings |
| client tsc --noEmit | 0 错误 |
| client vitest | 149 passed / 27 files |
| check_implementation_status | 未发现新缺口（未在本轮重跑） |

> **全量已不再需要 `--deselect`**：此前排除的 2 条地图用例是 codex 树缺
> `sim/content/assets/`（被 gitignore）所致，补齐后两树均可跑全量。
> 旧读数 2982 收集 / 138 vitest 已过时；上表为合并后现测。

## 3. 当前剩余缺口（codex 审计 8 组 + 主树 P0-3，已修 5 组，剩 3）

来源 `docs/security/gameplay-integrity-audit-2026-10-21.md`（codex `974611e`）：

| # | 缺口 | 状态 |
|---|---|---|
| P0-1 | 重启二次创世污染日志 | ✅ `846a052` |
| P0-2 | 历史读档 head-only / 世界态未恢复 | ✅ `de3a8ae` |
| P0-3 | **火格 `fire_id` 双语义**（主树探针新发现，不在 codex 8 组内）：`sim/world/fire.py:136` 蔓延格继承 `parent.fire_id`，`sim/npc/fire_runtime.py:73-78` 却每格自增签发新 `fire-{seq}` → 同一 ID 重复熄灭 → `FireWriteError` 整批拒写；`sim/api/ws.py:1401` 的 `await on_flush(events)` 无 try/except ⇒ **世界驱动直接死** | ✅ `d5c2931` |
| DA-03 | 余额/火场账本清零未重建 | ✅ `d5c2931`（读档）+ `afdfeb9`（冷启动） |
| DA-04 | 人物/中文货名目标不兼容 | ✅ `ecc9a14`（merge `f7720d7`） |
| DA-05 | 建筑表现跨分支残留 | ✅ `4518515`（merge `fe2e709`）：含前置 DA-05P |
| DA-06 | 坍塌还原未应用实时碰撞 | ⬜ 未修 |
| DA-07 | 主角走 NPC 死亡删除 | ⬜ 未修 |
| DA-08 | 重启后主角双控制源 | ⬜ 未修 |

> **不得称「全部玩法已修」**——剩 **DA-06/07/08 三组**未修。
>
> **DA-05 已收编（`fe2e709` = merge `4518515`），含前置单 DA-05P。**
> 前置缺陷：历史读档 fork 时 `_clone_bounded` **无条件**克隆父分支全表，
> `structures` 未像 `fires`/`relationships` 那样按包折叠 → 子分支**零 structure 事件却有结构行**。
> 修法：`fork.py` 新增 `_clone_structures_at_cursor`，沿 fork 链逐段按各层游标折叠
> （与 P-1 `read_branch_history` 同范式），复用 `fold_structure_snapshot`；head 路径不变。
> 表现层：`restore_structures` 相位映射（active→built，collapsing/rubble 原样，
> planned/building 不进完工层）、`remove_structure`、`on_flush` 补 collapsed/removed；
> 客户端 `full_snapshot` 全量替换 + `WorldScene` 按内容签名重绘。
>
> **主树判断纠错记录**：我曾据一次 `save()` 的探针误判为「测试夹具库路径错配，
> 别动产品代码」，并发回执让 codex 改夹具——**该判断错误**。真因是
> `locate_anchor`（`fork_orchestration.py:110`）只认 `protected = 0`，
> 单档情形下锚点不可读，探针因此走了失败分支。codex 的判断正确，我已撤回。
> 另：`check_implementation_status` 是静态结构检查，不等于玩法验收。
> **已关闭**：O 单（`9447d1b`，心声反馈 + 断线不谎报，客户端 143 passed）。
>
> **DA-05 派单注意**：不是纯服务端问题，必须允许改 `client/src`——① `ws.ts:170`
> `full_snapshot` 走 `applyStructures()` 是 upsert 不清旧；② `on_flush` 只投影
> `structure.completed`，collapsed/removed 从不入账；③ 启动路径 `_STRUCTURES`
> 从未填充（重启后建筑凭空消失）；④ `WorldScene` 只按 size 判重绘。

### P0-3 实测证据（2026-10-21 主树探针，seed=42）— 已修 `d5c2931`

```
IGNITED:     fire-1(10,10) fire-2(11,10) fire-3(9,10) … fire-21(12,9)
EXTINGUISH:  fire-1@(5,10) fire-1@(4,10) fire-1@(4,10) …   ← 同一 fire_id 反复熄灭
flush_tick → FireWriteError: fire_id='fire-1' 已于 tick=… 熄灭，重复熄灭
```

- 触发时间：该种子第一场火在 **tick 183600**（约 2.1 游戏日），60 天内 22 场 ⇒ 实况两天内必崩。
- 漏网原因：`test_m4d5_fire_live.py::test_spread_emits_ignite_events` 只断言「有 ignited 事件」，
  **从未**断言事件 `fire_id` 与内存格一致，也从未跑过落库。
- 修法：codex 采用**每格一个生命周期 ID**（`fire.seq` 每格自增，蔓延格换新 ID 并替换内存格），
  与「一行 fire = 一个火格」的库表设计一致；事件与内存格共用同一 ID。

### 冷启动账本缺口（主树 `afdfeb9` 独立发现，codex 未报）

DA-03 只接 `_drain_loads`（读档），两本账构造点在 `lifespan`，`build_loop` 只恢复 `WorldState`：

```
重启后 BALANCE={}  （库里 DB_COIN_GRANTS=1，余额 0）
重启后 fire_seq=0  → 新火又签 fire-1 → FireWriteError: fire_id='fire-1' 已存在
```

⇒ `ws.py` 驱动循环无 try/except，**世界直接停摆**。修法：`lifespan` 构造两账后立即
`restore_from_events(NpcStore(store, branch_id=current_branch).read_branch_history())`；
`current_branch is None`（空库创世）时跳过。红钉
`test_cold_start_rebuilds_coin_balance_and_active_fires`（两次真实 lifespan）。

## 4. 本轮已修（P 单四项，读档族清零）

| 项 | 修复 | 提交 |
|---|---|---|
| P-1 `tile_map` 读档不重建 | `rebuild_tile_map` + `read_branch_history` 沿 fork 链取祖先前缀；启动+读档两处 | `4a5dfa3` |
| P-2 `build_runtime` 读档不清零 | `reset()` + `restore_from_events()`，重放 started/checkpoint | `076ed21` |
| P-4 `fire_runtime` 读档不清零 | `reset()`（`cells=()`、`fire_seq=0`）；**更正 main.py 原注释**「火场由 fork 层承担」——fork 层根本不引用 fire | `076ed21` |
| P-6 `derive_tile_events` 零调用 | `on_flush` 里在 `maintenance.observe` **之前**补发逐格 `tile_changed` 还原 | `076ed21` |
| P0-3 火格 ID 双语义 | 每格一个生命周期 ID，蔓延格换新 ID 并替换内存格；事件与内存格同 ID | `d5c2931` |
| DA-03 余额/火场读档重建 | `CoinLedger.restore_from_events` + `FireRuntime.restore_from_events`；`FireStore` 同源 fold 计全部历史 ID 作 `fire_seq` 上界 | `d5c2931` |
| DA-03 冷启动账本 | `lifespan` 构造两账后按当前分支谱系恢复；空库创世跳过 | `afdfeb9` |
| DA-04 目标规范化 | 新增 `sim/agent/targets.py` 纯函数层：`resolve_actor_target`（唯一活体名、排除自身、曼哈顿 ≤12）/ `resolve_good_target`（中文名→ID，内部 ID 直通）/ `nearby_actor_names`（最近 12 名，只出戏内名）；在 `driver.py` 的 `parse_intent` 之后、`gate.validate` 之前 `model_copy` 重写 `target_id`；未解析原文仍原样送 gate（不放宽）。`economy.name_index()` 只索引唯一货名。`gate` 新增 `unknown_good` 拒绝码（规划期+执行期），未知货名不再静默 return | `ecc9a14` |
| DA-05P 历史 fork 结构真源 | `fork.py` 新增 `_clone_structures_at_cursor`：沿 fork 链逐段（各层 `seq <= 该层游标`）折叠 `structure.*` 事件再写子线；`kind="anchor"` 且 table=`structures` 时走新路径，head 克隆保持 `_clone_bounded` 不变。复用 `fold_structure_snapshot`/`_STRUCTURE_KINDS` | `4518515` |
| DA-05 建筑表现账本 | `ws.py` 加 `remove_structure`/`restore_structures`（相位映射表）；`main.py` 读档 reset 后从 `maintenance.structures` 同一快照重建、启动按当前分支填充、`on_flush` 补 collapsed→rubble / removed→删账；`_structures_delta_rows` 发 `op:remove` | `4518515` |
| DA-05 客户端镜像 | `ws.ts` `full_snapshot` 先 `structures.clear()` 再应用（空/省略也清）；`WorldScene.syncStructures` 判据由数量改为 `JSON.stringify` 内容签名（含 token/相位/格位） | `4518515` |

## 5. 踩坑记录（血泪，逐条有效）

**代码语义类**
- `WorldEvent.payload` 是 **dict**，不是 pydantic 对象 → 测试断言用 `["x"]`
- `StructureSnapshot` 字段是 `phase: StructurePhase`，**无** `state` / `integrity`
- `collision=True` 表示**可走**（变量名反直觉，别当成墙）
- `_default_map()` 的 (3,4) 恰好是障碍——契约测试不可写死坐标
- `maintenance.observe` 会 **pop REMOVED**，派生 tile 事件必须抢在它前面
- 还原值要逐格取 `_ground_tile_id`，不能共用首格（水面格要仍是水）
- **火的 ID 语义两侧必须对齐**：`FireCell.fire_id`（世界侧）与 `fire.ignited` 事件
  （运行侧）是同一命名空间；`fold_fire` 对重复 ignite/extinguish **fail-closed**，
  一侧漂移就是整批 flush 被拒，而不是静默降级
- **`on_flush` 无 try/except**：`sim/api/ws.py:1401` 的 `await on_flush(events)` 任何异常
  都会直接打死世界驱动任务（没有降级、没有重试、没有前端告知）。写落库相关代码要按
  「异常即停服」的标准衡量风险

**核查方法类**
- **核库后再报**：小写 grep 会漏驼峰符号 → 查符号用 codegraph 或大小写不敏感
- **门禁数字同场测**：不引用旧读数，不用文档自述
- **探针现测**：不引用他人读数
- **skip 分型**：逐条读原始 SKIPPED 行
- **汇报前先核库**：git log + Test-Path，此前有过虚构汇报的教训

**协作类**
- **两棵树是常态**：主树 `main` + codex 树 `codex`，不要再按「唯一树」记（2026-10-21 用户重申）
- agent 间**只走 talking.txt**：**不直接向 codex 发消息**、不查终端、不用 orca-cli 通知；
  派单/回执一律写对方工作树的 `.orca/talking.txt`（2026-10-21 用户明示）
- 派单要**极简**：codex 只看「当前任务」一节，历史压成表格一行
- 不推远程；只在本地分支提交，收编由主树做

## 6. 恢复序（新对话）

1. **本卡**（0–6 节）
2. `.orca/talking.txt`（当前波 + 阻塞）
3. `.orca/status.md`（质量门快照）
4. `git log --oneline -15` + `git status`
5. codex 树 `.orca/talking.txt` 的「回执区」

## 7. 项目长期分工

- **main**（Claude）：架构 / 质量 / 逻辑 / 测试 / 前端 / 体验 / 发布 / 运维，兼收编
- **codex**（第二棵树）：安全 / 合规 / 风险域；承接主树派单（用户授权可越域）
- 两树间**不直接通信**，只经各自 `.orca/talking.txt` 留痕

## 8. 技术栈速查

- 后端：Python 3.12 + FastAPI + SQLite，`uv` 管理，事件溯源唯一写路径（28 类事件，`extra=forbid`）
- 前端：React 19 + Phaser 3 + Vite + Zustand + Vitest
- 测试：pytest（2982 条收集）+ vitest（138 条）
- 文档：`DESIGN.md`（v2.1 冻结）+ `docs/`（128 篇）

---

<!-- ============ 以下为归档索引，正文见 .orca/archive/memory-2026-10-21-full.md ============ -->

## 归档内容索引

本地归档（`.*/` 忽略，仅本机可读）：`.orca/archive/memory-2026-10-21-full.md`

| 内容 | 归档文件内位置 |
|---|---|
| M0–M6 各轮快照 | §56 起 |
| claude 主树历史（①） | 866–1148 行 |
| cline 树（②）— 树已不存在 | 1149–1235 行 |
| opencode 树（③）— 树已不存在 | 1236–1406 行 |
| codex 树（④） | 1407–1459 行 |
| pi 树（⑤）— 树已不存在 | 1460–1778 行 |
| kilo 树（⑥）— 树已不存在 | 1779–2811 行 |
| opencode 专属恢复卡 | 85–244 行 |
| 旧恢复卡（M6 收官态） | 245–860 行 |

**无本地归档时**：`git log -p -- .orca/memory.md` 可取回任一历史版本。

---

# ④ codex 树快照（权威来源：codex 树 `.orca/memory.md`；收编时原样并入）

【2026-10-22 DA-08｜完成待收编；06已提交，07策略待核准】基准ea42b13（06已提交后才改08）。assemble_runtime新增不可变external_controller_ids装配规则，先过滤外控实体再建utility/hidden；main显式声明ChenmoDriver拥有CHENMO_ID，首启与重启均不进效用名册。默认通用装配兼容，不靠时序，不新增隐式LLM降级。真实同一隔离库两次lifespan红1F（重启名册多chenmo），改后相关47P，主角无utility动作、普通NPC有动作、driver两轮存在，人数/矩阵一致。原始not-bench全量2875P/121S/72D/0F（325.52s，无额外排除）；ruff/format355/pyright0，client tsc/149P全绿；日志.orca/da08-{red,focused,python-full,pyright,client}.log。08独立提交见talking/git log，未推送。下一步仅DA07：talking明确“主树核准后再实现”，已申请agent.incapacitated/recovered新kind及tick/main/ws/driver/combat_exec必要接线扩界，尚未收到核准，不写07实现或红钉。现有HP账本仅全体reset，恢复主角需单人恢复，不能清村民血量；settle_attack签名/技能距离部位系统不动。主角应保留entities，任务红钉“不在”与要求矛盾已回执更正；失能期间停行动但念头入队，恢复与时间推进均事件化。恢复新对话先看talking新增核准，不能将06/08重复实现，也不能自行越界07。

【DA-06 完成待收编】ea42b13；on_flush落库成功后只对结构终态批次增量消费tile_changed，同步app/build_runtime/pathfinder并清缓存，保留P6派生。真实红2F/1P→相关37P，完整2874P/121S/72D/0F（325.32s），client149P与静态检查绿；.orca/da06-*.log及审计报告。全波从main@fbfdff6同步（包含指定f7add60及DA05收编fe2e709），此后未再merge main，未改主树。

【2026-10-22 DA-05+DA-05P｜完成，待主树收编】基准969e616；主树复验真源污染后明确允许改fork.py，仅structures克隆路径扩界。历史anchor在同一分叉事务内，按包branch/seq及各祖先分叉点取有界结构事件，祖先在先、本层seq有序，复用fold_structure_snapshot写子线；不能复制父head，也不能只用snapshot window或把不同分支seq混排。head路径保留，不改BLOB/schema/WorldCheckpoint或materialize_structures_replay接口。启动按当前分支快照重建WS账本；读档fire.reset后清账，再复用maintenance同一快照；completed→built、collapsed→rubble、removed直接删账并发既有remove。active→built，collapsing/rubble保留；planned/building不入完工建筑层（工地另行表现）。客户端full_snapshot清空后替换（含空/省略数组），delta仍合并；真实syncStructures按token/相位/格位内容签名重绘，保留颜色/透明度。原始红后端9F/2P、客户端5F/4P；前置指定3F及额外未来坍塌/拆除回退/嵌套祖先边界3F均已绿，相关149P。最终原始not-bench全量2871P/121S/72D/0F（330.00s，无额外排除），客户端149P/27files，tsc/ruff/format353/pyright0/diff检查全绿。日志.orca/da05p-{red,boundaries-red,focused,python-full,client-full,pyright,tsc}.log，最初红证据仍在da05-*.log；先前2865P/3F是已解决历史。一次性本地提交包含本树memory，hash见talking与git log；未再merge main、未改主树、未推送。下一步等主树收编，不自开DA-06/07/08。

【已收编 DA-04】ecc9a14→主树f7720d7；唯一活体戏内名/中文货名在parse与gate之间规范化，候选最近12名，原gate执行范围保留。unknown_good是唯一新增理由，未知/重名仍拒；真实logger代理隔离避免缓存污染。完整决定与2857P基线见审计报告DA-04、talking及git log --oneline -- .orca/memory.md。

【已收编 DA-03】`d5c2931`→主树`4ec5112`，冷启动补修`afdfeb9`已同步；账本必须覆盖读档与lifespan构造两条路径，不能把生产级冷启动崩点当作范围问题遗漏。生命周期ID/余额/活火事件重建已接；燃料用初值12、HP事件来源仍未完整。旧缺素材两条失败口径已过时，当前原始门禁可全绿。历史证据见审计报告、talking和git log。

【已收编历史】DA-02 `de3a8ae`（真实物化/当前子线与玩家游标同事务交接/成功后回帧）；DA-01 `846a052`（世界检查点原子落库/重启恢复/拒重复创世）。均已由主树 `b929406` 收编并同步本树，旧「未含076ed21」口径已过时。完整红绿证据见 talking 回执、审计报告与 `git log --oneline -- .orca/memory.md`。

【审计历史】`974611e`：基准 main@3cbcd8d 确认8组缺口；报告 `docs/security/gameplay-integrity-audit-2026-10-21.md`，原始探针/JSON在 `.orca/audits/20261021-main-3cbcd8d/`。

## 收编踩坑（2026-10-21 merge codex）

- **`world_restore.flush_world` 与 P-6 `_with_structure_tile_restore` 必须叠加**：派生在前
  （`maintenance.observe` 会 pop REMOVED），然后整批交给 `flush_world` 写检查点。
  二选一都会丢东西——只走 `flush_world` 丢坍塌还原，只走 `flush_tick` 丢检查点。
- **codex 树的 `.orca/memory.md` 是旧全文副本**（2797 行），主树已瘦身到 118 行；
  合并时取主树版再人工并入 codex 新快照，不要盲目 `--theirs`。
- **`sim/content/assets/` 整个目录被 `.gitignore:86` 忽略**（`god-packs/`；另
  `zelda-like/pkg/`）⇒ `git worktree add` **不会带过去**，新 worktree 里该目录为空。
  症状：`test_m7_town_map.py::TestTownMap::test_deterministic_build` 与
  `test_m4d16_territory.py::TestTownGodMap::test_deterministic_build` 失败
  （`build_god_town` 依赖 `god-packs/taohuayuan-online/`，主树 67M）。
  **不是代码缺陷**，别用 `--deselect` 长期掩盖——补素材即可
  （`robocopy 主树\sim\content\assets 目标树\sim\content\assets /E`）。
  2026-10-21 已为 codex 树补齐，两条用例转 2 passed。
