# memory.md — 两树最小恢复卡

> 2026-10-25/26 多轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态

- **main HEAD**：本卡所在提交（第九轮派单 docs）；**代码收编点 `37e6a51`**
  （第八轮地形同源重建）。`git log --oneline -3` 即见。
- **codex HEAD**：`ba68e88`，落后主树 3 个提交（`040af24` docs / `37e6a51` 地形 /
  本卡所在 docs），**无分叉**，可 `merge --ff-only main`。
- **协议**：**`1.13`**（V4b 升级）；双落点已同改
  （`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts::PROTOCOL_VERSION`）。
  第八轮地形改动只动资产与客户端插值常量，协议字段未动。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单/架构/质量/收编复核/日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现、安全合规。
  - 只走各树 `.orca/talking.txt`；不直接对话。
- **在飞**：**第九轮「移动操作重做」已派 codex**（2026-10-29）。
  **未派**：V3.5 内容包 / V4-3D。
- **待人工验收**：① DA-07 失能/恢复真模型长局；② V3 画面观感。
  **③ V4a 挖放观感已于 2026-10-28 由用户验收通过。**
  **④ 走路是否还飘 / ⑤ V4b 三材料挖放观感——2026-10-29 已改（插值窗 250→200ms、
  地形同源重建），需重新肉眼验收。**
  **新增 ⑥ 地形可走面观感：可走 820→3947 格，房子/河/树是否还挡得住。**
  **新增 ⑦ 移动操作手感（第九轮派 codex 后）：点击/长按/拖拽/键盘是否顺手。**

## 1. 门禁（2026-10-29 地形修复后主树独立实测）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | **2985 passed** / 121 skipped / **0 failed**（356s） |
| ruff check / format | clean（365 files） |
| pyright | 0 errors, 0 warnings |
| client typecheck / lint / prettier | EXIT 0 |
| client vitest | **259 passed / 39 files** |
| gen:protocol:check | EXIT 0 |
| build_height_map --check | CHECK OK，heights={0:1112, 1:5515, 2:4379, 3:2994} |
| build_block_atlas --check | CHECK OK，counts 同上 |

## 2-new. 第九轮（2026-10-29）移动操作重做 —— **已派 codex，未接单**

用户四症状里的「移动特别局限」，**地图侧已由第八轮修完**（可走 820→3947，出生点 100% 可达）。
剩下的是**操作侧**，主树实测四条真缺陷：

1. **死区**：`WorldScene.handlePointerDown` 左键按下排 150ms 定时器，满 150ms 且目标格
   `collision==0` 才转 `dig_start`。于是「长按落在可走格」什么都不发。这条还被
   `voxel-input.test.ts:73` 当正确行为钉住了——**是缺陷的编码，不是设计**。
2. **零键盘**：全仓 `keyboard` / `addKey` / `keydown` / WASD 零命中，只能一格一格点。
3. **目标点永不消失**：`goalMarker` 只在建时隐藏 + 点击时显示，全仓无第二处隐藏。
4. **走不动零反馈**：点阻挡格前端直接 `return`；点不可达格服务端 `return None`（§4 既有
   权衡）；`runtime.requestMove` 无 `wsStatus` 守卫（对照 `requestVoxel` 有守卫 + 戏内提示）。

**派单裁决要点**（全文在 codex 树 talking.txt）：协议不动（能不加就不加）；W5 红线不变
（移动不走 impulse 文本旁路）；不可达反馈走**客户端预检**，不推翻服务端静默裁决；
确定性一行不改（`entity_move_phase` / `_MOVE_TICKS_PER_TILE` / `GameClock` / `_apply_move`）；
渲染侧（`INTERP_MS`、镜头跟随）与地形资产一行不改。

**已知会咬人的约束**：`ImpulseBar` 输入框聚焦时 WASD 会打字母并让人物乱跑，必须判焦点；
Phaser 键盘默认捕获方向键会滚画布；对角移动须两正交格可走（服务端禁穿角），
客户端发对角前必须同样预检，否则又是一个静默死区；行走有相位延迟最坏 14 tick ≈ 233ms，
属 C5 确定性，**不许靠调相位解决手感**。

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

**前端**
- `Phaser.Scene` 已有 `renderer` 字段，构造参数用 `renderMode`。
- CanvasTexture 不要按颜色/高度开；用固定图集 + tint。
- iso 覆盖层深度集中在 `ISO_DEPTH`（名牌 30 万+/气泡 31 万+/雨 40 万/夜幕 400001）。
- **走环判据要按「是否在动」而不是「是否换格」**：插值期间不换格，但人在动。
- **镜头目标必须与人物同一插值进度**：喂逻辑格 + 再叠缓动 = 双重滞后 = 飘。

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

