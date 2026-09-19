"""API 网关（DESIGN.md §5；WS 消息 schema 归 kilo TASK-001）。

模块划分：
- ws       WebSocket 网关（每 tick 增量广播；元信息字段绝不外发，见 §10 界面双层铁律）
- settings 设置页接口（Profile 管理 / 连接测试）
- main     FastAPI 应用装配与 uvicorn 入口

注意：协议类型只从本层 OpenAPI 生成（openapi-typescript → shared/protocol.ts），不手写。
"""
