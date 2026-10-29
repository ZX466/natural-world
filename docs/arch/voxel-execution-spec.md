# 施工总单：等距体素转向 V0-V3（执行规格书 · Claude 执行版）

> **角色定位**：本文是可直接开工的施工规格，也是本轮转向的**唯一执行真相源**。
> 决策链（三路径保留率对比、A0 选型、Three.js 触发条件）见 §10；原
> `voxel-transition-plan.md` 已于 2026-10-26 并入本文并从工作树删除（git 历史可查）。
> 项目宪法：`DESIGN.md`（六条约束 C1-C6 不可协商）。
> **本单 §0 的 A15-A18 是 2026-10-23 二次核实新增事实（结构图层/无视觉雾/建筑 tile=0/
> 点击行号），优先级高于早前讨论稿。**
> 单据日期：2026-10-23。范围：**仅 V0-V3**；V3.5/V4a/V4-3D 不在本单。

---

## 0. 现状锚点（实测事实，勿凭记忆，动手前逐一确认）

| # | 事实 | 位置 |
|---|---|---|
| A1 | `const TILE = 16` | client/src/game/scenes/WorldScene.ts:35 |
| A2 | 地图渲染收敛在 `redrawMap()`（**定义 :152**，:138-139 是调用；内部调 renderTileset :180） | WorldScene.ts:152 / :180 |
| A3 | 实体定位 `actor.x * TILE + TILE/2` / 深度 `(actor.y+1)*TILE` | WorldScene.ts:353-356 |
| A4 | 目标标记 goalMarker :77/:130 / 调试层同款线性投影 | WorldScene.ts |
| A5 | 雨层 `setScrollFactor(0)` 屏幕空间（:125/:128），昼夜色罩屏幕空间 | WorldScene.ts |
| A6 | `VILLAGER_SHEET = {cols:4, framesPerRow:4, standCol:0}`（:61）；`CHENMO_SHEET 17 列`（:56） | client/src/game/render/actors.ts:56-61 |
| A7 | 零依赖 PNG 编解码模块**已存在**（zlib+struct） | sim/content/png_codec.py |
| A8 | 17 张古风 sprite 已入库 | client/public/assets/sprites/god_villager_*.png |
| A9 | 63 个提交未推送（origin/gitee 均落后）；GitHub 走代理 127.0.0.1:7897 | git log origin/main..main |
| A10 | 前端 **149 passed / 27 files**（2026-10-23 亲跑 `npm run test` 实测）；后端 not-bench ~3000 | 各自门禁 |
| A11 | **地图已是桃花源替换产物**：`MAP_W=140, MAP_H=100`（build_god_town.py:37-38）；tileset = `god-town-16.png`（2240×1600，140 列），前端 `TILESET_KEY='god-town-16'`、`TILESET_COLS=140`（WorldScene.ts:42-44） | sim/content/build_god_town.py |
| A12 | **tileId 是整图切片序号，不是语义角色**：映射为 **`(id-1)%140` / `(id-1)//140`**（gid 1-based，0=空格哨兵），见 renderTileset :196-202。旧 sprout-palette.json **已不是运行时真相源** | WorldScene.ts:196-202 |
| A13 | **碰撞语义两套必须分清**：桃花源源图 `Collisions` 是 **1=阻挡/0=可走**；`extract_collision` 取反直转后，`linhe-town.json`/前端是 **1=可走 / 0=阻挡**（build_god_town.py:62-71；前端判据 `map.collision[...] === 1` WorldScene.ts:169/:227） | build_god_town.py:62-71 |
| A14 | 桃花源 `map_pack.json` 有 10 地标 anchor 坐标（祠堂/染坊市集/梯田等，D9 已裁避开瑕疵区） | assets/god-packs/taohuayuan-online/map_pack.json |
| A15 | **建筑不是地面贴图**：`structureLayer` 是独立 Graphics（depth 14），逐格 `fillRect` 平涂（phase=built 不透明度 0.92） | WorldScene.ts:81/:132/:246-259 |
| A16 | **全仓没有迷雾**：客户端无 fog/revealed 字段；sim 侧 `FogOfWar` 亦无任何消费方，2026-10-26 随死代码清理删除（视觉雾已于协议 1.8 移除；历史 `fog.reveal` 事件仍由 no-op handler 重放） | 全客户端 + sim grep 实证 |
| A17 | 建筑完工发 `tile_changed(tile_id=0)`（前端渲染时 `id===0` 直接跳过=留空），碰撞置不可走；坍塌/拆除按 P-6 补发静态原值恢复 | sim/agent/build_exec.py:199；sim/api/main.py:135-155 |
| A18 | 点击处理在 `handlePointer`（:221-234），碰撞判据在 **:227**，发 `client:move_request`（:233） | WorldScene.ts:221-234 |
| A19 | **没有 BootScene**（`game/scenes/` 只有 WorldScene.ts；客户端 README 过时）：预载在 `WorldScene.preload()` :90，tileset 于 :92 加载 | WorldScene.ts:90-92 |

