# m7-render-art — 渲染美术面（星露谷调性落地）

> 状态：设计稿 v1（2026-10-05，用户已核方案 A/Sprout Lands/docs.arch 落点/交付范围）
> 前置：M0-M6 收官（main `abbe765`）。本文档是 M7 第一单（渲染面）的唯一设计真相源。

## 0. 范围与结论

**一句话**：把前端从「色块占位」升级为星露谷调性的像素画面——真实小镇地图（瓦片渲染）、主角行走动画、昼夜光照，sim 侧换掉 32×32 全平占位图。

**本轮交付**（用户裁定）：
1. 小镇地图（sim 加载真实图，前端瓦片渲染）；
2. 角色行走动画（四向 idle/walk）；
3. 昼夜光照（phase 驱动色罩，真实时钟接线）。

**不做**（MVP 后清单，见 §8）：UI 皮肤、光源引擎、天气视觉粒子、换装骨骼、L1 村民 AI。

**方案**：A 案（扩展静态资产通道）。协议 minor 升版 1.2 → 1.3，一次覆盖两项加法
（`MapChunk.ground_b64` + 快照/增量 `time` 块）。

## 1. 现状与缺口（核库事实，2026-10-05）

| # | 事实 | 出处 |
|---|---|---|
| 1 | `Actor` 协议已有 `sprite/anim/facing/tint` 字段，前端全部忽略（只画矩形） | `shared/protocol.ts:174` / `WorldScene.ts:105` |
| 2 | sim 内部 `Chunk.ground`（每格 tile id）一直存在，但 `/api/world/map` 只下发碰撞位 | `sim/world/map.py:24` / `sim/api/ws.py:465` |
| 3 | sim 地图是硬编码 32×32 全平占位（`_default_map`）；`from_json_file` 已能加载真实图但无人调用 | `sim/api/main.py:47` |
| 4 | 前端 `gameClock` 只有 mock 在供数；真实链路快照不含戏内时间 → TopBar 恒显「第 1 天 00:00」 | `runtime.ts:115`（唯一 setGameClock 调用） |
| 5 | 协议真相源 = `shared/openapi.json`（mock 快照，切源暂缓 M2-C4），改动走 openapi.json → gen-protocol → protocol.ts | `tools/gen-protocol.ts` 头注 |
| 6 | 版本双落点：`sim/api/ws.py::_PROTOCOL_VERSION` + `client/src/net/ws.ts::PROTOCOL_VERSION`，`test_protocol_version.py` 锁死 | 当前均 `1.2` |
| 7 | sim 出站 actor：`facing="s"`、`anim="idle"` 硬编码；`sprite=rtoken 派生` | `sim/api/ws.py:350-363` |
| 8 | `sim/content/` 只有 README（M0 登记了「Tiled→内部格式」管线未实现）；素材清单要求登记来源与许可 | `sim/content/README.md` |

**出戏边界核对**：戏内时间（day/hour/minute/phase/集市日）是**戏内事实**（TopBar 本就展示，mock 已在同形状供数），非禁键（禁的是 tick/seq/branch/rng_state/内部 id）。地图 ground id 是**静态资产数据**（M0 裁决：静态资产不进世界状态快照、走 HTTP），不触碰 C4/C5。

## 2. 方案与裁决

### 2.1 A 案：扩展静态资产通道（采纳）

- `/api/world/map` 每 chunk 增 `ground_b64`（u16 LE 每 tile 的 ground id，行主序）；
- sim 从 `sim/content/` 加载构建期生成的真实小镇图，替换 `_default_map` 占位；
- 快照/增量增 `time` 块（戏内时钟权威源）；前端 BootScene 预载素材，WorldScene 瓦片渲染 + 行走动画 + phase 色罩。

### 2.2 否决案（存档）

- **B 客户端自带地图文件**：零协议改动，但地图双真相源，违反「世界真相只进事件日志」；M3 可变地图/读档分叉必失同步。
- **C 地图进 WS 快照**：直接违反 M0 裁决（静态资产不走 WS、不进世界状态快照）+ 快照 ≤5MB 预算（gzip 后）红线。

