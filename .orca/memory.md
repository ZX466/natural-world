# memory.md — 两树最小恢复卡

> 2026-10-25/26 多轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态（2026-10-31 第十二轮收编后）

- **main HEAD**：`7f89584`（第十二轮前端画面优化收编点）。
- **codex HEAD**：`7f89584`，**与主树同步**，工作区干净，无在途任务。
- **协议**：**`1.14`**（第十轮挖深字段升级）；双落点同改
  （`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts::PROTOCOL_VERSION`
  ↔ `sim/tests/test_protocol_version.py::EXPECTED_VERSION` + README 徽章 + `shared/openapi.json`）。
  第十一/十二轮均未动协议字段（纯客户端渲染与 UI）。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单/架构/质量/收编复核/日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现、安全合规。
  - 只走各树 `.orca/talking.txt`；不直接对话。
- **远程**：origin/gitee 停在 `2ad6606`，main 领先 **4 个提交未推**（推送由用户决定）。
- **在飞**：无。**未派**：V3.5 内容包 / V4-3D。
- **待人工验收**（9 条，7/8/9 优先）：
  1. DA-07 失能/恢复真模型长局
  2. V3 画面观感
  3. 走路是否还飘（`INTERP_MS` 200）
  4. ~~V4a 挖放观感~~ — **2026-10-28 已通过**
  5. V4b 三材料挖放观感（行囊土/石/木三行，为 0 不显示）
  6. 地形可走面观感：可走 820→3947 格，房子/河/树是否还挡得住
  7. **移动操作手感**：点击/长按/拖拽/键盘是否顺手——**必须先确认真机能走**
     （2026-10-29 曾因拾取器用错导致「完全动不了」，单测全绿但真机是死的）
  8. **土坎观感（第十一轮）**：1568 格隐形墙是否一眼可辨
  9. **前端画面（第十二轮）**：侧栏收起是否顺手、小屏是否还挤压世界、
     世界宽 872→1152 / 小屏 0→390 的实际观感——**codex 只截了图，主树没开浏览器**

## 1. 门禁（2026-10-31 第十二轮收编后主树独立实测）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | **2996 passed** / 0 failed（374.09s） |
| ruff check / format | clean（366 files） |
| pyright | 0 errors, 0 warnings, 0 infos |
| client typecheck / lint / prettier | EXIT 0 |
| client vitest | **321 passed / 44 files** |
| gen:protocol:check | EXIT 0（协议 1.14） |
| build_height_map --check | 逐字节一致 |
| build_block_atlas --check | 逐字节一致 |
| `tools/check_implementation_status.py` | 未发现缺口 |

> 第十二轮纯 UI 变更（`sim/**`、`game/`、`shared/`、地图/资产/依赖零 diff），
> 但主树仍按纪律复跑了全套。

## 2-newest. 第十～十二轮（2026-10-29 → 10-31）—— 悬空 / 隐形墙 / 前端画面

三轮都已 ff 收编，主树独立复核，无在飞任务。

**第十轮｜悬空修复（`7b1d559` RED → `1895014`），协议 1.13→1.14**

用户真机报「挖完建筑物悬空，人物悬在半空」。根因：服务端挖完发
`tile_changed(gid = 静态 gid)` → 客户端判可走；客户端又本地推算渲染高度 −1。
实测挖一次后 **4562 格**违反 `walkable ⇒ h==1`（2994 格可走却画 2 层高 = 悬空；
1568 格可走却画 0 = 陷地下）。

用户裁决：**服务端记挖深，挖到 h=1 才可走**；**跳跃不做**。落地：`VoxelEdit` 加
`height`（结果高度 0..3 必需）、`VoxelEditedPayload.height` 可选（老事件回退推算）、
`rebuild_tile_map` 重放 `VOXEL_EDITED` 跟踪高度、`walkable = (tile_id != 0 and height == 1)`。
主树独立复核挖 0/1/2/3 轮：**3947 / 8326 / 11320 / 11320，0 违规**。

**第十一轮｜土坎视觉区分（`46ce58e` RED → `6aa0528`）**

