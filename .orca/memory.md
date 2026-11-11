# memory.md — 两树最小恢复卡

> 2026-10-25/26 多轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态（2026-11-11 · 波 A/B/C/D/E 全收编 · 协议 1.19 · 3D 默认 · 土坎 2 格方块 `a152796`）

**波 E 派单（2026-11-11，codex 树 `.orca/talking.txt` §九）**：陈默动作面闭环
（work/eat/rest 进决策面 + 执行面 + 内感受 hunger + needs 推进 + PlanSlice）。
用户三条裁定：work **只给药铺邻域计酬**（复用 5 文/冷却口径）、**现有世界不重开**、
**验收在真库副本上跑**（`llm_profiles` 与世界同库，空库跑不出决策）。
派单前主树逐条核过行号，修掉了草稿里 6 处会做错的地方，其中三处是硬错：
① 陈默的内感受**已接了一半**（hp+时辰走感知帧 INTEROCEPTION，`main.py:405`），只缺 hunger；
② `needs` **全项目从未落库**（村民跑 45 万 tick 仍是种子值），所以「读档重置 needs」是给
不存在的东西写代码；③ `decide_once` 的 `assemble_prompt` **不在 try 内**且 `_chenmo_loop`
无异常兜底 ⇒ 任何一条带禁词的文本会让决策任务**永久静默死亡**（实测确认），本波必须先堵。
另删掉一条零区分度验收（「心声不重复」——29 条全不重复）。

**波 E 收编（2026-11-11，codex `5a85afc`）**：陈默 work/eat/rest 闭环。
`IntentAction` / `M1_SUPPORTED_ACTIONS` / prompt 枚举三处同步；三动作不填 target，
执行当拍结算（npc.act + 一条**结果** thought，不再重发 reason）。work 只在药铺
`PHARMACY_POS=(100,53)` 曼哈顿 ≤ `_SITE_ARRIVAL_RADIUS=4` 且冷却过才付 `_WAGE_AMOUNT=5`，
`wage_last` 与 main 同一个 dict；eat 按 `buy_price(meal)` 扣款、买成才 `apply_remedy`；
rest 免费补救 energy。`ProtagonistNeeds` 纯内存（不落库），main 每轮决策前推进并只把
`narrate_hunger` 送进 interoception。`PlanSlice.last_intent_result` 只取本意图事件窗口里
本人新发的 thought。`npc.act → anim` 改为 accepted-event 观察器（NPC 与陈默共用）。
四个移动臂统一拦 start==goal / 空路径 / 单点 / 回到起点，不发原地 MOVE。

**收编时主树独立抓到一处能永久冻住陈默的缺陷（codex 回执未提）**：`last_intent_result`
进 `[计划]` 段是**持久** prompt 状态，而闸门用 `quoted_echo_scan`（句首反问/引号转译**豁免**）、
装配器用不豁免的 `scan()`。一句能过闸门、过不了装配的 reason（实测 `"游戏？我不过是个学徒。"`）
会让此后**每一轮** `assemble_prompt` 抛 `PromptAssemblyError`，异常兜底只让循环活着、
`llm_calls` 恒 0 —— 陈默静默。修法在**写入侧**：`ChenmoDriver._record_result()` 按装配口径
`scan()` 预筛，过不了就存空串。钉子 `test_gate_exempted_reason_cannot_freeze_every_later_decision`
（闸门先断言 accepted，再断言三轮都真到 LLM）+ `test_banned_handler_thought_is_dropped_…`。

**试车台 = 世界结构（2026-11-09 用户改口「要和预览一样：可识别拆解，是障碍物实体」）**：
外部 SDK 整包原样入库 `vendor/linhe-lre-sdk/`（272K，除一份本仓新增的 `.d.ts` 外一字节未改），
只把**建筑模块**接进 three 世界。与上一版相比的三处改动：

1. **占地面进了世界碰撞。** `build_god_town.derive_terrain` 选出 17×15 矩形（全平、不压
   地标/出生点、**压进去不把可走区割裂**），把它写成不可走格，并输出
   `_structures.lre_test_stand`。实测中心 **(82,41)**，可走 3947 → **3692**，仍是单连通。
   连通性检查是必须的：最初选的 (83,37) 会切出一个 27 格的孤岛。
2. **客户端不再自己扫地形。** 锚点经 `GET /api/world/map` 的 `structures` 下发
   （协议 **1.17 → 1.18**），`landmark-lre.ts::standPlotFrom` 只做坐标换算。
   **`?landmark=0` 已删** —— 建筑是真障碍物，关掉地标会留下一堵看不见的墙。
3. **识别 / 拆解 / 三视图接了面板。** `landmark-lre-panel.ts`（裸 DOM，不进 React 树）
   接出 4 系统 24 部件清单、悬停浮签、点选详情、四级爆炸拆解滑块、PBR/HOLO/FLIR、
   点火开关。画布点击命中部件被 `three-input` 的 `pickStructure` 拦下，不会再发一条
   走到那格的移动指令。

**挖块禁挖**：`TileMap.structure_at()` + `voxel_exec._validate` —— 试车台格高度 1、碰撞 0，
与「土坎」判定同形，不拦就会被一路挖成坑而模型浮在上面。渲染侧同理：
`cell-appearance.staticStructureTiles` 把这些格排除出「土坎矮墙」（否则建筑被墙包住）。这条判据有钉子：
`test_voxel_runtime.py::test_static_structure_ground_is_undiggable`（dig/place 各一条，零事件）。

**土坎抬成 2 格方块（2026-11-10 用户裁定「土坎不要了，都变成方块」）**：
此前 `6dc5cea` 的做法（three 补三道 45° 斜杠、Phaser `syncBanks` 斜纹）**已被推翻**，
两处字形全部删除。现在**高度 1 但不可走**的格（天然土坎 1568 格 + 玩家放下的土块）
一律按 **2 格高实心方块**渲染，与石料/木料方块同形 —— 一眼就是矮墙、过不去。

核心是**渲染高度与逻辑高度拆开**：
- `cell-appearance.ts` 新增 `BANK_RENDER_HEIGHT = 2`、`isBankCell()`、`drawH` 字段、
  `renderHeightLookup()` / `cachedRenderHeightLookup()`。`drawH` = 土坎 2，其余 = `h`。
- **渲染/拾取/脚底/镜头/选框读 `drawH`**；**碰撞/`standable`/跳跃落点/`heightAt` 读 `h`**。
  `TerrainCell.h` 现在装的就是 `drawH`（字段 `bank` 已删）。
- `pickVoxel` 的 `isBank` 参数与 `hitsBankGlyph` 已删；`pickGround` / `groundFromRay`
  仍用**逻辑**高度反投影（土坎不可走，站在旁边时周围地面画在 1，按 2 反投影会整体偏一格）。
- 静态结构（试车台 17×15）靠 `staticStructureTiles` 排除，**不抬**（那是建筑地基）。
- `three-actors` 新增可选 `drawHeight`；`three-voxel-cues` 新增第 4 参。
- Phaser 侧 `syncBanks`/`BANKS` 图元、`iso-terrain` 的 `banks` map 全删，
  方块视图与脏区判断改读 `drawH`。

钉子：`iso-banks.test.ts` 钉 `{banks:1568, walkable:3692, adjacent:269}` 且逐格验证
`drawH` 有柱、无柱；`three-terrain-adapter.test.ts` 钉 `cells.h === appearance.drawH`。
**已提交 `a152796`**（15 文件，+421/−464）。门禁：pytest `3675P/121S/72D EXIT 0`
（533.18s）、vitest `736P/87F`、ruff/format/pyright/typecheck/lint/prettier/
gen:protocol/build 全 EXIT 0。协议仍 **1.18**（纯客户端）。
⚠ **仍未做真机验收**（2 格矮墙在其它机位/距离下的观感需 WebGL）。

其余边界不变：② **不替换角色系统**（SDK 每角色 46 mesh/2346 draw call，本仓
`avatar3d.ts` 已验收且是 51 call）；③ 锚点缺失（占位 32×32 图）或 shader 不可用就不建。
占地面实测 **17×15**（`getOccupiedTiles()` 取 `tileX±8`/`tileZ±7` 闭区间），
**不是规范文档写的 16×14**。包体 2309→2406 kB（gzip 572→604）。

**试车台收编门禁（`298d037`，41 文件）**：pytest `3675P/121S/72D EXIT 0`（415.97s）、
vitest `734P/87F`、ruff check+format / pyright / tsc / lint / prettier / gen:protocol:check /
build 全 EXIT 0；`build_height_map --check`、`build_block_atlas --check` 字节一致。
⚠ **仍未做真机验收**（悬停手感/面板布局/拆解动画需 WebGL）。

**波 C 收编（2026-11-10，codex `a8ec73f`）**：渲染三件，纯客户端不碰协议（仍 **1.18**）。
① **3D 主角穿墙剪影**：`three-avatar-occlusion.ts` 在世界正常颜色之后单独跑两遍 ——
清深度、只渲染**实心环境**深度（角色/影子/billboard 剪影/透明与裁切特效全部排除），
再用 `GreaterDepth` 画主角原 `SkinnedMesh`。NPC 不透视、无遮挡不染色、不复制网格或图集、
不换地形材质；`?avatar3d=0` 不建此 pass。② **近墙相机**：先横向搜索安全轨道再适度抬角，
**自动抬角 ≤35°**（用户主动高角度保留），围合空间改为缩短 boom；控制/朝向改读
`cameraAzimuth(实际相机)` 而不是 `orbitPose.azimuth`。避碰改用
`TerrainAdapter.renderHeightOf` —— 它读本帧交给场景的 `TerrainCell.h`（= `drawH`），
所以土坎抬成 2 格后**自动**跟随，不必在调用点再包一层。③ **Phaser 高度通道未复现**，
codex 用真实私库事件实测四段 `animClock` 增量均 0、非 airborne，故未改架构（符合派单）。

**收编时主树修的一处**：`lets a requested orbit escape padding…` 原用默认方位角 225°，
射线根本不碰那堵墙，新旧实现都会通过 —— **空转断言**。改为方位角 90°（脚点在 padding 内、
相机在墙另一侧、射线真穿实心柱）后旧实现确实把相机裁进柱体 `(0.65, 2.33, 0)`，
新实现绕开；已先红后绿。另用 54,000 个随机场景独立 fuzz 相机避让不变量，**零违规**。

**门禁**：pytest `3675P/121S/72D EXIT 0`（550.45s）· vitest `746P/88F` ·
ruff check+format / pyright / typecheck / lint / prettier / gen:protocol:check / build 全 EXIT 0。
vitest 比 codex 的 747 少 1 是预期的：主树 `a152796` 重写了土坎用例
（`iso-banks` 8→7、`three-terrain` 11→10），波 C 在 adapter 补 1 条（9→10），净 −1。
⚠ **仍未做真机验收**：剪影浓淡、侧移舒适度、实际帧耗归用户（codex 只做了 SwiftShader 技术读数）。

**波 D 收编（2026-11-10，codex `17f4d26` → 主树 `ec4a020`）**：协议 **1.18 → 1.19**。
用户实测原话「后端功能体现不出来」——世界在跑、库里有货，但画面看不出 NPC 在干什么、
谁身体不好、谁跟谁有交情、谁知道了什么。**#1 仍排除**（用户「1 先不填写」= 不给陈默配 LLM profile）。

- **D-1 动作可见**：`avatar3d.ts::AvatarAnim` 加 `work|eat|rest|chat`，**只用原 16 骨骼**摆姿势，
  不加网格/图集格/draw call（仍 1 SkinnedMesh/人、共享 512×256 图集）。
  `three-actors.ts` 的优先级是**位移优先**：airborne → 移动中的 `animClock` → 站定才读 `actor.anim`
  （`anim==='walk'` 的站定仍画 idle）。站定相位按**未暂停**的 `delta×speed` 推进，
  暂停冻结、恢复不补跑（`three-world.ts` 传 `ui.paused`）。**2D 回滚路径未接**：
  chenmo 图集有 R4–7 姿势行（逐格实测）、villager 4×4 没有，本波保持现状。
- **D-1 两处必须修的都修了**（这是派单里点名的）：
  ① `npc.act` 原本**不进** `pending_delta_entity_ids` ⇒ 站定原地切动作没有 delta 帧，
  姿势永远传不到客户端。现在 `_npc_tick_hook` 只在 `_anim_of` 前后值**真变**时标脏，
  钉子在 `test_npc_view_live.py::test_stationary_changed_action_marks_delta_once…`。
  ② `_ACTION_ANIMS` 原本只写不清 ⇒ 读档继承旧分支姿势。现在 startup/读档成功块/shutdown
  三处都调 `clear_action_anims()`（读档块与 `clear_npc_views()` 并排）。
- **D-2 健康/关系/知识出站**：新模块 `sim/api/npc_view.py`（SQL 只在这里读，且只在启动、
  读档、以及提交了 health/death/chat/retell/knowledge 批次之后），WS 侧 `npc_views` 账本
  只存**预构造好的叙事行**。`NpcView` 封闭四键+可选名：`{rtoken, name?, health[], bond, knows[]}`；
  `NpcViewDelta` 另允许 `{rtoken, op:"remove"}`。**快照发全集、delta 发变化**，
  广播判据补 `or _npc_views_changed()`（否则静止世界里关系变了永远不发帧）。
- **自我未知在构造期落地**（不是靠下游拦）：陈默自己的 `hidden=1` 只在
  `HiddenState.triggered` 命中时出；别人的隐藏健康必须陈默持有**双列对齐**的
  `(subject_npc_id, subject_attr_id)` 有效 knowledge 行。每句出站文字再用本分支隐藏元数据
  跑一次 `hidden_leak_scan`——已入册的旧 fact 也不能夹带**已消退的自身词面**或**无关隐藏项**，
  命中则整句不发（不改写、不发暗示）。**真库实测**：无触发时面板 10 行（陈默 + 9 名有过
  交谈的村民），只有陈默 1 条公开健康（`wrist_strain`）；`night_unease` 未触发不外发。
  刻意用假关系探针验过：villager_01 的 `shoulder_injury` 在无 knowledge 时**整行为空**，
  补一条对齐 knowledge 后才同时出现 health 与 knows。
- **账本学的是 lights 那套**：新连接不会吃掉别的连接待发的变更；只在快照见过的行
  仍会在之后发 remove；`A→B→A` 会补发（`_NPC_VIEWS_SNAPSHOT_DIRTY`）。
- **客户端**：`ws.ts → runtime.ts → uiStore → NpcPanel`（`PanelHost` 第三块「人物」）。
  快照**整组替换**（缺键=清空，防重连残留），delta 按 rtoken 合并/移除，输入去重复制。
  面板只渲染字符串，**不做数值→文案映射**（`narrate_health`/`narrate_bond` 在
  `sim/perception/narrate.py` 一处维护）。
- ⚠ **面板会显得空，这是真相不是 bug**：陈默 `knowledge` 只有 2 条，指向 `villager_02`/`villager_03`，
  而这两个人**不在** `relationships` 的 9 人里（真库 `owner_id='chenmo'` 是 0 行，
  印象只落在承受方）⇒ 面板里 `knows` 恒为空、`bond` 一律是「见面会同你搭句话」级别。
  别为好看补造数据、别放宽「认识」的判据。
- **门禁（主树独立复跑，`ec4a020` 树态）**：pytest `3696P/121S/72D EXIT 0`（539.74s）·
  vitest `792P/92F EXIT 0` · ruff check+format / pyright / gen:protocol:check / typecheck /
  lint / prettier / build 全 EXIT 0。⚠ **真机验收归用户**：姿势辨识度、面板观感、实际帧耗
  （codex 只有 SwiftShader 技术读数）。
