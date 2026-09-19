# client/src/ui — React 侧（canvas 外的 UI）

结构（docs/arch/m0-client.md §2）：

- `App.tsx`        壳装配
- `TopBar.tsx`     戏内时钟 / 倍速 / 连接状态点（只显示戏内时间，铁律 C3）
- `CanvasHost.tsx` 唯一 DOM 交界点：`<div ref>`，Phaser 挂载于此
- `PanelHost.tsx`  M1+ 思维面板/计划看板（M0 占位空）

铁律：React 不渲染游戏实体，不手写协议类型（用 shared/protocol.ts 生成物）。
本目录的 `.tsx` 实现属前端域（Claude），此处仅占位骨架。