用户报「地图仍有不可走的无障碍区域」。根因：`iso-terrain.ts` **完全不读
`map.collision`**，只按高度画 → 阻挡但 h=1 的土坎与可走 h=1 地面渲染完全相同。
实测 **1568 格隐形墙**，其中 269 格 4-邻接可走格（必撞）、91 格是「两片可走区之间的
假通道」、真实出生点 (100,53) 31×31 内 135 格。

**不能改成可走**：`_MATERIAL_BY_HEIGHT[1] = earth` 且 `place` 只对可走格生效
（`voxel_exec.py:124`）—— earth 唯一来源就是「阻挡的 h=1 格」。改成可走 = earth 断源
= 回到「只挖不放」（实测该方案仍留 142 格、土源 730→524）。**故只改渲染**。

落地：`bank = (effectiveHeight == 1) && (collision == 0)` → 画三道明暗土色短斜纹
（`#2c1b10` / `#f1d793`，亮度差 185.8，3.5x 下外纹 7px / 亮芯 3.5px），与「挖过的疤」
（内嵌深色菱形）互斥；retained-set 池化，`changed == false` 的帧零重建。
顺带把 `iso.ts::VoxelEdits` 与 `iso-terrain.ts::Edits` 两条类型路径收敛成
`Pick<VoxelEdit, 'height' | 'action'>`。主树独立复核 **1568 全标 / 0 误标 / 0 漏标**。

**第十二轮｜前端画面优化（用户直派，`bc6739c` RED → `7f89584`）**

原双常驻侧栏压垮小屏、canvas 宽 0 且报 3 次 WebGL framebuffer 错误。改为单一可收起
手札/存档侧栏（桌面默认手札、存档按需，小屏默认关闭、打开时覆盖而不挤压世界）。
世界宽 1440×900 **872→1152（+32.11%）**、1024×768 **456→736（+61.40%）**、
390×844 **0→390×688**。CanvasHost 补 ResizeObserver + `ready` 同步 + 卸载清理。

> **坑（已进 §3）**：Phaser RESIZE 模式必须用 `game.scale.setParentSize`；
> 只调 `scale.resize` 会在 refresh 时从旧 parentSize 回写，手机留下约 46px 底部空隙。

**主树未复核项（诚实说明）**：第十二轮 codex 用真浏览器截的 4 张 PNG 与
`verify-layout.cjs` 结论，主树只核对了 JSON 数值与源码 diff，**没有自己开浏览器**。

## 2-new. 第九轮（2026-10-29）移动操作重做 —— codex 交付 + **主树修掉一个 P0**

用户四症状里的「移动特别局限」，**地图侧已由第八轮修完**（可走 820→3947，出生点 100% 可达）。
第九轮只做**操作侧**，codex 交付 `f74f4af`（RED 测试）+ `04e2175`（实现），主树 ff 收编零冲突。

**codex 落地**：可走格短/长按即走（消死区）、拖拽合并最新目标 100ms 限频、WASD/方向键
逻辑八向、`goalMarker` 到达/换目标/取消即清、`requestMove` 加 `wsStatus` 守卫、
可达性 BFS 与 sim 同八邻禁穿角、墙/断路/断线给戏内提示。新增 `client/src/game/movement.ts`。

**主树收编后发现并修掉 P0「人物完全无法移动」**（`b0d4341`）：

根因——codex 把移动拾取从地面平面换成了 `pickVoxel`，而那是**为编辑设计**的拾取器
（`h>=2` 优先，因为玩家看到的高方块就是要挖/放的那个）。等距投影下 h=3 方块与它
**斜后方 2 格**的 h=1 地面顶面菱形**逐像素重合**（x−y 同、x+y 差 4、高度差 2×ISO.HH），
于是「点空地」被判成「点房子」→ `movementFailure` 全拒 → 一个移动帧都发不出去。

真实地图实测（3947 个可走格，逐格点自己顶面中心）：

| 拾取 | 命中自己 | 落阻挡格 |
|---|---|---|
| 第八轮旧版（纯地面平面） | 0% | 0 |
| codex `pickVoxel` | 80.7% | **763（19.3%）** |
| `b0d4341` 的 `pickGround` | **100%** | 0 |

出生点 13×13 邻域 26 个可走格里 codex 版只有 5 格点得中、**21 格落阻挡**；
十个地标邻域最差 15%（stream_bridge）。