- ~~顺带发现、仍未修未派~~ → **已于 `510e618` 修复**（见下方「事件静默丢弃」段）。

**事件静默丢弃两处修复（2026-11-11，主树 `510e618`）**：两处都是「事件面看着有、实际不落地」。
1. **起火落点**（`sim/api/main.py::_ignition_spot`）：哈希格不可走时环状外扩取最近可走格，
   同距离按 `(y, x)` 定序保 C5；新增 `avoid` 参数避开已在燃格。原实现只在哈希格恰好可走时点火，
   而真实地图可走格仅 **26.4%** ⇒ 设计 34%/日 被砍到实测 **9.13%/日**（500 seed × 200 日：
   抽中 33,907、落地 9,127）。`zlib` 已提到模块顶部。
2. **LOD 升降 / 隐藏浮现**（`sim/npc/sim_exec.py::_PASSTHROUGH_KINDS`）：`npc.lod_change` 与
   `npc.hidden_emerge` 走直通集合，不再被 `npc.act` 过滤丢弃。runtime 侧已改内存档、
   事件是**唯一落库路径** ⇒ 否则库里 `lod` 永远停在旧值（`chenmo` 库内 `lod=2` 但零 `npc.lod_change`
   事件，L2 从未真正升格）、浮现证据链断根。
3. 新增 11 条回归钉子：`sim/tests/test_fire_ignition_reachability.py`（可走落点 / 确定性 / `avoid`
   生效 / 抽签率仍在 28–44%）、`sim/tests/test_lod_event_flow.py`（升格与降格真出流 / 不挤掉同拍
   `npc.act` / 无升降不造事件 / 事件是合法存储行）。
4. **门禁**：pytest 全量 `3862P/126S/2F`（608.95s）。两个 F 都是 bench 阈值边缘
   （`test_retrieval_full_scan_degraded_sentinel` 实测中位 2.017ms vs 红线 2.000ms、
   `test_perception_sound_50npc`），**复跑均绿**，且本次改动未触及检索/感知路径。
   另跑 `-m "not bench"` 收尾确认：**`3797P/121S/72D EXIT 0`（497.77s）**。

**波 E 收编（2026-11-11，codex `5a85afc`）**：陈默动作面闭环，详见本节开头。
- **门禁（主树独立复跑，`5a85afc` + 本树修复树态）**：pytest `3786P/121S/72D EXIT 0`（496.06s）·
  vitest `792P/92F EXIT 0` · ruff check+format / pyright / gen:protocol:check / typecheck /
  lint / prettier / build / `build_height_map --check` / `build_block_atlas --check` 全 EXIT 0。
  比 codex 的 3785P 多 1：主树新增 2 条冻结缺陷钉子、替换掉 1 条旧的「装配必抛」断言
  （那条把缺陷**写成了期望行为**）。
- **未收 codex 的 `c3a382d`**（本树 voxel-execution-spec §10.5 订正）：主树该文件无 §10.5，
  且历史五份文档与主树分叉，**不要整树 merge**。
- ⚠ **真机验收归用户**：work/eat/rest 姿势辨识度、hunger 文案观感、实际帧耗。
- **仍排除**：不给陈默补启动金、不改 genesis 50 户各 15 文、不把 needs 落库。

**波 B 收编（`fb20719`，codex `d799fca`）**：真实火场出站 —— `sim/npc/light_view.py`
把活跃火格投影成既有六键 `Light`（不透明稳定 rtoken、x/y、`kind="fire"`、radius 5、
flicker 0.4），**不输出** fire_id / 燃料 / tick / 强度 / 归因，无火灾专用路由或帧类型。
全量带当前光源；增量 add 完整 upsert + remove by rtoken；快照独见 token 单独追踪，
既不让新连接吃掉别的连接待发的移除，也不漏「只在快照见过就熄灭」的移除。
**协议 1.16 → 1.17**（两处常量 + live app/info + 快照版本 + 版本登记 + `shared/openapi.json`
手改 `LightDelta` 可选 op/x/y/kind/radius 后重生成 TS）。`test_m5_fire_outbound.py` 逐字节未改。
⚠ **部署必须前后端同步 1.17**：1.16 客户端不处理 remove，火声可能滞留到下次全量同步。
⚠ **1.18 起同理**：1.17 客户端不读 `/api/world/map` 的 `structures`，试车台模型不建
（那块地仍然不可走 —— 只是看起来像空地）。
主树独立复跑 pytest `3670P/121S/72D EXIT 0`（490.79s）、vitest `723P/84F`、
ruff/format/pyright/tsc/lint/prettier/gen:protocol 全 EXIT 0 —— 与 codex 读数一致。

**波 A 收编（`3dbc0d6`，codex `1dc645a`）**：`take`/`give` 补上执行器 —— 各发 1 条
`material.moved`（`reason=take|give`）+ 1 条结果独白，复用土/石/木库存与
`fold_material_balance` 守恒；`MaterialLedger` 只观察已应用事件、不写 SQL；
`VoxelRuntime` 加可选 `stock_available` 读面防双花。协议仍 1.16。
⚠ **生产边界**：只有陈默有材料来源，村民从不持有材料 ⇒ 真实世界里 `take` 恒失败、
`give` 收下的料无下游。测试能过是因为夹具用 `world:seed` 合成库存（生产无此 ref）。
要让它有意义得先给村民材料来源（新玩法），别当 bug 修。

**本轮已落地**：用户 2026-11-09 亲口「验收都通过了」（3D 手感/观感、土坎配色、按住连续行走）；
同日裁定 **「3d默认」** → `c8d6c30`：`avatars3dFromSearch` 翻成「非 `0` 即开」，
`?avatar3d=0` 回滚 2D。codex 树已同步（`c41977a`，冲突全取主树侧），两处历史分叉消解。

**用户同批裁定「m2 t4 不做」**：M2 七日长跑（604,800 tick）与 T4 真模型重跑
**都不做、不落 artifact**，已写进 §1c 表，别当缺口再提。

**三波已全部收编**：波 A（`3dbc0d6`）/ 波 B（`fb20719`）/ 波 C（见 §0）。
开关与 URL 组合见根 `README.md`。codex 树已无待收编内容。

### 2026-11-09 土块透明修复 + 文档压缩（`a843e3a` / `99b4c9a`）

**「土块透明了」的根因不是透明度，是 `EDIT_COLORS` 两个下标写错**
（`client/src/game/render/cell-appearance.ts`）。该表**按格子高度索引**，两条都在用：

| 下标 | 旧值 | 问题 |
|---|---|---|
| h=0（挖到底） | `0x8f8055` 土色 | 与 h=1 同色 ⇒ 坑底看着像没动过的地面，而渲染器把它画成 0.06 厚的水面片 |
| h=2（挖掉木头柱） | `0x8a8880` 浅灰 | **luma 136 = 整帧 99 分位**（帧中位 87.3）⇒ 绿地上一块浅灰，读作「天空透出来了」 |

改法：h=0 → `WATER_COLOR`（新增导出，`0x5b7674`，图集 water 角色色）；h=2 → `0x5f5c43`
（图集 building 角色色，和自然石色同族）。h=1/h=3 不变。**别再往这张表里塞浅色**，
天空/浅灰在 three 的 BasicMaterial 地形上就是「透明」的观感。

**真机取证**（隔离空库 + 打包 Chromium）：射线在 5 个屏幕点全部命中 (99,50) h=2 `0x8a8880`；
6 条真实编辑 = `97,51` 放土 h1、`97,53`/`97,54` 挖土 h0、`98,50`/`99,50` 挖木 h2、`99,51` 放木 h3。
h=0 实例 color `#8f8055` + scaleY `0.06` ⇒ 土色水面片，坐实。改后 (98,50)/(99,50) 为 `#5f5c43`、
(97,53)/(97,54) 为 `#5b7674`，截图浅灰菱形消失、出现小块青色水面。

**测试**：新增 `edit-material-colour.test.ts`（3 条：放置用材质色 / 挖掉一层露出的层色 /
挖到底=水不是土）；`iso-terrain.test.ts` 两处硬编码 `0x8a8880` 改为 `EDIT_COLORS[2]`。

**文档压缩（`99b4c9a`，8 文件 +116/−319）**：
- `README.md` 新增「停机补跑」段（默认 1 游戏小时 = 3600 tick ≈ 15s，
  `LZ_OFFLINE_CATCHUP_MAX_TICKS` 取 `(0, 86400]`，非法值启动即失败；**不再需要删库重建**），
  补 `WORLD_DB_PATH` **无效**说明、编辑格配色说明、故障表「启动很慢」一行。
- `m7-render-art.md` 197→**35** 行：只剩仍生效的 R2/R3/R8；其余标死。
- `character-model-3d-plan.md` 117→**48** 行：从「待决方案」改为「实际形态」。
  （提交信息与本节旧记写的是 68/61，与文件实际行数不符；2026-11-09 按
  `git show 99b4c9a --numstat` 与 `wc -l` 复核订正。）
- `openapi.md` §4.1 从 32×32 占位样改为真实 `MapChunk`（140×100 / `god_town_v1` /
  protocol 1.3 的 `ground_b64`）。
- `docs/README.md` 同步索引，新增纪律「**文档写完即回写**」。
- 三条 m7 测试 docstring 里已不存在的节号改为按文档名引用。
- 删除 `three/__tests__/probe-enclosed.test.ts`（临时探针）与仓库根 61 张未跟踪调试 PNG。

**门禁**：pytest `3632P/121S/72D EXIT 0`（472s）· vitest `720P/83F` · ruff / ruff format /
pyright 0 / typecheck / lint / prettier 全 EXIT 0。

**codex 树分叉（别整树 merge）**：codex `41772de` 独立做了同一件事但结论相反——
① 删掉 `m7-render-art.md` / `character-model-3d-plan.md`（主树是压缩保留，且
`docs/README.md`、`docs/api/versioning.md` 仍引用）；② 把 `avatars3dFromSearch`
写回 `protagonistAvatar3dFromSearch`（主树 `f528f42` 已改名）。
下次动 codex 先 `git merge --no-ff main`，然后**丢弃这两处**保留主树版本。
该树另有 ~210 MiB 待清理缓存（2026-11-09 记数，别再当成精确值），删除被自动审批
拒绝，需用户手动执行 `codex/.orca/audits/tidy-2026-11-09/cleanup-generated.ps1 -Apply`
（脚本已实测存在）。两树 `talking.txt` 已于 2026-11-09 同步重写。

**【2026-11-08 3D 主角试水（已收编 `7279e8a`，留作上下文）】**

用户指令「1 3 2」：① 收编 codex 移动轮 ② 3D 模型批量化/图集问题 ③ **先只把主角一个人换成 3D 试水**。
第 ① 步已完成（`890337e`，主树独立复跑 `3625P/121S/72D EXIT 0`）。
第 ③ 步与第 ② 步已合并实现并提交为 `7279e8a`：

| 文件 | 状态 | 作用 |
|---|---|---|
| `client/src/game/render/three/avatar3d.ts` | 新增 ~1040 行 | Gemini SDK 移植版，**真 `SkinnedMesh`**：16 骨骼 / 1 mesh / 1 图集 |
| `client/src/game/render/three/__tests__/avatar3d.test.ts` | 新增 14 条 | mesh 数、图集共享、NPC 名字映射、骨骼刚性权重、尺寸、落地、朝向、相位、flipY、顶点色、tint、光照隔离、**无描边**、释放 |
| `three-actors.ts` | +~80 | `ActorLayerOptions.avatars3d` 开关 + 建图集 + 每帧驱动 |
| `three-world.ts` | +12 | 按 URL 建灯光、随 `releaseWorld` 释放 |
| `presentation.ts` | +7 | `avatars3dFromSearch()` |
| `__tests__/three-actors.test.ts` | +3 条 | 开关关闭全 2D；开启后标签锚点仍在；遮挡时标签跟着隐藏 |

**开关**（历史记录，已被 `c8d6c30` 取代）：当时 `?avatar3d=1` 打开 3D、默认 2D；
**2026-11-09 起默认 3D，`?avatar3d=0` 回滚**。当日只换主角，`2ac5ed2` 起覆盖全部人形。

**形态换掉了（这就是第 ② 步的答案）**。Gemini SDK 原样是 21 个 `Group` + 23 次 `addPart`
⇒ **每角色 46 个 mesh**（本体 + 描边各一份），50 人约 **2300 draw call**，且每个角色各自
`document.createElement('canvas')` 生成 64×64 贴图（spec 声称的 512×512 共享图集**根本没实现**）。
改为：

1. **真 `SkinnedMesh`**：16 根 `Bone`（hips / spine / head / 两臂两段 / 两腿两段 / 四个配件槽），
   所有零件几何按骨骼 bind 矩阵烘进**一份** `BufferGeometry`，`skinWeight` 全 1（刚性蒙皮）。
   ⇒ **每角色 1 个 draw call**，51 人约 **51 次**（2D 路径约 50 次，同一量级）。
2. **共享图集**：19 个预设（`chenmo` + `villager` + 17 个 GOD 名）打进一张 **512×256**
   `DataTexture`，8 列 × 4 行 × 64px。每个角色只换 UV，不换材质/贴图。
3. **纯色件走顶点色**：发髻、腰带、药篓、锄柄原本各需一个材质，现在采样图集里的白块 ×
   顶点色，一份 `MeshLambertMaterial` 全覆盖。`setTint` 因此**回归 `color.setHex`**——
   顶点色承载基色，材质色是纯乘数，白 = 不变。
4. **配件建时烘死**（发髻、背篓、药锄不参与动画），不再每帧挂/摘。

**踩到的两个坑**：
1. **`DataTexture` 默认 `flipY = false`，`CanvasTexture` 默认 `true`**。我的 UV 按 canvas
   约定（`1 - py/H`）算，不设 `flipY = true` 会**整张图上下颠倒**（真机实测：头长在腿上、
   药篓花纹贴到躯干）。**本次最坑的一条**，已有测试钉住。
2. **SDK 的预设键是 `god_villager_01..17`，游戏里的 sprite 键是 `GOD_SPRITE_POOL` 里的名字**。
   不建映射的话每个 NPC 都会**静默回退到主角配色**。已导出同序的 `GOD_SPRITE_POOL` 副本，
   并加测试断言 17 个 tile 互不相同。

**3D 描边：主动不提供（重要，别当缺口）**。2D 路径的「穿墙剪影」用同位置 Sprite +
`GreaterDepth`：那张 sprite 是**平面**，深度处处相等，只在真被挡住时显色。3D 网格自身
有前后深度差，同样的比较会让被身体挡住的胳膊透出来——**真机上就是整个人套了个黄罩子**。
改成外扩会在零件交界处露黄边；模板缓冲版本依赖严格两遍渲染顺序，判为脆弱。
**宁可没有，也不留一个错的视觉**，理由写在 `avatar3d.ts` 模块头里，并有测试断言
`'setXray' in avatar === false`。要做对属于独立一轮。

**光照**：three 场景**原本一盏灯都没有**（`three-terrain.ts:205` 明确写了亮度烘在顶点色里）。
3D 角色用 `MeshLambertMaterial` 必须有灯，故新增 `createAvatarLighting()` 一组
`HemisphereLight(2.2) + DirectionalLight(2.0)`；地形是 `MeshBasicMaterial`，**完全不受影响**。

