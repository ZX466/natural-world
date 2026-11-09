# 世界可辨认性与自生长 — 设计（2026-11-05）

> 用户 2026-11-05 验收反馈驱动的批次。目标：**一眼能认出的镇子** +
> **NPC 能建造改变镇子**。three.js 自由视角世界已于 2026-11-06 实现，
> **2026-11-07 经用户验收后成为默认渲染器**；`?terrain=phaser` 退回 Phaser（§7）。

## 1. 用户诉求（原话）

1. 「这个世界空空如也，npc 只会聚集，没有建筑，没有地点，只有无意义的方块」
2. 「其他操作 llm 无法执行」（寻路可以）
3. 「挖的石头等材料不能用，只能用泥土」
4. 「主角老是说有奇怪气味」

用户裁定：**A（画面）与 B（后端）都做，按复杂度分配到两棵树**；C（three.js）原先保留为未来方案，2026-11-06 用户另行裁定启动地形部分（§7）。

## 2. 实测根因（每条都追到源码，非推测）

| # | 症状 | 根因 | 位置 |
|---|---|---|---|
| ① | 世界是彩色方块 | `readColors()` 把每格图块**平均成一个 RGB**，`paintBlock` 画纯色菱形 | `client/src/game/render/iso-terrain.ts:537` |
| ② | NPC 只聚集 | 定籍制 + **片区三个动作指向同一格**：15 个站点槽位只有 6 个不同格 | `sim/npc/sim_exec.py:179-204`、`_WANDER_RADIUS=6` |
| ③a | LLM 只会寻路 | `take`/`give` 在白名单与解析层，但**无执行器**（落到尾部独白，零副作用）。（`wait` 有执行器，已订正） | `sim/agent/gate.py:33` vs `driver.py:333-372` |
| ③b | LLM 给错坐标 | prompt 写「镇子是 96×96」，真实图 **140×100** | `sim/llm/prompts/assembler.py:35` |
| ④ | 石/木用不了 | 材料取自**目标格当前高度**，而 place 只允许可走格（h 恒 =1）⇒ 永远是 earth | `sim/agent/voxel_exec.py:114,117,124` |
| ④' | 凭空造石（新发现） | 同一根因的另一半：放土 → 该格 h=1→2 → 再挖回来 → `_MATERIAL_BY_HEIGHT[2]` = **stone** ⇒ 一块土变两块石头 | `sim/agent/voxel_exec.py:117,198` |
| ⑤ | 老是奇怪气味 | **每个实体**都是强度 1.0 的持续气味源，门槛与听觉同档 0.04 | `sim/perception/senses.py:322`、`smell_world.py:20` |
| ⑥ | 建棚失败后反复念叨（新发现） | 已有工地时 `start()` 返回 None，失败路径**每拍**吐「这块地使不得了」；且回滚只改内存余额、**不发事件**（C4 违规） | `sim/agent/build_exec.py:124-125`、`sim/npc/build_action.py:31-34` |
| ⑦ | 地标表少了 5 个（新发现） | `main.py:1080` 硬编的「你知道这些去处」只列 6 个，漏祖屋/村塾/钟山/藏书房，村广场被「药铺（100,53）」顶替（药铺**不在** `_landmarks` 里） | `sim/api/main.py:1080` vs `sim/content/linhe-town.json::_landmarks`（10 项） |

### 2a. 四个硬阻断（「世界长出来」现在四层全断）

| 层 | 事实 |
|---|---|
| 决策 | `utility.py` 的 `_GAIN` 里 build 三项增益全 0 ⇒ 得分恒 `HABIT_BONUS=0.05`，而 request_chat 0.24 / eat·rest 0.10 ⇒ **argmax 永远轮不到 build** |
| 参数 | `runtime.py:176` 的 params 只从 scores 取键，永远取不到 `x`/`y`；而 `sim_exec.py:653` 要求 `set(params)=={"x","y"}` |
| 资金 | 创世不发 `coin.grant`；盖棚要 40 文，只有 `work` 到站发 5 文 |
| **并发** | `BuildRuntime.start` 在已有工地时**直接返回 None**（`build_exec.py:123`）⇒ 全镇同时只允许一个工地；而失败路径每拍吐一句「这块地使不得了」，且回滚**不发事件**（C4 违规） |

### 2b. 症状 → 改动映射（用户每条抱怨都落到具体项）

| 用户原话 | 真正缺的是什么 | 改动 |
|---|---|---|
| 「空空如也」「只有无意义的方块」 | 镇子的美术**已经画好了**，但 `readColors` 把每格压成一个色块，把它全扔了 | A |
| 「没有建筑」 | 建筑就在图里（h≥2 的 7373 格），被压成纯色菱形 | A |
| 「没有地点」 | 10 个地标坐标都在、都实测可走，但画面上认不出、NPC 也几乎不去 | A（可见）+ B2（可去） |
| 「npc 只会聚集」 | 15 个站点槽位只有 6 个不同格 | B2 |
| 「其他操作 llm 无法执行」 | `take`/`give` 有白名单无执行器；prompt 坐标尺寸写错；地标表少 5 个去处 | B4 + B2 |
| 「石头等材料不能用，只能用泥土」 | 材料由目标格高度推出，而 place 只允许 h=1 | B3 |
| 「主角老是说有奇怪气味」 | 每个实体都是强度 1.0 的持续源，门槛低一个数量级 | B1 |
| （隐含）「世界不会变」 | 建造四层全断（决策/参数/资金/并发） | B2 |

**关键判断：镇子不是不存在，是没被画出来。** 美术资产是完整的
（2240×1600，14000 个互不重复的格子），渲染层把它降维成了纯色方块。
所以 A 是「恢复已有内容」，不是「新增内容」——这也是它能在主树小改完成的原因。

### 2c. 量化证据（本轮实测）

- **气味**（50 人聚广场、静风、200 tick 模拟）：
  浓度 p5 **5.67** / 中位 **8.76** / p95 **10.40** / max **10.75**，门槛 0.04
  ⇒ **50/50 每帧超阈值**，且 50/50 全落最高档「一股浓重的气味直冲鼻子」。
  （复跑脚本 `.orca/audits/round23-2026-11-05/measure_smell.py`——`.orca/` 下除
  `workflow.txt`/`agent-registry.md`/`memory.md` 外都被 `.gitignore` 的 `.*/` 兜底
  忽略，属本地证据不进库；B1 落地时把等价断言写成 pytest 用例，才是长期回归入口。）
  **独行者也有 1.57**——一个人走在街上也永远闻得到「浓重气味」，这是用户反馈的直接来源。
- **图集**：2240×1600 真像素画，**14000 个不同 gid 且两两不重复**；按等距投影烘焙后
  **一眼可辨**（桃花林/溪流/石桥/瓦顶/梯田全在），见 `.orca/tmp/preview/iso-full.png`。
- **可挖格**：8941 格 = h1 土 1568 / h2 石 4379 / h3 木 2994 ⇒ 石木是主力，现在全无用途。

## 3. A｜等距烘焙（主树，前端域）

### 3.0 一个必须先知道的资产事实

`linhe-town.json` 的 `ground` 里 **14000 个格子的 gid 全部互不相同**
（`gid == y*140 + x + 1`，实测 14000/14000 吻合），而
`god-town-16.png` 正好是 2240×1600 = 140×100 个 16px 格。

⇒ **这不是图集，是一张整图被切成了 14000 个唯一小块**。
所以「烘焙整张地图」等价于「把这张源图按等距投影铺开」，没有重复图块可复用。
这条事实同时决定了下面两件事：
- 地面烘焙**不需要**任何按 gid 的纹理缓存（一张整图 canvas 就够）；
- 高格的顶面**必须**走图集/变换路径，不能逐 gid 建纹理（7373 个 h≥2 格
  就有 7373 个不同 gid）。

### 3.1 做法（已用离线实验验证）

改动集中在 `client/src/game/render/iso-terrain.ts` 的 `paintGround` 与 `syncBlock`
两个函数；`pickGround`/`pickVoxel`/`iso.ts`/`world-mirror.ts`/协议一律不碰。

1. **画法**：不需要逐像素循环——现有 `BlockAtlas.face()`
   （`block-atlas.ts:112`）的四点仿射变换**已经正好是等距投影**：

   ```
   p = [sx, sy-hh, sx+hw, sy, sx, sy+hh, sx-hw, sy]
   transform → source (u,v) 落到 (sx + hw*(u-v)/16, sy - hh + hh*(u+v)/16)
   ```

   代入 `ISO.TW=32, TH=16`（hw=16, hh=8）即得
   `dx = u-v, dy = (u+v)/2 - 8`——与离线实验里验证过的正投影逐像素公式完全一致。
   ⇒ 新增 `paintTile(ctx, sx, sy, gid)`：把这套 transform 的 source 从
   `this.mask` 换成**源图集图像**，`sourceX/sourceY` 取 `gid` 对应的格子位置，
   一次 `drawImage` 画完，`imageSmoothingEnabled = false`。

   ⚠ 离线实验踩过的坑：按屏幕坐标**反解** (u,v) 只能画出半个菱形（可见为
   三角栅格）。上面的正向仿射没有这个问题。