## 1. 硬红线（违者返工，全阶段有效）

1. **C1-C6 全部有效**（DESIGN §2）。本单最易踩：C3（渲染层不得引入元信息词面）、C5（图集/转换脚本确定性：同输入逐字节可重建，禁 random/时间戳）。
2. **sim 侧只允许动 `sim/content/`**（管线脚本区）。`sim/core|world|npc|agent|llm|api` 一行不改——`git diff --stat` 里这些目录出现任何变更即违规（V1-V3 明确零内核改动）。
3. **WS 协议零变更**：每阶段收尾 `npm run gen:protocol:check` EXIT 0 是硬门禁。渲染器切换是纯前端能力，不得新增任何帧字段。
4. **flat 渲染器永久保留**：iso 是增量分支不是替换；同世界 flat/iso 双渲染下实体位置与交互语义必须一致（这是「换皮不换魂」的验收形态）。
5. **测试先行**（TDD）：投影/拾取纯函数先写 vitest RED 再实现；渲染断言适配不得删除既有测试语义，只加 renderer 分支。
6. Conventional Commits（`feat(render): ...`）；每阶段原子提交；**V0 的推送在阶段内完成，不留尾巴**。

## 2. V0 收口（半天）

1. **推送 63 提交**：`git push origin main && git push gitee main`（github 已配域名级代理；失败先看代理再看冲突，勿 force）。
2. **DESIGN.md v2.2 修订登记**（走 §18 认可的 v2.x 路径，最小编辑）：
   - §0 修订摘要表加一行：`修订 v2.2 | 视觉调性换轨：元气骑士调性→等距体素（Minecraft 风格）；渲染层 Phaser 内等距投影，其余六条约束与玩法不变；flat 渲染器永久保留（执行规格 docs/arch/voxel-execution-spec.md）`
   - §1「视觉」条改为：等距体素调性（2:1 等距投影、方块世界、Minecraft 风格表现层；玩法与操控模型不变）。
   - **其余章节一字不动**。
3. 提交本单与 plan 文档入库（含 §11 修正）。
- **验收**：远端同步（两 origin 均 0 落后）；DESIGN 仅两处 diff；全量门禁绿。

## 3. V1 等距渲染壳（2-3 天）

### 3.1 纯函数层（先测后码）

新增 `client/src/game/render/iso.ts`：

```ts
// 渲染常数与逻辑 TILE=16 解耦（R1）。h = 顶面距地高度（方块高 h 存于 0..h）
export const ISO = { TW: 32, TH: 16, HH: 16 }; // 菱形宽/高、单位高度像素
// 世界→屏幕（返回「顶面中心」；h=0 即地面基线）
isoProject(x, y, h): {sx, sy}   // sx=(x−y)*TW/2, sy=(x+y)*TH/2 − h*HH
isoUnproject(px, py): {x, y}    // 地平面命中（R6：忽略高度柱）。
                                // 输入是世界坐标 → 内部先减 (originX, originY) 再逆变换；
                                // 菱形内判定 |dx|/(TW/2)+|dy|/(TH/2) ≤ 1
heightOf(x, y): number          // 查 linhe-height.json（每格 0..3；缺表/越界 fail-soft → 1）
                                // ⚠ 绝不能用 tileId 做键（A12：tileId 是切片序号）
depthKey(x, y): number          // (x+y)*1024 + y（R4 行序）
```