**动画口径**：相位不自己累计 delta，由 `phaseFromAnimClock(motion.animClock)` 从回放缓冲的
**实际显示距离**换算（每格 250ms × 0.6s/格）。3D 与 2D 同源，不另起计时。

**真机证据（2026-11-08 终态，隔离空目录后端 + 打包 Chromium）**：
- `?avatar3d=1` 页面运行 **0 错误 / 0 警告**；**无黄罩子**，黑发、五官、米色袍、蓝紫护腕、
  红腰带、深棕靴、背篓、右手药锄全部正确；走路帧腿部姿态明显摆动。
- 屏幕上偶尔出现的**白色线框盒不是模型问题**，是鼠标悬停的格子光标
  （`three-voxel-cues.ts` 的 `EdgesGeometry`），移开鼠标即消失。
- 其他 NPC 全部仍是 2D 图集，未受影响。
- 隔离后端 `world.db` 落在 `_scratch_avatar3d/` 空目录，**未触碰真实库**。
- 关闭时控制台的 `ERR_CONNECTION_REFUSED` 是**停掉后端/vite 之后**的重连失败，与代码无关。

**门禁（终态全部真跑，EXIT 0）**：pytest `3625P/121S/72D`（427.79s）、vitest `702P/82F`、
typecheck、lint、prettier、gen:protocol:check、ruff、ruff format、pyright（0 errors）。

**下一步（2026-11-09 已派 codex 树，已收编 `2ac5ed2`）**：**3D 铺开到全部 NPC**。用户明确把「3D 主角
实机手感验收」**搁置**，不阻塞。派单要点：

- 形态**不许再改**（1 SkinnedMesh / 共享图集 / 顶点色）——那是 `7279e8a` 刚钉死的结论。
- 映射两处：服务端 `sprite` 是 `"protagonist"`（**不是** `chenmo`），需映射到 `chenmo`；
  `god_villager_*` → 同名预设；`fauna_*` **保持 2D**。
- **最大静默失败面**：`presetFor` 对未知 id 静默回落到 chenmo ⇒ 名字错配不报错，
  只表现为「全城一个色」。派单要求显式处理未识别值并加测试钉住。
- 预算 ≤ 2× 当前 draw call（51 人 × 1 mesh ≈ 51 次）。
- 验收必须真机：≥5 个不同 NPC 配色互不相同、动物仍 2D、关闭开关行为零变化。

**主树代同步**：codex 树原先没有 `avatar3d.ts`（停在 `1dae9f1`），已由主树
`git merge --no-ff main` 同步到 **`d558800`**（无冲突），否则派单无从下手。

### 2026-11-09 NPC 3D 铺开：已收编 `2ac5ed2`（codex `968b3e4` 摘入）

**改动只两个文件**：`three-actors.ts`（+34）与其测试（+240）。`avatar3d.ts`、
`sim/`、`shared/`、依赖锁**一字未动**，协议仍 **1.16**。

**映射**（`avatarPresetForSprite`）：`fauna_*` → `null`（留 billboard）；
`protagonist` → `chenmo`；其余命中 `AVATAR_PRESET_IDS` 就用自身；**未识别 → 显式
`villager`**（不靠 `presetFor` 的静默回落）。

**一个必须记住的实现细节**：`avatarPreset` 与 billboard 的 `key` **分开跟踪**。
两者混用会出 bug——两张缺图的表都回落到 `villager` 纹理键，但预设不同，
若不单独比 `avatarPreset` 就会留着上一个 NPC 的旧皮不换。

**主树独立真机复验（隔离空库 + 打包 Chromium）**：
- 51 个 avatar root / 51 个 SkinnedMesh / **1 张共享图集** / 用上 **18 种预设**
  （chenmo + 17 个 GOD 名，`villager` 未被真实 NPC 命中，符合后端哈希分布）。
- 关掉 `?avatar3d` 后全员回到 billboard，与 `7279e8a` 一致。
- 0 页面 / 0 控制台错误。

**踩坑记录（这次差点误判）**：夜色下把地形藏起来之前，NPC 在截图里像一堆巨大黑块。
实测几何（0.95×1.96×0.66）、骨骼世界坐标、UV 范围、顶点色、贴图（512×256 /
srgb / flipY=true）、蒙皮半径全部正常；把 `InstancedMesh` 地形临时 `visible=false`
后两个 NPC 立刻显色且互不相同 ⇒ **黑块是夜色下的建筑遮挡，不是模型问题**。
教训：**真机判色前先隔离地形**，否则夜色 + 深色建筑会把结论带偏。

**门禁（主树终态真跑）**：pytest `3625P/121S/72D`（470.34s）· vitest `715P/82F` ·
typecheck / lint / prettier / gen:protocol:check / ruff / ruff format / pyright 全 EXIT 0。

**本轮清理**：临时调试钩子 `window.__probe`（曾加在 `three-world.ts`）与探针测试
已删除，工作区干净。

**更早的状态（已收编，留作上下文）**：

## 0b. codex 移动轮派单与收编（2026-11-08 已完成）

- **2026-11-08 已派 codex 树四项**（用户裁定「这些问题和跳跃都交给 codex 树」）：
  ① 人物朝向行号写反（真 bug）② 走/跑分离 ③ 走环与位移速度脱钩
  ④ **跳跃——用户明确选「可跳上 h2/h3 高块」**（不是纯表现跳跃）。
  另加 ⑤ **2D billboard → 3D 模型只出方案、不动代码**。
  派单全文在 codex 树 `.orca/talking.txt` 第二节；主树等回执后独立复跑 + 真机复验 + 收编。
- **派单前已解决一个阻塞**：codex 树缺 `a74aa1d`（回放缓冲）、`e49b7c1`（three 默认）
  等主树专有提交，直接派单会基于旧前端实现、收编必冲突且可能回退回放缓冲。
  已由主树代为 `--no-ff` 同步（codex `51d1e2f`）：`git merge-tree` 预演确认**代码零冲突**，
  只有 3 个文档冲突，按权威归属解决（`memory.md` §0–6 取主树、§7 保留本树原字节；
  两份 README 取主树）。同步后 `actors.ts`/`motion-buffer.ts`/`three-actors.ts`/
  `WorldScene.ts` 与 main **逐字节一致**。
- **人物朝向 bug（主树 2026-11-08 逐像素独立复测，非采信旧卡）**：
  `actors.ts::facingRow` 用**一张表**覆盖三套图集，而三套行序实测不同 ——
  `chenmo.png`（272×256 = **17 列 × 8 行** @16×32）与 `villager.png`（4×4 @16×32）
  是 **下/右/上/左**（0/1/2/3）；`god_villager_*.png` 是 下/上/右/左。
  表里写的是后者 ⇒ 主角和村民**按 W 时侧身走**（用右侧脸背对镜头）。
  测法：逐行 ASCII 渲染 + 眼睛数量/位置（正脸 2 眼对称、侧脸单眼偏一侧、背面 0 眼）
  + 头部肤色占比（背面 ≈ 0.07）+ 帧与自身水平镜像差异度。
  **注意**：旧的「皮肤重心 − 头发重心」判据对 villager/god **区分度不够**（头发左右对称），
  主树第一版探针就因此误判，别再用它。
  修法：`SheetGeometry` 增 `rows` 映射，`facingRow(sheet, facing)`，改两个调用点
  （2026-11-09 实测位置：`three-actors.ts:307`、`WorldScene.ts:1182`）+
  `actors.test.ts:67-71` 那 4 条断言（现在钉的是**正确**行序）；顺带订正
  `actors.ts:28-30` 的「16 行 @16px」注释。
- **2026-11-08 行走不连贯已修并收编**（主树 `3b58669`，摘 codex `1bfe956`，2 文件）。
  根因：`three-input.ts::drive()` 只试斜向格，失败就 `stop()` 并把「被挡意图」缓存进
  `keyIntent`；而默认 `azimuth=225` 下 **WASD 四键全映射成对角**，所以一个被挡的斜向
  就等于彻底卡住，旁边的正交格明明可走却不试。修法：斜向 → 横向 → 纵向依次用同一个
  `ports.step` 试，三个都不通才停/报错；墙角语义仍由 `canStep` 保证。
  **主树独立真机复验**（不是采信 codex 读数）：出生点 (100,51) 按住 S 5.2s 走
  **10 格**（100,51→90,49），按住 W 5.2s 滑 (101,52)→(101,53) 后在三个候选全堵处正确停下；
  0 page/console 错误，私库隔离。证据 `.orca/audits/walk-verify-2026-11-08/`（ignored）。
  主树门禁：vitest **573P/78F** · typecheck/lint/prettier 全 EXIT 0。
- **2026-11-07 追加：测试探针打开真实 `world.db` 的根因已定位并修复**。
  `test_m6_death_path_data.py` 的探针 `finally` 把锚点单例指回相对路径
  `sqlite:///world.db`，而 `os.chdir` 已回仓根 ⇒ 全量门禁每跑一次就在真档上
  `create_all`（幂等，只动 mtime；缺表就会真写）。审计钩子取证 + 新钉子
  `test_probe_never_opens_the_repository_world_db`。详见 §3「测试收尾『还原成默认值』
  会把真档打开」。三树 `world.db` 数据一条未变。

- **移动连贯性修复已提交**（`a74aa1d`，用户 2026-11-08 默认切 three 后一并落地）。
  回放缓冲 `render/motion-buffer.ts`，两条渲染路径共用。证据
  `.orca/audits/motion-smoothness-2026-11-07/REPORT.md`。
- **本轮做了什么**：用户报「动作一顿一顿不连贯」。根因是**插值窗（200ms）比服务端节拍
  （250ms/格）短 50ms 且每来快照从当前视觉位置重起** ⇒ 每格末尾空等 + 剩余帧超速 +
  走环逐格重置（第 2 帧永远看不到）。旧实现实测 1x 冻结 19.9%、16x 冻结 98%。
  改为**回放缓冲**（`render/motion-buffer.ts`）：存 `(到达时刻, 权威位置)` 样本，
  画「落后一个延迟」的时刻，在**两个真实样本之间按时刻插值**。
  **Phaser 路径（默认渲染器）有完全相同的缺陷，一并修复**。
- **三种方案都实测过，前两种被数据否掉**：① 按样本序号插值 ⇒ 每来样本进度归零，
  4x 下 47 帧冻结；② 纯时间轴回放 ⇒ 延迟随倍速跳变，16x→1x 人物**倒退 2.06 格**
  （加大保留窗口反而倒退 12.06 格）。最终方案是时间轴回放 + **延迟平滑爬升**
  （`rampDelay`，`RAMP_RATE=0.6` < 实时 ⇒ 绘制时刻单调前进）。落定后三档均 **0 冻结**、
  速率达标、切速 `maxBackJump = 0.00`。
- **子代理 review（19 分钟 76k tokens，0C/1H/2M/3L）**：HIGH「停顿后起步瞬跳」是真的
  （旧实现把 10 秒间隔压进一帧），已修（到达前补锚点样本）并加回归测试；
  LOW「传送按跳跃方向转身」「Phaser 传送阈值 2.7 格 vs three 3.0 格」也已修。
  **明确遗留**：Phaser 路径的高度变化（脚下建房/塌房）仍会被判成「移动」而播放走环
  ——修它要把高度从位置拆成独立通道，属下一轮。
- **第二十四轮已收编**（`--no-ff` 合并 `cb820bf`，codex 侧
  `d03f806`..`5db4005`，零冲突）。three.js 自由视角世界已实现；
  **2026-11-07 用户验收通过并裁定切为默认**——不带参数即进 three，
  `?terrain=phaser` 退回 Phaser 等距路径（回滚开关）。
- **第二十四轮主树独立复跑（不采信 codex 自测）**：pytest **3544P/121S/72D**
  （462.12s，EXIT 0）· vitest **537P/75F** · ruff/format/pyright **0/0/0** ·
  tsc/eslint/prettier/gen:protocol 全 EXIT 0 · 两资产 `--check` 逐字节一致 ·
  `check_implementation_status.py` EXIT 0（零缺口）。
- **主树额外独立验证**：把 `visibility.ts::lineBlocked` 与真实
  `sim/perception/propagation.py::line_blocked_grid` 做 **2400 例随机差分**
  （Python 生成 oracle，seed 20261106）：**0 不匹配**（1566 阻断 / 834 通视）。
  证据 `.orca/audits/round24-verify-2026-11-06/`（本地 ignored）。
- **合并后复查（必做）**：清理轮 `f77fa81` 的 `pyproject.toml`/`uv.lock`/`.env.example`/
  `.gitignore` 与合并前逐字节相同（codex 从 `3912f7c` 分叉，未回退清理）；
  `sim/`/`shared/`/协议 1.15/`client/package*.json`/`DESIGN.md` 均零改动；
  `voxel-picking.ts`/`cell-appearance.ts`/`tile-color.ts` 零改动。
- **第二十四轮做了什么**：A 透视跟随/可旋转相机 + 天空/地平线雾（`d03f806`）·
  B three billboard 人物 + 动画/朝向/同格偏移/名牌/气泡 + 天气音频（`03ab898`）·
  C 独立移动(平面反投影)与编辑(实例 raycast)拾取 + 真鼠标键盘手势（`8fa3f56`）·
  D 整列选中/材料高度预览/服务端进度/移动目标（`e45a4ed`）·
  E 客户端视线遮挡（Python Bresenham 逐行移植、半径 12 由源文件钉死）（`5eacfbc`）·
  审查修复 lostpointercapture + 逐事件世界/连接/焦点守卫（`b7ac220`）。
- **第二十四轮遗留（别当已关闭）**：DPR 只在创建时读取（跨屏/缩放不刷新，Minor）·
  构建包 2309kB/gzip 572kB 警告 · 房屋仍 h2 实心块、无动态光照投影/水波/塌落动画 ·
  ~~服务端仍不发 `perception` 帧~~ → **2026-11-07 订正：这是已登记的设计决定**
  （`docs/api/ws-protocol.md:76`，M5-K6 / 裁 28-C GAP-F），不是缺口，别再提案补出站；
  听嗅文案按设计只进 NPC prompt，玩家侧没有它们是对的 ·
  相机默认 yaw225 且近墙会抬高（临墙构图可能高于请求 12°）· 提示置顶可能覆盖前景。
- **下一步**：① ~~提交或回退连贯性修复~~ → 已提交（`a74aa1d`）；
  ~~② 切 three 默认~~ → 已切（`e49b7c1`，用户验收通过）；
  ~~③ 行走单步卡住~~ → 已修（`3b58669`）；
  ~~④ 人物朝向 bug 待修~~ → **已派 codex（2026-11-08），连同走跑/走环/跳跃**；
  ⑤ 用户亲验剩余项（见 `talking.txt` 待人工验收表）；⑥ 相机近墙抬高到约 70° 的构图问题
  已记录待用户裁定；⑦ P2 玩家念头回执 `ws.py:1400` 硬编码文案
  （旧记 `:1295` 已漂移，2026-11-09 实测订正）。