### 2.3 本轮设计裁决（逐条）

| 裁决 | 内容 | 理由 |
|---|---|---|
| R1 | 地面渲染数据走 HTTP 静态通道（`ground_b64` 加进 `MapChunk`），**不走 WS** | 沿袭 codex 意见 5 既定裁决，静态资产≠状态流 |
| R2 | `facing/anim` 由**前端从位移推断**（dx/dy → 朝向；位移≠0 → walk），sim 侧 `facing/anim` 硬编码维持原状不动 | 零协议/零 sim 状态改动（`EntityState` 只有 pos）；表现层推断是纯客户端职责，后续 sim 真供数时前端无缝切换 |
| R3 | 戏内时钟：**服务端权威、前端平滑推进**——快照/`session_state`/增量每帧带权威 `time`，两帧之间前端按 speed+paused 本地推进，收到任何帧即重同步 | 免每 tick 协议流量；世界暂停/倍速/读档分叉时最坏漂移一帧间隔 |
| R4 | 素材包定 **Sprout Lands**（Cup Nooble，16×16）；**许可在下载落库时以官方页面为准核验并登记**进素材清单（不以口头记忆为准） | 用户裁定 + DESIGN 风险表「三级管线第 1 级：通用 tile 基础包」 |
| R5 | ground id → 图集坐标的**调色板单一真相源放 client**（`client/public/assets/tilesets/sprout-palette.json`）；sim 侧地图构建脚本**读取该调色板**取 id，保证一致 by construction；sim 测试钉「图中 id ⊆ 调色板值域」 | 避免双落点；渲染语义归前端域 |
| R6 | 地图构建走**确定性 Python 脚本**（矩形布局：草地/土路/农田/水塘/房屋脚印），产物 `sim/content/linhe-town.json`（内部格式）入库可 diff；不引 Tiled 编辑器依赖 | 与项目确定性文化一致；48×48 首轮规模脚本足够；Tiled 留作后续 |
| R7 | 创世增派 3 名占位村民（`world_create` 的 entity_ids 增员），**静止实体**（无 AI；M2 runtime 装配线接入前由 tick 驱动为不动的真实实体） | 世界有生气且完全真实（真实体真事件）；村民 AI 归 M2 线不属本设计 |
| R8 | 昼夜色罩沿用现有 `nightOverlay`（phase → alpha 查表），**不引光照引擎**；`weather.ambient_light` 接线为色罩强度乘子（visual 粒子不做） | YAGNI；M0 已有骨架 |

## 3. 内容管线（sim/content）

### 3.1 素材落库与登记

```
sim/content/
├── README.md            # 追加：素材清单登记（来源/许可/版本/落库日期）
├── build_town.py        # 确定性地图构建脚本（R6）
├── linhe-town.json      # 构建产物（内部格式，from_json_file 可加载）
└── assets/              # 素材原件存档（tileset png + 角色表 png + LICENSE 记录）
```

- 素材**运行时副本**放 `client/public/assets/`（Vite 静态服务；sim 不服务素材文件，只服务 id）；
- `sim/content/README.md` 登记：包名/作者/官方页/许可条款/落库日期/文件清单（DESIGN §20 风险对策「M0 就列素材清单」的兑现）。

### 3.2 调色板（R5）

`client/public/assets/tilesets/sprout-palette.json`：

```json
{ "tileset": "sprout_lands_v1", "image": "sprout-tileset.png", "image_size": [w, h],
  "tile_size": 16, "ground": { "grass_1": 0, "grass_2": 1, "path_dirt": 10, "water": 20, "farm_soil": 30, "...": 0 } }
```

- `ground` 值域 = 图集首列起按行主序的 tile index；sim `build_town.py` 读取此文件取 id 写入 `linhe-town.json`；
- sim 测试断言 `linhe-town.json` 所有 ground id ⊆ 调色板 `ground` 值域（防漂移钉）。

