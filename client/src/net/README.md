# client/src/net — WS 客户端与协议

- `ws.ts`        连接/重连/消息分发
- `protocol.ts`  **只做 re-export**：`export * from '@shared/protocol'`（自动生成，不手写）

协议字段 schema 与生成管线归 kilo TASK-001（`docs/api/ws-protocol.md`、`docs/api/codegen.md`）。