- **跳跃的硬前提（2026-11-08 派单时写；已由 `890337e` 收编解决，留作判据）**：
  当时 `EntityState` 没有 height、协议也没有，可走判据是布尔 `collision`。
  **落地形态（2026-11-09 实测复核）**：
  - `EntityState`（`sim/core/world.py:52-63`）只增**可选** `gait` / `jump`
    （`None` 不序列化），**没有存 height 标量**；站立高度由 `SurfaceMap`
    事件投影推导（`sim/world/surface.py:41` 仍是 `walkable and height == 1`）。
  - 协议 `Actor`/`ActorDelta` 增可选 `elevation` / `gait` / `jump`（`shared/protocol.ts:227-246`）。
  - `state_hash`（`world.py:87-93`）已改成对 `model_dump` 全量哈希，不再是
    `{world_seed,tick,entities}` 白名单——新增可选字段靠 `None` 省略保旧哈希。
  - `terrain_class.py:244-253` 的 `walkable ⇒ HEIGHT_EARTH` **仍是单向不变量**，
    跳跃没有靠把它改成双向来实现（双向 ⇒ earth 无来源 ⇒ 只挖不放）。**别回退这两点**。
- **2026-11-06 清理轮（`f77fa81`）**：删掉三个零引用依赖（`pydantic-settings`/`tenacity`/
  `hypothesis`，DESIGN §4 同步改写）、`.opencode/`（61M）、`agent-registry.md` 里
  四个已不存在的工作树、`.env.example` 两个死键、两份 331M 备份库、各类缓存/构建产物。
  1.5G → 719M。清理后门禁实测：pytest **3544P/121S/72D** · vitest **478P/0F** ·
  ruff/format/pyright 全 0 · tsc/eslint/prettier/gen:protocol/lock/两资产 全 EXIT 0。
- **第二十三轮已收编**（上一轮，`5e4e20b`）：主树部分 `c7b7d1d`/`c3e2a2b`/`c7f5e31`，
  codex 部分 `424ec34`/`1738e09`，`--no-ff` 合并（4 处冲突全解）。
- **收编后主树独立复跑（不采信 codex 自测）**：pytest **3544P / 121S / 72D**
  （497.88s，EXIT 0）· ruff 410 files + format 全过 · pyright **0/0/0** ·
  client typecheck/eslint/prettier/gen:protocol 全 EXIT 0 · vitest **428P / 57F** ·
  两资产 `--check` 逐字节一致 · `uv lock --check` 一致 · 协议 **1.15**（双落点同值）。
  警告 556 条全为既存（2 starlette/anyio 弃用 + 1 alembic path_separator + 8 旧迁移子进程
  UTF-8 线程警告 + Pydantic 弃用），**无一条来自本轮改动**。
- **协议 1.15 落点核对**：`sim/api/ws.py::_PROTOCOL_VERSION` 与
  `client/src/net/ws.ts::PROTOCOL_VERSION` 同值；`FastAPI(version=)` / `shared/openapi.json` /
  `shared/protocol.ts` 三处一致，`gen:protocol:check` 通过。
- **合并后复查（必做）**：`ensure_schema`（`main.py:250` 调用点）仍在、`ChatLedger.remember`
  的 `speaker` 必填与 `_heard_mems` 转述归因仍在、`narration_cache.py` 仍在、
  `onMonologueHistory` 整组替换仍在、`voxel-picking.ts` **零改动**（拾取基线不变）。
- **本轮做了什么**（用户验收驱动，原话：世界空空如也 / npc 只会聚集 / llm 除寻路无法执行 /
  石头等材料不能用 / 主角老说有奇怪气味）：
  - **A 等距烘焙**（`9b83d79`..`c3e2a2b`）：真实 tileset 像素烘进地面画布（`tile-projection.ts`
    新增）；高格顶面注册 `tile-<gid>` 帧。验收截图三档均见桃花林/草地/石阶/水面。
  - **B1 气味**（`3e915b5`/`4bea378`）：`SMELL_SOURCE_STRENGTH=0.04` + 新增独立旋钮
    `smell_floor=0.08`（与 `hearing_floor` 解耦）；`narration_cache.py` 跨帧抑制重复气味行。
    实测：聚集 50 人 50/50 可闻，稀疏 0/10，独行 0.0628 不可闻。
  - **B4 主体**（`6a008fa`）：prompt 里 `96×96` → **`140×100`**；集合差测试钉死
    `IntentAction - M1_SUPPORTED_ACTIONS == {demolish, use}`。`take`/`give` 按用户裁定单列。
  - **两处实机缺陷**（都不是计划里的）：① 心声/街谈巷议面板每次重连整屏重复——
    `full_snapshot.monologue_history` 被逐条追加，改为 `onMonologueHistory` +
    `replaceMonologues/replaceChatter` 整组替换（`d95696e`）；② 脏矩形裁剪只有 4×4 图的
    等价测试（脏矩形≈整幅=没测），补 16×16 图回归钉（`c3e2a2b`）。
  - **门禁**：pytest **3503P/121S** · ruff/format 全过 · pyright **0/0/0** ·
    client typecheck/eslint/prettier EXIT 0 · vitest **423P/56F** · 两资产 byte-identical ·
    协议 **1.14 未动** · 拾取与基线逐项相同（448/448 · 3947/3947 · 7141/7373）。
- **🚨 本轮事故（已处置）**：`sim/api/main.py:76` 硬编码 `WORLD_DB_PATH = Path("world.db")`，
  **不读同名环境变量**。用 `WORLD_DB_PATH=<临时路径> uv run uvicorn` 起验收后端，实际写的是
  真实档 48 分钟（14:03–14:51，+1,274,454 events、tick 66000→309910、快照 2→12）。
  已按 `seq 341740` 边界回滚：events **341,740** / snapshots 1 / knowledge 62 /
  relationships 151（按事件重放重建，值与存库 83/83 零误差）/ npc_memories 384；
  `integrity_check: ok`，`restore_world` 实测恢复 **tick 66000 / 54 实体**。
  备份保留：`world.db.bak-20261105-203825`（回滚前）、`world.db.polluted-20261105-150143`（取证）。
  **下次起验收后端：`cd` 进空目录，或 monkeypatch `main.WORLD_DB_PATH`。**
- **第二十二轮（codex，土坎拾取）已收编**：`pickVoxel` 增可选第六参 `isBank(x,y)`；
  `WorldScene` 传实时 `collision===0`。只有 h=1 土坎的**实际三道斜纹像素**
  （`|x-2y|<=5 && |3x+4y|<=5`，offset -7/0/7）与高块同池，按 `depthKey+.5` 与绘制同序；
  烘焙顶面空白/侧面/普通地面保留低池。**不能全局深度优先**（普通低地面会抢房屋侧面），
  也**不能整块顶面提升**（空白处实际显示身后房屋侧面）。旧五参 `pickVoxel` 保持旧行为。
  - 实测（同张未改静态图，主树独立复跑 `measure.cjs` 得到同读数）：土坎自命中
    149/448 → **448/448**；高块 7141/7373 不变；可走 3947/3947 不变；`pickGround` 逐字未动。
  - 门禁：typecheck/lint/prettier/gen:protocol 全 EXIT 0；vitest 360P/49F（codex 树）；
    主树合并后 399P/53F。协议 1.14。后端未改。
- **主树转述归因修复（`74fe95c`，2026-11-04）**：`ChatLedger.remember` 增必填 `speaker`，
  记忆条目变 `(tick, text, speaker)`；转述取最新一条**不是自己说的**记忆（`_heard_mems`），
  无外人之言则不转述；署记忆里的原说话人。实机双口径 0 自指（浏览器 39 条、事件表 136 条）。
  第一版只补 speaker 时实机仍 37/62 自指——**单测抓不到，实机才抓到**。

## 0a. 上一轮（第二十一～二十三轮，已收编）

> 正文已删除，考古走 `git log`。只留**收编哈希**与**仍在生效的结论**。

| 轮次 | 内容 | 收编 |
|---|---|---|
| 第二十三轮 | 世界可辨认性 A/B 全部落地（等距烘焙 + 气味 + prompt 尺寸订正）；实机修掉心声面板重连整屏重复 | `5e4e20b` |
| 第二十二轮 | 土坎拾取：`pickVoxel` 增可选 `isBank(x,y)`，土坎自命中 149/448 → **448/448** | `5e4e20b` |
| 第二十一轮 | 读档 D1/D2：成功读档按连接 `ControlState` 重投影 `clock`；`session_state` 改按连接定向投递 | `1d55179` |

**仍在生效的结论**：

- **读档成功路径必须恢复 `clock.speed`**。失败路径故意 fail-closed 冻结世界（别为凑绿取消），
  但成功路径只置回 `world_source_ready` 而不恢复 `clock.speed`，会让世界永久冻结——
  而每连接 `ControlState.paused` 是 False，「继续」按钮回 `bad_action`。既有测试只锁
  「失败要冻」，缺「成功要解冻」这一半。
- **`session_state` 必须按连接定向投递**（`manager.send_to_control`），不能从全局
  `clock.speed == 0` 推断 `paused`——两者会分裂。
- **读档面板的文案只认两种 code**：`load_failed` / `bad_anchor` 可直显；`bad_channel`
  等工程措辞走戏内兜底，否则英文原文漏进玩家面板。
- **大库读档要轮询等 `full_snapshot`**（重放 20s+）；固定 `waitForTimeout` 会假红
  （实测踩到 5 条假失败）。
- **`protected` 只表达「不许删这个档」，与能否载入无关**（`anchors-api.md` §1.4）。

## 1. 门禁（**2026-11-03 第二十轮收编后主树独立实测**；第十六轮复核见 §1e）

> **第十六轮在 codex 树实测（独立复跑，非采信自测）**：
> pytest `-m "not bench"` **3074 passed / 0 failed / 121 skipped**（394.51s）·
> ruff/format EXIT 0 · pyright 0E/0W · 协议仍 1.14 · client/shared/uv.lock/DESIGN 零 diff。
> bench **2F 属既有基线**：主树**无本轮代码**同样 2F（`test_perception_sound_50npc`
> 与 `test_retrieval_full_scan_degraded_sentinel`），且两条单跑均通过 ⇒ 抖动，非回归。
> 回执称「sound baseline passes」是错的。

| 项 | 本批实测（2026-11-03，读档缺陷修复后） |
|---|---|
| pytest `-m "not bench"` | **3460 passed** / 0 failed / 121 skipped（469.33s，三次独立复跑同读数） |
| ruff check / format | clean（**403 files**） |
| pyright | 0 errors, 0 warnings, 0 infos |
| client gen:protocol:check / typecheck / lint / prettier | EXIT 0 |
| client vitest | **360 passed / 48 files** |
| build_height_map --check | 逐字节一致 |
| build_block_atlas --check | 逐字节一致 |
| `uv lock --check` | 一致 |
| 协议 | **1.14**（双落点同值） |

> **读档修复新增 3 条**：3460 − 3457 = **3** = `test_m5_fork_orchestration.py`
> `test_protected_tail_anchor_is_locatable` 1 + `test_historical_world_load.py`
> `single_save` 夹具下 `test_load_the_only_anchor_after_saving_it` /
> `test_reloading_a_previously_loaded_anchor` 2。vitest 360 − 353 = **7** =
> `runtime-impulse.test.ts` 5（loadError 路由／发新请求清旧文案／code 白名单／
> 空串原样透传／成功后清文案）+ `SaveLoadPanel.test.tsx` 2（提示框/空串不渲染）。
> pytest 新增数不变（e2e 的 `ref`/`code` 断言是补钉，不是新用例）。

> **第二十轮收编 `66637b7` 后读数（历史）**：pytest 3457P/0F/121S（434.12s）·
> ruff/format 403 files · pyright 0/0 · vitest 353/48。

> **本批新增数对得上**：**3457 − 3350 = 107**，与 codex 回执的独立审查读数
> **B 50P + A 57P** 精确吻合（B = 模块 47P + 生产冷 child/故障态 3P；
> A = 模块 51P + 真实日切 live 6P）。
> ruff 397 → **403 files**（+2 新源文件 `health_evolve.py`/`seeding.py`，其余为本轮测试文件）。
> 关键回归文件单跑 **98P**；fork 相关 39P/1S。vitest 仍 **353/48**（本轮零前端改动）。

> **上一批（主树 1A/2A/4A/roles，2026-11-02）新增 70**：3350 − 3280 = **70** =
> `test_villager_identity_consistency.py` **6** + `test_monologue_history_fork_reset.py` **4**
> + `test_willingness_action_context.py` **53** + `test_roles.py` **+5**（2→7）
> + `test_historical_world_load.py` 端到端 **1** 条 × `saved_world` 两个 `params` = **2**。

> **收编后门禁（上一轮实测，2026-11-02）**：pytest **3280 passed** / 0 failed / 121 skipped
> （419.73s）· ruff/format **394 files** · pyright 0/0 · client 四件 EXIT 0 ·
> vitest **353 passed / 48 files** · 两资产逐字节一致 · `uv lock --check` 一致 · 协议 1.14。

> **收编后首跑 1 失败，已修**：`test_m5_fork_replay.py::TestR2SeamConsistency::test_A_health_seam_equal`
> —— 该测试是主树 `02e3b10` 的钉子，codex 分支**不含那笔提交**，所以 codex 不知道
> 这个文件里还有一个手搓 `_minimal_package` 调用点；合并后第十八轮新加的 fail-closed
> 判据（`package.profile_rows is None` ⇒ `ForkError`）把它撞了。修法：夹具增
> `profile_rows` 形参 + `_profile_rows_at()` 从库导全列（该夹具的世界**有** chenmo，
> 不能像另两个空名册夹具那样填 `()`）。修后该文件 20P，全套 3280P。
> **这正是「收编必独立复跑」的活例**：codex 自测 3253P 全绿，主树一合就红。

> 第十五轮动的是 `sim/world/offline.py`（新）+ `sim/core/persistence/` + `sim/api/main.py`
> + 整个 `client/src/game/audio/`，故两侧全套必跑。
> 3069 − 3061 = 8 条 = 定线新增（5 条 soak 契约 + 3 条 T5 阈值）。
> 3061 − codex 自测 3056 = 5 条 = 主树第十四轮的 `test_schema_self_heal.py`（codex 分支不含那笔提交）。
> **第十七轮：3100 − 3069 = 31 条**（`test_species_knowledge.py` 6 + `test_m3_social_wiring.py` 25）；
> vitest 353 − 337 = **16 条**（`name-labels.test.ts`）。两边新增数与主树复跑读数逐条对上。
> **第十八+十九轮：3280 − 3114 = 166 条**（codex 自测 3253 与本树 3280 的 27 差 =
> 主树第十九轮 A/D 的 13 条 + 主树 02e3b10 的健康游标钉子等主树专有提交）。
> vitest 仍 **353/48**（两轮未动前端）。

## 1d. 收编复核纪律的一条实证（2026-11-01）

**codex 的交付回执会说谎，而且是无意的。** 第十五轮回执写「tsc、eslint、prettier 全过」，
主树复跑 `npm run typecheck` 实为 **EXIT 2**：

```
src/game/audio/__tests__/world-audio.test.ts(48,18): error TS2345:
  Argument of type '{ unlock: Mock<Procedure | Constructable>; ... }'
  is not assignable to parameter of type 'AudioBackend'.
```

修法按仓库既有约定（`client/src/game/__tests__/runtime-map.test.ts:14,18` 的
`vi.fn<签名>()`）给每个 mock 显式签名 + `import type { EffectId }`。复跑 EXIT 0。

**教训**：`npm run typecheck 2>&1 | tail -3; echo $?` 报的是 **tail 的退出码**，
不是 npm 的。必须 `cmd > log 2>&1; echo "EXIT:$?"`。这条对任何管道都一样。

## 1e. 第十六轮复核：测试全绿但生产不通（2026-11-01）

**这是 §1d 那条教训的升级版**：不是回执说谎，是**测试根本没跑生产路径**。

codex 交付 `820c653`（+886 行，18 条新测试），门禁全绿，但：

