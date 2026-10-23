# memory.md — 主树记忆（Claude）

> **历史全文已归档**：`.orca/archive/memory-2026-10-21-full.md`（492KB，含 M0–M6 各轮快照、
> 各 agent 树历史、claude/codex/pi/kilo 分节）。**该目录被 `.gitignore:68`（`.*/`）忽略，
> 只在本地存在**；换机器/新克隆时没有它，需要历史就查 git history（`git log -p -- .orca/memory.md`）。
> 本文件只保留**当前有效**的部分。

<!-- ===== 新对话快速恢复卡（2026-10-21 P 单收口）===== -->

## 0. 本会话状态

- **HEAD**：`fb09a5b`（merge codex：V2 实况接管）；V0 收口 `eb3a260`
- **已收编**：DA-03 `d5c2931`／DA-04 `ecc9a14`／DA-05 `4518515`／DA-06 `ea42b13`／DA-07 `fd31113`／DA-08 `01d8142`（merge `bb57acf`）；**V1**（merge `9437cff`）；**V2**（merge `fb09a5b`，含 `2377108` billboard/拾取/相机 + `9213f3a` 结构层）
- **在飞**：无。**V1/V2 均已收编验收**；V3（气泡/名牌/天气昼夜/结构步进/图集/iso 默认）等用户发话
- **V0 验收**：DESIGN v2.2 仅两处；规格/方案入库 `eb3a260`；双远程已推到 `67aa31b`
- **V1 验收**：高度表 `--check` 逐字节一致；主树叠图肉眼抽查通过；独立 Chromium 复跑 flat/iso 零 JS 异常（见 §2.5）
- **V2 验收**：真实 lifespan 33 帧/54 actors 复跑；Chromium 遮挡像素差 **behind=0 / after=2860**；结构池 4 块+1 rubble、无 structureLayer（见 §2.5）
- **遗留待人工验收**：① **V3 必须补深度层级**（名牌 71-89、雨层 99/夜幕 100 低于 iso 高块）；② DA-07 失能/恢复真模型长局；③ 高块 7643 纹理待 V3 图集替换
- **协议**：1.11（真相源 `sim/api/ws.py::_PROTOCOL_VERSION`，前端 `client/src/net/ws.ts` 同源）
- **工作树：两棵**（2026-10-21 用户重申，长期有效）
  - 主树 `E:/zxdevelop/project7` → 分支 `main`（Claude）
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex` → 分支 `codex`（HEAD 随其提交推进，收编前以实际 `git log` 为准）
- **远程**：origin/gitee 停在 `67aa31b`；V1/V2 merge 未推（按阶段推送，不随手推）

## 1. 里程碑

**M0–M6 全部收官**（M6 于 2026-10-05，G1–G4 全 ✅）；**M7 渲染面**已落（地图/时钟/视角/昼夜）。
代码侧整体完成，剩余是收口型缺口。

## 2. 门禁（2026-10-23 V2 收编后实测）

| 项 | 结果 |
|---|---|
| sim 全量 pytest（`-m "not bench"`） | **2887 passed** / 121 skipped / 72 deselected，**0 failed**（333s） |
| ruff check / ruff format | clean / 357 文件已格式化 |
| pyright sim/ | 0 errors, 0 warnings |
| client typecheck / lint / format | 全 0 |
| client vitest | **182 passed / 31 files**（V2 新增 14 条） |
| 高度表 `build_height_map --check` | **byte-identical**（JSON + PNG） |
| gen:protocol:check | EXIT 0 |
| check_implementation_status | 未发现新缺口（未在本轮重跑） |

> **2026-10-23 首轮全量曾出现 2 个负载敏感假红**：`test_smell_world_step_tick_amortized`
>（墙钟性能守卫，单跑通过）与 DA-07 恢复用例（30s 等待上限 < 负载下实需 ~40s）。
> 后者已改 120s（`c500379`），V1 收编后全量 334s 全绿。**不是产品回归**。
>
> **全量已不再需要 `--deselect`**：此前排除的 2 条地图用例是 codex 树缺
> `sim/content/assets/`（被 gitignore）所致，补齐后两树均可跑全量。
> 旧读数 2982 收集 / 138 vitest 已过时；上表为 V0 收口后现测（3080 总收集）。

## 2.5 等距体素转向 V0-V3（2026-10-23 开工）

- **规格**：`docs/arch/voxel-execution-spec.md`（唯一权威；§0 A1-A19 为实测锚点）；
  方案/理由 `docs/arch/voxel-transition-plan.md`（§11 终审修正）。冲突以规格为准。
- **范围**：仅 V0-V3；V3.5/V4a/V4-3D 不在本单。**sim 内核零改动**，只动
  `client/src/game/**`、`client/public/assets/tilesets/**`、`sim/content/**`。
- **V0（主树，已完成）**：DESIGN v2.2 仅两处；两文档入库 `eb3a260`；双远程推送完成。
- **V1（已收编 `9437cff`）**：`iso.ts` 纯函数（14000 格可逆/菱形边界/depthKey 全序/注入式
  高度表）+ `build_height_map.py`（固定 HSV 阈值、`--check` 逐字节一致）+
  `?renderer=iso` 渲染壳（矮块烘 3840×2040 画布、高块 Image、iso 不建矩形 structureLayer）。
  **主树抽查**：把 `linhe-height.json` 叠回原图生成 `.orca/tmp/height-overlay.png`——河道连续、
  屋顶/墙体对齐、粉冠对准树冠，**止损门通过**。独立 Chromium 复跑（主树代码）：flat
  2240×1600/1 Image/有结构层；iso 3840×2040/7922 Images/无结构层/errors=[]。
  h 分布 0/1/2/3 = 688/5391/5496/2425。
- **V2（已收编 `fb09a5b`）**：实体 billboard（脚底贴顶面、`depthKey+1`、影子压扁 16×4）、
  `isoUnproject` 拾取（碰撞判据/move_request 零改动）、相机边界四侧 64px + 顶点中心跟随、
  结构层并入同一深度池（`built` 0.92 / `collapsing` 0.5 / rubble 低矮标记，无 depth=14 层）。
  主树独立复跑：真实 lifespan 33 帧、54 actors、hero+22 村民+3 动物移动；
  Chromium flat/iso `errors=[]`；遮挡像素差 **behind=0 / after=2860**（与 codex 一致）；
  结构 4 块+1 rubble、无 structureLayer、移除后 marker 销毁。
  **V3 必补**：名牌/气泡深度仍 71-89、雨层 99/夜幕 100，均低于 iso 高块深度（万级）——
  名牌会被建筑压住、夜色/雨不覆盖 iso 世界；V3 不能只改定位，必须提层级。V3 待派。
- **主树实测锚点**：tileset 2240×1600（140 列）；地图 140×100；ground 界内
  14000 格全覆盖、**无 gid=0**；63 个 16×16 chunk，边缘 padding 的 0 在界外；
  树冠主色是**粉色桃花**（不是只有深绿）。原图缩略图 `.orca/tmp/map-overview.png`。
- **V1 派单**已写入 codex 树 `.orca/talking.txt`「当前任务」区（39 行精简版）。

## 3. 缺口清单（codex 审计 8 组 + 主树 P0-3，**全部已修**）

来源 `docs/security/gameplay-integrity-audit-2026-10-21.md`（codex `974611e`）：

| # | 缺口 | 状态 |
|---|---|---|
| P0-1 | 重启二次创世污染日志 | ✅ `846a052` |
| P0-2 | 历史读档 head-only / 世界态未恢复 | ✅ `de3a8ae` |
| P0-3 | **火格 `fire_id` 双语义**（主树探针新发现，不在 codex 8 组内）：`sim/world/fire.py:136` 蔓延格继承 `parent.fire_id`，`sim/npc/fire_runtime.py:73-78` 却每格自增签发新 `fire-{seq}` → 同一 ID 重复熄灭 → `FireWriteError` 整批拒写；`sim/api/ws.py:1401` 的 `await on_flush(events)` 无 try/except ⇒ **世界驱动直接死** | ✅ `d5c2931` |
| DA-03 | 余额/火场账本清零未重建 | ✅ `d5c2931`（读档）+ `afdfeb9`（冷启动） |
| DA-04 | 人物/中文货名目标不兼容 | ✅ `ecc9a14`（merge `f7720d7`） |
| DA-05 | 建筑表现跨分支残留 | ✅ `4518515`（merge `fe2e709`）：含前置 DA-05P |
| DA-06 | 坍塌还原未应用实时碰撞 | ✅ `ea42b13` |
| DA-07 | 主角走 NPC 死亡删除 | ✅ `fd31113`（新增 agent.incapacitated/recovered） |
| DA-08 | 重启后主角双控制源 | ✅ `01d8142`（`external_controller_ids`） |

> 缺口表已全绿。**但「全绿」≠「玩法全部验收」**：见 §0 遗留待人工验收三项。
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
| DA-06 实时碰撞 | `on_flush` 在 `flush_world` 成功后消费本批 `tile_changed`，`tile_map.with_collision` 增量更新并同步 `app.state.tile_map`/`build_runtime.tile_map`/`pathfinder.observe_map` + 清缓存；仅结构终态那帧触发，不每 tick 全图重建 | `ea42b13` |
| DA-07 主角失能 | 新增 `agent.incapacitated`/`agent.recovered` 内部事件；`EntityState.incapacitated_until`（wrap serializer 在 None 时省略，保旧哈希）；火灾/战斗致命结算对主角转失能（保留实体、清路径、停行动、保留念头），普通 NPC 仍 `npc.death`；按既有快进预算跳 1 游戏小时后在最近可走无火格恢复，`CombatLedger.recover` 仅恢复主角 HP | `fd31113` |
| DA-08 控制权 | `assemble_runtime(external_controller_ids=frozenset({CHENMO_ID}))`：主角从效用装配中显式排除，归属由装配方声明、与档案落库时序无关 | `01d8142` |

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

**前端/渲染类**
- **`Phaser.Scene` 已有 `renderer` 字段**：WorldScene 把构造参数叫 `renderer` 会触发 TS2416
  （基类属性类型冲突）；V1 用 `renderMode` 规避。后续渲染策略沿用此名
- **V1 高块纹理按 (h,采样色) 缓存 → 实测 7643 个 CanvasTexture**（约 60-80MB）。V1 可接受；
  V3 图集管线必须替换，别在 V2 再加纹理维度
- **iso 深度池与 flat 深度带不兼容**：高块/实体深度 = `depthKey`（千~24 万），而名牌 71-89、
  雨层 99、夜幕 100 仍是 flat 带 → iso 下名牌会被建筑压住、夜色/雨不覆盖世界。
  V3 处理名牌/气泡/天气时必须同步提层级，否则「定位对了但看不见」

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

- 后端：Python 3.12 + FastAPI + SQLite，`uv` 管理，事件溯源唯一写路径（30 类事件，`extra=forbid`）
- 前端：React 19 + Phaser 3 + Vite + Zustand + Vitest
- 测试：pytest（3080 条收集，`-m "not bench"` 选中 3008）+ vitest（149 条）
- 文档：`DESIGN.md`（v2.2 冻结）+ `docs/`（含 voxel 规格与方案）

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

【2026-10-23 V2｜完成，待主树收编】两笔本地原子提交：2377108（实体billboard/共享高度/拾取/相机）+本快照同笔feat(render)结构层等距化提交（完整hash见talking与git log）。结构反向并入IsoTerrain高块Image池，每个built/collapsing格只画一次、高度2、alpha .92/.5、depthKey；rubble在恢复的静态高度上画1/4单位低矮三面Graphics，与方块/实体同深度池，跳过被新结构覆盖的旧rubble，同格残垣去重；签名未变早退，重连/移除/空地图/销毁清理。IsoTerrain现也使用唯一effectiveHeight，四处高度规则同源。保留flat默认及全部原行为，未实现V3气泡/昼夜/图集/阶段动画/局部重绘。完整门禁与浏览器证据见下一段；收到V3派单前停手，不merge/推送/改主树。

【V2-1｜2377108 实体/拾取/相机】基准b55edf5（V1已merge9437cff、主树高度止损门已过、c500379恢复等待120秒）。iso.ts新增唯一effectiveHeight规则：built/collapsing覆盖2、rubble/移除回静态；WorldScene共享给实体、相机、拾取目标标记，IsoTerrain已在第二笔接入同函数。iso实体脚底=有效顶面，origin(.5,1)，depthKey+1，影子16×4、depthKey+.5；朝向/动画/命名策略保留。iso相机以独立{x,y}逻辑顶面目标跟随，避免同格视觉错位干扰，边界四侧64px（镇图-64,-64,3968,2168）；flat公式逐项原样。R6拾取仍只交地平面，碰撞判据与move_request不变；目标标记投影到共享顶面并用depthKey+1.5避免被高块盖住，flat保留70.5创建深度。无独立debug层；mapLayer的iso路径已由地形画布接管。红8F/13P→相关21P；目标深度另红1F/8P→最终client182P/31files，未删旧语义。结构相位与去重由第二笔提交交付；不做V3。

【V2 本轮验证｜全门禁通过】原始完整uv run pytest -q -m 'not bench'：2887P/121S/72D/0F，331.41s；无--deselect或额外排除。ruff check/format357、pyright0；client typecheck/lint/format/test/gen协议EXIT0，182P/31files（14条新增，全部168旧用例语义保留）；最后marker修正后已重跑完整client门禁。本树自审已完成，零sim内核/既有sim测试/协议/依赖/资产变更。日志.orca/v2-{actors-red,actors-green,structures-red,focused-green,goal-depth-red,python-full,pyright,client-*}.log。真实生产lifespan+run_world_driver+snapshot_payload隔离库录33帧54实体（tick60→2058），主角/22村民/3动物有位移；既有profile-provider测试缝禁用模型，未调用真模型。Chromium重放flat/iso均54views、errors=[]，iso相机边界/顶面中心吻合；另受控双树遮挡肉眼通过，主角树后差异像素0，隐藏树后/绕出后均2860，截图.orca/v2-occlusion-{before,behind,after}.png及v2-occlusion-pixels.json。真实结构Graphics探针：built/collapsing高48、alpha .92/.5、共depthKey；rubble1标记，清空后0且销毁，无矩形结构层，errors=[]；截图v2-structures.png。原始帧/统计/截图日志在.orca/v2-{live-frames.json,world-record.log,browser-smoke.log,browser-structures.log,browser-evidence.json}。实况重放和受控遮挡是不同夹具，未冒充真模型长局或实时WS长局。

【V1已收编｜9437cff】078eb89/a97bf82已由主树验收，高度止损门通过；管线h0/1/2/3=688/5391/5496/2425。历史30秒恢复超时及授权提交证据见git log与talking归档；主树c500379已改120秒，本轮V2原始全量全绿。

【2026-10-23 DA-07｜完成，本波收工待收编】用户“你核准后收工吧”及“继续”已直接授权本树核准此前策略与必要接线扩界，旧待核准状态结束。火灾/战斗主角致命结算改agent.incapacitated；普通NPC仍npc.death。新agent.incapacitated/recovered模型extra=forbid并登记总线/PAYLOAD_MODELS；EntityState绝对期限随内部检查点保存，健康态省略字段兼容旧哈希及pydantic>=2.9。失能清路径/停行动、保留最近念头，旧LLM决策由world_revision作废；世界复用快进预算推进一游戏小时后，选择最近可走无火格恢复，仅恢复主角HP，发既有full_snapshot/戏内心声。暂停沿原时钟控制；自动恢复与玩家快进按段重读时间尺，共享240预算。协议仍1.11，未改settle_attack签名/技能距离部位系统。初始红3F/1P；预算边界另红assert241<=240，修后WS相关76P；核心/死亡/重启/读档88P/2S，字段契约/人口计数14P。首轮全量2884P/1F为EntityState三字段旧白名单，显式登记期限并保留封闭检查，未删钉/跳过/排除。最终原始not-bench全量2887P/121S/72D/0F（290.58s），ruff/format356/pyright0、client tsc/149P、gen:protocol:check均绿；最终日志.orca/da07-python-verified.log，红/预算/首轮输出保留da07-*.log。DA07独立commit见talking/git log；本波06 ea42b13、08 01d8142均已完成；未再merge main、未改主树、未推送。回执后收工，不自开新单。

【DA-08 完成待收编】01d8142；main以external_controller_ids明确ChenmoDriver拥有主角，assemble_runtime在构建utility/hidden之前排除外控实体，首启/重启名单一致且普通NPC效用继续。红1F→相关47P，全量2875P/121S/72D/0F，client149P与静态检查绿；.orca/da08-*.log和审计报告保留完整证据。

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
