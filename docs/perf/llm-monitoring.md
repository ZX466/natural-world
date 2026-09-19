# LLM 异步延迟监控口径（docs/perf/llm-monitoring.md）

> 性能域（pi）F05 交付 ②。给 Claude（C06 LLM 客户端）的接单规格——按此照抄事件名与字段，客户端接好即可。
> 依据：DESIGN §15 成本治理（单决策 1.2–2k tok、一游戏日 40–60 次决策）、§17 M1 验收（决策延迟 P95<8s、单决策 <2k tok）、bench-plan §0（LLM 延迟不进 tick 基准，独立看板）。

## 1. 监控的两个量纲（互不混淆）

| 量纲 | 对象 | 指标 | 看板 |
|---|---|---|---|
| **TICK 侧** | 世界内核 `sim.core` | 每 tick 各子系统耗时 | nightly bench（`pytest -m bench`） |
| **LLM 侧（本文件）** | 异步推理调用 `sim.llm` | tokens / latency / 重试 / 缓存命中 | 日汇总看板，**独立于 tick bench** |

LLM 延迟 P95<8s（M1 验收线）是异步第三方依赖，bench 里**不做**（烧钱+抖动，bench-plan §0 已定）；本文件定义其采集口径，M1 客户端照抄即可点亮看板。

## 2. structlog 事件名（固定，别改名）

| 事件名 | 触发点 | 用途 |
|---|---|---|
| `llm.request` | 每次发请求前 | 计数、剔除输入（**绝不记 prompt 明文**） |
| `llm.response` | 每次成功返回 | tokens/延迟主字段 |
| `llm.retry` | tenacity 重试时 | 重试统计 |
| `llm.timeout` / `llm.error` | 超时/异常 | 可用性 |
| `llm.cache_hit` | 身份锚前缀缓存命中时 | 缓存命中率（成本大头，§15） |
| `llm.decision` | Agent 决策落地时（Intent 产生） | 端到端决策延迟（P95<8s 验收对象） |

## 3. 字段清单（llm.response / llm.decision 必带，其余可带）

```
profile_name: str       # 使用的模型 profile（供应商+型号），不记 api_key
model: str              # 型号名
stream: str             # rng 流名（llm.*，联调用）
request_id: str         # 本次调用唯一 id（重试链路串联）
prompt_tokens: int      # 输入 tok（身份锚缓存命中时 = 实际发送量）
completion_tokens: int  # 输出 tok
total_tokens: int       # 合计
latency_ms: float       # 请求发出 → 响应返回 的墙钟毫秒
ttft_ms: float | None   # 首 token 时间（流式时），非流式为 None
attempt: int            # 第几次尝试（1 = 首次）
cache_hit: bool         # 身份锚前缀缓存是否命中
decision_ms: float      # [llm.decision] 意图触发 → Intent 产出 的端到端延迟（含队列/重试）
```

**必记**：`prompt_tokens` / `completion_tokens` / `total_tokens` / `latency_ms`（DESIGN §15 原文）。
**必不记**：`api_key` / prompt 明文 / 完整响应明文 / 任何戏内元信息（C3 推论）——响应字段只取 token 计数与延迟，不落 `choices` 全文。

## 4. 采集口径

- 每次调用都记（不分流）；只有 `ttft` 分「流式/非流式」，其他字段统一。
- 日汇总口径（与 §15「日汇总」对齐）：按 profile_name 分组的 sum/mean/P50/P95/max（`total_tokens`、`latency_ms`）、retry 计数、cache_hit 率。
- 决策延迟口径：`llm.decision` 的 `decision_ms`，P95<8s（M1 验收）；同一决策链的多次 `llm.request`（规划/校验）以 `request_id` 前缀串联，`decision_ms` 由最后一次完成的时间戳减触发点计算。
- 异常：`llm.error` 里 `error_kind ∈ {timeout, connection, http_4xx, http_5xx, rate_limit}`，`error_hint` 不落堆栈全文（防 log 注入）。

## 5. 验收（给 C06 的接入检查）

1. 每次 `sim.llm` 调用发出前必有 `llm.request`、返回后必有 `llm.response`。
2. `llm.decision` 在 Intent 产生点输出，`decision_ms` = 端到端（含重试）。
3. 日汇总可生成：per profile 的 tokens/latency P95 + retry + cache_hit 率。
4. 无 api_key/prompt 明文/响应明文落日志（用 codex K4/K8 脱敏 processor 兜底）。

## 6. 阈值（初版，M1 实测后回调）

| 指标 | 阈值 | 依据 |
|---|---|---|
| 单决策 total_tokens | < 2000 tok | DESIGN §15 / M1 验收 |
| 决策延迟 P95 | < 8000 ms | §17 M1 验收 |
| cache_hit 率 | 目标 > 50%（身份锚为最大头） | §15 手段 |
| retry 率 | 警戒 > 5% | 供应商稳定性信号 |