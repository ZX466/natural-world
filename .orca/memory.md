# memory.md — 主树记忆（Claude）

> **历史全文已归档**：`.orca/archive/memory-2026-10-21-full.md`（492KB，含 M0–M6 各轮快照、
> 各 agent 树历史、claude/codex/pi/kilo 分节）。**该目录被 `.gitignore:68`（`.*/`）忽略，
> 只在本地存在**；换机器/新克隆时没有它，需要历史就查 git history（`git log -p -- .orca/memory.md`）。
> 本文件只保留**当前有效**的部分。

<!-- ===== 新对话快速恢复卡（2026-10-24 V4a 派单后）===== -->

## 0. 本会话状态

- **代码 HEAD**：`e7f6543`（merge codex：V3 玩法对齐与收官）；最新 `4c8e2fd`（merge codex：V4a 挖放）；
  V0 收口 `eb3a260`
- **已收编**：DA-03 `d5c2931`／DA-04 `ecc9a14`／DA-05 `4518515`／DA-06 `ea42b13`／DA-07 `fd31113`／DA-08 `01d8142`（merge `bb57acf`）；**V1**（merge `9437cff`）；**V2**（merge `fb09a5b`）；**V3**（merge `e7f6543`，含 `b410e32` 图集管线 + `71cb448` 分层/玩法收官）；**V4a**（merge `4c8e2fd`，含 `6e890e6` sim/协议 + `2eed719` 前端）
- **在飞**：无。codex 树已收工（HEAD `2eed719`），等下一单派发。
- **未派**：V3.5 内容包 / V4-3D / V4b（材料分类等）
- **V0 验收**：DESIGN v2.2 仅两处；规格/方案入库 `eb3a260`；双远程已推到 `67aa31b`
- **V1 验收**：高度表 `--check` 逐字节一致；主树叠图肉眼抽查通过；独立 Chromium 复跑 flat/iso 零 JS 异常（见 §2.5）
- **V2 验收**：真实 lifespan 33 帧/54 actors 复跑；Chromium 遮挡像素差 **behind=0 / after=2860**；结构池 4 块+1 rubble、无 structureLayer（见 §2.5）
- **V3 验收**：主树独立复跑全门禁 + 真实 Chromium 闭环（默认 iso / 念头气泡 / 差事往返 / 战斗慢镜 / 昼夜雨 / 结构相位 / 显式 flat），`errors=[]`；深度层级已提到 iso 池之上（名牌 300000+/气泡 310000+/雨 400000/夜幕 400001），图集 `--check` 逐字节一致，textures 从 7643 降到地形固定 4（见 §2.5）
- **V4a 验收**：主树独立复跑 **2935P/121S/72D/0F（299s，无 deselect）**、ruff 364 文件格式对齐、pyright 0、
  client typecheck/lint/format EXIT 0、vitest **217P/39files**、`gen:protocol:check` 通过、高度表与图集 `--check`
  双 byte-identical。十条施工裁决逐条对上（详见 §2.6）。
- **遗留待人工验收**：① DA-07 失能/恢复真模型长局；② V3 画面观感（逐格 tint 与图集贴图的整体质感）人工过目；
  ③ **V4a 挖放观感**——挖后回静态高度（不必然塌成平地），只靠土色标识，需人眼确认可读性