**修法**：新增 `pickGround`（`voxel-picking.ts`）——不做遮挡判定，只把屏幕 y 下移
`WALK_HEIGHT × ISO.HH` 再反投影；单向不变量 `walkable ⇒ h == EARTH` 保证可走面恒在这一层，
故是**精确**反投影而非近似。防御性拒绝高度非 EARTH 的格。`WorldScene` 一次按下同问两个
拾取器：`digTarget`（编辑）、`ground`（移动）；能挖则起计时器，短按抬手仍落回移动。
拖拽与键盘同改走 `groundTarget`。

**教训（已进 §3）**：**单测全绿 ≠ 真机能动**。codex 交付时 290 个前端测试全过、门禁全绿，
但真实地图上 19% 的可走格根本点不中——因为测试夹具造的是「可走格与高块不重叠」的
玩具图，而真实地图上重叠是常态。凡涉及拾取/投影的改动，**必须用真实地图数据实测命中率**。

## 2a. 第八轮（2026-10-29）地形同源重建 —— main，已提交 `37e6a51`

**用户症状**：障碍物可以穿过 / 移动闪现 / 移动特别局限 / 只挖不放。

**根因（三条各自独立，但都指向同一个结构性缺陷）**：
1. 源包 `Collisions` 层与 `World Blocks` **逐字节相同**，只画了三条贯穿建筑与河道的
   直线带（820/14000 = 5.9%）。碰撞真相是它，渲染高度却由另一套 HSV 分类器独立推导
   ⇒ **493 格可走却画成实心**（穿模）、**5752 格画成平地却不可走**（移动局限）。
2. `place` 门槛是「目标格必须可走」，而可走面只有 820 格的窄带 ⇒ 想放东西几乎必然
   越界拒绝；即便成功，行囊里也没有 earth。
3. 客户端 `INTERP_MS=250` **正好等于**行走节拍 250±15ms——滑行永远差一点没走完就被下一格
   重置起点，逐格累积落后（实测 57% 帧落后 >0.5 格，最大 1.20 格）⇒ 视觉「闪一下」。

**落地**：
- 新增 `sim/content/terrain_class.py`（唯一分类源）：逐格 16×16 HSV 占比
  （walk/canopy/water）→ 5×5 均值滤波 4 轮 → 只留最大 4 连通块 → 作者真值挖通道。
  一次 `classify()` 同时产出 `linhe-town.json` 的 collision 位、`linhe-height.json` 的 h、
  以及图集基色档。
- `build_height_map.py` 改为**委托** `build_god_town.derive_terrain`，不再自己分类；
  `render()` 成为唯一写出路径（两处共用）。`build_block_atlas.py` 改为直接读
  `linhe-height.json` 的 h 值，不再依赖 `classify_height`。
- **土坎**（`_is_earth_bank`）：阻挡但瓦片本身像土面（**逐瓦片原始** walk ≥0.45，不平滑——
  平滑会把屋顶拉成土色）且 4 邻可走 ≤2 的格标 h=1。**这是 earth 的唯一来源**：
  若把土坎也判 stone，行囊永远挖不出土，`place` 永久缺料 = 「只挖不放」。
- 不变量**单向**：`walkable ⇒ h==EARTH`，反向不成立（土坎可挖不可走）。
  **做成双向会立刻回归「只挖不放」**（阻挡 h==1 变 0 格，实测已验证）。
- `INTERP_MS` 250 → 200（节拍的 80%，留抖动余量；平均落后 0.57→0.43 格，最大 1.20→1.00）。

**结果**：可走 820 → **3947**（28.2%），1 连通块，出生点可达 3947/3947，
90/90 出生候选、10/10 地标可走，高度档 {0:1112, 1:5515, 2:4379, 3:2994}，土坎 1568。
端到端实测：出生点旁 3 格挖土坎得 earth 1 → 平地放置成功。

**连带修的测试**（旧坐标落在新分类的阻挡格上）：`test_e1_talk_to`（走廊移到行 51）、
`test_m4d12_disperse`（不再把 50 NPC 塞同格，改用生产出生路径）、
`test_m4d20_motion`（走廊移到 (105,56)→(111,56)，那里才有垂直抖动空间）。

