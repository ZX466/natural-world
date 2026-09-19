# shared — 前后端共享产物

`shared/protocol.ts` **自动生成，永不手写**（DESIGN.md §4 工具链、§19 禁止事项）。
真相源 = sim 端 pydantic 模型 → OpenAPI JSON → `openapi-typescript`。

- 生成命令：`npm run gen:protocol`（在 `client/` 下执行；脚本本体 `tools/gen-protocol.ts` 由接口域 kilo 维护，
  见 `docs/api/codegen.md`；M0 阶段 `shared/openapi.json` 为手写 mock，sim 起服务后切换真实导出）。
- 漂移检测：`npm run gen:protocol:check`（CI 守卫「生成物与提交一致」；接入 ci.yml 的时机由 Claude 定）。
- 前端消费：`client/src/net/protocol.ts` 只做 re-export + 判别联合别名（m0-client.md §2）。
- 依赖：本脚本直接以 `node` 运行 `.ts`，**要求 Node ≥ 24**（无旗标类型剥离；`client/package.json` engines 与 CI 已对齐）。
