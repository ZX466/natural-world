# 前端

启动与验证命令见[仓库 README](../README.md)。运行环境为 Node.js 24+，依赖按 `package-lock.json` 安装。

- `game/runtime.ts` 连接 sim 并更新 `WorldMirror`；高频世界数据直接供 Phaser 使用。
- `game/scenes/WorldScene.ts` 绘制世界、处理相机与鼠标交互；`game/render/` 保存几何、动画和图集计算。
- `ui/` 绘制 canvas 外界面；`store/uiStore.ts` 只维护 UI 需要的低频状态。
- `net/` 处理 HTTP、WS 与协议类型封装。

Phaser 负责 canvas 内的世界，React 负责界面。协议修改与生成方式见[codegen](../docs/api/codegen.md)。
