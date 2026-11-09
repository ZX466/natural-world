# m7-render-art — M7 渲染面裁决留档

> **状态：已实施，施工内容全部被后续管线取代。** 本文只剩**仍在生效的裁决**，
> 供后续改动判断「哪些行为是有意为之、不要顺手改掉」。
>
> 2026-10-05/06 实施（T1-T8 提交链 `851aef7..f69de0f`）；2026-10-26 起 Sprout/Zelda
> 图管线整体退役。现行渲染架构见 [`voxel-execution-spec.md`](voxel-execution-spec.md)
> 与 [`world-liveliness-design.md`](world-liveliness-design.md) §7。
> 本文档已从 197 行压缩到裁决本身；被删的施工细节（旧脚本、旧调色板、未实现的
> BootScene/tilemap 路径）走 `git log -- docs/arch/m7-render-art.md` 考古。

## 仍在生效的裁决

| 裁决 | 内容 | 为什么保留 |
|---|---|---|
| **R2** | `facing` / `anim` 由**前端从位移推断**（dx/dy → 朝向；位移 ≠ 0 → walk），sim 侧 `facing` 硬编码为 `"s"`、`anim` 走姿势账本 | 零协议、零 sim 状态改动（`EntityState` 只有 `pos`）。实现在 `client/src/game/render/actors.ts::inferFacing`，`sim/api/ws.py` 仍发 `facing: "s"`。**不要因为看到 sim 发 `"s"` 就以为朝向功能缺失。** |
| **R3** | 戏内时钟：**服务端权威、前端平滑推进**——快照 / `session_state` / 增量都带权威 `time`，两帧之间前端按 speed + paused 本地推进，收到任何帧即重同步 | 免每 tick 协议流量；暂停 / 倍速 / 读档分叉时最坏漂移一帧间隔。协议 1.3 起 `TimeInfo` 是封闭五键 `{day,hour,minute,phase,is_market_day}`。 |
| **R8** | 昼夜用 `nightOverlay`（phase → alpha 查表）叠色罩，**不引光照引擎**；`weather.ambient_light` 接线为色罩强度乘子 | YAGNI。`WorldScene.ts` 的 `nightOverlay` + 批次 D7 的天气压暗叠乘就是这个裁决的落地。**不要因为 three.js 场景有灯就以为地形受光照影响**——地形用 `MeshBasicMaterial`，亮度烘焙在顶点色里。 |

## 已死的部分（别再照做）

- 素材包 **Sprout Lands**（R4）、`sprout-palette.json` 作 ground id 真相源（R5）：均已退役。
  现行调色板 = `client/public/assets/tilesets/linhe-block-atlas.json`，图集 =
  `god-town-16.png`（2240×1600，桃花源源图缩半）。
- 程序化 48×48 小镇（R6 的矩形布局）：现行地图 140×100，由 `sim/content/build_god_town.py`
  从桃花源 `map_pack.json` 提取。R6 的「确定性脚本、产物入库可 diff」精神仍然成立。
- 创世 3 名静止占位村民（R7）：已退役，现行创世名册是陈默 + 50 村民 + 3 只动物。
- `BootScene.ts`、`game/render/tilemap.ts`：**从未按此文实现**。预载在
  `WorldScene.preload()`，地图渲染在 `render/iso-terrain.ts`。

## 唯一还需记住的协议事实

协议 **1.3** 是 M7 的加法变更，至今有效：`MapChunk.ground_b64`（地面层走 HTTP 静态通道，
不走 WS）+ `TimeInfo` 时钟权威帧。登记见 [`../api/versioning.md`](../api/versioning.md) 的 1.3 行，
响应形状见 [`../api/openapi.md`](../api/openapi.md) §4.1。