2. **接入点**：`paintGround`（`iso-terrain.ts:345`）的 `paintBlock` 调用换成
   `paintTile`（h<2 的地面格）；**保留它的对角线遍历顺序**——这是
   遮挡关系的唯一来源，不能改成行列序。

   **`paintTile` 必须自己处理「没有源像素」的三种情况**，不能假设 gid 一定有效：
   - `map.ground` 缺失（mock/网格模式）——现有代码已经写成
     `this.colors(map.ground?.[y * map.w + x] ?? 0)`（第 244 行），可选链已兜住；
   - `gid == 0`——结构占地会把 gid 抹成 0，**源图里没有这块像素**；
   - `gid > 14000`——脏数据。

   前两种的**既有契约**是画木色 `FALLBACK_COLOR = 0x6b4f2a`（`iso-terrain.ts:11`，
   第 8-10 行注释「Structures may replace their ground gid with 0. No source
   pixels exist then; use the same deterministic timber fallback as
   build_height_map.py」），且 `sampleTileColor` 第 43 行
   `gid <= 0 || gid > cols*rows` 已经返回它。
   ⇒ `paintTile` **沿用同一个兜底**（gid 无效就退回 `paintBlock(ctx, ..., h, FALLBACK_COLOR)`），
   不要在这里画空/透明——房屋占地会露出底色。

   顺带确认：`MapStatic.ground` 在类型上本来就是**可选**的
   （`world-mirror.ts:47` `ground?: Uint16Array`，注释「mock 模式无此层
   （色块渲染回退）」），所以 `paintGround` 不能假设它一定存在。

3. **高格叠加**：`syncBlock`（`iso-terrain.ts:307`）现在给每格挂一张
   `iso-block-${h}`（**只有 2 张**，h=2 和 h=3），靠 `setTint(color)` 区分颜色。
   要贴真实图块顶面，这个「共用纹理 + 整体着色」的结构必须改。

   ⚠ **不能逐格建 canvas**：实测 h≥2 有 4379+2994 = 7373 格，
   逐格一张 `32×(h*16+16)` 的 canvas 合计 **49 MB GPU 纹理 + 7373 个纹理对象**，
   纹理切换会把 draw call 打爆。

   **首选做法：复用已经加载的 tileset 纹理，零新增显存。**
   `god-town-16.png` 本来就整张在显存里（2240×1600 RGBA ≈ **13.7 MB**）。
   `this.load.image()` 加载的是**单张无 frame 的纹理**，所以要先给 gid 注册 frame。
   Phaser 的 `texture.add(name, sourceIndex, x, y, w, h)` 只是**元数据**，不复制像素。
   14000 个 frame 按每帧 200–800 B 估 **2.7–10.7 MB JS 堆**——可接受，
   但**只注册实际用到的 gid**（地面 14000 个已够，高格 7373 个是它的子集，不必另注册）。
   这样：
   - **顶面**：`setTexture(TILESET_KEY, frameOf(gid))` —— 直接显示该格真实图块
     （`TILESET_KEY` 在 `WorldScene.ts:79` 已有，`preload` 已加载）；
   - **侧面**：继续用现有 `BlockAtlas` 的 mask + `setTint(侧面暗化色)`。

   > `iso-terrain.ts` 现在完全没有用过 `texture.add(frame)`——`addCanvas` 只用于
   > 整图（`GROUND_KEY`）和块纹理（第 277/321 行）。所以这套 frame 注册是**新增机制**，
   > 要有对应单测（同一 gid 取到的 frame 矩形必须等于 `((gid-1)%140, (gid-1)/140, 16, 16)`）。
   > 注意 `sampleTileColor` 的取源公式（`iso-terrain.ts:48-49`）与它**同源**，
   > 两处必须一致，否则顶面图块会整体偏移一格。
   >
   > **已实测**（真实地图 5 个抽样格，含 (0,0)/(139,99)/(70,50)/(15,18)/(100,52)）：
   > `frameOf(gid)` 落点与 `cell(x,y)` 的源块位置**5/5 精确吻合**。
   > 这个等价关系是本轮 A 的地基，可以放心建。

   > **已知不一致（不在本轮修）**：服务端 `ws.py:898` 发的 `tileset` 名是
   > `god_town_v1`，但客户端 `WorldScene.ts:79` 硬编 `TILESET_KEY`
   > 且从不读这个字段。目前不炸（图固定），但换图时会静默用错素材。
   > 本轮 A 不碰它——记在这里，别当成 A 的缺陷。

   一个 `Image` 只能有一个纹理，所以每格需要拆成两个 sprite
   （侧面 `depth = depthKey - 0.01`，顶面 `depth = depthKey`），
   或合成到一个 `Container`。**这个选择留给实现者**，两种都可接受。

   （变体 d：`.orca/tmp/preview/variant-d.png` — 有立体感且不破图）

4. **保留现有表现**：挖放疤（`syncScars`）、土坎三道斜纹（`syncBanks`）、
   废墟（`syncRubble`）、结构 phase 淡入（`phase()`）全部不动。

5. **编辑格**：现在 `iso-terrain.ts:242` 用
   `edits.has(key) ? EDIT_COLORS[h] : colors(gid)` 选色，烘焙后 `paintTile`
   吃的是 **gid** 而不是 color，所以这一支要单独处理：
   - 编辑格**不贴图块**，继续画纯色菱形（`paintBlock` 保留，用 `EDIT_COLORS[h]`）；
   - 其余格走 `paintTile(gid)`。

   ⇒ `paintGround` 里需要按 `cell.edited` 分流。`SurfaceCell` 要加一个
   `edited: boolean`（现在只有 `color`，没有「这格是不是被编辑过」的独立标志；
   `color` 被 `EDIT_COLORS` 覆盖后无法反推）。

   ⚠ **脏检测也必须带上 `edited`**：第 257 行与第 289 行的变化判断都只看
   `h` / `color` / `phase`。若某格的 `EDIT_COLORS[h]` 恰好与它原图块的平均色
   相同（`EDIT_COLORS[0]=0x8f8055` 与 `EDIT_COLORS[1]=0x8f8055` 已经同值，
   说明这套色本来就撞过），编辑状态变化会被漏判 ⇒ 该格不重绘 ⇒ 屏幕上
   显示的还是旧图块。加 `edited` 进比较式即可。

   `readColors()` 不删——它的角色从「画地面」收窄为「算立方体侧面暗化色」。

### 3.2 为什么不是别的

| 方案 | 否决理由 |
|---|---|
| 只贴高格不烘焙地面 | 出现黑洞（变体 b：`.orca/tmp/preview/variant-b.png`）——地面没画 |
| 整图躺平、不画高格 | 丢立体与挖放反馈（变体 a 虽好看但建筑压平） |
| three.js 重写 | §7 |

### 3.3 一个可以省掉 14000 次绘制的捷径（可选）

因为 `gid == y*140 + x + 1`，**整张源图就是地图本身**。取全局像素坐标
`X = 16x + u`、`Y = 16y + v`，代入 §3.1 的投影：

```
16x - 16y + u - v        = X - Y
8x + 8y - 8 + (u+v)/2    = (X + Y)/2 - 8
```

⇒ 对**同一高度**的所有格子，整图可以用**一次** `ctx.transform(1, 0.5, -1, 0.5, ...)`
+ 一次 `drawImage` 精确画完，与逐格绘制逐像素等价。

但地图里 h=0（水，1112 格）与 h=1（陆，5515 格）是**交错**的，而两者的
`isoProject` 垂直位移差 `HH = 16px`。所以捷径只在「所有格子同高」时成立。
（实测：h==0 的 1112 格 collision 全为 0，h==1 的 5515 格中 3947 可走、1568 是土坎。）
**不能**改成「先画全部 h=0、再画全部 h=1」——`depthKey` 是 `(x+y)*1024 + y`，
与 h 无关，两层在深度序上是交错的，分层绘制会破坏遮挡。

⇒ **默认不走捷径**，保留逐格绘制以维持现有遮挡与水面台阶；
若实测性能不足，再评估「整图一次 warp + 只重画水面格」。

### 3.4 会被打红的既有测试（必须一起改）

| 测试 | 为什么红 | 怎么改 |
|---|---|---|
| `iso-terrain.test.ts:363` 「shares a fixed height texture across differently colored cells」 | 它**钉的正是要被拆掉的设计**：h=2 的所有格子共用一张 `iso-block-2`，靠 `setTint` 区分。烘焙后每格顶面用自己的图块，共用纹理不成立 | 改成断言「不同 gid 的 h=2 格子**不**共用顶面纹理」，并保留侧面暗化仍按色走 |
| `iso-terrain.test.ts:171-174` `sampleTileColor` 四连断言 | 函数本身不删（收窄为算侧面暗化色），**断言不用动** | 不动 |
| `iso-terrain.test.ts:384` 「uses the resulting stone layer for a dug high column」 | `setTint` 期望值会变（侧面暗化色算法保留则不变，需实测） | 跑一次确认；若变，改成按新暗化口径断言 |