【2026-10-29 第九轮｜地形已入库 `37e6a51`，移动操作已派 codex】第八轮地形同源重建
（可走 820→3947、土坎保 earth 来源、`INTERP_MS` 250→200）已提交，门禁全绿。
第九轮把「移动特别局限」的操作侧派给 codex：>150ms 按压落可走格是死区、零键盘、
目标点永不消失、走不动零反馈，四条都要修。协议不动。

- **开新对话只需知道**：① 地形已入库、门禁全绿（pytest 2985P/0F、vitest 259P）；
  ② **在飞**：codex 做移动操作（基线须 ff 到 `37e6a51`）；③ 待**肉眼**验收：
  走路是否还飘 / V4b 三材料行囊 / 地形可走面 / **新增：移动操作手感** / V3 画面 + DA-07 长局；
  ④ **不变量必须单向**（`walkable ⇒ h==EARTH`），做成双向会立刻回归「只挖不放」。
- **未推送**：origin/gitee 停在 `2d7c4cf`；main 领先若干提交未推。推送是用户决定，不自动推。
- **配置目录**：维持用户 10-26 裁定「不进 git、不推远程、本地须存在」；主树不建 `.pi`。
- **浏览器**：仅用户明确要求时用，路径 `C:\Users\zx198\AppData\Local\ms-playwright`。
- **全局 git 邮箱**：`zx19836980213@outlook.com`。
- 本轮教训已进 §3：`.orca/talking.txt` 必须保持未跟踪，否则 ff 会覆盖派单。

## 7. ④ codex｜新对话恢复快照

【2026-10-29 第九轮移动操作｜实现与门禁完成，待主树收编】可走格短/长按即时发移动；拖拽合并目标，WASD/方向键八向持续，松手/Escape/失焦取消续走；目标标记到达/换目标/取消会清理。墙、断路、断线和世界未就绪均给戏内提示。协议仍 1.13；无在途实现，下一步由 Claude 独立收编与人工验手感。

- 基线 `0aa5d00`（含 `37e6a51` 新地形）：按派单先备份 talking，再 fetch+ff；talking 仍未跟踪，永不 git add。V4b 已收编。移动 RED 检查点 `f74f4af`，实现与最终交付提交见 git log；收编取 `0aa5d00..codex` 整段。旧 V4b 细节查历史快照，不重复启动。
- 实现只在客户端：movement.ts 复用碰撞数组做八邻 BFS，禁斜穿角；runtime 做连接/可达性预检并复用现有 HUD 提示槽。main 的本地结果回调只表示客户端受理，不是服务端确认。移动一律 move_request，无 impulse 旁路；鼠标移动与挖放共用可见格拾取，不改投影/高度函数。
- 输入：可走格 pointerdown 同步发起；阻挡格仍按住 150ms 才挖，右键放置保留。拖拽保留最新点，至少 100ms 且看到角色位置进展才替换在途路径，避免反复插入起点导致原地不动；松手最多补最后一条。键盘按逻辑格轴八向（W/上=-y），同源同方向不重发；松手以现有 move_request 指向最新角色格取消。输入框/textarea/select/contenteditable 不吞键，keyup、blur、shutdown、断线及换世界均有清理测试。
- 实测条件与数字：客户端虚拟时钟下按键/可走格按下同栈派发（0ms）；4Hz 位置快照夹具中 1000ms 的 124 次 pointermove 合成 **4 条移动请求，释放补 1 条**。真实服务端无网络探针遍历 15 种起始相位，首次实际换格 **266.667–500ms（16–30 tick）**；路径包含起点会先消耗一拍，不能只算派单的 0..14 tick 相位。长直线路径稳态 **4 格/s**，逐邻格键盘续发 **2 格/s**；本单按约束未改 sim 相位/路径语义。
- 本轮亲测：pytest **2985P / 121S / 72D / 0F，4 warnings，371.81s**；ruff check/format（365 files）与 pyright 0 errors/warnings；gen:protocol:check、client typecheck/lint/format 通过；Vitest **290 passed / 40 files**；生产 build 通过（11.56s，保留现有大 chunk 提示）。两资产 --check 逐字节一致。证据/复核在 `.orca/audits/movement-input-2026-10-29/plan.md`，原生探针 server_timing.py 可复跑；日志/JSON 为本地件。
- 范围与限制：sim/**、shared/**、renderer/**、client/public 资产与依赖均零改动；相机方法逐字节不变，INTERP_MS=200 / effectiveHeight 不动。未做浏览器、网络 RTT 或真人输入到显示延迟验收，服务端已经迈出的在途一步不能由客户端撤销；覆盖率未配置、不报百分比。保留工作树，仅本地提交、不推远程，只用 talking 留回执。
- 恢复先 workflow → talking → 本节；i-have-adhd 与简洁中文持续启用，CodeGraph 返回源码视为已读；50% 上下文提醒已给，本单交付后建议切新对话。不启动未派的 V3.5/V4-3D。
