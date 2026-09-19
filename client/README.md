# client — 前端骨架

DESIGN.md §4 技术栈：TypeScript 5.7+ / Vite 6 / Phaser 3.87 / React 19 + Zustand / Tailwind CSS 4。

- 结构定义见 `docs/arch/m0-client.md` §2；`src/{game,ui,net,store}` 为四个分区。
- 依赖锁定在 `package.json`；`npm install` 前需用户确认（工作流环境守则），
  故仓库暂无 `package-lock.json` 与 `node_modules/`。
- `npm run codegen:protocol` 从 FastAPI OpenAPI 生成 `shared/protocol.ts`（kilo TASK-001 定管线）。