> 判定原则：**测试钉的是旧实现细节还是旧行为？** 上面第一条钉的是实现细节
> （「共用一张纹理」本身不是用户可见行为），所以该改；第三条钉的是行为
> （挖掉树冠层后显示石层），不该改——只更新期望值。

### 3.5 硬约束

- **不碰协议、不碰后端**：`MapStatic.ground` 已是真 gid，前端自足。
- **注意两个同名不同值的常量**：`iso-terrain.ts:6` 的
  `GROUND_KEY = 'iso-ground-composite'` 与 `WorldScene.ts:82` 的
  `GROUND_KEY = 'ground-composite'`（后者只在 flat 模式用）。名字一样、值不同，
  **别在重构时「统一」成一个**——等距与平铺是两套互斥的底图。
- **`pickGround`/`pickVoxel` 逐字不动**：拾取是事故高发区（三次历史事故）。
- **不变量**：`walkable ⇒ h==1` 保持。
- 性能：绘制次数与现状同量级（14000 次 `drawImage`，源是同一张已解码的图，
  无逐格 `getImageData`——这比现在的 `sampleTileColor` 路径**更省**，
  因为它不再对每格做 16 次像素读取）。
- **`redraw` 是全量重绘**，触发点有两处：地图对象/尺寸变化（`sync` 第 166 行判断）
  与 **窗口 resize**（`WorldScene.ts:272` 的 `scale.on('resize')`）。
  逐帧路径走的是 `sync` → `updateSurface(..., full=false)` → `paintGround(dirty)`。
  `paintTile` 必须与 `paintBlock` 同样支持 dirty 矩形裁剪，否则 resize 拖拽时
  会变成每帧 14000 次全量重绘。

## 4. B｜后端（codex 树，复杂/跨层）

### 4.1 气味（B1，小改 → 主树）

三处都要动，缺一条就不成立：

1. **源强度** `SMELL_SOURCE_STRENGTH: 1.0 → 0.04`（`smell_world.py:20`）。
2. **独立门槛** `PerceptionProfile` 增 `smell_floor: float = 0.08`，`senses.py:323`
   不再复用 `hearing_floor`（0.04 对嗅觉低了一个数量级）。
3. **文案阈值重定标** `narrate_smell`：现档位 2.0 / 0.5 / 0.1 是为旧强度设计的，
   新强度下最高才 0.54，全部会落进「说不清的味道」。

**门槛必须与最低档重合（0.08）**——否则会出现「过了门槛却落不进任何档」的死区。
这是设计约束，不是巧合：`smell_floor` 就是「隐约」档的阈值。

定标依据（实测，见上引脚本）：

| 口径 | strength=0.04 / floor=0.08 |
|---|---|
| 独行者 1 人 | **0.063** ⇒ 不触发 |
| 稀疏 10 人 | 中位 0.063 / max 0.066 ⇒ **0/10 触发** |
| 聚集 50 人 | min 0.168 / p5 0.227 / 中位 0.350 / p95 0.416 / max 0.430 ⇒ **50/50 触发** |

实测分档（聚集 50 人，min 0.168 / max 0.430）：
**「明显」39 人 / 「说不清」10 人 / 「隐约」1 人**，
最高档「浓重」无人命中——那档只留给将来的 matter 源（尸体/食物堆，M3）。

⇒ 语义正确：**人挤人的地方才有味道，一个人走路闻不到**。
若把强度取 0.03，拥挤场景会掉到 0/50（人群也不触发）；取 0.05 则独行也可能
擦到 0.08（取决于站位）。0.04 让「聚集可闻、独行不可闻」同时成立。

#### 会被打红的既有测试（必须一起改，不能靠调门槛绕过）

`sim/tests/test_m2_smell_wiring.py::test_frame_contains_smell_observation`
用两人相距 1 格（(10,10) / (11,10)）的夹具断言「帧里必须有嗅觉观测」。
实测该夹具在新强度下浓度只有 **0.0196**（旧强度 0.49），远低于任何合理门槛。

⇒ 这是**测试夹具的设计问题**，不是实现问题：一格之外的一个人**本来就不该**
让人闻到味道。改法是把夹具改成真实密集场景（≥5 人同格聚集），
而不是把门槛降到 0.02——后者等于把「独行也闻得到」这个 bug 又装回去。

另：同一观察者的气味观察做**跨帧新鲜度抑制**（同档文案不连续重复）。
`_select_raw`（`salience.py:42`）已经按 subject 去重，所以**同一帧内**不会重复；
但感知每帧重算，`frame.narrated()` 会逐帧产出同一句 ⇒ 面板里连续刷同句话。
抑制放在叙事层，不改显著性规则。

**落点必须是 `main.py:537` 的 `_narrated_cache`，不是 `frame.narrated()`。**
理由：`PerceptionFrame.narrated()`（`frame.py:55`）是**纯的、无状态的**
pydantic 方法（`model_config = ConfigDict(frozen=True)`），帧本身每拍重建，
所以它**没有任何地方可以记「上一句说过什么」**——想在它里面做抑制，
就必须给它塞一个可变参数，那会污染一个被大量测试直接调用的纯函数。

而 `main.py:537` 已经有现成的按人缓存：

```python
_narrated_cache: dict[str, tuple[Any, str]] = {}   # npc_id → (frame, text)
```

它按**帧对象身份**缓存（`cached[0] is frame`），帧一换就重算。抑制只需
把它从「帧变了就重算」升级为「帧变了也先比一下上一句」：

| 项 | 口径 |
|---|---|
| 状态 | `dict[npc_id, tuple[frame, last_smell_line, repeat_count]]` |
| 抑制对象 | **只压嗅觉那一句**（内感受/视觉/听觉照常逐帧出） |
| 「抑制」的含义 | 第 2 次连续同句 → 换成省略式（`「那股味道还在。」`）；≥3 次 → 整句不出现（回落到「四周很安静。」若帧内无他物） |
| 重置时机 | `_narrated_cache.clear()`（`main.py:1257` 读档/换分支）已经天然覆盖 |
| 谁调用 | **陈默与 NPC 共用同一个 `_hidden_context`**（`main.py:548`），所以抑制对两边同时生效，不需要两套 |

> ⚠ 不要把它做成「按 tick 计数」：`frame.tick` 是戏内坐标，抑制状态必须
> 跟着帧身份走而不是跟着 tick 走，否则重放/快进时会出现「历史里本该重复
> 的那句被吞掉」，破坏 replay 面。
>
> ⚠ 也不要写进 `Observation` 或 `salience` 排序：显著性只决定「选不选它」，
> 「说过几遍」是叙事层的事实，混进去会让 M1 的显著性基线整体漂移。

### 4.2 NPC 活动范围 + 建造四层阻断（B2，复杂 → codex）

#### 先看现状有多塌

`_TERRITORY_EAT / _TERRITORY_REST / _TERRITORY_WORK`（`sim_exec.py:179-204`）
15 个槽位里只有 **6 个不同格子**：

| 片区 | eat | rest | work | distinct |
|---|---|---|---|---|
| 村广场 (100,52) | (100,53) | (100,53) | (72,52) | 2 |
| 桃门 (15,18) | (15,19) | (15,19) | (15,19) | **1** |
| 溪桥 (66,19) | (66,20) | (66,20) | (66,20) | **1** |
| 客栈院 (44,53) | (44,54) | (44,54) | (44,54) | **1** |
| 梯田 (122,19) | (121,20) | (121,20) | (121,20) | **1** |

四个片区的吃、睡、干活是**同一格**，再套上 `_SITE_SCATTER_RADIUS=4` 的散点、
`_WANDER_RADIUS=6` 的闲逛 ⇒ 50 人实际只在 **6 个格子**周围转。
10 个地标里有 **4 个（祖屋/村塾/钟山/藏书房）从来没被任何动作指向**。

> 注意 D16 的历史包袱：定籍制是上一轮用户验收「npc 在一部分区域乱走，
> 让每个 npc 在固定区域呆着」的**修复**。这次要放宽，必须**不是**退回随机游走
> ——否则会重新触发那次验收的失败。

#### 改法