## 2. 第七轮成果（2026-10-28）V4b 材料分类 —— codex，已收编 `ba68e88`

**问题**：`VoxelEditedPayload.material_id` 写死 `Literal["earth"]`——挖树挖石屋都只进「土」。
主树实测可挖格（碰撞 0 且静态 h>0）**12511 格**，按静态高度正好三档：
h=1 土 5083 / h=2 石 5102 / h=3 木 2326。

**落地**：
- `voxel_exec.py`：`_MATERIAL_BY_HEIGHT = {1: earth, 2: stone, 3: wood}`；`_validate` 返回材料，
  `_inventory`/`_reserved` 改为三材料字典；`_pending` 存 `(action, material)`。
- **place 消耗目标格所属材料**——挖石得石、放石耗石，往返净值 0；缺料 fail-closed
  （`行囊里没有石料了。`，不落库）。
- 协议 **1.13**：`VoxelInventory` 保留必需 `earth`，新增可选 `stone`/`wood`（缺省 0，仍封闭对象）。
  `MaterialMoveReason` 不改，`MaterialBalance` 零迁移。
- HUD 三行，为 0 不显示；**行囊仍只进 HUD，不进 prompt / 世界事件**（C3）。

**主树独立验证**（不只是跑测试，另写探针实跑）：
- h=1/2/3 各挖一次 → `material_id` 分别 earth/stone/wood，行囊 `{earth:1, stone:1, wood:1}` ✅
- 在 h=2 格放置 → stone 1→0 ✅；再放一次 → 拒绝「行囊里没有石料了。」✅

**codex 自报的告警**：全量跑有 `test_m4c_llm_driver::...test_seed_inserts_profile_and_idempotent`
的 aiosqlite `Event loop is closed`；单独复跑 1P/1.81s 未重现，**未声称已修复**。
主树本轮 2969P/0F 也未见该失败——按间歇性处理，若复现再查。

**否决的候选**：V4a 精确深度（边角缺陷，需改协议，性价比低，用户已验收观感）/
V3.5 内容包（需外部素材与录音管线）/ V4-3D（DESIGN §10.2 三条启动条件均不成立）。

## 2b. 第五轮成果（2026-10-26）

**A｜挖土看得见（推翻决策 9）** —— codex
- `client/src/game/render/iso.ts::effectiveHeight`：`dig → max(0, h-1)`、`place → min(3, h+1)`，
  built/collapsing footprint 仍优先返回 2。
- 挖到 0 时**不再留悬空深色菱形疤**（主树收编解冲突时落地：`height === 0 → continue`，
  疤贴在**降后**顶面）。
- **碰撞真相不变**：仍是 `TileMap.collision`；dig 后仍可走、place 后仍不可走。sim 与协议 0 改动。
- **已知近似**：`VoxelEdit` 无编辑深度字段，先 `place` 再 `dig` 可能掉两层。精确解需改协议，未做。

**B｜等距渲染增量** —— codex
- `WorldMirror.terrainVersion` 失效标记 → `WorldScene` → `IsoTerrain`，静止帧零遍历。
- 脏区裁剪重绘，画布贴图保留；40×40 地图单格 dig 的 CPU fill **4800 → 67（-98.6%）**（codex 自测）。
- **未测的**：浏览器实际 FPS；变更帧仍比较一次全部表面缓存，Phaser refresh 仍可能全画布上传。

**C｜计划看板退役** —— main `bb871f2`
- `state_delta.plan` 条目**全部**来自 NPC 的 defers（`sim/npc/runtime.py` → `set_plan_from_expression`），
  文本恒为「先去别处，等会儿再回来」，不是陈默的计划。
- 面板**直接删除**，未并入心之声（并入会把 NPC 打算误挂成陈默内心）。
- 协议 `PlanDelta` 与 `uiStore.plans` **保留**，只撤 UI。`DESIGN.md` 三形态 → 两形态。

**D｜移动不飘** —— main `bb871f2`
- 走环原来只在「换格那一帧」推进，其余帧归站立帧 → 人物站着滑。加 `gliding` 标志修掉。
- 镜头原来被喂新逻辑格，人物还在滑 → 镜头先跳一格。改喂**插值后的逻辑顶面**
  （不含同格错位偏移），并去掉 0.12 跟随缓动（双重滞后）。