```
真实 lifespan 600 tick：events 0→3775，relationships 0→25 ✅，knowledge 0→0 ❌
主树真实库副本：        events 187857→191674，relationships 0→37 ✅，knowledge 0→0 ❌
```

**根因一条**：`sim/perception/senses.py:270-274` 把 `Observation.subject` 设成**中文显示名**
（同一个 `label` 既作叙事文本又作 subject），而 `witnesses_of_entity_emerge`
（`evidence.py:159`）拿 `rtoken_of(subject)` 去比 ⇒ **永不匹配** ⇒ `witnesses` 恒空
⇒ `npc.knowledge_learned` 零产生 ⇒ `knowledge` 表恒 0。`told` 路以 knowledge 行为源，
同根因被堵死。`frame.py` 里 `subject: str  # rtoken` 的旧注释是**过时的**
（现已改为「戏内词面，不是 rtoken」）。

**为什么 18 条测试没抓到**：全部手造 `PerceptionFrame`（`subject=rtoken_of(...)`），
**没有一条跑真实 `lifespan`**。测试用的帧形态与生产形态不同 ⇒ 测的是另一个世界。

**教训（写进纪律）**：验收面凡写「实况跑起来后 X 表有行」，
就**必须有一条真跑 `lifespan` 的集成测试**；纯函数单测证明不了接线通。

**bench 2F 的真相**：主树**无本轮代码**同样 2F（`test_perception_sound_50npc` /
`test_retrieval_full_scan_degraded_sentinel`），两条单跑均通过 ⇒ 抖动，非回归。
回执里「sound baseline passes」是错的。

**codex 树 `world.db` 是坏的**：有 **83 个 `world.create`**，而 `restore_world`
（`world_restore.py:179`）要求恰好 1 个 ⇒ 该树真实库**无法恢复**。主树库健康
（1 genesis / 187857 events / tick 36001 可恢复）。两树库是不同文件，别互用结论。

**✅ 已修（主树 2026-11-01，TDD 红→绿→重构）**：
- `witnesses_of_entity_emerge` 新增 `display_name_of` 形参，在**戏外边界**用
  entity_id→显示名 反查；`Observation.subject` 语义**未动**（叙事仍说人话）。
- **重名 fail-closed**：显示名不唯一 → 返回 `([], None)`，宁缺勿错；无显示名的
  实体按 rtoken 作词面（`senses` 同一默认分支），不误判歧义。
- 调用点 `main.py:787` 传入 `display_name_of=_display_names`；`frame.py:37` 过时注释已改正
  （现 `frame.py:36-39` 写明「不是 rtoken」）。
- **真跑 `lifespan` 的集成测试**已补（`test_lifespan_witnesses_knowledge_from_real_perception`），
  且**照抄生产执行序**（先 `_run_npc_runtime` 后 `_run_perception`，`tick.py:95-97`）
  ——我第一版写反了，会把当帧帧喂给 `frame.tick < tick` 过滤器而必然全拒。
- 实测（零注入，真实地图）：`witnesses` 9 人 / `knowledge` 落库带 `evidence_seq` / `conf=0.9`。
- 门禁：pytest **3091P/0F/121S**（404.88s）、ruff 0、format 0、pyright 0/0、
  client tsc/lint/prettier 0、vitest 337P、两资产 + protocol + lock + impl 全过。

**⚠️ 同一会话的事故（须记）**：手写探针 `import sim.api.main` 起 `lifespan` 时**绕过
`conftest` 的 `WORLD_DB_PATH` 重定向**，直接写了主树真实 `world.db`：events
187857→929424、max tick 36000→178270（`offline.capped` 补推 86400）、knowledge 0→27、
relationships 0→591。已核：`seq 1..187857` 的 payload/witnesses SHA256 与备份**逐字节一致**；
备份里用户操作事件仅 `tile_changed: 30`，追加段内 `tile_changed/structure_*/npc.death/
player_anchor` **全为 0** ⇒ **未丢用户操作**。但追加段含我伪造的 9 行
`fact="小满: 肩头旧伤"`（attr_id 却挂真实 `health_night_fear`）= 脏数据。
**回滚待用户裁定**（备份是迁移前形态，缺 `npc_health.code`，需 `ensure_schema` 自愈）。
**纪律**：任何起 `lifespan` 的脚本必须自己把 `main.WORLD_DB_PATH` 指到临时库，
或干脆写成 pytest 用例走 `conftest` 夹具。

## 1f. 锚点读档「复制父分支未来态」根因族（2026-11-01，**第十八轮派单依据**）

**一个根因，两处受害。** `fork.py` 的 `kind="anchor"` 分支里，`_BOUNDED_TABLES`
各表靠一串 `if table == ...` 特判；**没被特判的表落到 `_clone_bounded`**——
`INSERT … SELECT … WHERE p.branch_id = :pid`，复制父分支**当前 head 行**，
完全不看锚点游标。锚点之后父分支若继续推进，子分支读档就拿到「未来」。

已特判的表（正确）：`fires:533`、`structures:540`、`npc_health:547`（本轮新加）、
`material_balances:555`、`relationships:562`（跳过，按包写）。
**未特判而受害**：`npc_profiles`（`fork.py:53` 起，26 列宽表）。

**✅ 已修（主树，`02e3b10`，TDD 红→绿）**：`npc_health`。

- RED 实测：锚点 tick=1 处 severity=0.2，父 head（tick=5）处 0.8 ⇒ 子分支拿到 **0.8**。
- 修法 `_clone_health_at_cursor`（`sim/core/persistence/fork.py:797`，调用点 `:559`）：
  按 seq 重放 `npc.health_changed`
  （复用 `_project_health`，折叠规则单一来源）+ 补齐无事件源的创世种子行
  （判据 `created_at_tick <= fork_tick`）。
- **踩到的坑（写进纪律）**：`npc_health` 是**混合表**——创世种子
  （`content/health.py::seed_health`）直接 INSERT、**无事件源**，事件投影只增量改行。
  我第一版只重放事件 ⇒ 丢掉全部种子行，被既有
  `test_m6_death_profiles_contract::test_fork_does_not_clone_dead_health_row` 抓出。
  **别照抄 `structures` 的纯重放写法**。

**✅ 已修（第十八轮 `8b6b702`，主树收编 `bdeeb19`）**：`npc_profiles`，后果比健康表重——**丢整个 NPC**。

主树对照实验（临时内存库，唯一变量 = 锚点后父分支是否推进）：

```
A 锚点 tick=1，tick=5 死亡  → child=[('a',2)]              ← 'd' 凭空消失
B 锚点 tick=1，tick=5 lod 1→2 → child=[('a',2),('d',1)]    ← 'a' 的 lod 是未来值
对照（锚点后不推进）        → child=[('a',1),('d',1)]      ← 正确
```

**生产可触达**：玩家读档 → `main.py:1244 orchestrate_materialized_load_anchor`
→ `sim/core/persistence/fork_orchestration.py`（`kind="anchor"`；模块在
`sim/core/persistence/`，不在 `sim/world/`）。

`npc_profiles` 写入面（已查实，**只有两条事件**）：`NPC_LOD_CHANGE`（改 `lod`+
`updated_at_tick`）、`NPC_DEATH`（**删行**）。其余 24 列无运行时写入路径，只由种子直插。

**顺带发现（第二十轮任务 B，已修，主树收编 `66637b7`）**：
`seed_villagers`（`villagers.py:327`）幂等判据原本是 `select(NpcProfile.id)` **无 branch
过滤**，`_profile_row` **硬编码 `branch_id="main"`**（`villagers.py:284`、`protagonist.py:33`），
`seed_animals`（`animals.py:19`）是同一缺陷的**第三处**（复用 `villagers._profile_row`）。
主树 5 组临时内存库实测（修前）：**(main0,child0)→main50；(main0,child50)→新增0；
(main0,child49)→main1/child49；(main50,child49)→新增0；(main50,child50)→新增0**
⇒ **只补 main，子分支永远补不上**。

**修后（codex `bb0647e`）**：三处播种都按 `(branch_id, id)` 判存在，`_profile_row`
的 `branch_id` 由调用方传入（`villagers._profile_row(p, *, branch_id="main")`、
`protagonist._profile_row(*, branch_id="main")` 仍零参可调）。新增
`sim/content/seeding.py::read_branch_death_ids`：`main.py` 用**既有 store** 一次读取
**有界祖先死亡前缀**（`read_branch_history` 沿 `forked_from_branch` 拼），同一个
`frozenset` 传给三个播种函数；独立调用（`dead_ids=None`）时用
`SqlEventStore(session_factory)` 只读 wrapper 自算，不另开 SQL 驱动。
**祖先分叉游标之后的死亡不纳入**（父分支未来死的人不算子分支的死者）；缺祖先 /
缺 cutoff / 循环 / 孤儿事件一律拒绝盲补。
**故障态不猜 main**：`current_branch is None` 且**库里已有 Branch 行** ⇒ 判为故障、
不播种（只有真正空库才当创世写 `"main"`）。
**修后实测**（codex，主树已复跑同组）：目标分支语义下 5 组全对；
十个目标分支组合第二次调用均 0（幂等）；本线与祖先死者三类都不补。

> ⚠️ **主树 2026-11-03 收编实测**：真实冷 child 场景 `main 54` 不变、`child 49` 补
> 3 个缺失活人后 `52`，两名已死者仍缺行。**这是正确行为**（死者不复活）。

## 1b. 已关闭但代码不支撑的承诺（主树 2026-10-31 审计，**新对话先读**）

六里程碑 2026-10-05 宣告收官（`abbe765`），下列五条实测当时是空的。**这些不是 bug，
是「宣告了但没做」**，任何新方向裁定前必须知道。**2026-11-01 第十五轮后：四条已有实现
或取证，只剩残余项**（音效主观听感、T5/soak 阈值定线、真实库迁移仍归用户）。

| 缺口 | 实测证据 |
|---|---|
| **音效**（**已验收**） | ~~全仓 0 个 `.mp3/.ogg/.wav`、0 处 `this.sound`~~ → **2026-11-01 第十五轮已收编（`28e8ac9`）**：Phaser 3.87 内置 WebAudio，`client/src/game/audio/{synth,world-audio,index}.ts`；零新 npm 依赖、零资产文件、协议不变。默认静音 25% 音量、8 音轨上限、8 格衰减、120ms 节流；只消费可观测的 `voxel_edits`/actor 位移/`combat_event`/`lights`，不碰独白。**2026-11-01 用户亲听验收通过**（5 短音 step/dig/place/combat/collapse + fire 循环）。**仍未做**：真实火场音效外发（用户裁定为独立缺口） |
| **M3 社会层** | ~~0 生产调用点~~ → **2026-11-01 第十六轮 `ffa74bd` 已收编并修好根因**：关系真实库副本 0→37 行，知识 22 行（隔离库 Playwright 实测）。根因是 `Observation.subject` 为中文显示名而装配拿 rtoken 去比 ⇒ 恒空；修法 `display_name_of` 反查 + 重名 fail-closed（§1e）。**第十七轮 `16b7eae` 已收编**：物种知识门（`can_hold_knowledge`，仅 human 持有/转述，未知 fail-closed；目击仍留在 `hidden_emerge.witnesses`）+ 名牌屏幕空间避让 |
| **`npc_health`** | ~~有模型/迁移/读路径，但**零写入**~~ → **2026-10-31 第十四轮已收编并修好启动自愈（`1d4bfa9`）**：事件→总线→同事务健康投影→感知触发→陈默闸门/记忆已接通；6 条内容种子。**2026-11-01 真实库已正式迁移（`d64464d`）**：备份 `world.db.bak-20261101-150615`（先副本演练再动真库），版本 `0015_health_code`、`code` 列补齐，events **187857** / snapshots **3946** / max seq 187857 **零丢失**，存档副本启动成功（tick 36001 / 54 实体）。~~**仍未做**：历史锚点 fork 的 severity/active 还原、每日严重度演进、第三方浮现见证链。~~ → **2026-11-03 订正：三条全通**（前两条 11-02，第三条第二十轮收编 `66637b7`）：
  ① **锚点 fork 的 severity/active 还原：已修**（主树 `02e3b10`）——`fork.py:559` 现走
     `_clone_health_at_cursor`（按 seq 重放事件 + 补无事件源的种子行，`created_at_tick <= fork_tick`），
     不再 `_clone_bounded` 复制父 head。钉子 `test_m5_fork_replay.py::test_A_health_seam_equal`。
  ② **第三方浮现见证链：已通**——真实库 `npc.hidden_emerge` 2 条带完整 `witnesses` 列，
     `knowledge` 32 行（`witnessed` 18 / `told` 14），`main.py:782` 的
     `witnesses_of_entity_emerge` + 物种知识门在链上。
  ③ **每日严重度演进：已修**（第二十轮 codex，主树收编 `66637b7`）——新增
     `sim/content/health_evolve.py`：同步无 IO 快照适配器，挂在 `main.py` 的
     `_on_day_switch`（反思先、健康后，两者返回值均丢弃），**只 `loop.enqueue`
     `npc.health_changed` 七键事件、不直写行**（C4），下一帧 drain+flush 落库
     （正常 1 帧延迟）。数值表（严重度/游戏日）：`old_injury -0.05` /
     `disease +0.10` / `addiction +0.02` / `disability 0` / `trauma -0.02`；
     round 12 位后 clip[0,1]；愈合归零后 `active=False` **只发一次**，恶化到 1 饱和
     不重复。`run_world_driver` 签名与同步语义**未改**。
     **离线选 (b)**：`advance_offline` 不演进健康，补跑结束后才建基线，不在首个
     在线日追补离线天数（已写进两处 docstring，**是真缺口、明确保留**）。
     **重症上限只到健康投影**：本适配器不产 `AGENT_INCAPACITATED`——普通 NPC 没有
     生产恢复入口，静默制造永久失能会把世界卡死（不是漏做，是**故意不做**）。
     **本树 fork 侧仍未做**：`fork.py` 走 `_clone_bounded`，没有主树的
     `_clone_health_at_cursor`；codex 按 A5 改钉「事件逐字段相等 + 投影行全列重放相等」
     替代，**未冒称历史健康锚点端到端验收**（收编后主树版本已在，见 ①）。
  > `anchor_package.CORPUS_TABLES` 仍不含 `npc_health`（设计如此：健康是**可折叠族**，
  > 走 `_clone_health_at_cursor` 重放，不进包——第十八轮也只在包里加了 `npc_profiles`）。 |