1. **地标表**：`linhe-town.json::_landmarks` 的 10 个地标坐标**全部实测可走**
   （已逐格验证），且都是单格：

   | key | 坐标 | 中文名 |
   |---|---|---|
   | `peach_gate` | (15,18) | 桃门 |
   | `ancestral_hall` | (40,18) | 祖屋 |
   | `stream_bridge` | (66,19) | 溪桥 |
   | `old_school` | (93,19) | 村塾 |
   | `terraced_fields` | (122,19) | 梯田 |
   | `signal_hill` | (18,52) | 钟山 |
   | `guest_yard` | (44,53) | 客栈院 |
   | `craft_market` | (72,52) | 染坊市集 |
   | `village_square` | (100,52) | 村广场 |
   | `archive_room` | (124,52) | 藏书房 |

   中文名现在**硬编在 `sim/api/main.py:1080` 的一段字符串里**，只列了 6 个，
   **漏了 5 个**（祖屋/村塾/钟山/藏书房，以及村广场——它被「药铺（100,53）」
   顶替了，而药铺**不是** `_landmarks` 里的条目，是另一个坐标）。
   ⇒ 建立单一来源 `sim/content/landmarks.py`（key → (x,y) + 中文名 + 语义标签），
   `main.py` 的 `_landmarks` 与 `_site_anchor_of` 都从它生成，**不再硬编**。

   ⚠ 改这段文案**没有测试钉**（全树对「你知道这些去处」零命中），所以它是
   「改了没人拦、不改正悄悄少 5 个去处」的一类。落地时必须补一条断言：
   `landmarks.py` 的条目数 == `linhe-town.json::_landmarks` 的条目数。

2. **目的地改由「职业 × 地标」决定**，不再由片区决定。

   ⚠ **只有 8 个职业，但有 10 个地标**（`villagers.py:133` `OCCUPATIONS` 是
   农人/商贩/匠人/渔夫/樵夫/伙计/杂役/艺人，**没有书生**——上一版本文档
   错写了书生，实际不存在）。所以「职业→地标」映射**必然有 2 个地标没人用**，
   必须显式指定是哪两个，而不是留给实现者随手补：

   | 职业 | 主地标 | 次地标（错开时段用） |
   |---|---|---|
   | 农人 | 梯田 (122,19) | — |
   | 商贩 | 染坊市集 (72,52) | — |
   | 匠人 | 染坊市集 (72,52) | 祖屋 (40,18) |
   | 渔夫 | 溪桥 (66,19) | — |
   | 樵夫 | 钟山 (18,52) | — |
   | 伙计 | 客栈院 (44,53) | — |
   | 杂役 | 藏书房 (124,52) | 村广场 (100,52) |
   | 艺人 | 村广场 (100,52) | 桃门 (15,18) |
   | **（空置）** | **村塾 (93,19)** | **（无人）** |

   `村塾` 空置的理由：它是唯一「室内/文教」语义的地标，8 个职业里没有对位者。
   **不要为此新增「书生」职业**——`OCCUPATIONS[i % len(OCCUPATIONS)]`
   （`villagers.py:171`）是按名册序轮转分配的，插入一项会让**所有现存世界**
   的每个村民职业整体错位一位（读档后同一个人从农人变商贩），是存档兼容破坏。

   ⇒ 村塾先作为**纯视觉地标**（A 会把它画出来），B2 不动它；若将来要让它有
   NPC，应该走「新增职业并同时给旧世界做职业迁移」的单列轮次。

3. **`_site_anchor_of` 的签名可以一个字都不改。** 这是本节最省的地方：
   - 职业是 `npc_id` 的**纯函数**（`villagers.py:171` 的 `i % len(OCCUPATIONS)`，
     `npc_id` 就是 `villager_01`…`villager_50`），不需要注入 profile；
   - 时段已经由 `sim/npc/schedule.py:35` `current_slot()` 转成**动作**了
     （DAWN/DAY/DUSK/NIGHT → wander/work/wander/rest，艺人白天→request_chat，
     商贩集市日→market），而 `_site_anchor_of` 收到的正是 `action`。

   ⇒ 把「片区→单格」三张表换成「`(occupation, action)` → 地标」一张表即可，
   函数仍是 `(action, npc_id) → (x,y)` 的纯函数，**12 个调用点和 6 个测试文件
   都不用动**。这直接消掉了「要不要给 `_site_anchor_of` 传 day_phase」的整场争论。

4. **`home_base_of` 保留**，但降级为「夜里回哪睡」——不再是所有动作的锚。
   注意 `home_base_of` 仍被 `villagers.py:209` 的出生点逻辑与 `_chat_target_of`
   （本区化聊天）使用，**不能删**。

5. **闲逛**：`wander_near` 的 home 从「片区锚点」改为「当前位置所在的片区」，
   半径按片区尺度放宽；仍保留「归巢」语义防止累积漂移。

6. **散点半径**按新地标邻域的可走格数复核（现在 4 是为一格锚点定的）。
   注意 `_SITE_SCATTER_RADIUS=4` 同时被**到站判定**使用（`sim_exec.py:493`
   规划侧、`:678` 需求回写、`:693` 工钱发放，三处都是
   `dist <= _SITE_SCATTER_RADIUS`）：调大它会让「离得很远也算到站」，
   到站即回写需求/发工钱。**目的地半径与到站半径要拆成两个常数**，
   否则放宽活动范围会连带放宽需求回写。

#### 建造四层阻断

1. **决策层** `_GAIN`（`utility.py:37`）给 build 一个非零增益。
   ⚠ 不能只加一个常数：`_GAIN` 是「需求×动作」矩阵，build 不满足任何需求。
   正确做法是给 build **单独的条件分**（有闲钱 + 有空地 + 无更高紧迫需求），
   在 `scores` 组装之后叠加，而不是塞进矩阵。

   ⚠ **这个分数算不出来在 `NpcRuntime.tick` 里**——它的签名只有
   `hidden_states / context_of / chat_cooldown_until / action_overrides`
   （`runtime.py:81-90`），**拿不到 `CoinLedger`，也拿不到 `Pathfinder`**
   （选空地要查可走格）。而 `npc_events_for_tick`（`sim_exec.py:535-555`）
   两者都有（`pathfinder` 是位置参数，`coin_ledger`/`build_runtime` 是关键字参数）。

   ⇒ **条件分的注入点必须是 `npc_events_for_tick`，不是 `runtime.tick`**：
   在它调 `runtime.tick` 之前，先按「余额 ≥ 成本」过滤出一份
   `action_overrides`-式的允许集，或把 build 的条件分作为参数传进 tick。
   现有 `action_overrides: Mapping[str, str]` 只能**改动作名**、不能改分数，
   所以要新增一个入参（例如 `bonus_of: Mapping[str, Mapping[str, float]]`）。
   这是本节唯一需要改 `runtime.tick` 签名的改动，改动点集中在一处。

2. **参数层** `runtime.py:176` 的 `params` 只从 `d.scores` 取键，永远产不出 `x/y`。
   需要在 `NpcRuntime` 决策输出里**显式带选址**（选一块附近可走 2×2 空地），
   让 `sim_exec.py:653` 的 `set(params) == {"x","y"}` 真正成立。

   ⚠ 但选址同样需要 `Pathfinder`——见上条，选格必须发生在
   `npc_events_for_tick` 层，**不能**放进 `runtime.tick`。实现口径：
   `runtime.tick` 只决定「这拍选 build」并留空 params，由
   `npc_events_for_tick` 在写 `npc_act_event` 之前补上 `x/y`。

3. **资金层** 创世不发 `coin.grant`，盖棚要 40 文，`work` 到站才发 5 文。
   ⇒ 必须给村民起始资金，**且严格小于 40**（否则第一天全村同时盖棚）。
   建议起始 10–15 文（干 5–6 天活才够盖第一间）。

4. **并发层（新发现的第四层阻断）** `BuildRuntime.start` 在
   `self._site is not None` 时**直接返回 None**（`build_exec.py:124-125`）——
   全镇同一时刻只允许一个工地。而 `build_action_events`（`build_action.py:20-38`）
   的失败路径是「先扣后退 + 一句独白」：

   ```python
   if not ledger.apply_grant(npc_id, -cost, tick=tick): ...   # 钱不够
   started = runtime.start(...)
   if started is None:
       ledger.apply_grant(npc_id, cost, tick=tick)           # ← 只改内存
       return say("这块地使不得了，另寻去处吧。")
   ```

   ⇒ 只要有工地在建，**每个选了 build 的 NPC 每拍都会吐一句
   「这块地使不得了」**，50 人 × 3 游戏日 = 大量独白噪声（正是 §4.1 那类
   「刷同一句」问题）。必须在**决策层**就知道「已有工地在建」⇒
   把 `build_runtime` 的「是否有在建工地」也作为条件分输入
   （`build_runtime` 已在 `npc_events_for_tick` 的签名里，第 550 行）。

   ⚠ **同时这是个 C4 违规**：失败回滚 `apply_grant(+cost)` 只改内存余额，
   **不发事件**；而成功路径发的是 `coin_grant_event(-cost)`。
   于是重放 `restore_from_events`（`economy.py:65`）后余额**对不上实况**——
   实况里扣了又退（净 0），事件流里只有「成功那笔」。
   修法：回滚也必须发 `coin_grant_event(+cost, note="build:refund")`，
   或干脆**先调 `runtime.start` 再扣钱**（把失败前置到不花钱的地方）。
   推荐后者：`start` 是纯内存检查，先试后扣最省事件。