- **加载时序**：**项目没有 BootScene**（`client/src/game/scenes/` 只有 WorldScene；
  客户端 README 的 BootScene 描述已过时）——在 `WorldScene.preload()`（**:90**，
  tileset 于 :92 加载）追加
  `this.load.json('linhe-height', '/assets/tilesets/linhe-height.json')`。
  `heightOf` 依赖已载入的表；未载入时 fail-soft 返回 1，但 iso 模式启动前必须就绪。

- 配套 `iso.test.ts`：投影可逆性（isoUnproject∘isoProject=id，地平面）、菱形边界
  （内/外/边线上各取点）、depthKey 全序性、**heightOf 用「注入式 mini 高度表」**
  （4×4 手写 h 值夹具，不依赖真实产物文件——保持纯函数可测、TDD 先 RED 可落地）。
  实现上建议 `createHeightLookup(table)` 工厂 + 默认全局实例读产物，测试注入夹具。
- **⚠ A12 关键事实：tileId 是整图切片序号，不是语义角色**——`heightOf` 必须按
  **坐标 (x,y)** 查高度表，不能用 tileId。两条落地路径：
  1. **视觉驱动（推荐起步）**：新增 `sim/content/build_height_map.py`，逐格采样
     `god-town-16.png` 的中心像素（每格 16×16 取中心 4×4 均值）。**采样路径**：
     先读 `linhe-town.json` 的 ground gid，再定位 tileset 格
     `((gid-1)%140, (gid-1)//140)`（tileset 是原图 1:1 切片；按 gid 而非直接按
     (x,y) 采样，可容忍地图改动）。按色相/亮度聚类定性：水蓝→0、路径/土色→1、
     绿植被→1、深绿树冠→3、建筑屋顶→2、墙体→2。**聚类阈值表写死在脚本头注**，
     配重跑确定性测试。产物 **`client/public/assets/tilesets/linhe-height.json`**
     （运行时副本，入库；与 `god-town-16.png` 同目录、同惯例——浏览器必须能静态取到，
     放 sim/content 会取不到）。格式：`{ "w":140, "h":100, "h_values":[0..3 × 14000] }`
     （**键 = 地图坐标扁平数组**，与地图同 commit）。

     > **2026-10-28 修订**：中心 4×4 单点采样的 HSV 分类实测不可用（整图是 1:1
     > 绘画切片，14000 格 = 14000 个不同 gid，逐格噪声 → 794 个 h==1 孤岛，
     > 90 个出生点只有 35 个落在 h==1）。现由 `sim/content/terrain_class.py`
     > 单源产出：每格 16×16 的走/冠/水占比 → 5×5 均值滤波 4 轮 → 只留最大连通块
     > → 作者真值（90 出生格 + 10 地标）挖最短通道接回。碰撞位与高度档来自
     > **同一次分类**，不可各自推导。
  2. **语义驱动（备选）**：从桃花源 `map_pack.json` 的 10 地标 bounds 生成确定性
     语义区（建筑带→2、水域→0），其余→1——粗但零视觉魔法。
- **V1 强制止损门（新增）**：高度表产物必须做**可视化抽查**——用一次性 HTML/脚本
  按 h 值上色渲染 140×100 缩略图，肉眼确认水/树/建筑分类合理；不合格调阈值重跑。
  **抽查不通过不得进入 V2**（同「地图重组可视化抽查」纪律）。

### 3.2 渲染器策略与混合分层（R4）

- WorldScene 加 `renderer: 'flat' | 'iso'`（默认 flat；URL `?renderer=iso` 可切——
  V3 才翻默认）。`redrawMap()` 内分支。
- **h 语义统一（先钉死，避免半埋/悬空）**：`h` = **方块高度 = 顶面距地高度**（0..3）。
  高度 h 的方块：顶面菱形中心 `project(x,y,h)`，地面侧的下沿点
  `S = project(x,y,0) + (0, TH/2)`，左右侧面从顶面下沿画到 S（侧面像素高 = h·HH）。
  实体脚底 = `isoProject(x, y, effectiveHeight(x,y))`（顶面中心）。