| **`npc.lod_change` 持久化** | **已完成**（`sim/npc/runtime.py` 发射 + `npc_store._project_lod_change` 双键投影）。此前记忆卡写「仍未做」是过时记录，2026-11-01 已订正。⚠ **2026-11-11 `510e618` 补修**：发射与投影都在，但 `sim_exec.npc_events_for_tick` 的 `npc.act` 过滤把 `npc.lod_change` / `npc.hidden_emerge` **静默丢掉**，事件从未到落库层——库里 `lod` 永远停在旧值（`chenmo` 库内 `lod=2` 却零 `npc.lod_change` 事件）。现走 `_PASSTHROUGH_KINDS` 直通 |
| **离线推进** | ~~`sim/world/offline*.py` 不存在~~ → **2026-11-01 第十五轮已收编（`28e8ac9`）**：`sim/world/offline.py::advance_offline` 复用现有 `TickLoop`；墙钟只在启动边界采样一次（`_offline_wall_time`）；水位取 `snapshots/branches.created_at`（控制元数据，不进事件流与 `state_hash` ⇒ **C5 安全**）；批上限 240 tick、`MAX_CATCHUP_REAL_SECONDS=4.0`、上限 1 游戏日（`TICKS_PER_GAME_DAY=86400`，超限记 `offline.capped`）；同墙钟重启零补跑。主树实测：60s→3600 tick、30 天→86400 tick 且丢弃 2590560s、两遍重放 hash 相同、玩家档零写。**仍未做**：真实 `world.db` 上跑一次真实停机补偿（需备份） |
| **T5 差事完成率** | ~~`errands_rate.py` 明写「本轮不设阈值」~~ → **2026-11-01 已定线（`d64464d`）**：用户裁定 **`ERRAND_COMPLETION_RATE_MIN = 1.0`**。依据实测 40/40（10 seed × 4 链，中位与最差都 1.0，`.orca/audits/t5-baseline-2026-11-01/baseline.json`）。**不留缓冲的理由**：口径是确定性脚本链（零 LLM/网络/随机），无抖动来源，0.95 只会让真实回退静默通过。**不沿用 M1 的 80%**（单决策口径）。**口径边界写死在模块 docstring**：这是脚本完成率，不是生产 NPC 自主完成率 |
| **soak 实体流失** | ~~`SOAK_ENTITY_LOSS_PER_GAME_DAY = 0`，从未抬高~~ → **2026-11-01 已定线（`d64464d`）**：用户裁定 **良性上界保持 0**，另立契约「**流失须被死亡解释**」（`净流失 - 已记录 npc.death = 无解释流失`，必须为 0）。**为什么不抬到实测的 4.0/游戏日**：那是每小时强制近身互殴的**夹具**，不是自然流失率；现有 soak 用 `make_mock_feeder` **根本没有死亡源**，抬到 4.0 会在 604800 tick 里程碑跑里允许 **28 个实体凭空消失而不报红**，等于把泄漏检测变瞎。契约在 `_assert_entity_stable(..., explained_deaths=...)`，测试 `sim/tests/bench/test_soak_loss_contract.py` |

**另一个口径缺口**（不算未实现，但要注意）：战斗表现层协议有 `Hit`/`Projectile`
schema，`sim/api/ws.py:1765` 只发 `posture_visual`，客户端 `client/src/net/ws.ts:238`
只 `recordCombatEvent()` 计数（`world-audio.ts:125` 拿它当音效键）——
**用户已明确裁定不做**，别再提案。

## 1c. 用户已裁定**移除**的功能（不是缺口，别再提案）

审计时最容易误判的一类：代码里「找不到」的功能，有些是**用户主动砍的**，不是没做完。
下面这些**不要再当成缺口提**，也不要再排期：

| 已移除 | 裁决时间 | 落地 | 现在的状态 |
|---|---|---|---|
| **迷雾 / 空间未知** | **2026-10-12 用户裁决**（playtest-4） | `0363769`（协议 1.7→**1.8** 减法变更） | 内核不再产 `fog.reveal`；WS `fog` 键与 `FogState` schema 删；前端 fog 罩全撤；`m3_fog`/`m4d17_fog`/`fix_fog_spawn` 三个测试文件随葬 |
| **战斗表现层**（弹幕/翻滚/受击） | 用户明确裁定不做 | — | 协议有 `Hit`/`Projectile` schema，只发 `posture_visual`；客户端只计数 |
| **计划看板**（UI 面板） | 2026-10（第五轮） | `bb871f2` | 面板删除；`PlanDelta` 协议与 `uiStore.plans` **保留**（只是不显示） |
| **M2 七日长跑取证**（604,800 tick） | **2026-11-09 用户裁定不做** | — | harness 在（`sim/tests/bench/soak.py`、`PI_M2_FULL_SOAK=1`），但**不跑、不落 `docs/perf/soak-windows.jsonl`**。别再把「缺 soak 证据」当缺口提 |
| **T4 真模型探针重跑** | **2026-11-09 用户裁定不做** | — | 探针集 248 条仍在 `sim/tests/test_t4_probes.py`，缺 `T4_RUN=1` 即 skip（52 条）。唯一记录是 `t4-nightly.yml` 头注「2026-09-28 18 passed」。**不建 artifact、不烧钱重跑** |

**迷雾的残留（合法，不要「清理」）**：
- `EventKind.FOG_REVEAL` + `FogRevealPayload` + `PAYLOAD_MODELS` 登记 + `_apply_fog_reveal` no-op
  —— **C4 事件不可销毁**：老日志里有 `fog.reveal` 行，删 kind 会让历史流重放直接炸。
  `sim/core/world.py:344-347` 的 docstring 已写明「no-op 即重放安全」。
- `sim/tests/test_m6_content_events.py` 仍锁 `FOG_` 前缀 —— 它锁的是**事件登记存在**，
  不是迷雾功能存在。删掉这条测试才是错的。
- `DESIGN.md` §13/§17 仍列「空间迷雾」（**冻结基线不回写**，见 §19/§20 的冻结声明）——
  DESIGN 是历史契约，不随裁决改；真相在 `docs/api/versioning.md` 的 1.8 行。
  真实库 `world.db` 里 `fog.reveal` 事件 **0 条**（生产从没发过）。

## 1g. 心声/街巷的真实产线（2026-11-02 实测，**B/C 的依据；C 已由 4A 关闭**；L2 段 2026-11-04 订正）

用户问「模型能控制人物吗 / 心声和街巷太乱，感觉模型没发挥作用」。查证结论：

**模型只控制 1 个人**（2026-11-02 实测；**2026-11-04 订正：已有第三处**）。
`self._llm.complete(...)` 现在三处：`sim/agent/driver.py:188`（陈默决策）、
`:282`（陈默对话台词）、**`sim/agent/npc_l2.py:268`（近身村民 L2 决策，第十九轮接入）**。
所以「模型只管陈默」在第十九轮之后**不再成立**——3 格内升格的村民也吃模型。
- 陈默：`main.py::_chenmo_loop` → `driver.decide_once`，`CHENMO_DECIDE_SECONDS`
  默认 **60 秒 1 次**；
- 50 村民：`sim/npc/runtime.py:156 evaluate_batch`（numpy 效用矩阵，实现在
  `sim/npc/utility.py`），每 10 tick；
- 赵铁/小满/苏婉：`npc/roles.py::role_events` 硬编码 f-string，每 600 tick（10 秒）。

**⚠️ 订正（2026-11-04）：本节原写「『升格 L2』是空壳」——已过时。第十九轮就接齐了。**

实测（2026-11-04 复核）：
- `sim/agent/npc_l2_runtime.py:84` 真的判 `profile.lod == 2`
- `sim/api/main.py:753`（升格名单）、`:862`（专属角色）都读 `lod == 2`
- `sim/api/main.py:1074` 装配 `NpcL2Coordinator`，`:1097` 定义 `_npc_l2_loop`；
  `npc_l2_live` 在离线补跑完成后置 true（`main.py:1516`）
- 有界单步、`L2Policy` 默认 min_interval 60s / max_calls 4 / timeout 8s / max_tokens 192
  （env 覆盖 `NPC_L2_MIN_INTERVAL_SECONDS` / `NPC_L2_CALLS_PER_MINUTE` / `NPC_L2_TIMEOUT_SECONDS`）

所以验收第 ⑪ 条「L2 是否真的有脑子」是**观感验收**，不是代码缺口。
原判据「全仓非测试代码没有任何地方读 `lod == 2`」在第十九轮（`bdeeb19`）之后已失效。

**心声（心之声面板）来源**：

| 来源 | 代码 | 性质 |
|---|---|---|
| 陈默 thought | `sim/agent/driver.py:370`，`content=intent.reason` | 真模型，~1 条/分钟 |
| 村民嘟囔 | `sim/agent/will.py:90 _TEMPLATES`（每档 12 句）+ `:415 _pick_index(key, pool_size)` | 纯模板 |
| 三专属角色 | `sim/npc/roles.py:25-42`，三条 f-string | 纯模板 |
| 玩家念头回执 | `ws.py:1398-1401` | **恒为「这话我记下了。」**（2026-11-09 实测订正行号；cue 仍是 `ws.py:1417-1431` 的标点启发式，真表 `sim/npc/plan_view.py:159 band_to_cue` 未接线） |

`_pick_index(npc_name)` **不含 tick / 动作 / 处境** ⇒ 同一 NPC 同一 band 永远同一句
（坏掉的唱片；50 人分 12 句）。且 36 句全是「不想干活」口径，**与动作无关**。

> **4A 已修（2026-11-02）**：动作专属池 `_ACTION_TEMPLATES`（5 动作 × 3 档 × ≥12 句）
> + `willingness_expression(..., action=)`，选取键变 `(npc_name, action)`；
> `move`/`build` 无专属池 ⇒ 池与键**一起**回落（与修前逐位一致）。见 §0。

**街巷（街谈巷议面板）来源**：`dialogue.py:34 template_line`，池
`:18 _CHAT_TEMPLATES` 5 句；但生产语域 `SpeechContext(平民, in_circle=False)` →
`speech_register` 返回「粗」→ `_REGISTER_TEMPLATES["粗"]` **只有 2 句**。
实测 50 人一整天不同台词总数 = **2**。

> **4A 已修（2026-11-02）**：`粗` 2→9 句、`文雅` 2→7 句（每句必带「您」）。
> 真实库 `npc.chat` 实测（278 条）修前「粗」池的两句占了绝对多数
> （「忙着呢，回头再说。」110 次）。见 §0。

> **订正（2026-11-02，我上一轮报错）**：我先前说屏幕上会出现字面量「旁人」——
> **生产不会**。`sim_exec.py:803` 是 `(display_name_of or {}).get(target_id, target_id)`，
> 主树 `main.py:765` 实传 `_display_names`（50 村民 + 陈默 + 动物 + 三专属角色全覆盖），
> 所以真机上署名是戏内真名，退化成 `villager_02` 只在**没传映射的测试替身**里发生。
> 真正的「旁人」兜底在 `driver.py:261`（陈默 L2 侧，`or "眼前的人"`）——那是
> 陈默找不到对方名字时的措辞，属正常兜底，不是缺陷。别照这个去改。

**「乱」的数量根因（3 游戏日 ≈ 72 真实分钟实测）**：

| 项 | 修前 | 修后（A 之后） |
|---|---|---|
| 嘟囔 bubble | 27.8 条/分钟（36 句） | 17.9 条/分钟（19 句） |
| 聊天 chat | 47.4 条/分钟（**2 句**） | 38.6 条/分钟（2 句） |
| 合计 | **75.2 条/分钟** | 56.5 条/分钟 |
| `CHATTER_CAP=8` 换屏周期 | **6.4 秒** | 8.5 秒 |
| 陈默心声 | 1 条/分钟 | 1 条/分钟 |

街巷是心声的 **75 倍**，句库 2 句，6 秒换屏 —— 用户「感觉模型没发挥作用」是准确的。

**根因链（一条解释全部）**：
`REMEDY_RELIEF` 无 `request_chat` → social 只涨不降 → 第 2 游戏日起恒 1.00 →
`synthesize_verdict` 需求冲突维 ≥0.8 → 全场 band 3 → 唯一补救动作 `request_chat`
又被 `sim_exec.py:65-77` 的 `chat_cooldown_until_of` 压掉 → 人被逼去 wander/rest/eat（都不 remedy social）
→ 满屏「这活儿我实在打怵」而人在闲逛。**A 已修**（见 §0），第 0~5 日 band>0 恒 2%。

**A 修后仍存在的残留（4A 已于 2026-11-02 修掉前两条）**：
- ~~第 3 日 band>0 只剩 `rest band2` 10,298 + `request_chat band1` 212 次决策，
  文本仍是「不想干活」口径~~ → **4A 已修**（动作专属池）。
- ~~街巷句库 2 句~~ → **4A 已修**（粗 9 / 文雅 7）。
- 「旁人」兜底**不是缺陷**（见上方订正），保持原样。

## 2. 历史轮次（第五～十九轮，已全部收编）

> 正文已删除（本文件纪律：考古走 `git log`）。只留**收编哈希**与**仍在生效的结论**；
> 逐轮细节查 `git log --all --grep='第N轮'` 与 `.orca/audits/`。

| 轮次 | 日期 | 内容 | 收编 |
|---|---|---|---|
| 第十九轮 | 11-02 | A social 需求闭环（`request_chat → social -0.3`）+ D 心声历史私密面（thought 只出本人视角） | `e28e144` |
| 第十八轮 | 11-02 | 锚点读档按游标重建 `npc_profiles`；L2 真实调用路径接齐（有限单步） | `e28e144` |
| 第十七轮 | 11-01 | 物种知识门（仅 human 持有/转述）+ 名牌屏幕空间避让 | `16b7eae` |
| 第十六轮 | 11-01 | M3 社会层根因修复（`Observation.subject` 是中文名非 rtoken ⇒ 恒空） | `ffa74bd` |
| 第十五轮 | 11-01 | 音效（WebAudio 合成，零资产）+ 离线推进 + T5/soak 定线取证 | `28e8ac9` |
| 第十四轮 | 10-31 | `npc_health` 写入路径接通 + 启动自愈 `ensure_schema` | `1d4bfa9` |
| 第十三轮 | 10-31 | 快照治理（真实库 3946→9 行，events 零删） | `92fbc1b` |
| 第十二轮 | 10-30 | 前端画面优化（世界宽 872→1152；单一可收起侧栏） | `7f89584` |
| 第十一轮 | 10-30 | 土坎视觉区分（1568 格隐形墙 → 三道斜纹，0 误标） | `6aa0528` |
| 第十轮 | 10-30 | 悬空修复（`walkable ⇒ h==1`），协议 1.13→**1.14** | `1895014` |
| 第九轮 | 10-29 | 移动操作重做；主树修掉 P0「人物完全无法移动」（`pickVoxel` 误判 → `pickGround`） | `04e2175` + `b0d4341` |
| 第八轮 | 10-29 | 地形同源重建（可走 820→3947，出生点 100% 可达） | `37e6a51` |
| 第七轮 | 10-28 | V4b 三材料分类（土/石/木） | `ba68e88` |
| 第五轮 | 10-26 | 挖土看得见（推翻决策 9）；碰撞真相仍是 `TileMap.collision` | — |

**仍在生效的结论**（从上述正文提炼，别丢）：

- **`pickVoxel` 与 `pickGround` 是两个拾取器，别混**：前者为**编辑**设计（`h>=2` 优先），
  后者只做地面反投影。移动必须走 `pickGround`——用 `pickVoxel` 时「点空地」会被判成
  「点房子」（等距下 h=3 方块与其斜后方 2 格地面顶面逐像素重合），实测 19.3% 落阻挡格、
  出生点 13×13 邻域 26 格里 21 格点不中。这是单测全绿但真机完全动不了的那次事故。
- **土坎（阻挡的 h=1）不能改成可走**：`_MATERIAL_BY_HEIGHT[1] = earth`，`place` 只对
  可走格生效 ⇒ earth 唯一来源就是阻挡 h=1 格。改成可走 = 土源断供。故只改渲染。
- **快照治理已落地但只是标记**：`is_cold` 仍留主库，不导出独立 SQLite，不批量迁移既有存档；
  活动分支旧热行在下一次快照写入时才收敛。DESIGN §12 的 <2GB 硬上限**未声称达成**。
- **冷归档/事件不可销毁**：`FOG_REVEAL` 事件 kind 必须保留（老日志重放要能过），
  `test_m6_content_events.py` 锁的是事件登记存在、不是迷雾功能存在——删这条测试才是错的。