- **止损**：`build_action_events` 已有失败退还工料与戏内文案，沿用（但要按上条修）。

### 4.3 材料闭环（B3，协议 1.14 → 1.15 → codex）

**核心：材料必须成为格子的属性，而不是高度的函数。**
事件层与出站层**早就准备好了**，缺的是运行时把它们当真值用：
- `VoxelEditedPayload` 已有 `material_id`（`sim/core/events.py:171`）
- `_voxel_bad_target` 已有三种材料的文案（`ws.py:913-918`）

所以这条的改动面比看起来小：**入站请求 + 运行时材料表 + 客户端选材**。

1. **入站请求**：`VoxelRequestFields` 增可选 `material: Literal["earth","stone","wood"]`，
   仅 `place` 有意义；缺省回落 `earth`（旧客户端行为不变）。
2. **放置**：`place` 扣的是**请求的**材料（不是目标格高度推出来的）；
   该格材料记为 `material`，高度按材料定（earth→1、stone→2、wood→3，不得超 3）。

   ⚠ **副作用必须写进验收**：`place` 只允许可走格（h==1）。放石后 h=2，
   `_edit` 里 `gid = 0`（`voxel_exec.py:199`）⇒ `TILE_CHANGED` 让该格**变成阻挡**。
   于是该格之后不能再 `place`（`is_walkable` 已 False），只能 `dig` 回来。

   推演闭环：放石 → 阻挡 → 只能挖 → 挖出石料 → h=1 且 gid 恢复 → 又能走。
   **这是预期行为**（石头垒起来当然挡路），但玩家会「咦我怎么过不去了」——
   所以 B3 的验收要显式测这一条，且 UI 上放石前该格应已标为阻挡预览。
3. **挖掘**：`dig` 产出的是**该格记着的材料**，不是 `_MATERIAL_BY_HEIGHT[当前高度]`。
   `_heights` 旁边要有一份 `_materials: dict[(x,y), material]`，与 `_observe_height`
   同源从 `VoxelEditedPayload.material_id` 恢复（含读档）。
4. **不变量校验**：`walkable ⇒ h==1` 保留，但新增
   `h==1 ⇒ material == earth`——`_edit` 里现成的 `gid <= 0` 检查（`voxel_exec.py:200`）
   已经隐含这层，只需把材料一起钉死。

> 修 ④' 是这条的副产物：放土后挖回来产出的是土，不是石。若不修，
> 材料闭环反而会把「凭空造石」变成一条**玩家可稳定刷的石料生产线**。

5. **客户端选材**：`WorldScene.ts:445` 现在右键只发 `{action:'place', x, y}`。
   需要增加**当前选中的材料**——最省的做法是用 HUD 里已有的三材料行做选择器
   （`voxel-mirror.test.ts:114` 已证明 `voxel_state.inventory` 支持三材料）。
   材料不足时该行不可选（服务端仍会拒，但别让玩家点了才知道）。
   默认选中 `earth`，保持旧手感。
6. **下行投影也要带材料**：`sim/api/voxel_view.py` 的行只有
   `{x,y,action,gid,height}`（`set_voxel_edit`，第 14 行），客户端
   `world-mirror.ts:204` 的 `applyVoxelEdits` 也只校验这五个字段。
   ⇒ 行里加 `material`，客户端 `VoxelEdit` 类型跟着加（**可选字段，缺省 `earth`**，
   保证旧快照仍能读）。

   ⚠ `apply_voxel_events` 的 `TILE_CHANGED` 分支（第 49-53 行）重建行时
   **只透传了 `action` 和 `height`，材料会在这里丢掉**。这条必须一起修，
   否则结构建好/塌掉时该格的材料会被重置成默认值。

   **不加上行的话**，重连后客户端不知道该格是什么材料，再挖一次就会按高度
   重新推断——④' 会在重连路径上复活。
7. **协议落点同改**（实测**八处必须改 + 三处不动**，1.14 现状）：

   | # | 落点 | 性质 | 改？ |
   |---|---|---|---|
   | 1 | `sim/api/ws.py:91` `_PROTOCOL_VERSION` | 代码常量（信封 `v`） | **改** |
   | 2 | `client/src/net/ws.ts:52` `PROTOCOL_VERSION` | 代码常量（前端信封） | **改** |
   | 3 | `sim/api/main.py:1458` `app = FastAPI(..., version="1.14")` | **OpenAPI `info.version` 的来源** | **改** |
   | 4 | `shared/openapi.json:5` `info.version` | 快照（codegen 唯一真相源） | **改** |
   | 5 | `sim/tests/test_protocol_version.py:36` `EXPECTED_VERSION` | 钉（同时校验 3/4） | **改** |
   | 6 | `docs/api/versioning.md:12` §1「当前基线」+ §7 追加登记行 | 正文 | **改** |
   | 7 | `docs/api/ws-protocol.md:25` §2「当前协议 1.14」正文 | 正文 | **改** |
   | 8 | `README.md:5` 徽章 | 正文 | **改** |

   第 3 条是最容易漏的：`main.py:1458` 的 `version=` 就是
   `test_live_openapi_version_matches_the_envelope_version` 校验的对象，
   它与 `ws.py:91` 是**两个独立常量**，只改一个测试立刻红。

   **三处不动**（是历史事实，改了就是伪造记录）：
   - `docs/arch/audio.md:4`「协议仍为 1.14」——当时的时点陈述；
   - `docs/perf/bench-plan.md:121,177,179` 的「档位比 1.14」——基准机档位，与协议无关；
   - `docs/perf/baseline-epyc7763.json:1947` 的 `1.1411999...`——一个测量值。

   **两处要按性质判断**：
   - `docs/arch/voxel-execution-spec.md:127`「协议 1.14 起…直接使用服务端提交的
     height」——**现行规则描述**，加 `material` 后必须同步扩写。
   - `sim/core/events.py:169` 注释「Height-less pre-1.14 rows remain readable」
     ——历史兼容说明，**不改**（1.15 后它描述的仍是事实）。

   **测试里另有 4 处硬编 `"1.14"` 字面量**（`test_e7_ws_structures.py:15`、
   `test_voxel_gateway.py:33,240`、`test_voxel_protocol.py:16,58`）——
   它们钉的是「信封 `v` 与快照 `info.version` 一致」，**必须一起改**，
   否则 1.15 落地后 5 条断言直接红。

8. **OpenAPI 源与生成物**——这里有个**方向性错误必须先纠正**：

   `tools/gen-protocol.ts` 头部明写「唯一真相源 = mock 快照 `shared/openapi.json`；
   `--src` 切真实源**暂缓**」（`docs/api/codegen.md` §4.1 有完整声明：
   sim 真实 OpenAPI 缺 21 个 HTTP 子结构 schema、无 WS 消息 components，
   切真实源会丢契约）。**所以不是「改 `openapi_ext.py` 然后跑 codegen」**——
   codegen 读的是快照，`openapi_ext.py` 改了也不会进 `shared/protocol.ts`，
   `gen:protocol:check` 还会保持绿（因为两边都没变），于是 `material`
   永远不会出现在前端类型里。

   正确顺序是**手改两处、让它们保持相等**：
   1. `sim/api/openapi_ext.py:558-567` 的 `VoxelRequestMessage` 加
      `material`（可选，**不进 required 列表**）；
   2. `shared/openapi.json` 的同名 schema **手写**加同样字段（**不进 `required`**）；
   3. `npm run gen:protocol` 重生成 `shared/protocol.ts`；
   4. `npm run gen:protocol:check` 必须绿。

   > 第 2 步不能省、也不能靠生成：`sim/tests/test_voxel_protocol.py:19` 与
   > `test_protocol_version.py:69` 都断言 **live schema == 快照 schema**。
   > 只改 `openapi_ext.py` 会让这两条测试红；只改快照会让 live 端红。
   > **两边手改到逐字相等**才是唯一通过路径（这也是 `docs/api/codegen.md:108`
   > 「三者同一次提交」的实际含义）。

> ⚠ **1.15 的登记必须显式推翻 1.13/1.14 的两句话**，否则文档自相矛盾：
> 1.13 写「放置消耗**目标格**对应材料」，1.14 写「按**当前高度**扣料」。
> 1.15 改为「按**请求指定的**材料扣料」。versioning.md 的表格是追加式的，
> 新行不会自动作废旧行——**要在新行里点名「覆盖 1.13/1.14 的扣料口径」**。

### 4.4 LLM 动作面（B4，小改 → 主树）