## 3. 踩坑（逐条有效）

**代码**
- `WorldEvent.payload` 是 dict；`StructureSnapshot` 用 `phase`；`collision=True` 表示可走。
- `maintenance.observe` 会 pop REMOVED；派生 tile 事件要抢在它前面。
- 火的 ID 两侧对齐：`FireCell.fire_id` 与 `fire.ignited` 同一命名空间；`fold_fire` fail-closed。
- `on_flush` 无 try/except：落库异常会打死世界驱动任务。
- **挖放高度纯属视觉**：`linhe-height.json` 只是近似，碰撞真相只有 `TileMap.collision`。
  **但静态高度是 V4b 的材料判据**（h=1/2/3 → 土/石/木）——同一张表，两种用途，别混淆。
- **「可挖格」= 碰撞 0 且 h>0**：`_validate` 判据是 `is_walkable != (action=="place")`，
  即 dig 要求**不可走**、place 要求可走。别按「所有地面」统计可挖面。
- **`state_delta.plan` 不是主角计划**：全部来自 NPC defers。别再把它接到「心之声」。
- **地形只有一个真相源**（`sim/content/terrain_class.py`）。碰撞位、渲染高度、图集基色档
  必须同一次 `classify()` 产出。历史上碰撞取源包 `Collisions`（三条直线带）、高度另跑一套
  HSV 分类器，结果是 493 格可走却画成实心、5752 格画成平地却不可走。
- **「可走 ⇒ 土面」是单向不变量**，反向不成立：土坎（阻挡但材质是土）标 h=1，
  是 earth 的唯一来源。**做成双向 ⇒ 阻挡 h==1 归零 ⇒ earth 永不可得 ⇒ 只挖不放**
  （本轮亲自踩过一次并实测复现）。
- **土坎判据用逐瓦片原始 walk 占比，不平滑**：平滑会把屋顶拉成土色，屋顶与田垄就分不开了。
- **客户端插值窗口不得等于服务端节拍**：`INTERP_MS` 曾正好 250 = 行走 250±15ms，
  抖动使滑行永远差一点，逐格累积落后 → 视觉闪现。取节拍的 ~80% 留余量。
- **移动拾取与编辑拾取必须是两个函数**（`pickGround` vs `pickVoxel`）。等距投影下
  h=3 方块与斜后方 2 格的 h=1 地面顶面**逐像素重合**；用编辑拾取器判移动，真实地图
  19.3% 的可走格会被判成阻挡格（实测 763/3947），出生点邻域 26 格里 21 格如此 →
  「人物完全无法移动」。`voxel-picking.ts` 的 docstring 早就写明这个契约，别违反。
- **单测全绿 ≠ 真机能动**。玩具夹具（4×4、可走格与高块不重叠）测不出投影重合。
  凡改拾取/投影/坐标换算，**必须拿真实地图数据实测命中率**（.orca/tmp 写过一次性探针
  再删即可），否则会在「全绿」状态下交付一个死功能。
- **测试夹具不得造违反生产不变量的格**：`iso-live` 曾让 (2,1) 可走却 h=3，
  生产里不可能（`walkable ⇒ h==1`）。夹具违规格会掩盖真实缺陷、也会让修好后误报红。

**前端**
- `Phaser.Scene` 已有 `renderer` 字段，构造参数用 `renderMode`。
- CanvasTexture 不要按颜色/高度开；用固定图集 + tint。
- iso 覆盖层深度集中在 `ISO_DEPTH`（名牌 30 万+/气泡 31 万+/雨 40 万/夜幕 400001）。
- **走环判据要按「是否在动」而不是「是否换格」**：插值期间不换格，但人在动。
- **镜头目标必须与人物同一插值进度**：喂逻辑格 + 再叠缓动 = 双重滞后 = 飘。
- **渲染层不读 `map.collision` 会造成「隐形墙」**：`iso-terrain.ts` 只按高度画，
  阻挡 h=1 与可走 h=1 渲染完全相同（2026-10-30 实测 1568 格）。任何新增「地面长相」
  的渲染都要问一句：这一格能不能走？不能走就得给标记。