- **Phaser RESIZE 模式必须 `game.scale.setParentSize`**：只调 `scale.resize` 会在 refresh 时
  从旧 parentSize 回写，手机留约 46px 底部空隙。

## 3. 踩坑（逐条有效）

**测试**
- **纯函数单测证明不了接线通**（第十六轮实证）。18 条测试全绿，生产 0 行。
  凡验收面写「实况跑起来后 X 表有行」，必须有一条**真跑 `lifespan`** 的集成测试。
  手造 `PerceptionFrame` 与生产帧形态不同时，测的是另一个世界。
- **`Observation.subject` 是中文显示名，不是 rtoken**（`senses.py:270-274`，同一个 `label`
  既作叙事又作 subject）。`frame.py:36-39` 已写明这一点。任何按 rtoken 匹配 subject 的
  代码都会静默失效——fail-closed，不报错，只是恒空。
- **`flush_for_anchor()` 读 `loop.pending_events`**：先 `drain_events()` 再调它 = 刷空列表，
  探针会假绿（我第一版就这么写的）。
- **`advance_frame(1/60)` 推不动 tick**：时钟累积器吃小数会一直是 0；喂 ≥1 实秒才动。
- **测试收尾「还原成默认值」会把真档打开**（2026-11-07 审计钩子取证）。
  `test_m6_death_path_data.py::_probe_driver_write_lock` 的 `finally` 写
  `get_anchor_store().__init__("sqlite:///world.db")`——**相对路径**，而 `os.chdir`
  已回仓根 ⇒ 下一次 `get_anchor_store()` 在仓库真实 `world.db` 上 `create_all`。
  全量门禁每跑一次打开一次真档；`create_all` 幂等（18 张表全在）所以只动 mtime，
  但这是运气——缺表/迁移漂移就会真写。**纪律**：夹具收尾要**还原跑之前的状态**
  （换单例引用、把原引用放回），不要发明默认值；`get_anchor_store` 的默认 URL 是
  相对路径，任何在 `chdir` 之后调用它的代码都在读「当前目录的 world.db」。
  定位手段：`sys.addaudithook` 监听 `sqlite3.connect`，按绝对路径过滤后打栈——
  比读代码猜入口快得多。钉子：`test_probe_never_opens_the_repository_world_db`。

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
- **客户端插值窗口不得等于服务端节拍**：旧 `INTERP_MS` 曾正好 250 = 行走 250±15ms，
  抖动使滑行永远差一点，逐格累积落后 → 视觉闪现。取节拍的 ~80% 留余量。
  **现行实现已换成回放缓冲**（`actor-motion.ts`：`TILE_CADENCE_MS_1X=250` +
  `REPLAY_DELAY_CADENCES=1` + `REPLAY_JITTER_SLACK_MS`，延迟由 `rampDelay` 平滑），
  `INTERP_MS` 这个名字已不存在——看到旧文引用它时按回放缓冲理解。
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

**持久层**
- **`create_all` 不给已有表加列**（第十四轮血案）：`Base.metadata.create_all` 只建**缺失
  的表**。本项目 `world.db` 就是它建出来的（**没有 `alembic_version` 表**），于是任何
  「新增列」的迁移（如 `0015` 的 `npc_health.code`）**永远补不上**，真实存档启动直接
  `OperationalError: no such column`。测试用临时/fresh 库天然带新列，**永远撞不上**。
  → 启动必须 `init_database` 之后再 `ensure_schema(engine)`（三分支：无版本且结构已
  匹配只 `stamp`；无版本且结构落后 `stamp` 基线再 `upgrade`；有版本直接 `upgrade`）。
  **「结构已匹配」分支不能省**：新 `create_all` 库已含新列，直接 stamp 基线再 upgrade
  会撞 `duplicate column name`。
- **`alembic.ini` 的 `script_location` 是相对 CWD 的**：本仓库大量测试
  `monkeypatch.chdir(tmp_path)`，直接 `Config("alembic.ini")` 会去 tmp_path 找迁移目录，
  报 `CommandError: Path doesn't exist`。→ 构造 Config 后必须
  `set_main_option("script_location", 绝对路径)`。
- **`alembic/env.py` 调 `asyncio.run`**：不能在运行中的事件循环里直接跑，必须
  `asyncio.to_thread`。`env.py` 从 `WORLD_DB_URL` 读地址，**用完要还原**，否则污染进程环境。
- **快照可删，事件不可删（C6）**：热保留删的是 `snapshots` 行；`events` 与 `is_cold=1`
  的快照一行不动。两者语义不同，别把「热保留」也做成 `is_cold` 标记。
- **删中间快照不会破坏恢复**：`restore_world` 沿祖先回退到更早的合格快照，再重放；
  没有任何合格快照时走 `expand_world({}, history)` 全量重放。**只增加耗时，不改正确性**
  ——真实库副本实测 3946→9 行后恢复 payload 逐位相同。
- **保留集是「最近 8 份热 ∪ 每日首份」**，可重合，故热行上界是 `8 + 覆盖日数`，
  不是恒定 8。同 tick 可有多份快照（主键是 `(branch_id, seq)`），日首份要用
  `row_number() over (partition by tick//86400 order by tick, seq)` 取一条，
  不能按 `MIN(tick)` 全保。
- **`prune_hot_snapshots` 先 `session.flush()`**：`autoflush=False` 的工厂里新快照
  否则对查询不可见。策略函数用**调用者 session、不自行 commit**，失败随事务整体回滚。
- **只有 `Branch.status == 'active'` 才授权删除**：缺失分支行或 abandoned 分支的旧热行
  一律保留（legacy 数据不能因为「看着是热的」就被清掉）。
- **head-fork 封存父线才标冷，anchor-fork 不标**：历史点读档不能把玩家正在跑的线
  变冷。判据是既有的 `parent_status == "active" and kind == "head"`。
- **清理开销实测 +0.76ms/flush**（带清理 4.31ms vs 不带 3.55ms，60 tick/s 下可忽略）。
  若将来 flush 频率再涨，可考虑「仅在行数超阈值时才跑」——本轮**未改**。

**离线推进 / 收编纪律（第十五轮）**
- **墙钟只能存控制元数据**：`snapshots.created_at` / `branches.created_at` 是墙钟，
  但它们**不进事件流、不进 `state_hash`** ⇒ 用它算离线时长不破 C5。反过来，任何墙钟
  值一旦写进 event payload，C5 立刻破。离线路径**只在启动边界采样一次**（`_offline_wall_time`），
  循环里不再取时间。
- **离线推进必须复用 `TickLoop` 的既有节奏**，不要另写一套推进器：批上限
  `_MAX_TICKS_PER_FRAME=240`、`MAX_CATCHUP_REAL_SECONDS=4.0`、1x=60 tick/秒、
  战斗尺度 1 tick/秒；每批之间 `await asyncio.sleep(0)` 让出事件循环。
- **cap 是 1 游戏日（`TICKS_PER_GAME_DAY=86400`）**，超限记 `offline.capped` 并丢弃秒数。
- **重启幂等靠水位**：`last_recorded_at` 读最新 `Snapshot.created_at`，回退到
  `Branch.created_at`。同墙钟再启动 ⇒ `offline_seconds=0` ⇒ 零补跑（主树实测）。
- **`advance_offline` 会强制切到 1x 再还原**，所以调用前必须记下当前倍速。
- **收编合并可能不能用 ff**：codex 从旧基线开分支时，主树的新提交它没有 ⇒
  用 `git merge --no-commit --no-ff` 并逐个解冲突。解完**必须复查主树侧新增章节
  还在**（本轮 §1c 就在解冲突后仍被误判为丢失，实际是没 stage）。
- **管道里的 `$?` 是管道最后一个命令的**：`cmd 2>&1 | tail -3; echo $?` 拿到的是
  `tail` 的退出码。要判真实结果必须 `cmd > log 2>&1; echo "EXIT:$?"`。
  **本轮就是靠这条抓到 codex 回执误报的 tsc 失败。**

**第十六轮修根因（2026-11-01）**
- **感知帧的 `subject` 是戏内词面，不是 rtoken**。`senses.py` 视觉/听觉填显示名
  （叙事要人话），内感受填自身 rtoken。任何戏外装配（witnesses / 统计 / 回指）
  **必须经 `display_name_of` 反查**，直接拿 rtoken 比会静默恒空。
- **重名必须 fail-closed**：显示名不唯一时无法从词面反推是谁，返回 `([], None)`。
  注意区分「**没**显示名」（按 rtoken 词面，天然唯一，**不是**歧义）与「**多个**同显示名」。
- **手写探针起 `lifespan` 会写真实库**：`sim/tests/conftest.py:16-20` 的 autouse 夹具
  （`isolated_world_database`）只对 pytest 生效。
  脚本里 `import sim.api.main` 直接用默认 `WORLD_DB_PATH=Path("world.db")`，且启动即跑
  `advance_offline`（会补推最多 1 游戏日）。**要么显式改 `main.WORLD_DB_PATH` 到临时库，
  要么写成 pytest 用例。** 2026-11-01 本轮就踩了：真实库 +741567 events / knowledge +27。
- **集成测试必须照抄生产执行序**：`_tick_once` 是 `npc_runtime → maintenance → perception`
  （`sim/core/tick.py:95-97`），emerge 只能拿**上一帧**。先跑 perception 再跑 npc_runtime 的写法
  会把当帧帧喂给 `frame.tick < tick` 过滤器 ⇒ 永远 `([], None)`，看着像功能没实现。
- **`model_copy` 的字段要走 `update={...}`**：`model_copy(pos=(x,y))` 是 TypeError。

**定线（2026-11-01）**
- **取证值 ≠ 可用的阈值**。soak 的危害夹具实测 4.0 实体/游戏日，但那来自「每小时强制
  一对近身互殴」的人工死亡源；现有 soak 用 `make_mock_feeder` **没有死亡源**，实体结构性
  守恒。把上界抬到 4.0 ⇒ 604800 tick 的里程碑跑允许 28 个实体凭空消失 ⇒ **泄漏检测变瞎**。
  正确做法是把「允许的流失」与「已记录的解释」绑定，而不是给一个绝对数字。
- **确定性夹具不要留缓冲**。T5 的 `chain_runner` 零 LLM/网络/随机，实测 40/40 = 1.0 且
  中位=最差=1.0 ⇒ 无抖动 ⇒ 0.95 只会让真实回退静默通过。有抖动的指标才需要缓冲。
- **定线必须写死口径边界**。T5 的 rate 是**脚本完成率**，不是生产 NPC 自主完成率；
  后者没有基线数据，模块 docstring 里必须写明「本模块不对它做断言」，
  否则下一个人会把 1.0 当成生产指标。
- **真实库迁移的顺序**：备份 → 在**副本**上演练并核对行数 → 确认无损 → 才动真库 →
  迁移后拿备份逐项对账（events 计数 + max seq + snapshots）。备份文件名带时间戳，
  且 `.gitignore` 必须有 `*.db.bak-*`（`*.db` 匹配不到 `world.db.bak-2026...`）。
- **`ensure_schema` 要能重复调用**：迁移后再启动会二次调用，必须幂等
  （`at_head` 分支直接 return）。

**方法**
- **本卡里的 `file:line` 会漂移，引用前先实测**（2026-11-09 全卡复核，40+ 处里
  有 20 处已失效，最大偏移 500 行以上）。权威写法是「文件 + 符号名」，行号只作
  辅助；引用时用 `grep -n "<符号>"` 现查，别照抄旧行号。反例：`ws.py:1295` 已到
  1400；`main.py:1056` 已到 1244；`ws.py:1619` 已到 1765。
- 查符号/调用链/影响面先用 `codegraph_explore`（显式 `projectPath`）。
- 门禁数字同场实测，不引用旧读数；**收编后主树必须独立复跑**。
- **删文件/依赖前先查 `DESIGN.md`**：它写死了承诺（`tests/invariants`、`tests/replay`
  为保留占位），零 grep 命中≠可删。
  **2026-11-06 用户裁定**：Hypothesis / tenacity / pydantic-settings 三个死依赖已删，
  DESIGN §4 同步改写；**别再按旧说法把它们当「承诺」而拒绝删除，也别再引回来**。
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

1. 本卡 §0（当前状态）+ **§1b（已关闭但没做的承诺）** + **§1c（用户裁定移除的功能，
   不是缺口）**——后者防的是「把砍掉的功能当没做完，又去重做一遍」。
2. `git log --oneline -10` + `git status`，两树各一遍。
3. 两树 `.orca/talking.txt`（只留当前波 + 纪律 + 未做；2026-11-09 实测
   主树 104 行 / codex 树 72 行，**别记死数字**）。
4. `docs/README.md` + `docs/dev-workflow.md`。
5. 需要历史细节才查 §2-newest / §3 / `git log`。

## 5. 分工与技术栈

- 主树：架构/质量/测试/前端/发布/收编；codex：复杂实现、安全合规。
- Python 3.12 + FastAPI + SQLite + uv；React 19 + Phaser 3 + Vite + Zustand + Vitest。
- 文档真相源：`shared/openapi.json`、ORM/迁移、`docs/` 活文档。

## 6. ① Claude｜新对话恢复快照

【2026-11-11 波 E 收编 + 事件静默丢弃修复｜无在途任务】主树 `510e618`。
① 收编 codex 波 E `5a85afc`（陈默 work/eat/rest 闭环，`8b483db`），**未收** `c3a382d`
（本树无 §10.5）。② 收编时独立抓到并修复一处能**永久冻住陈默**的缺陷：`last_intent_result`
是持久 prompt 状态，闸门 `quoted_echo_scan` 豁免、装配器 `scan()` 不豁免 ⇒ 一句能过闸门
过不了装配的 reason 让此后每轮 `assemble_prompt` 抛错，`llm_calls` 恒 0。修在写入侧
`ChenmoDriver._record_result()`。③ 本轮新修两处**事件静默丢弃**（`510e618`）：起火落点
不可走时改投最近可走格（实测 9.13%/日 → 设计 34%/日）、`npc.lod_change`/`npc.hidden_emerge`
走 `_PASSTHROUGH_KINDS` 直通。④ 两树 `talking.txt` 已精简重写（主树 9KB、codex 7.7KB），
codex 树残留临时日志已清。门禁：pytest 全量 `3862P/126S/2F`（2F 均为 bench 阈值边缘，
复跑绿）、ruff/format/pyright 全绿。**当前无在飞**；两树 `talking.txt` 均指向「下一波先 merge」。

【2026-11-01 定线与真实库迁移 `d64464d`｜历史】用户裁定三项并已落地：
① T5 完成率 **1.0** 硬阈值（依据实测 40/40，确定性脚本链无抖动故不留缓冲）；
② soak **良性保 0** + 新契约「流失须被死亡解释」（不抬到夹具实测的 4.0——
现有 soak 无死亡源，抬线会把泄漏检测变瞎）；
③ 真实 `world.db` **已正式迁移**：先备份 `world.db.bak-20261101-150615`，
再在副本演练确认无损，最后动真库 ⇒ 版本 `0015_health_code`、`code` 列补齐、
events 187857 / snapshots 3946 / max seq 187857 **零丢失**，存档副本启动
（tick 36001 / 54 实体），`ensure_schema` 二次调用幂等。
`.gitignore` 加 `*.db.bak-*` 防备份入库。
门禁 3069P/0F/121S（391.73s，+8 = 5 soak 契约 + 3 T5 阈值）、ruff 380 files、
pyright 0/0、client 337P/47F、两资产/实现程度/uv lock 全绿；
`PI_T5_FULL=1` 全量 10 seed 通过（178.56s）。
**只剩音效亲听这一件归用户。**

