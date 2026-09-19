# client/src/game — Phaser 侧（canvas 内的世界）

结构（docs/arch/m0-client.md §2）：

- `main.ts`         `new Phaser.Game(config)`，`parent` = CanvasHost 的 div
- `scenes/`         BootScene（加载 tilemap/精灵表）、WorldScene（地图/精灵/摄像机/输入转发）
- `render/`         tilemap.ts（地图层 + 碰撞调试层）、entities.ts（精灵池，避免每帧 new）、camera.ts
- `lighting.ts`     读 store 的 phase_of_day 做简单昼夜调光（M0 不点光源）

铁律：Phaser 只画 canvas 内的世界，不与 React 共享 DOM；不在 `update` 里 setState。
本目录的 `.ts` 实现属前端域（Claude），此处仅占位骨架。