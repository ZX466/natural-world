# 协议版本策略（docs/api/versioning.md）

> 能力域：接口 / 兼容性（kilo） | 对齐 DESIGN.md §4 §17
> 本文为**设计文档**初稿。目标：client 与 sim 能独立演进，不因一侧升级而互相破坏。

## 1. 版本号模型

采用 **major.minor**（不带 patch；协议层无实现缺陷语义，缺陷修复不改变协议形态）。

- **major**：不兼容变更——字段删除 / 改名 / 语义反转 / 消息行为改变。major 不一致 = 必须协商，协商失败即拒绝连接。
- **minor**：兼容增量——新增可选字段 / 新增消息类型。minor 升级对旧端**透明**（旧端忽略未知字段与未知 type）。
- 当前基线：`v = 1.0`（信封 `v` 字段，见 ws-protocol.md §2）。

> 信封里的 `v` 在协商后全程不变，等于协商选定的 major.minor。

## 2. WS 协商流程（connect-time）

```
client ──hello──► { "client_versions": ["1.0","1.1"], "client_build": "0.1.0" }
                            │
sim: 取交集最高 → 选定 v
                            ▼
client ◄──hello_ack── { "v": "1.1", "server_versions": ["1.0","1.1"], "server_build": "0.1.0" }
                            │
                  全程以 v=1.1 收发
                            ▼
（协商失败） client ◄── error{code:VERSION_MISMATCH} + 关闭连接
```

- `hello` / `hello_ack` 走 control 通道，是连接建立后首帧。
- 服务端默认**向后兼容至少一个 major**（即旧 major 仍可连），降低单端独立部署时的断裂面。

## 3. 兼容性规则（保证独立演进）

| 变更类型 | 归类 | 旧 client 行为 | 旧 sim 行为 |
|---|---|---|---|
| 新增可选字段 | minor | 忽略未知字段（`state_delta` 多一个字段不影响渲染） | — |
| 新增消息 type | minor | 收到未知 type → 忽略 + 仅开发模式记日志（不崩溃、不出戏） | — |
| 字段删除 / 改名 | major | 协商阶段即发现 major 不一致 | — |
| 语义反转 | major | 同上 | — |

**核心铁律：client 永不因收到未知 type/字段而崩溃或出戏。** 这是 sim 升级先于 client 部署（或反之）时不破坏体验的保证——未知消息静默忽略，渲染照常。

## 4. HTTP 版本

- 当前单用户本地部署、无外部消费者：HTTP 端点**不引入 URL 版本前缀**（保持 `/api/...`），用 OpenAPI schema 变更 + 重新生成 `shared/protocol.ts` 管控。
- 预留策略：若未来出现外部消费者，引入 `/api/v2/...` 路径前缀；旧路径保留一个里程碑周期。本初稿不实施，仅记预案。

## 5. 版本与生成物的联动（见 codegen.md）

- 改 WS 消息集合或字段 → 先定 minor/major → 更新 sim pydantic 模型 → 重新生成 `shared/protocol.ts`。
- 在 `shared/openapi.json` 的 `info.version` 与 WS 信封 `v` 双处记录版本；CI 漂移闸（codegen.md §5）保证生成物与源同步。

## 6. 回放与确定性不受版本影响

- 回放（C4/C5/T2）基于世界事件流与确定性 RNG，与协议版本正交：旧版本回放仍可由新 sim 重放，因为世界真相（事件 seq/branch）独立于对外协议。
- 协议版本只管"对外呈现的字段集合"，不动世界内部因果——这与 §11「seed/tick/seq 不进任何戏内接口」一致：内部真相不随版本外泄。

## 7. 变更登记（初稿留空，随演进追加）

| 版本 | 变更 | 影响端 | 日期 |
|---|---|---|---|
| 1.0 | 协议基线（ws-protocol.md 全量消息） | client+sim | 2026-09-19 |

## 8. 不在本文件范围

- 消息字段定义 → `ws-protocol.md`；HTTP 端点 → `openapi.md`；生成管线 → `codegen.md`。
- 回放/确定性内部机制 → 架构域（Claude）+ 测试域。