> **订正（2026-11-05，核实源码后）：`wait` 已经有执行器了，不需要补。**
> `execute_pending`（`driver.py:300-372`）的**末尾独白分支**是兜底路径：
> 任何动作只要不在 `("buy","sell","build","attack")` 的排除元组里，都会走到
> `loop.enqueue(npc_monologue_event(...))`。`wait` 正是这样被覆盖的——
> 它不进任何 `elif` 分支，直接落到尾部独白。
> 且有测试钉住：`test_m4c_llm_driver.py::test_wait_intent_no_move`
> （「wait 意图：无位移，仍产 thought 独白」，实测 **1 passed**）。
>
> ⇒ 上一版本文档写的「`wait` 无执行器」是**错的**。B4 的实际范围因此缩小为：
> 坐标尺寸订正 + `take`/`give` 的静默落空（本轮不动）。

现状的四层不一致（`take`/`give` 能过前两层、死在第三层且无声）：

| 层 | 位置 | 含 take/give？ | 含 wait？ |
|---|---|---|---|
| 解析 schema | `intent.py:12` `IntentAction` | 是 | 是 |
| 闸门白名单 | `gate.py:33` `M1_SUPPORTED_ACTIONS` | 是 | 是 |
| **prompt 输出契约** | `assembler.py:31` `_REQUIREMENTS_TEXT` | **否** | 是 |
| **执行器** | `driver.py:333-372` | **否**（落到尾部独白，零副作用） | **是**（尾部独白，已测试） |

⇒ 模型被 prompt 约束不会主动输出 take/give，但**一旦输出**（模型不听话、或
未来改了 prompt），它会通过解析、通过闸门、落进 `_pending`，然后在
`execute_pending` 里**静默什么都不做**——只落一条 reason 独白。

改动：
1. `_REQUIREMENTS_TEXT` 的「镇子是 96×96」→「**140×100**」。
   （附带：同段的 `params` 说明只提 posture，build 需要 `target_pos`，
   契约里已写「要去的地点或要施工的地块」——这条不用改。）

   ⚠ 全树提到「96×96」的有 **6 个生产/测试文件**（另加本文档自身），
   **只有 `assembler.py` 这一处要改**：

   | 文件 | 性质 | 改？ |
   |---|---|---|
   | `sim/llm/prompts/assembler.py:35` | 喂给模型的**事实陈述**，且是错的 | **改** |
   | `sim/api/ws.py:894` | 旧 Zelda 图名的兼容说明 | 不改 |
   | `test_e1_talk_to.py:17` / `test_m4d12_disperse.py:31` / `test_m4d16_territory.py:55` / `test_m7_time_block.py:178` / `test_m7_town_map.py:6` | 历史注释（「旧图随 D10 退役」） | 不改 |

   判据：**看它是「描述现在」还是「记载过去」**。前者错就要改，后者改了就是伪造历史。
2. ~~`wait` 补执行器（无事件，只落 reason 独白）。~~ **已存在，不需要做**
   （见本节开头的订正；`test_wait_intent_no_move` 已钉）。
3. `take`/`give` **本轮不动**（用户 2026-11-05 裁定：单列下一轮，见 §9）。
   保留现状 = 它们仍在 `M1_SUPPORTED_ACTIONS` 与 `IntentAction` 里、
   仍会在 `execute_pending` 里静默落空。**这是已知的、被显式接受的技术债**，
   不是漏做。第 4 条的集合差测试因此要**排除这两项**，
   否则测试一落地就是红的。

   > 下一轮再定方向时的完整代价（复核已量化，直接可用）：
   > `take`/`give` 出现在 `gate.py` 的**三个校验分支**（第 87 行 `missing_target`、
   > 第 138 行 `target_gone`/`target_out_of_range`），且
   > `sim/tests/fixtures/errands.py` 有 **3 条夹具**依赖它们：
   >
   > | 夹具 | 类型 | 含 |
   > |---|---|---|
   > | `E08_捡拾_路上` | 单差事 | `expected_actions={"take","investigate","move_to"}` + 脚本 `{"action":"take"}` |
   > | `E10_还钱_欠账` | 单差事 | `expected_actions={"move_to","talk_to","give"}` + 脚本 `{"action":"give"}` |
   > | `C03_集市日_购木修栏` | 差事链 | 第 2 步 `{"action":"take"}`，`expected_actions={"take","move_to"}` |
   >
   > 而 `ERRAND_COMPLETION_RATE_MIN = 1.0`（`errands_rate.py:29`，**100%**，
   > 设计说明明写「确定性夹具无随机源，缓冲只会让真实回退静默通过」）。
   > ⇒ 删 `take`/`give` 后这 3 条**必然失败**，T5 基线（`test_m1_metrics.py`
   > 20 条、`test_golden_full.py` 4 条链）的 `errand_completion_rate` 会从
   > 1.0 掉到 0.85/0.75，**golden 基线需要重新登记**。
   >
   > 两个方向的规模：**删**要改 3 条夹具 + 重登记 T5 golden（契约变更）；
   > **补**要新建拾取/转移执行面（物体实体化、进背包、持有关系，动 `WorldState`），
   > 工作量大于 B4 其余三项之和。

   ⚠ 无论选哪个，`gate.py:87/138` 的三处元组都要跟着改——漏一处会让
   `take` 从白名单消失但仍能通过 `missing_target` 校验，形成「半删」。
4. 补一条测试：对 `M1_SUPPORTED_ACTIONS` 里**每一个**动作，
   `execute_pending` 都必须有一条能产出事件或独白的分支——
   用集合差断言，防止下次再加动作时又漏执行器。

   注意**反方向也要钉**：`IntentAction`（解析层）与 `M1_SUPPORTED_ACTIONS`
   （闸门层）的差集必须为空，否则会出现「能解析但被闸门拒」的动作
   （现在 `demolish`/`use` 正是这个状态——它们不在白名单但仍在
   `IntentAction` 里，属**有意保留**：模型若输出会得到 `unsupported_action`
   的明确拒绝而不是解析错误。这条边界要在测试里写清楚，别被「集合差为零」
   的断言顺手删掉）。

### 4.5 take/give 材料交接（2026-11-09 波 A）

用户本轮选择**先复用土、石料、木料库存**。§4.4 的「不动」和通用背包估算是
2026-11-05 的历史边界；本次只补既有材料交接，不建立通用物品实体或药品背包。

- `take` 从交接对象的库存取出材料，`give` 把自己的材料交给对象。`target_id`
  沿用现有戏内名称解析、目标存在性和执行距离校验；不能转给自己或伪造归属引用。
- `params.item` 必填，取土/石料/木料或对应已有材料 ID；`params.quantity` 是
  1–999999 的正整数字符串，省略时为一份。缺参数、未知物品或库存不足只给明确的
  失败结果，不猜物品、不凭空补库存。旧规划夹具仍可解析；执行失败不会伪称成功。
- 成功时通过既有 `material.moved` 记录来源、去向、数量，内部 reason 增加
  `take`/`give`；双方归属继续使用 `npc:<entity_id>` 与既有 `material_balances`
  投影。`MaterialLedger` 只是按已应用事件重建的内存读面，不直写 SQL。
- 同帧交接与放置共用可用量约束，不能重复花费。HUD 库存仍在提交成功后更新，
  未提交的收入不能提前放置；启动和历史读档按当前分支谱系恢复双方库存。
- prompt 已列出两种动作与参数，执行结果仅产生一条结果独白。买卖铜钱语义、
  药品库存、地面独立物品实体与协议形态不变，协议仍为 **1.16**。波 B/C 另行执行。

## 5. 分工