- **Phaser RESIZE 模式必须用 `game.scale.setParentSize`**，只调 `scale.resize` 会在
  refresh 时从旧 parentSize 回写（手机留下约 46px 底部空隙）。容器尺寸走
  ResizeObserver，`ready` 后补一次同步，卸载要 `disconnect()` + `off()` + `destroy(true)`。
- **`VoxelEdits` 只有一条类型路径**：`Pick<VoxelEdit, 'height' | 'action'>`
  （`iso.ts` 导出，`iso-terrain.ts` 直接复用）。曾出现 `iso.ts` 定义 `{height}`
  而 `iso-terrain.ts` 走协议 `VoxelEdit`（带 `action`）两条路径，`tsc` 不报错但
  「挖过的疤」判定会静默失效。

**方法**
- 查符号/调用链/影响面先用 `codegraph_explore`（显式 `projectPath`）。
- 门禁数字同场实测，不引用旧读数；**收编后主树必须独立复跑**。
- **删文件/依赖前先查 `DESIGN.md`**：它写死了承诺（`tests/invariants`、`tests/replay`、
  Hypothesis/tenacity），零 grep 命中≠可删。
- 删/移文档后全树扫旧路径；用脚本抽反引号路径比对存在性最省事。
- 测试夹具共享在 `sim/tests/conftest.py`；只在与共享版真有差异时才本地覆盖。
- 协议版本双落点必须同改：`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts`。
- **两树派单必须写明基线**：codex 曾因 `git diff ... | git apply` 撞二进制删除而阻塞
  （补丁缺 `--binary`）。正确做法是主树先 merge，或让 codex 从同步后的基线开分支。
- **收编的文档冲突按用户最新裁定解**，不按「谁后写谁赢」：本轮 codex 的
  「点号目录本地入 git」与用户 10-26 裁定「维持 gitignore」冲突，取主树侧。
- `.orca/` 在 `.gitignore` 里，但已跟踪文件仍需 `git add -f`。
- **`.orca/talking.txt` 永远不进 git**（`.gitignore` 第 73 行：per-worktree local inbox）。
  `729921a` 曾误 `git add -f` 入库，后果是 codex 执行 `merge --ff-only main` 时被
  **静默覆盖掉派单**（已实验复现）。2026-10-28 已 `git rm --cached` 修正；
  改完不要 `git add`，提交里不该出现这个路径。
- Windows 提交时 CRLF 警告正常（`.gitattributes` 为 `* text=auto eol=lf`），忽略。

## 4. 恢复序

1. 本卡 §0–§2。
2. `git log --oneline -10` + `git status`，两树各一遍。
3. 两树 `.orca/talking.txt`。
4. `docs/README.md` + `docs/dev-workflow.md`。

## 5. 分工与技术栈

- 主树：架构/质量/测试/前端/发布/收编；codex：复杂实现、安全合规。
- Python 3.12 + FastAPI + SQLite + uv；React 19 + Phaser 3 + Vite + Zustand + Vitest。
- 文档真相源：`shared/openapi.json`、ORM/迁移、`docs/` 活文档。

## 6. ① Claude｜新对话恢复快照

【2026-10-31 第十一 + 第十二轮收编完成 `7f89584`｜无在途任务】两轮 ff 收编零冲突：
第十一轮土坎视觉区分（`46ce58e` RED → `6aa0528`），第十二轮前端画面优化
（`bc6739c` RED → `7f89584`，用户直派）。主树独立复核 pytest 2996P/0F、
vitest 321P/44F、土坎判定 1568/0/0。协议仍 1.14。

- **开新对话只需知道**：① 两树同步 `7f89584`、无在飞任务、门禁全绿；
  ② 待**肉眼**验收 9 条，**7/8/9 优先**（见 §0）；**主树全程没开浏览器**，
  第十二轮的观感只有 codex 的截图证据；
  ③ **不变量必须单向**（`walkable ⇒ h==EARTH`），做成双向会立刻回归「只挖不放」；
  ④ **移动拾取 ≠ 编辑拾取**，合成一个会在真实地图上死掉 19% 的可走格；
  ⑤ **单测全绿 ≠ 真机能动**，改拾取/投影必须用真实地图实测命中率。