- **有效高度（2026-10-26 用户裁决：挖一次降一层，放一次升一层）**：
  建筑 footprint 的 `phase ∈ {built, collapsing}` 优先返回 2；其余格从静态
  `heightOf(x,y)` 计算：`dig → max(0, h-1)`、`place → min(3, h+1)`，无编辑保留 h。
  挖到 0 不留悬空菱形疤痕；碰撞与 gid 仍由 `TileMap.collision` / 服务端编辑决定。
  同格连续重复同一动作会被服务端拒绝；当前协议只记录最后动作，故先 place 再 dig 会从
  视觉 h+1 变为 h-1（边界截断除外）。这是本轮明确接受的近似，精确深度须另改协议。
  **客户端只有 `built | collapsing | rubble` 三态**（world-mirror.ts:70；planned/building
  不进客户端投影）。rubble 已补发静态原值恢复地面（P-6），按上述地面编辑规则回落，无编辑时为 heightOf。
  依据 A15/A17：建筑完工后地面 gid 变 0（画布留空）+ 碰撞不可走，建筑由
  `structureLayer` 表现；等距下必须按 h=2 的方块绘制，否则会出现「地面空洞」。
  坍塌成 rubble 后 structure 仍在表中但按地面高度绘制（低矮瓦砾），不能继续按 h=2。
- **矮块（h≤1：水/路/普通地面）烘进等距画布**：画布上逐格画菱形顶面 + 左右
  侧面平涂（零纹理；**底色 = god-town tileset 对应格的采样色**——与 build_height_map
  同一采样源，勿引 sprout-palette；面着色伪 AO 顶 100%/左 75%/右 60%，R5：
  不用 IsoBox，画布直绘）。画布尺寸：**宽 = (W+H)·TW/2 = 3840；
  高 = (W+H)·TH/2 + maxH·HH + TH/2 + 64 边距 = 2040**（maxH = 高度表最大值，至少 3）；
  **画布原点偏移 originX = H·TW/2 = 1600、originY = maxH·HH + TH/2 = 56**
  （偏移必须含菱形半顶点余量：只减 (H−1)·TW/2 会让最左侧格的左顶点出画 16px；
  偏移写进 `isoProject`/`isoUnproject` 内部唯一一处，调用方仍用世界坐标）。
- **高块（h≥2：树/建筑）为 Phaser Image**：贴图先用运行时生成的纯色三面小画布
  （V3 图集替换；**贴图底色同样取自该格采样色**）。
  **几何（推导已核）**：顶面菱形中心 = `isoProject(x,y,h)`；方块最低点 S =
  `isoProject(x,y,0) + (0, TH/2)`；整块像素高度 = `h·HH + TH`。
  因此：`position = isoProject(x,y,0) + (0, TH/2)`，`setOrigin(0.5, 1)`，
  图片尺寸 = **TW × (h·HH + TH)**（例：树 h=3 → 32×64）。
  **勿用 (h·HH + TH/2)**——会少 TH/2，方块会整体浮起 8px。
  `depth = depthKey(x,y)`。
  高块清单 = 全图 `effectiveHeight(x,y) ≥ 2` 的格子（静态高度表 + 结构覆盖；
  V1 构建时枚举一次，结构新增/移除时增量更新）。
- **结构与 TILE_CHANGED**：WorldMirror 在地图、编辑和结构变更时递增 `terrainVersion`；
  WorldScene 将版本传给 IsoTerrain，未变帧 O(1) 返回，不序列化集合、不扫描地面。
  变更帧比较一次表面缓存；矮块只清除并重绘变更前后包围盒，按原对角线顺序补绘
  所有相交邻格，包围盒外像素保留，复用画布贴图。未传版本的独立调用仍支持显式同步。
  高块保留坐标对象池；`built ↔ collapsing` 只改不透明度，不重烘或上传地面；
  **`collapsing → rubble` 要重建该格高块**（高度 2 → 地面编辑后的高度，地面已恢复）。
- **结构图层的等距化（必须做，A15）**：`syncStructures()` 的 `fillRect` 改为等距方块：
  `built/collapsing` 按 h=2 实心/半透明方块，`rubble` 画低矮瓦砾标记。
  **必须与高块/实体同深度池（`depthKey(x,y)`）**，不得保留原 depth=14 独立层——
  否则建筑永远在实体后面，遮挡关系错误。保留现有 `lastStructureSignature` 早退机制，
  签名变化时重建该层对象池（勿每帧重建）。**这是 V2 必须项，不是可选项。**
- **验收**：静态世界（启动即 full_snapshot）等距形态可看；?renderer=iso 切换正常；
  纯函数测试全绿；高度表可视化抽查通过；全量门禁绿。

