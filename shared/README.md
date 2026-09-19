# shared — 前后端共享产物

`shared/protocol.ts` **自动生成，永不手写**（DESIGN.md §4 工具链、§19 禁止事项）。
生成方式：FastAPI 的 OpenAPI JSON → `openapi-typescript`。

- 生成命令：`npm run codegen:protocol`（在 `client/` 下执行；具体管线归 kilo TASK-001，见 `docs/api/codegen.md`）。
- 前端消费：`client/src/net/protocol.ts` 只做 re-export（m0-client.md §2）。
- CI 校验：协议类型不得出现在手写文件中（kilo TASK-001 落地）。
