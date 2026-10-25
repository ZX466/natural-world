# 文档索引

运行入口见[仓库 README](../README.md)，设计基线见[DESIGN.md](../DESIGN.md)。
本目录只保留现行契约、操作说明和仍有参考价值的架构记录。阶段预研、过程审计和重复计划已删除。

协议字段以 `shared/openapi.json` 和生成类型为准；数据字段以 ORM 模型和迁移为准。架构文档中的历史示例不替代这些真源。

## 使用与开发

- [开发流程（docs/dev-workflow.md）](dev-workflow.md)

## 接口与协议

- [﻿# 玩家档锚点接口契约（docs/api/anchors-api.md）](api/anchors-api.md)
- [OpenAPI → shared/protocol.ts 生成管线（docs/api/codegen.md）](api/codegen.md)
- [HTTP 端点设计（docs/api/openapi.md）](api/openapi.md)
- [协议版本策略（docs/api/versioning.md）](api/versioning.md)
- [WebSocket 消息协议设计（docs/api/ws-protocol.md）](api/ws-protocol.md)

## 渲染与演进

- [m7-render-art — 渲染美术面（星露谷调性落地）](arch/m7-render-art.md)
- [施工总单：等距体素转向 V0-V3（执行规格书 · Claude 执行版）](arch/voxel-execution-spec.md)
- [Minecraft 风格转向方案 v2（最大保留版 · 等距体素优先）](arch/voxel-transition-plan.md)

## 持久化

- [事件溯源方案](data/event-sourcing.md)
- [Alembic 迁移策略](data/migration.md)
- [SQLite Schema 设计](data/schema.md)

## 性能

- [基准测试方案（docs/perf/bench-plan.md）](perf/bench-plan.md)
- [性能预算（docs/perf/budget.md）](perf/budget.md)
- [性能热点预判与对策（docs/perf/hotspots.md）](perf/hotspots.md)
- [L1 效用算法规格（docs/perf/l1-spec.md）](perf/l1-spec.md)
- [LLM 异步延迟监控口径（docs/perf/llm-monitoring.md）](perf/llm-monitoring.md)

## 安全与测试

- [玩法与存档完整性深度复检（2026-10-21）](security/gameplay-integrity-audit-2026-10-21.md)
- [L1 动作白名单与升格隐藏属性契约（docs/security/l1-whitelist.md）](security/l1-whitelist.md)
- [记忆写入前禁词扫描设计（memory-scan.md）](security/memory-scan.md)
- [自我未知安全边界（docs/security/self-unknown.md）](security/self-unknown.md)
- [﻿# T1 信息边界 10k 采样验收口径（docs/security/t1-sampling-10k.md）](security/t1-sampling-10k.md)
- [T3 出戏对抗样本集（t3-corpus.md）](security/t3-corpus.md)
- [﻿# T4 真模型探针集（t4-corpus.md）](security/t4-corpus.md)
- [﻿# 轻量威胁模型（docs/security/threat-model.md）](security/threat-model.md)

机器基线：[EPYC 7763](perf/baseline-epyc7763.json)；[runner 记录](perf/runner.txt)。

## 历史与维护

旧阶段稿的完整正文保留在 Git 中，例如 `git show 3b33328:docs/arch/m0-core.md`。
现行火灾订正归入 WS 协议，权力态及存档分类归入 schema，长跑执行归入基准方案，分支证据链归入自我未知边界。
后续变更直接维护对应契约，避免再建立平行的预研稿、结论稿和多份状态台账。