## 4. V2 实况接管（2-3 天）

1. **实体 billboard**：`position = isoProject(x, y, effectiveHeight(x,y))`（脚底贴顶面，
   **不是 h=0**——地面块高 1，写 0 会让所有实体陷进地里）；`setOrigin(0.5, 1)`；
   **depth = depthKey(x,y) + 1**（与高块同池，实体在北侧树后被树冠遮挡、在南侧在前
   ——R4 遮挡语义）；影子改压扁椭圆（宽≈TW/2、高≈TH/4）贴顶面。
2. **点击拾取**：pointer → `isoUnproject(pointer.worldX, pointer.worldY)` → 按
   **A18** 替换 `handlePointer` 里的 `Math.floor(worldX/TILE)`（WorldScene.ts:221-234）；
   后续可走校验与 `client:move_request`（:227/:233）**零改动**。
3. **摄像机**：边界 = 菱形外接盒 + 64px 边距（R3）；跟随陈默时中心 =
   `isoProject(pos.x, pos.y, effectiveHeight(pos))`（顶面中心，勿再手动减高度）。
4. **调试层/目标标记**（A4）：全部经 isoProject 换算。
- **验收**：陈默+50 村民+三动物在等距世界按既有逻辑走动；遮挡正确（肉眼核验
  「走到树后消失、绕出再现」）；149 条测试适配后全绿（适配=渲染断言加 iso 分支，
  runtime/协议类测试应零改动）；全量门禁绿。

## 5. V3 玩法对齐（2-3 天）

1. **气泡/名牌**：`isoProject(x, y, effectiveHeight(x,y))` 定位并按屏幕坐标上浮；
   深度沿用「气泡置顶」惯例。
2. **迷雾：本单无此任务（A16 修正）**。全仓当前**没有任何迷雾实现**——客户端无渲染，
   sim 侧 `FogOfWar` 也已随死代码清理删除（2026-10-26）。V3 不新增视觉雾；将来若要
   「玩家探索迷雾」，是独立需求（届时才做菱形覆盖与揭示事件），**不要按旧稿去找
   不存在的 chunk 雾盖或 `sim/world/fog.py`**。
3. **雨层/昼夜色罩**：屏幕空间，预期零改动——如有裁剪错位只动呈现参数。
4. **结构阶段表现**：building/collapsed 相位的等距方块透明度与步进动画（复用现有
   phase 字段），坍塌后高块移除、静态地面高度回落（§3.2 有效高度规则）。
5. **图集管线**：新增 `sim/content/build_block_atlas.py`——**复用 png_codec.py**（A7）
   程序化生成 16×16 纹理 × 按高度档位（水/地/建筑/树冠）三面着色变体；**色源 =
   god-town tileset 采样色（与 height_map 同源）**，勿引 sprout-palette；确定性
   （同输入逐字节一致，禁 random/时间）；产物入 `client/public/assets/tilesets/`；
   `sim/content/README.md` 素材清单登记（程序化生成，无外部许可）。
   前端高块与矮块画布切图集渲染（平涂→贴图替换，接口预留于 V1）。
6. **iso 成为默认渲染器**（flat 保留可切）。
- **验收**：念头注入→独白气泡、差事往返、战斗慢镜、天气昼夜在等距下全闭环；
  图集脚本重跑 diff 为零；全量门禁绿；**本单收官提交**。

## 6. 每阶段统一门禁（收尾必跑，全绿才提交）

```powershell
uv run pytest -q -m "not bench"      # 后端全量（必须带 marker；裸 pytest -q 会跑 bench，慢且易抖动——CI 同口径）
uv run ruff check . && uv run pyright
git diff --stat -- sim/core sim/world sim/npc sim/agent sim/llm sim/api   # 必须为空
cd client
npm run test                          # 基线 149 passed / 27 files
npm run typecheck && npm run lint && npm run format:check
npm run gen:protocol:check            # EXIT 0 硬门禁
```

## 7. 交付清单

- [ ] V0：63 提交推送双远端；DESIGN v2.2 两处最小修订；方案两文档入库
- [ ] V1：iso.ts 纯函数+单测（注入式 mini 高度表）；`build_height_map.py` + 产物
      `linhe-height.json` + **可视化抽查通过**；renderer 策略；矮块画布/高块对象混合分层