- **未推送**：origin/gitee 停在 `2ad6606`，main 领先 4 提交未推。推送是用户决定，不自动推。
- **配置目录**：维持用户 10-26 裁定「不进 git、不推远程、本地须存在」；主树不建 `.pi`。
- **浏览器**：仅用户明确要求时用，路径 `C:\Users\zx198\AppData\Local\ms-playwright`。
- **全局 git 邮箱**：`zx19836980213@outlook.com`（2026-10-31 实测，`dev-workflow.md`
  原记的 `223049848+ZX466@users.noreply.github.com` 已过期）。
- 本轮教训已进 §3：`.orca/talking.txt` 必须保持未跟踪，否则 ff 会覆盖派单；
  **派单里的坐标/数字必须来自代码实测，不能拿 `spawn_candidates` 当运行时出生点**。

## 7. ④ codex｜新对话恢复快照

【2026-10-30 用户直派前端画面｜真实浏览器检查及优化完成，待主树收编】双固定侧栏压缩世界，小屏canvas宽0并报WebGL错误，已改为单一可收起手札/存档侧栏。宽屏保留手札，小屏默认收起、打开时覆盖世界；修复容器尺寸同步与设置页适配。真实截图/交互回归通过；无在途实现。

- **授权/基线**：用户明确要求“检查前端画面，优化一下”，本轮允许浏览器渲染验证并直接授权本树做UI。基线 **6aa0528**，RED **bc6739c**，实现提交见git log；本轮取 **6aa0528..codex** 全段。主树收尾核验仍 **2ad6606**，故第十一轮 **2ad6606..6aa0528** 也尚待其收编；两轮回执均在本树talking。第十轮已收编，不重做。仅本地提交、不推送、不改主树，talking永不git add。
- **实现与画面**：App/TopBar共用journal/saves选择，>=900px初始手札，窄屏初始关闭且跨入窄屏会收起；存档按需挂载，侧栏切换不重建canvas；中文输入组合态Esc不会关栏/抢焦点（真实浏览器先红后绿）。收起/ESC/遮罩关闭返回相应按钮焦点，设置仍用返回按钮并恢复焦点。顶栏可换行，根壳用100dvh，空手札卡紧凑、长记录独立滚动，移除念头栏窄装饰并补无障碍标签；设置空态居中、小屏有配置时也单列且可滚动。既有暖木宣纸配色保留。
- **必须记住的坑**：Phaser RESIZE模式需要更新 **game.scale.setParentSize**；只调用scale.resize会在refresh时从旧parentSize回写，手机曾留下约46px底部空隙。CanvasHost用ResizeObserver读取非零client尺寸、ready补同步，卸载断开观察/监听并用disposed防回调。浏览器验收要求canvas和父容器差<1px、只有一个canvas，不能只检查可见性。
- **实测与证据**：1440×900 canvas宽 **872→1152**（+32.11%），1024×768 **456→736**（+61.40%），390×844 **0→390**、高度688；宽屏收起侧栏可全1440宽。真实Chromium侧栏切换/ESC焦点/长记录/跨断点/手机遮罩/空和已有配置设置页通过，pageerror0、独立手机reload console error0。前后4张截图、acceptance.json与回归脚本在 **.orca/audits/frontend-visual-2026-10-30/**；计划plan.md，其他截图/日志本地。本轮 **321P/44files**，tsc/eslint/prettier/gen:protocol:check通过，build11.26s（旧大chunk提示）。仅UI源码与测试改变；sim、game渲染/相机/移动、协议1.14、资产/依赖均零diff，本轮未重复后端/资产全套门禁。
- **预览与恢复**：使用批准目录chromium-1248/chrome-win64/chrome.exe，模块取ms-playwright/.links中既有playwright-core1.64.1，无安装。预览backend以本树.orca/tmp/frontend-visual-2026-10-30为cwd建独立world.db，禁用模型driver；长叙事/配置仅浏览器夹具，不是用户数据或真模型输出。任务自己启动的browser与5173/8000进程已按PID/命令行验证归属后关闭，未动用户浏览器/存档。先workflow→talking→本节；CodeGraph显式本树projectPath；Python全程uv、UTF8=1，PS日志可能UTF16 BOM。删npm/venv先问；后续浏览器仍按用户明确要求和固定目录。i-have-adhd持续，50%提醒此前已给，交付后建议新对话。