【2026-11-01 第十五轮已收编 `28e8ac9`｜历史】codex `47f9e80` 以
`--no-ff` 合并（codex 分支不含主树第十四轮 4 个提交，ff 不可用），仅
`.orca/memory.md` §7 一处冲突。主树独立复核：pytest **3061P/0F/121S**（400.34s，
= codex 自测 3056 + 主树自愈测试 5）、ruff 379 files、pyright 0/0、client
tsc/eslint/prettier EXIT 0、vitest **337P/47F**、两资产 `--check` 逐字节一致、
`uv lock --check` ok、`gen:protocol:check` ok、`check_implementation_status.py` 无缺口。
**发现 codex 回执误报**：`npm run typecheck` 实际 `EXIT 2`（`world-audio.test.ts:48`
TS2345），已按仓库 `vi.fn<签名>()` 约定修复。自写 16 条不变量探针 16/16 通过。
复跑 codex 两份取证脚本数字一致（T5 40/40 率 1.0；soak 对照 0 / 危险 4.0）。
**留给用户**：音效亲听、T5 与 soak 阈值定线、真实 `world.db` 正式迁移（需备份）。

【2026-10-31 第十四轮已收编 `1d4bfa9`｜历史】`3603ecb..5a48f7c` ff 收编零冲突；
主树独立复核发现并修复阻断缺陷：**`world.db` 由 `create_all` 建出（无 `alembic_version`），
`create_all` 不给已有表加列 ⇒ `0015` 的 `npc_health.code` 永远补不上，真实存档启动即
`OperationalError`**。修法 `ensure_schema()`（三分支自愈：新库只 stamp、老库 stamp 基线再
upgrade、有版本直接 upgrade；`script_location` 覆盖绝对路径以抗 `chdir`；环境变量用完还原），
启动时调用。真实库副本实测：code 补齐 / events 187857 零丢失 / 6 种子行 / 版本 0015；
异目录 CWD 同样通过。门禁 pytest 3037P/121S/0F、Pyright 0E/0W、client 321P/44F 全绿，
协议仍 1.14。**真实 `world.db` 正式迁移尚未执行**（现在启动会自动升级，需一次备份确认）。

【2026-10-31 第十四轮已派 `671931c`｜历史】用户裁定走 `npc_health` 写入路径、深度端到端，
已写进 codex 树 talking。**派单前主树实探出三个隐藏事实**（不在 §1b 原表里）：
① 读链路在生产中断（当时 `main.py` 丢弃 `_hidden_states`，`npc_events_for_tick`
   无该参数）——**已修**：现签名含 `hidden_states=`（`sim/npc/sim_exec.py:609`），
   `main.py:771` 实传；
② `build_default_bus()` 缺 6 个 handler（含 4 个 `matter.*`），接线即崩，主库不炸只因
`matter_state`/`structures` 均为 0 行；③ `attr_id` 用 DB 自增派生、fork 不克隆 `id` ⇒
跨分支漂移，而 evidence 按它匹配。派单含 `code` 列（迁移 `0015`）修法。**协议保持 1.14**
（此前选项里写「预计 1.15」是错的）。收编复核重点见 talking。

【2026-10-31 推送 `671931c`｜无在途任务】用户授权推送，6 个提交双远端直连成功
（origin 直连绕代理、gitee 直连）。

【2026-10-31 第十三轮收编完成 `317460b`｜无在途任务】快照治理 ff 收编零冲突
（`1fd362f` RED → `92fbc1b`）。主树独立复核 pytest 3012P/0F/121S、vitest 321P/44F、
并在真实 `world.db` 副本上实测 **3946→9 行、events 一行未删、恢复逐位相同**。
协议仍 1.14。**两树 talking 已精简**（556 行 → 138 行，只留当前波）。

- **开新对话只需知道**：① codex `16b7eae`（**第十七轮已交付待收编**）、主树收编后门禁需重跑；
  远程停在 `3603ecb`（主树领先未推，现测 `git rev-list --count origin/main..main`，等用户决定）；
  ② 待**肉眼**验收 9 条，**7/8/9 优先**（见 §0）；主树 2026-11-01 第十六轮
  **开过一次**浏览器（用户明确授权，验社会层接线实机效果，**不是**观感验收）；
  那 5 条观感**仍未验收**，第十二轮的观感只有 codex 的截图证据；
  ③ **§1b 的承诺缺口**：`npc_health`（第十四轮 + 真实库已迁移）、音效/离线推进
  （第十五轮）、T5 与 soak **已定线**（`d64464d`）；**只剩音效未亲听**——
  别以为 M0–M6 收官就等于都实现了，也别以为已实现就等于用户已验收；
  ④ **不变量必须单向**（`walkable ⇒ h==EARTH`），做成双向会立刻回归「只挖不放」；
  ⑤ **移动拾取 ≠ 编辑拾取**，合成一个会在真实地图上死掉 19% 的可走格；
  ⑥ **单测全绿 ≠ 真机能动**，改拾取/投影必须用真实地图实测命中率；
  ⑦ **快照可删、事件不可删**：热保留删的是 `snapshots` 行，`events` 与冷快照一行不动（C6）；
  ⑧ **墙钟只能存在控制元数据里**：离线时长靠 `snapshots/branches.created_at`，
     绝不进事件 payload / `state_hash`，否则 C5 立刻破（第十五轮的设计前提）。
- **远程**：origin/gitee 均停在 `3603ecb`；主树领先若干提交（**不记数字**，
  `git log origin/main..main` 查全表）**未推**。推送仍是用户决定，不自动推。
- **配置目录**：维持用户 10-26 裁定「不进 git、不推远程、本地须存在」；主树不建 `.pi`。
- **浏览器**：仅用户明确要求时用。**已改为 `--browser chromium` + 升级打包版（2026-11-01）**：
  - 现状：`.claude/mcp.json` = `@playwright/mcp --browser chromium`；
    `ms-playwright` 内为 `chromium-1252`（Chrome **157.0.8103.15**）。
  - 为什么改：原先是 `--browser chrome`，而 `chrome` 是 **channel 语义不是目录**
    （README 原文 "browser **or chrome channel**"），解析到**已安装的**
    `C:\Program Files\Google\Chrome`。铁证：旧 MCP profile 的 `Last Browser` 就是那条路径。
    实测对比：`--browser chrome` → `Program Files\...\chrome.exe`；
    `--browser chromium` → `ms-playwright\chromium-1252\...\chrome.exe`。
  - **升级方式**：`playwright install chromium`。直连 `cdn.playwright.dev` 被掐断
    （ECONNREFUSED / server closed connection），**必须**带
    `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright`
    （npmmirror 镜像实测可用）。install 会**清理旧 revision**（1248 被删）。
  - **不要在 `mcp.json` 硬编码 revision**：install 换版后硬编码立刻失效。
    `.orca/audits/frontend-visual-2026-10-30/verify-layout.cjs` 已改为
    `playwright.chromium.executablePath()` 动态解析。
  - **用户数据零共享**（实测）：MCP 独立 profile `ms-playwright-mcp/`（History 仅
    `http://127.0.0.1:5173/` 1 行、无 Bookmarks、无登录态）；用户 `User Data` 零写入。
  - 规则已同步：`.orca/workflow.txt` §5 与 `docs/dev-workflow.md`。
- **全局 git 邮箱**：`zx19836980213@outlook.com`（2026-10-31 实测，`dev-workflow.md`
  原记的 `223049848+ZX466@users.noreply.github.com` 已过期）。
- 本轮教训已进 §3：`.orca/talking.txt` 必须保持未跟踪，否则 ff 会覆盖派单；
  **派单里的坐标/数字必须来自代码实测，不能拿 `spawn_candidates` 当运行时出生点**。
- 第十三轮教训已进 §3「持久层」：**收编时在真实库副本上验证，不要只在内存库自测**。
  codex 的 `world.db`（0 快照/10033 事件）与主树的（3946 快照/187857 事件）是**两个不同文件**，
  自测结论不能互相冒用。

## 7. ④ codex｜新对话恢复快照

【2026-11-11 波 E｜技术交付，待主树收编】陈默work/eat/rest、hunger与上次结果闭环，装配异常不杀决策任务。真实库副本30轮成功主决策：work22/eat6，npc.act28；3笔工资共15文、两顿饭花14文，余额0→1，原地MOVE0。pytest3785P/121S/72D、Vitest792P/92files及全部门禁EXIT0。协议仍1.19；本地提交见Git，唯一talking回执后停等收编。

### 当前状态与恢复入口

- 基线cb4338f，已同步主树e7858c0/波Dec4a020，A/B/C/D已收编，勿重做。恢复workflow→完整talking→本节→registry→Git；代码先CodeGraph(projectPath=E:/zxdevelop/.orca/worktrees/project7/codex)。只本树Conventional Commit，不push/不改主树/不自行merge或rebase/不联系其他树终端；talking永不入Git。
- 历史5份文档与主树分叉，别整树merge回去。本轮顺手订正voxel-execution-spec§10.5的过期剪影句，独立docs提交；主树该文件无§10.5，可只收波E实现提交。
- 用户本轮补充确认：读档重建主角内存投影、不写库。实际assemble_runtime完全排除chenmo，不会自动重建；main成功载档块新建ProtagonistNeeds并清旧结果，按最新裁定执行，勿再照派单D段的旧假设去删除这处接线。

### 波 E 的实际契约

- IntentAction、M1_SUPPORTED_ACTIONS、prompt同一对全角括号枚举同步work/eat/rest；不要求target，prompt明确三者不填target_id/target_pos，原地干活/吃饭/歇息不要反复move_to。unsupported gap仍{demolish,use}，不绕banned/hidden闸门，profile None仍0调用。
- driver三动作在执行当拍结算，各有npc.act+一条结果thought，不再重发动机reason。work只在PHARMACY_POS=(100,53)曼哈顿≤既有_SITE_ARRIVAL_RADIUS=4且冷却已过时+既有_WAGE_AMOUNT=5，note=wage:work；远处只摆姿势/「这儿没活可干」且不付钱。wage_last复用main同一dict，既有载档clear仍生效。药铺常量在protagonist.py，不增LANDMARKS或genesis。
- eat按buy_price(meal,tick,seed)扣款，成功后apply_remedy(eat)缓解hunger.3/energy.15，余额不足零扣款/零补救；rest免费apply_remedy(rest)缓解energy.3。即时结算是陈默LLM意图路径的明确取舍，不改村民到站/wage/errand链。可选经济/needs依赖缺席时fail-soft，尤其eat不会付钱却无补救。
- build_needs()与档案JSON复用原0.3/.2/.4种子；ProtagonistNeeds只按正向tick差复用DEFAULT_DECAYS/advance_needs，补救复用apply_remedy，不写SQL/WorldState/state_hash，不进NpcRuntime效用。main每轮决策前推进并只传narrate_hunger到interoception_text；hp/时辰既有感知链不重接，不用BodyState重复伤情。
- PlanSlice.last_intent_result记本意图实际新发的本人结果thought原文（buy/sell/take/give/build/attack/三动作）；其他动作记reason。只取本意图事件窗口，旧事件/对手/bubble不混入，下一prompt按当前HiddenState过滤后仍终扫；成功载档清旧结果。
- _chenmo_loop每轮Exception记录chenmo.decision_failed后继续，保留原sleep/节拍；CancelledError继续传播。PromptAssemblyError及一般临时故障均先红后绿证明任务存活/后轮可执行/可取消。别把坏装配当作任务可以静默死亡的理由。
- 既有npc.act→anim块移为accepted-event观察器，NPC与陈默共享同一桥；只在anim变化时标pending_delta_entity_ids，站定切换可见。未改ws.py/协议/其他出站面。driver四个移动臂统一保护start==goal与空/单点/终点回到起点路径，不发原地MOVE，也不用原地MOVE停旧路径；原聊天/独白fail-soft保留。

### 真实副本验收与经济核算

- 真正源库是E:/zxdevelop/project7/world.db（约500MB，2317894events/tick450740/1加密profile/29陈默心声）；本树world.db是Oct21旧档，不能拿它充当带profile的验收世界。SQLite mode=ro在线backup含WAL复制到审计live-copy；chdir后才import后端，world/anchor/profile全指副本，SQL guard拒绝副本外连接。现有加密profile用已有主密钥正常解密，未造/改profile行，不打印或复制明文凭证/主密钥。
- CHENMO_DECIDE_SECONDS=5，LZ_OFFLINE_CATCHUP_MAX_TICKS=1；0会ValueError，offline.py注释说0关闭是旧错误，本轮未改该模块。仅取消副本NPC L2模型后台worker以隔离额外成本，真实世界driver/L1/工资/errand照跑；没有脚本替代陈默主决策。
- 同一30轮真实成功主响应：queued work22/eat6/talk_to1，一轮未入队；实际npc.act work22/eat6；wage:+5三笔共15，buy:meal -8/-6两顿共14，初始0→最终1。原地MOVE事件/提案均0，站定work/eat动作delta12条，hunger文本全无数字；tick450742→475584。真实网络过程约454秒，额外既有聊天调用不计主决策轮数。
- 首次验收统计错把npc.act归属查为envelope.actor_id（工厂该字段为空，归属是payload.npc_id），因此runner跑完30轮后断言失败。未改生产代码或付费重跑；对同一已提交窗口按正确字段只读重统计通过，原JSON/log/exit1保留；live-recount.exit0、最终live-acceptance.json passed=true，finalize另用SQL JSON字段独立交叉核验28动作/3工资/0原地MOVE。
- 可行性：hunger.3→.7需34560tick；工钱冷却[3600,10800)，陈默实值7344；meal基准8、实际浮动6–9，两笔5文=10已够，保守两工资周期≤21600tick仍早于需求增量.4窗口。不是靠补启动金；新旧世界均不改50户各15文的genesis。

### 验证与后续边界

- .orca/audits/wave-e-2026-11-11/含plan/progress、surface/needs/driver/review报告、各RED→GREEN日志与.exit、gates、私库脚本/副本和30轮元数据。独立审查无已证实Critical/Important/Minor，另在SQL受限/模型禁用的隔离环境独立跑57P。最终pytest3785P/121S/72D，503.40s；Vitest792P/92files；ruff/check+format、pyright、TS类型/lint/格式、gen:protocol:check、build均EXIT0。构建保留既有大chunk提示，不扩优化。
- 原主树源库、源WAL及本树旧库hash前后不变；未操作其他树服务，无新监听端口/服务器，副本验收任务已退出。未改协议1.19、客户端/素材/地图、NpcRuntime/sim_exec工资链、core.tick、offline模块、outbound_guard或genesis。
- Needs纯内存，重启/按用户最新裁定读档回种子，不补持久化；周期内只主角投影推进。姿势辨识度/硬件帧耗与主观观感仍归主树/用户，事件/WS观察证据不冒充WebGL主观验收。
- 波D人物叙事仍须self触发/他人双列知识、整句过滤；snapshot-dirty按current|broadcast并集含缺席，防A→B→A漏撤回。波C仅主角环境深度剪影与近墙≤35°自动抬角保留，90°padding测试勿回225°；土坎逻辑1/绘制2与试车台世界锚点保留。
- Python用uv，三store一起隔离，不能__init__还原真库。浏览器仅明确授权时用ms-playwright打包Chromium/独立profile；删包/venv需另行授权。旧清理blocked by policy勿重试/绕工具；DPR/包体/离线健康/perception出站/M2七日/T4真模型不扩。