### 3.3 小镇地图（R6，48×48）

- 布局（脚本内矩形定义，全部坐标常量可审）：四周树林墙（不可走）+ 草地底 + 十字土路 + 药铺/住宅 2-3 座房屋脚印（不可走，占位矩形——本轮不画建筑精灵图，房屋用色块 tile 表达，建筑精修留后续）+ 农田若干 + 水塘 + 主角出生点 (0,0) 附近保证可走；
- `collision` 语义沿用：不可走 = false；房屋脚印/水/树 = 不可走。

## 4. sim 侧改动

| 文件 | 改动 |
|---|---|
| `sim/api/main.py` | `_default_map()` 改为：优先 `from_json_file(sim/content/linhe-town.json)`，异常时回退现占位图（fail-safe，启动不炸）；创世 `entity_ids=("chenmo", "villager_1", "villager_2", "villager_3")`（R7） |
| `sim/api/ws.py` | ① `map_static_payload` 每 chunk 增 `ground_b64`（u16 LE，行主序）；② `snapshot_payload`/`delta_payload` 增 `time` 块（R3 权威源）：`{"day","hour","minute","phase","is_market_day"}`（由 `game_time(tick)/phase_of_day(tick)/is_market_day(tick)` 派生，`session_state` 同步增；**零 tick 原值出站**） |
| `sim/api/main.py` | `MapChunk`/`WorldMapResponse`/`SessionStateMessage`/`WsMessage` 对应 schema 模型加字段（`extra="forbid"` 封闭集纪律） |
| `_PROTOCOL_VERSION` | `"1.2"` → `"1.3"`（minor，加法变更） |

## 5. client 侧改动

| 文件 | 改动 |
|---|---|
| 新增 `game/scenes/BootScene.ts` | 预载 tileset 图集 + 角色精灵表（四向 idle/walk 帧），完成后启动 WorldScene |
| `game/scenes/WorldScene.ts` | ① `redrawMap` 改为解码 `ground_b64` → Phaser tilemap 层（静态单层，碰撞层仅作寻路请求过滤，仍不渲染调试层）；② `syncActorViews` 矩形换精灵：按调色板/精灵表 key 取帧，位移推断 facing/anim（R2）；主角保留摄像机跟随 |
| 新增 `game/render/tilemap.ts` | `ground_b64 + MapInfo + 调色板 → tilemap` 组装纯函数（可 vitest） |
| 新增 `game/render/actors.ts` | facing/anim 推断纯函数 + 精灵帧选择（可 vitest） |
| `net/ws.ts` | ① `PROTOCOL_VERSION → '1.3'`（第二落点）；② dispatch 增 `time` 处理：快照/增量/`session_state` → `uiStore.setGameClock`（R3 权威帧）；③ `/api/world/map` HTTP 加载实现（现缺位）：取 chunks → 解码 collision + ground → `worldMirror.setMap` |
| 新增 `game/clock.ts` | 本地时钟推进器：权威帧重同步 + 按 speed/paused 平滑推进（R3；mock 的 `mockStep` 时钟逻辑迁来泛化） |
| `game/runtime.ts` | mock 分支**保留**（无后端演示价值，用户实际在用），但 mock 也走 BootScene 素材与新渲染路径（同一渲染代码，只是数据源不同） |

## 6. 协议变更登记（1.2 → 1.3，minor/additive）

按 `docs/api/versioning.md` §7 三行登记 + 生成链纪律：

1. `shared/openapi.json`（真相源）：`MapChunk.ground_b64`（新增，string）、`WorldMapResponse.time` 与 `StateDeltaMessage.time`、`SessionStateMessage.time`（新增可选 `TimeInfo` 对象：`day/hour/minute/phase/is_market_day`）、版本枚举登记 1.3；
2. `npm run gen:protocol` 再生 `shared/protocol.ts`（同 commit，`--check` EXIT 0）；
3. `docs/api/versioning.md` §7 三行登记（1.3 = m7 渲染面：地图地面层 + 戏内时钟）；
4. 双落点版本常量同 commit：`sim/api/ws.py` + `client/src/net/ws.ts`；
5. `sim/tests/test_protocol_version.py::EXPECTED_VERSION = "1.3"`。

