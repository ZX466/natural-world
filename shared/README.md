# 共享协议

当前类型生成真源是入库的 `shared/openapi.json`；`shared/protocol.ts` 是生成物。

在 `client/` 运行 `npm run gen:protocol` 更新类型，运行 `npm run gen:protocol:check` 检查漂移。Node.js 要求 24+。

协议修改必须同步服务端 schema、协议快照、两端版本和生成物；不能直接修改生成类型或擅自切换生成源。完整步骤见[codegen](../docs/api/codegen.md)，兼容性规则见[版本管理](../docs/api/versioning.md)。
