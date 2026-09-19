# client/src/store — Zustand 状态桥

- `worldStore.ts` 世界状态摘要（实体位置、戏内时间、光照相位）
- `uiStore.ts`    UI 状态（倍速、暂停、选中实体）

Zustand store 是 React 与 Phaser 之间的**唯一桥**（m0-client.md §1）：
React→Phaser 走控制指令，Phaser→React 走状态摘要事件。