- **协议**：**1.12**（真相源 `sim/api/ws.py::_PROTOCOL_VERSION`，前端 `client/src/net/ws.ts` 同源）
- **工作树：两棵**（2026-10-21 用户重申，长期有效）
  - 主树 `E:/zxdevelop/project7` → 分支 `main`（Claude：拆单/架构/质量/收编复核/日常小改）
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex` → 分支 `codex`（**复杂任务默认派此树**；安全/合规/风险域；HEAD 随其提交推进，收编前以实际 `git log` 为准）
- **远程**：origin/gitee 停在 `67aa31b`；V1/V2/V3 merge 及后续 docs 提交均未推（按阶段推送，
  不随手推）。**不要在本卡写死领先数**——每次 docs 提交都会变，用
  `git rev-list --count gitee/main..main` 现测。

## 1. 里程碑

**M0–M6 全部收官**（M6 于 2026-10-05，G1–G4 全 ✅）；**M7 渲染面**已落（地图/时钟/视角/昼夜）。
代码侧整体完成，剩余是收口型缺口。

## 2. 门禁（2026-10-24 V4a 收编后主树独立实测）

| 项 | 结果 |
|---|---|
| sim 全量 pytest（`-m "not bench"`） | **2935 passed** / 121 skipped / 72 deselected，**0 failed**（299s） |
| ruff check / ruff format | clean（`All checks passed!`；364 files already formatted） |
| pyright sim/ | 0 errors, 0 warnings |
| client typecheck / lint / format | 全 0（均 EXIT 0） |
| client vitest | **217 passed / 39 files**（V4a 新增 22 条） |
| 高度表 `build_height_map --check` | **byte-identical**（JSON + PNG） |
| 方块图集 `build_block_atlas --check` | **byte-identical**（12 帧；688/5391/5496/2425） |
| gen:protocol:check | EXIT 0 |

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
- **范围**：仅 V0-V3；V3.5/V4a/V4-3D 不在本单（**V4a 已于 2026-10-24 另行派单，见 §2.6**）。
  V0-V3 **sim 内核零改动**，只动
  `client/src/game/**`、`client/public/assets/tilesets/**`、`sim/content/**`。
  （V4a **会**动 sim 与协议——这是转向方案里「V4 才动 sim」的兑现点，属预期。）
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
- **V3（已收编 `e7f6543`）**：iso 深度分层到位（`ISO_DEPTH`：名牌 300000+/气泡 310000+/
  雨 400000/夜幕 400001，flat 保留 71..89/99/100）；名牌气泡按 `aboveSurface` 屏幕像素上浮；
  built 0.92 / collapsing 0.5 + 240ms delta 过渡（不重烘、不改高度），rubble 回落静态地面；
  `BlockAtlas` 共享遮罩 + 逐格 tint（地形纹理固定 4，全页 96，flat 94）；iso 成为默认渲染器
  （`?renderer=flat` 保留）。主树独立复跑：真实 lifespan/实时 WS，默认 iso 57 actors/views
  `errors=[]`；念头注入→主角气泡；5 号差事抵达再返回奖励 5→10；真实 driver 攻击 combat=true、
  rate=1，退出恢复；昼夜 alpha 0/.38、雨 80 滴；结构相位 .92→.71→.5、rubble 回 h1 无高块；
  显式 flat 深度 76/85/99/100 回归不变。证据 `.orca/v3-main-*`（截图 + 证据 JSON，gitignored）。
- **主树实测锚点**：tileset 2240×1600（140 列）；地图 140×100；ground 界内
  14000 格全覆盖、**无 gid=0**；63 个 16×16 chunk，边缘 padding 的 0 在界外；
  树冠主色是**粉色桃花**（不是只有深绿）。原图缩略图 `.orca/tmp/map-overview.png`。
- **下一波**：**V4a 已收编验收通过（2026-10-24）**，详见 §2.6；V3.5 / V4-3D / V4b 未派。

## 2.6 V4a 挖放（2026-10-24 派单 → 已收编验收）

- **用户拍板**：V4a 做、**只陈默挖放**（NPC 不参与）；口径按 Minecraft。
- **状态**：codex 交付 `6e890e6`（sim/协议）+ `2eed719`（前端），主树 merge `4c8e2fd`，**独立复跑全绿**。
  派单原文仍在 codex 树 `.orca/talking.txt`「当前任务」节，回执在该文件回执区末三行。
- **主树核实的关键事实**（codegraph 实测，写进了派单，勿再重查）：
  - 输入链路 `handle_client_message`(ws.py:804) → `_ALLOWED_CLIENT_TYPES`:75 与 `_CHANNEL_FOR` **成对**注册
    → `_handle_move_request`:874 → `issue_move`(tick.py:292) → `move_event`(events.py:630)。
  - 碰撞 **1=可走**；`with_collision`(map.py:92) 不可变替换 + 标脏；`observe_map`(pathfinding.py:119) 换图清缓存。
  - 读档**免费**：`rebuild_tile_map`(main.py:95) 重放全部 `tile_changed`（`walkable = tile_id != 0`）；
    `event_tile_position`(pathfinding.py:30) 已把 TILE_CHANGED 当定位事件标脏。
  - **前端零处消费 `tile_changed`**；`delta_payload`(ws.py:629) 无瓦片字段 ⇒ 挖了看不见，这是本单第一断链。
  - `MaterialMoveReason`(events.py:307) 恰 5 值；`material_move` 17 个调用点全在 fire.py；
    `world:*` 允净负、**npc/structure 非负 fail-closed**。
  - 渲染：`effectiveHeight`(iso.ts:52) 只认「结构 + 静态高度表」，`linhe-height.json` 是**颜色近似、非碰撞真相**；
    `IsoTerrain` 按 `lastGround`/`surfaceSignature` 缓存 ⇒ **只改 collision 画面零变化**。
  - 协议 1.11；`shared/openapi.json` 是唯一真相源；改协议须 ws.py + ws.ts + openapi.json + `gen:protocol:check` 同提交。
- **派单核心裁决**（codex 若偏离，收编时按此复核）：
  1. `VOXEL_EDITED` 事件承担语义/审计，**同时必须发既有 `TILE_CHANGED`**（禁开第二条还原路径）。
  2. 本单**只有一种材料 `earth`**；`MaterialMoveReason` 增 `dig_yield`/`place_consumed`；材料分类留 V4b。
  3. `DIG_TICKS = 30`（1x 下 0.5s），挖的进度由 **sim 持有**（确定性），客户端只发起手/松手。
  4. 协议升 **1.12**：C→S `voxel_request`、S→C `voxel_state`、快照与增量各加可选 `voxel_edits`。
  5. 进程内 `_VOXEL_EDITS` 账本（仿 `restore_structures`），读档/重连供全量，**不每帧查库**。
  6. 距离曼哈顿 ≤4，起手与完成各校验一次；拒绝走 `error{code:"bad_target"}` + 戏内文案，不落库。
  7. 左键**短按仍走 `move_request`**（现有 vitest 必须绿）；按住 ≥150ms 才挖；右键 must `preventDefault`。
  8. `effectiveHeight` 增 edits 参、`surfaceSignature` 并入 edits（否则挖完不重绘）；平铺渲染不受影响。
  9. 行囊 chip 只取 `voxel_state.inventory`，**不得进 prompt/世界事件**（C3）。
  10. 图集与高度表 `--check` 必须仍 byte-identical（本单不开美术管线）。
- **基准偏差**：派单写 `3cdff1d`，codex 分支停在 `71cb448`（差 3 个 docs 提交，不影响代码）。
  按纪律他不 merge main ⇒ 以其 HEAD 开工，收编时主树自然合得上。

### 收编复核要点（2026-10-24，主树实测）

- **裁决 2 的记账时序有个必须知道的坑**：库存只在事件真正落库后由 `observe(events)` 更新
  （`voxel_exec.py:226`），而放置的扣减要先过 `_earth - _reserved < 1` 预检，`_reserved`
  在 `VOXEL_EDITED` 落库时才减。**这样连点右键不会超支**，但也意味着测试里必须真的跑
  `observe`，不能只调 `request` 就断言库存。
- **codex 主动报了三处越界修复**（均经复核合理，非擅改）：
  1. `fork.py::_clone_materials_at_cursor`——历史 anchor 分叉时材料余额不能复制父 head，
     改为按游标 + 祖先边界重放 `material.moved`。**这是 V4a 暴露出的旧缺陷**，不是新功能。
  2. `_stop_paths`——放墙后用既有 `move_event(pos,pos,(pos,))` 停掉穿过该格的路径，不改 MOVE 语义。
  3. `voxel-picking.ts`——编辑按可见柱拾取，短按仍用旧地平面拾取（保旧 vitest）。
- **画面口径（重要，别误读为 bug）**：挖 = 回静态高度 + 土色标识，**不是**塌成 h1 平地。
  实测目标静态 h2，挖前/挖后/放后都 48px。可走性是真的，视觉高度不变。这是派单裁决 9 的原意。
- **C3 出站守卫**：拒绝文案走 `_voxel_bad_target` 的固定中文字面量集合，不透传异常消息。

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
- **别把 `linhe-height.json` 当碰撞真相**：它是 `build_height_map.py` 按固定 HSV 阈值从像素
  推出的**视觉近似**（文件头自述 "not collision or semantic truth"），h 只喂渲染抬升。
  碰撞真相只有 `TileMap.collision`。V4a 挖放改的是后者，改高度表属于另一件事
- **V1 高块纹理按 (h,采样色) 缓存 → 实测 7643 个 CanvasTexture**（约 60-80MB）。
  **已在 V3 修**：`BlockAtlas` 共享遮罩 + 逐格 tint，地形纹理固定 4（全页含人物/文字 96）。
  教训：任何「按颜色 / 按高度」开 CanvasTexture 的写法都会线性膨胀，正确做法是固定小图集 + tint
- **iso 深度池与 flat 深度带不兼容**：高块/实体深度 = `depthKey`（千~24 万），而名牌 71-89、
  雨层 99、夜幕 100 仍是 flat 带 → iso 下名牌会被建筑压住、夜色/雨不覆盖世界。
  **已在 V3 修**：`ISO_DEPTH` 常量集中定义（名牌 300000+/气泡 310000+/雨 400000/夜幕 400001），
  flat 保留原带。**新增 iso 覆盖层时先查这个常量，别再手写 99/100 这类散落数字**

**核查方法类**
- **核库后再报**：小写 grep 会漏驼峰符号 → 查符号用 codegraph 或大小写不敏感
- **门禁数字同场测**：不引用旧读数，不用文档自述
- **探针现测**：不引用他人读数
- **skip 分型**：逐条读原始 SKIPPED 行
- **汇报前先核库**：git log + Test-Path，此前有过虚构汇报的教训
- **查代码优先 `codegraph_explore`**（2026-10-24 用户指正）：一次调用返回**逐行源码 +
  调用路径 + 影响面**，等价于 Read，不必再 grep 复核。本会话反例：查 V4a 派单背景时
  用几十次串行 grep/sed，同一批事实读了两三遍，耗时远超必要；换 codegraph 后 6 次调用
  覆盖全部面（输入链路/瓦片/材料/渲染/协议）。**约束：查符号、追调用链、看影响面先用它；
  仅在它没覆盖处（配置、文档、生成物）才回退到 Read/Grep**
- **止损点要提前定**：核实类工作先写「我要答哪 3–5 个问题」，答完立即产出，不要
  「查一项冒两项」无限扩。派别人做的活按**最低可派标准**核实，不必按自己实现的标准勘察

**协作类**
- **两棵树是常态**：主树 `main` + codex 树 `codex`，不要再按「唯一树」记（2026-10-21 用户重申）
- agent 间**只走 talking.txt**：**不直接向 codex 发消息**、不查终端、不用 orca-cli 通知；
  派单/回执一律写对方工作树的 `.orca/talking.txt`（2026-10-21 用户明示）
- 派单要**极简**：codex 只看「当前任务」一节，历史压成表格一行
- **收编后清板**：把回执行移到 `.orca/archive/talking-receipts-<date>.md`，派单区改回
  「无（待派单）」，两棵树都保持 60–70 行；否则下一波要读上千行历史
- 不推远程；只在本地分支提交，收编由主树做

## 6. 恢复序（新对话）

1. **本卡**（0–6 节）；**§2.6 是 V4a 派单的完整裁决**，接手 V4a 必读
2. `.orca/talking.txt`（当前波 + 在飞）
3. `.orca/status.md`（质量门快照，2026-10-24 V3 收编后已刷新）
4. `git log --oneline -15` + `git status`（主树）；**codex 树同做一遍**——派单后他可能已开工
5. codex 树 `.orca/talking.txt`：先看「当前任务」是否还是我写的那一版（他开工后可能补注），
   再看「回执区」末尾几行

> 会话交接常识：`.orca/` 被 `.gitignore:68`（`.*/`）忽略，**不会随 git 走**；
> 换机器/新克隆需要靠 `git log -p -- .orca/memory.md` 或本机归档目录。

## 7. 项目长期分工

- **main**（Claude）：架构 / 质量 / 逻辑 / 测试 / 前端 / 体验 / 发布 / 运维，兼收编
- **codex**（第二棵树）：安全 / 合规 / 风险域；承接主树派单（用户授权可越域）
- 两树间**不直接通信**，只经各自 `.orca/talking.txt` 留痕

## 8. 技术栈速查

- 后端：Python 3.12 + FastAPI + SQLite，`uv` 管理，事件溯源唯一写路径（30 类事件，`extra=forbid`）
- 前端：React 19 + Phaser 3 + Vite + Zustand + Vitest
- 测试：pytest（3080 条收集，`-m "not bench"` 选中 3008）+ vitest（195 条 / 33 文件，V3 后）
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

其他本地归档（同样 gitignored）：

| 目录/文件 | 内容 |
|---|---|
| `.orca/archive/memory-2026-10-24-pre-trim.md` | 本次瘦身前的主树 memory 全文（含被移出的 codex 快照） |
| `.orca/archive/auto-memory-2026-10-24/` | Claude 自动记忆 19 个旧文件全文（D10–D20 逐批、T4 首跑、dispatch 五单、五子树工作流） |

---

## 归档：codex 树快照（原文已移出本文件）

codex 树的逐单回执（V1/V2/V3、V4a、DA-01…DA-08、P 单）不再在此重复；权威副本在三处：

1. codex 树 `.orca/memory.md`（其自身快照）
2. codex 树 `.orca/archive/talking-receipts-2026-10-23.md` / `-2026-10-24.md`（逐行回执原文）
3. 本地 `.orca/archive/memory-2026-10-24-pre-trim.md`（本次瘦身前全文，gitignored）

主树侧只保留**收编结论**：见 §0 已收编清单与 §3 缺口表。

---

## 收编踩坑（2026-10-21 merge codex）

- **`world_restore.flush_world` 与 P-6 `_with_structure_tile_restore` 必须叠加**：派生在前
  （`maintenance.observe` 会 pop REMOVED），然后整批交给 `flush_world` 写检查点。
  二选一都会丢东西——只走 `flush_world` 丢坍塌还原，只走 `flush_tick` 丢检查点。
- **两树的 `.orca/memory.md` 形态不同**：主树是瘦身恢复卡（本文件，约 340 行），
  codex 树是它自己的快照 + 逐单回执。合并时取主树版再人工并入 codex 新快照，
  不要盲目 `--theirs`；收编后也别把 codex 全文再抄回主树（2026-10-24 已清理过一次）。
- **`sim/content/assets/` 整个目录被 `.gitignore:86` 忽略**（`god-packs/`；另
  `zelda-like/pkg/`）⇒ `git worktree add` **不会带过去**，新 worktree 里该目录为空。
  症状：`test_m7_town_map.py::TestTownMap::test_deterministic_build` 与
  `test_m4d16_territory.py::TestTownGodMap::test_deterministic_build` 失败
  （`build_god_town` 依赖 `god-packs/taohuayuan-online/`，主树 67M）。
  **不是代码缺陷**，别用 `--deselect` 长期掩盖——补素材即可
  （`robocopy 主树\sim\content\assets 目标树\sim\content\assets /E`）。
  2026-10-21 已为 codex 树补齐，两条用例转 2 passed。