- [ ] V2：billboard（effectiveHeight 脚底）/拾取（A18）/相机/遮挡；**结构图层等距化**；
      实况走动；149 条测试适配后全绿
- [ ] V3：气泡/结构阶段表现/图集管线/默认 iso；玩法全闭环；收官提交
- [ ] 全程：协议零漂移、sim 内核零改动、flat 保留可回退

## 8. 明确不做（本单外，防蔓延）

- V4a 挖放（含「谁来挖」裁决——**需用户拍板，默认建议 A：只陈默挖**）
- V3.5 内容包（音效/日记/录屏）、V4.5（合成/采集/季节）、V4-3D（Three.js，T 系列）
- **玩家侧视觉迷雾**（A16：全仓无此实现，属独立新需求，不进本单）
- 任何 sim 内核改动、任何协议字段、任何新 npm 依赖（V1-V3 零新依赖）
- 阴影区局部失效优化（V2 局部重建够用）、移动端 chunk 画布

## 9. 出问题的止损口

- **V1 观感不达标**（等距形态丑/性能差）：停下，截图报备用户裁决——flat 零损失
  可回退是本路线的保险，不要自行加码优化。
- **深度遮挡边角异常**（同格相邻高块/实体闪烁）：先核 depthKey 公式与锚点，
  再考虑 y 次序微调；禁止引入排序引擎或重建渲染架构。
- **门禁红灯不明原因**：按 README 台账惯例定位（pytest -k 聚焦 / 分型 skip），
  禁止 --deselect 掩盖（memory 已有判例）。

## 10. 决策链与边界（原 voxel-transition-plan.md 并入）

### 10.1 为什么是「Phaser 内等距体素」而非 Three.js 重写

| 资产（2026-10-23 实测） | A0 等距体素 @ Phaser（采纳） | Three.js 重写（否决） | 真 MC 集成（永久排除） |
|---|---|---|---|
| sim 内核 + 测试 | 100% | 100% | ~30%（C4/C5/C6 崩塌） |
| WS 协议 | 100% | 100% | 重写 |
| React UI 壳 + store | 100% | 100% | 100% |
| Phaser 前端骨架（WorldScene/runtime/world-mirror/net） | ~90%（只换投影 + 地图渲染器） | ~0% | 弃用 |
| 17 张古风 sprite | 100% 原样（billboard） | 需重绘 MC skin | 弃用 |
| 桃花源语义地图（碰撞/地标/五区/差事坐标） | 100% | 100% | 弃用 |

等距化只需**两个收口点**：投影函数（`isoProject`/`isoUnproject`）与 `redrawMap()`；
深度排序、天气/昼夜覆盖、点击寻路链路均原样存活。这就是「换收口点不换骨架」。

### 10.2 Three.js（V4-3D）的启动条件

只有以下需求**真实出现**才启动 V4-3D（届时等距阶段的概念资产全部平移）：

- 建造玩法需要自由旋转视角观察立体结构；
- 洞穴/多层垂直空间成为玩法；
- 「真 MC 观感」成为核心卖点。

在此之前等距体素已满足「Minecraft 风格」定义（方块世界 + 挖建预留）。

### 10.3 沿用裁决

1. 路径：等距体素起步（A0）→ 按需 V4-3D；真 MC 集成永久排除。
2. 角色：billboard（古风 sprite 原样）；MC skin 重绘降为未来可选表现层升级。
3. 存档导入（原 V5）列入路线图尾部，站稳再启动。
4. **flat 渲染器永久保留**：回退保险 + 低配模式，零维护成本。

### 10.4 风险与止损

| 风险 | 等级 | 对策 |
|---|---|---|
| 等距观感不如预期 | 中 | V1 即止损门：一周内见真图，不满意切回 flat 零损失 |
| 深度排序边角（树冠/屋檐遮挡实体） | 中 | 按行分层绘制（`depthKey`）；气泡始终置顶 |
| 局部重绘失效复杂化（TILE_CHANGED） | 低 | 先全图重绘（1.4 万格 canvas 秒级）再优化——勿过早优化 |
| 两次转向损耗士气 | 中 | V1 快速正反馈；flat 保留 = 无路可退之忧 |