| 项 | 树 | 理由 | 复核后的实际规模 |
|---|---|---|---|
| A 等距烘焙 | 主树 | 前端/体验域；离线原型已验证 | 1 文件主体（`iso-terrain.ts`）+ 1 测试改写；`paintTile`/frame 注册是新增机制 |
| B1 气味 | 主树 | 常量 + profile 字段 + 文案 + 缓存抑制 | 4 处代码 + 1 夹具改写 + 新增跨帧抑制状态 |
| B4 坐标/动作面 | 主树 | 文案订正 + 集合差测试 | **已裁定：本轮只做主体**——`96×96`→`140×100` + 集合差测试（`wait` 执行器已存在，不需补）。`take`/`give` **不动**，单列下一轮（见 §9 裁定表） |
| B2 NPC 活动 + 建造 | **codex** | 跨 sim/npc + sim/agent + 内容常量，高复杂度 | 4 层阻断（决策/参数/资金/**并发**）+ 1 条 C4 修复；`runtime.tick` 需增一个入参 |
| B3 材料协议 | **codex** | 协议变更跨 sim + client + shared + 文档 | **八处必须改 + 两处手改到逐字相等**（快照与 `openapi_ext`）；1 条下行投影修复 |

> **B4 的拆分建议**是复核后的结论：`take`/`give` 的「删」会触发 T5 golden
> 基线重登记（阈值 1.0），这不是「小改」的规模。B4 主体（坐标尺寸 + 集合差）仍可在主树当轮做完；`take`/`give` 的执行面决策单独走一轮，
> 因为两个选项都要么改契约、要么新建引擎能力。

## 6. 验收口径

### 6.1 先分清「要不要模型」

当前环境**没有模型 key**（验收报告 2026-11-04 的 ⑪ 就是因此 BLOCKED）。
所以每条验收都要标明它属于哪一档：

| 档 | 含义 | 适用项 |
|---|---|---|
| **无模型可验** | pytest / 浏览器 / 事件表即可判定 | A、B1、B2、B3 |
| **需模型** | 没有 profile+key 就无法判定 | B4 的实机部分 |

> 不要因为 B4 的实机部分验不了，就把整轮报成 BLOCKED——B4 的**代码侧**
> （白名单↔执行器的集合差测试、`96×96`→`140×100`）是无模型可验的。

### 6.2 逐项

- **A**：浏览器实机截图，与 `variant-a/d` 对照；拾取命中率必须复跑
  `real-map-picking` 全套（土坎 **448/448**、可走 **3947/3947**、
  高块 **7141/7373** 不得回退——这三个是第二十二轮实测基线，
  见 codex 树 `.orca/audits/round22-2026-11-04/after.json`）。
  **2026-11-05 主树实测（与基线逐项相同，渲染改动未扰动拾取）**：
  土坎 **448/448**、可走 **3947/3947**、高块 **7141/7373**；
  烘焙目视三档（1440/1024/390）均见真实 tileset（桃花林/草地/石阶/水面），
  无横向溢出、零 pageerror、单 canvas（像素级色彩多样性读不到 WebGL 画布，
  只能靠人工看图，见 SDD 台账 Task 6 裁定）。
- **B1**：复跑 `measure_smell.py` 断言「独行 0 触发 / 稀疏 0/10 / 聚集 50/50」；
  并把等价断言写成 pytest（`.orca/` 不进库，pytest 才是长期回归入口）。
  实机部分：跑一段，确认陈默的处境文本里气味不再每帧出现。
  跨帧抑制单独可验：连拍 5 帧、同一帧内容不变 ⇒ 第 3 帧起该句消失，
  且 `_narrated_cache.clear()` 后立刻恢复（§4.1 的抑制口径）。
  **2026-11-05 主树实测（`SMELL_SOURCE_STRENGTH = 0.04` / `smell_floor = 0.08`）**：
  聚集 50 人 **50/50** 可闻（p5 0.2267 / 中位 0.3504 / p95 0.4159，
  最低 0.1676——离地板仍有 2 倍余量）；稀疏 10 人 **0/10**（中位 0.0632）；
  独行者 **0.0628**（低于地板，不再闻到）。
  另修一条**验收截图中发现的第二重复通道**：`full_snapshot` 的
  `monologue_history` 原被逐条追加，每次重连/读档把心之声与街谈巷议整屏重复；
  改为整组替换后实测 2 次快照各带 7 条历史、两面板 **零重复行**。
- **B2**：3 游戏日（`TICKS_PER_GAME_DAY = 86_400`，加速档下实机跑）内
  `structure.started` ≥ 1 条；NPC 目的地 distinct ≥ 8 个地标；
  **且每个片区内的动作不再全部落在同一格**（用 `npc.act` 事件表按片区统计
  distinct 目的地，旧值 6，新值应显著更大）。
  **另加三条**（都对应本轮新发现的缺陷）：
  - 「另寻去处吧」独白在 `structure.started` 存在期间**必须为 0**
    （§4.2「建造四层阻断」第 4 条）；
  - `coin.grant` 事件流重放后，每个 NPC 的余额 == 实况余额
    （§4.2「建造四层阻断」第 4 条的 C4 修复）；
  - `landmarks.py` 条目数 == `linhe-town.json::_landmarks` 条目数 == 10
    （§4.2「改法」第 1 条，防止文案继续漏 5 个）。
- **B3**：放石 → 得 h=2 石格、行囊 stone −1；再挖 → stone +1。
  **放土再挖必须回土**（④' 的回归钉）。
  **放石后该格必须变阻挡、且不能再 place**（§4.3 第 2 条的副作用）。
  协议 1.15 七处落点一致。
- **B4**：`chenmo.gate_rejected` 中 `unsupported_action` 归零；
  新测试断言「白名单每个动作都有执行分支」（无模型可验），
  **断言集必须排除 `take`/`give`**（本轮不动，见 §9 裁定）；
  **且反向差集钉死**：`set(get_args(IntentAction)) - M1_SUPPORTED_ACTIONS`
  必须**恰好**是 `{"demolish","use"}`（这两个有意保留在解析层、被闸门明确拒；
  实测现状就是这两项，不得多也不得少）；
  **T5 golden 基线不需要重登记**（本轮不删 `take`/`give`，3 条夹具原样保留，
  `errand_completion_rate` 应仍为 1.0——这本身就是一条回归信号）；
  `wait` 已有测试（`test_wait_intent_no_move`，无模型可验，跑 pytest 即可）；
  若要在实机确认，跑一次看 `NPC_MONOLOGUE`——**这条需模型，验不了就如实记 BLOCKED**，
  不许用单测冒充「实机已验证」。

## 7. C｜three.js 自由视角世界（2026-11-06 第二十四轮；2026-11-07 成为默认）

用户要求自由旋转视角观察立体建造，已命中 `voxel-execution-spec.md` §10.2 的启动条件。
主树 `92f435f` 的固定等距地形是历史起点；第二十四轮将 `?terrain=three` 升级为完整世界渲染。
**2026-11-07 用户实机验收通过并裁定切为默认**：不带参数即进 three 世界，
`?terrain=phaser` 退回 Phaser 等距路径。验收覆盖 11 项（世界启动 / 零页面错误 / 235fps /
旋转 / 缩放 / 移动 / 挖掘 / 放置 / 材料选择 / 客户端视野），另修两处缺陷：自己脚下放置
（已修）与出生点默认机位过近（已记录，待调）。

### 7.1 当前实现

| 项 | 结果 |
|---|---|
| 世界画布 | three 路径由单张 canvas 绘制地形、人物、名字、气泡、天气、夜幕与建造提示；React UI 继续复用 |
| 相机 | `PerspectiveCamera`，fov 60°、初始俯仰 12°、请求距离 8 格、方位 225°；跟随主角并避开方块，右键/中键拖动旋转，滚轮缩放 |
| 天空与方块 | 渐变天空、32～80 格雾；每层为 1:1 立方体，沿用共享取色、烘焙面明度，加确定性像素纹理 |
| 人物 | 原古风资源作为 billboard，投影决定远近大小；复用朝向、行走帧、同格偏移、名字避让和气泡逻辑 |
| 拾取 | 编辑用 Raycaster 命中最近 InstancedMesh 实例；移动单独反投影到高 1 可走平面，校验碰撞与高度 |
| 建造 | 整列轮廓、材料高度预览、不可放提示、服务端挖掘进度与移动目标；库存与完成结果仍由服务端决定 |
| 视野 | 欧氏半径 12 + 服务端 Bresenham 逐行移植；同一可见集合控制人物、接触阴影、名字、气泡，目标提示也受视线约束 |

`alignTarget`、`HEIGHT_UNIT` 和 `pixelsPerUnit` 已移除。自由视角不再依赖两张画布对齐。
`cell-appearance.ts`、`tile-color.ts` 与旧 Phaser `voxel-picking.ts` 保持原样；sim、shared、协议 1.15、资源和依赖清单均未改。

### 7.2 拾取与输入的回归证据

- 新移动路径与旧 Phaser 路径使用等价输入对照；真实地图全部 3947 个可走中心点、历史土坎案例、四个相机方向与侧面编辑拾取均有测试。
- 点击移动与编辑保持独立：移动忽略前景遮挡，编辑选择最近方块。真实鼠标验证了移动、长按挖掘、HUD 选材料、右键放置与挖回，旋转不发送编辑请求。
- 输入在每个事件、定时器与帧更新处核对世界版本、连接和文本焦点；旧世界手势仅清本地状态。丢失捕获会结束当前手势，正常松开不会重复取消。

### 7.3 主角视野与验收证据

`render/visibility.ts` 与 `sim/perception/propagation.py::line_blocked` 使用相同端点排除、方向与误差更新规则。
测试从 `profiles/human.py` 读取 `vision_radius=`，钉住常量 12；主角始终可见，受遮挡像素另有仅主角可用的淡轮廓。
名字重复时抑制无法归属的气泡，避免墙后说话者借同名人物泄露。

真实 140×100 地图的出生名册中，主角 `(100,53)` 可见 **10/51**（含主角），与独立 Python 结果一致。
最终复跑以真实鼠标移动至 `(99,53)` 后，可见 **2/57**，其中附近四名 NPC 被墙遮挡；同一地图和人物快照的 Python 逐人判定完全一致。
这关闭的是客户端人物视野，服务端仍未发射 perception 帧。

最终客户端门禁：**75 文件 / 537 测试通过**，tsc、eslint、prettier、协议生成一致性检查和生产构建均通过。
独立审查发现的两项输入问题已用失败回归测试复现并修复。
原始日志、私有库脚本、截图和逐阶段记录保留在 `.orca/audits/round24-2026-11-06/`；
截图包括 `e-observer-three-desktop.png`、`e-observer-three-orbit.png`、`e-observer-three-1024.png` 与同视口 `e-observer-default-phaser.png`。
测试后端的世界、锚点、配置库均隔离，未访问真实存档，也未调用付费模型。

### 7.4 实测教训

1. `lookAt()` 后必须更新世界矩阵；透视 resize 只更新 aspect 和投影矩阵。
2. 保留烘焙顶点明度，避免原 Lambert 方案明显偏暗。方块高度现在为真实单位立方体，不再使用旧等距压缩系数。
3. 近墙会遮住跟随相机或主角，采用相机避碰与仅主角轮廓；建造预览最后绘制以保证近处可读，几何位置仍在世界空间。
4. 浏览器测试须使用真实鼠标；Vite 热更新后，读取镜像必须导入页面实际加载的模块 URL，含时间戳。测试期间不编辑产品源码。
5. `setPointerCapture` 首先设定待生效捕获；原生捕获丢失补测先等待实际 `gotpointercapture`，再释放并检查可信浏览器事件。

### 7.5 仍未完成的部分

- 用户的主观观感、操作手感和默认切换尚未验收；本线程未附参考原图，未声称完成逐像素对比。
- 房屋仍为 h=2 实心结构块；有简单接触阴影，未实现动态光照投影、水波和结构塌落动画。
- 审查 Minor 暂缓：渲染器仅在创建时读取 DPR，跨显示器或浏览器缩放后未主动刷新；CSS 坐标拾取正确，画面清晰度和 GPU 分配可能沿用旧值。
- 构建保留大于 500 kB 的 chunk 警告：主 JS 约 2.309 MB，gzip 约 572 kB。不同硬件帧率、长期 GPU 资源增长和音频听感未作验收。
- 不增加感知出站，不做夜间视距修正、听觉/嗅觉文案或视距外地形消失；任意垂直层叠、take/give 与健康演进均不在本轮范围。

## 8. 实施陷阱清单（逐条都是本轮实测出来的，不是推测）

| # | 陷阱 | 后果 | 出处 |
|---|---|---|---|
| 1 | 按屏幕坐标**反解** (u,v) 画菱形 | 只画出半个菱形（三角栅格） | 本轮 `iso_variants.py` 第一版实测 |
| 2 | 高格逐格建 canvas | 49 MB GPU + 7373 纹理对象，draw call 爆 | §3.1 实测 |
| 3 | 把 `paintGround` 的对角线遍历改成行列序 | 遮挡关系全乱 | §3.1 第 2 条 |
| 4 | 只烘焙 h<2 的格子 | 高格下面是黑洞 | 变体 b |
| 5 | 按「先 h=0 再 h=1」分层绘制 | `depthKey` 与 h 无关，遮挡破坏 | §3.3 |
| 6 | 编辑格不重绘（脏检测只看 color） | 挖过的格仍显示原图块 | §3.1 第 5 条 |
| 7 | `smell_floor` 与文案最低档不重合 | 「过了门槛却落不进任何档」的死区 | §4.1 |
| 8 | 为了救旧测试把 `smell_floor` 降到 0.02 | 「独行也闻得到」的 bug 装回去 | §4.1 |
| 9 | 只在 `runtime.py` 加 x/y 而不改 `_GAIN` | build 仍选不上，params 永远到不了执行面 | §4.2 |
| 10 | 创世给 ≥40 文起始资金 | 第一天全村同时盖棚 | §4.2 |
| 11 | 材料只写入站不写下行 | 重连后按高度重推，④' 复活 | §4.3 第 6 条 |
| 11b | 忘了放石会封死该格 | 玩家「我怎么过不去了」，且验收漏测 | §4.3 第 2 条 |
| 12 | `TILE_CHANGED` 分支不透传 material | 结构建好/塌掉时材料被重置 | §4.3 第 6 条 |
| 13 | 按 grep 命中数批量替换「96×96」 | 改坏历史叙述与存档兼容说明 | §4.4 |
| 14 | 只加执行器不钉集合差 | 下次再加动作又漏执行器 | §4.4 第 4 条 |
| 15 | 协议只改两处代码落点 | 漏掉 `ws-protocol.md:25` 正文与 README 徽章 | §4.3 第 7 条 |
| 16 | 改 `openapi_ext.py` 就以为 `shared/protocol.ts` 会跟着变 | codegen 读的是**快照**，两边没动 ⇒ check 绿、前端类型永远没有 `material` | §4.3 第 8 条 |
| 17 | 只改快照不改 `openapi_ext.py`（或反之） | `test_voxel_protocol.py:19` 断言 live == 快照，必红 | §4.3 第 8 条 |
| 18 | 只改 `ws.py:91` 忘了 `main.py:1458` | OpenAPI `info.version` 不变，`test_live_openapi_version...` 必红 | §4.3 第 7 条 |
| 19 | 给 build 加分/选地在 `runtime.tick` 里做 | 那里没有 `CoinLedger`/`Pathfinder`，写不出条件分也选不出格 | §4.2「建造四层阻断」第 1、2 条 |
| 20 | 调大 `_SITE_SCATTER_RADIUS` 放宽活动范围 | 它同时是**到站半径**（三处使用），放宽后「离得远也算到站」，需求回写与工钱跟着失真 | §4.2「改法」第 6 条 |
| 21 | 删 `take`/`give` 只改白名单 | `gate.py:87,138` 三处元组 + `errands.py` 3 条夹具 + T5 golden 基线全要跟 | §4.4 第 3 条 |
| 22 | 在 `frame.narrated()` 里做跨帧抑制 | 它是 frozen 纯函数、帧每拍重建，无处记状态；且被大量测试直调 | §4.1 |
| 23 | 回滚 `apply_grant(+cost)` 不发事件 | 重放后余额对不上实况（C4 违规），只在真机/读档时暴露 | §4.2「建造四层阻断」第 4 条 |
| 24 | 给 `OCCUPATIONS` 插「书生」补第 9 个职业 | `i % len()` 轮转整体错位一位 ⇒ 所有现存世界的人职业全变 | §4.2「改法」第 2 条 |

> 第 9、11、12 条是「改了一半看起来对」的典型：单测都能绿，真机才暴露。
> 项目纪律已写明「改 NPC 行为必须实机复验」——这三条尤其。

## 9. 非目标与待确认

### 非目标

- 不做建筑可进入的室内玩法（`pku` 室内 tileset 仍闲置）。
- 不做真实火场出站、玩家念头回执（用户已明确搁置）。
- 不改 `DESIGN.md`（冻结基线）。
- **不新增职业**（含「书生」）。理由见 §4.2「改法」第 2 条：`OCCUPATIONS` 是按名册序
  `i % len()` 轮转分配的，插入一项会让所有现存世界的村民职业整体错位。
  村塾（`old_school`）本轮作为纯视觉地标，不指派 NPC。
- **不动 `take`/`give`**（用户裁定单列下一轮）。
- **不做离线健康演进、不产 `AGENT_INCAPACITATED`**（用户裁定维持现状）。

### 已裁定（2026-11-05，用户三选一）

本轮开工前的三个悬而未决项，用户已当场裁定。**这三条是决策记录，不再讨论。**

| 项 | 裁定 | 落地口径 |
|---|---|---|
| 方案范围 | **按文档实施 A+B** | A（主树）+ B1（主树）+ B4 主体（主树）+ B2/B3（codex） |
| 「明确保留的边界不要了」 | **别再提：维持现状** | ① 离线补跑**仍不演进健康**；② 重症 1 上限**仍不产 `AGENT_INCAPACITATED`**。两条都从「未做清单」里删除，**不再作为提案出现**，也不再作为「本轮不做」的理由引用——它们现在是**已裁定的现状**，不是技术债 |
| `take`/`give` | **本轮只做 B4 主体，此项单列** | B4 当轮交付 = `96×96`→`140×100` + 集合差测试（`wait` 执行器已存在）。`take`/`give` 的处置（删 vs 补执行器）**留给下一轮**，本轮**不动**它们的白名单与 `gate.py` 元组 |

> 因为「边界」一条裁成了**维持现状**，§9 上表里「若『要放开』」那一列
> 全部作废——**不要**再去实现离线健康演进或重症产失能。
> 同理，`health_evolve.py:17-19` 的原文警告继续有效，别删。

**`wait` 的执行面语义（已核实，无需改动）**：`execute_pending` 的尾部独白分支
已经覆盖 `wait`（无位移、产一条 `NPC_MONOLOGUE`），且有测试
`test_wait_intent_no_move` 钉住。所以「LLM 执行了操作」在事件表里确实只表现为
一条独白——这是**既有行为**，本轮不改。若验收要求更强的可观测痕迹
（例如 `waited_ticks`），单列。