**兼容性**：加法 minor——旧 client 收 `ground_b64`/`time` 未知字段静默忽略（versioning §3 铁律，JSON 保留未知键不炸）；新 client 对旧 server 的 `time` 缺省回退现状（时钟 null → TopBar 占位）。sim 侧 `extra="forbid"` 只约束入站；`ground_b64` 出站对旧 client 无害。

## 7. 测试与门禁

**sim 侧（pytest，T1/T2 口径）**：
- 地图加载：`linhe-town.json` 可被 `from_json_file` 加载；48×48；出生点可走；ground id ⊆ 调色板值域（R5 钉）；
- `map_static_payload`：`ground_b64` 解码后与 chunk.ground 逐位一致；碰撞位与现口径一致；
- 快照/增量/`session_state` 的 `time` 块：由固定 tick 推导断言（确定性）；**零禁键**（tick/seq 原值不出站，沿用 T3 出站扫描）；
- 创世：4 实体在 entities（含 3 村民）；回放确定性（T2 既有钉自动覆盖）；
- 版本钉：`EXPECTED_VERSION = "1.3"`。

**client 侧（vitest）**：
- `tilemap.ts`：b64 u16 解码、调色板组装、越界容错；
- `actors.ts`：位移→facing/anim 推断表驱动用例；
- `clock.ts`：权威重同步、speed 推进、暂停停走、回退容错；
- 既有 `protocol-types.test.ts` 随生成物再生自动覆盖新字段。

**门禁全绿口径**（每提交 CI 同口径）：`uv run pytest -q`（全量 not-bench）· ruff · pyright · `gen:protocol --check` · `npm run test` · `tsc --noEmit`。

## 8. 不做清单（MVP 后清单，本设计明确排除）

- UI 皮肤星露谷化（面板/字体/边框）——二期；
- 建筑精灵图精修（本轮房屋=占位 tile 矩形）；
- 光照引擎/点光源/天气视觉粒子（雨雪雾）；
- 角色换装骨骼（DESIGN 三级管线第 2 级，仅在免费包不够时启用）；
- L1 村民效用 AI（M2 runtime 装配线职责）；村民行为活化归彼处；
- Tiled 编辑器管线（脚本够用时不上工具）。

## 9. 风险与对策

| 风险 | 级别 | 对策 |
|---|---|---|
| Sprout Lands 许可条款与预期不符（如禁商用/需署名） | 中 | R4：下载时以官方页面核验登记；不符则换 LimeZu/开源包重跑（调色板机制让换包成本=换图集+调色板 JSON） |
| 免费包 tile 种类不够表达小镇（建筑/家具缺） | 中 | 本轮建筑本就占位矩形；缺口进素材清单备注，二期评估 Aseprite 自制 |
| `time` 块与出戏扫描误伤（phase/is_market_day 等枚举词） | 低 | 均为戏内词汇（TopBar 已展示同形数据）；T3 出站扫描若命中按白名单程序走既有裁决流程 |
| 前端插值与瓦片坐标漂移（16px×2 zoom） | 低 | 既有 TILE/插值常量不动，瓦片层与 actor 层同坐标系；视觉验收门 |
| world.db 旧档兼容（创世实体变 4 个） | 低 | 开发库可删重建（用户已知情清缓存）；anchors 分叉重放以事件日志为准，无 schema 变更 |

## 10. 验收（视觉门）

后端 + 前端双起后：草地/路/水/农田瓦片正确铺装、主角四向行走动画流畅、村民可见（静止）、昼夜四相位色罩随戏内时间变化、TopBar 时钟与戏内时间同步走动、`16x` 倍速下时钟不漂出戏内日循环。
