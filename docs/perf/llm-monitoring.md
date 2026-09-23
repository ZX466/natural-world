# LLM 异步延迟监控口径（docs/perf/llm-monitoring.md）

> 性能域（pi）F05 交付 ②。给 Claude（C06 LLM 客户端）的接单规格——按此照抄事件名与字段，客户端接好即可。
> **M3-P1（2026-09-23）增补 §7 `llm.embed_*` 事件族**（m3-plan A6）：chat 族（§2/§3）口径**不动**；embedding 延迟特征不同（无 ttft/stream、批量为主）→ 独立事件名 + 独立阈值。
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

## 7. embedding 族 `llm.embed_*`（M3-P1 / m3-plan A6；A1 定稿后由 opencode 客户端照抄）
> 背景：`vec-preplan.md` §3 结论——**向量检索非瓶颈，成本大头在 embedding 生成**（写路径）。
> embedding 与 chat 的延迟画像不同（无 ttft、无 stream、天然批量），故**独立事件族 + 独立阈值**，
> 不复用 `llm.response` 字段（避免把两个分布混进同一 latency 字段）。
### 7.1 事件名（固定，别改名）
| 事件名 | 触发点 | 用途 |
|---|---|---|
| `llm.embed_request` | 每次 embedding 请求发出前 | 计数 + batch_size（批量是降成本主手段） |
| `llm.embed_response` | 每次成功返回 | latency/tokens 主字段 |
| `llm.embed_error` | 失败/降级（切 numpy 兜底）时 | 可用性 + 降级率 |
| `llm.embed_cache_hit` | 内容哈希命中缓存（同内容不重复调）时 | 缓存命中率（成本大头） |
### 7.2 字段清单（embed_request / embed_response 必带）
```
profile_name: str       # embedding profile（A1 裁 V3 三选一定型后填），不记 api_key
model: str              # embedding 型号名（与 chat 型号可不同）
dim: int                # 向量维度（384/768；A1/V2 定后固定；错维 = 数据损坏信号）
request_id: str         # 本次调用唯一 id
batch_size: int         # 本条 embedding 调用携带的文本条数（1 = 单条）
input_chars: int        # 输入总字符数（token 近似成本；**不记文本明文**）
total_tokens: int       # 输入 tok（embedding 无 completion_tokens）
latency_ms: float       # 墙钟毫秒（单条 or 整批，由 batch_size 区分）
attempt: int            # 第几次尝试
cache_hit: bool         # 内容哈希是否命中（命中时无 latency，仍记 cache_hit 事件）
degraded: bool          # 是否降级为 numpy/本地兜底（embed_error 时 True）
```
**必记**：`batch_size` / `total_tokens` / `latency_ms` / `dim`。
**必不记**：`api_key` / 文本明文 / 向量本体（384 维 float 落日志 = 灾难）/ 戏内元信息。
### 7.3 阈值（**独立于 chat**；M1 无 embed 实测，M3 首个 profile 点亮后回调）
| 指标 | 目标 | 依据 |
|---|---|---|
| 单条 latency P95 | < **300ms** | 同步写路径阻塞预算：写记忆不在每 tick 路径，但慢会拖 L2 升格 |
| 批量（≤32 条）latency P95 | < **2s** | 批量摊销是主要降本手段（vec-preplan §3「批量化+缓存+降级」） |
| cache_hit 率 | 目标 > 60% | 同一叙事内容重复 embedding 概率高（descriptors/高频台词） |
| 降级率（degraded） | 警戒 > 10% | 超限说明主路径不稳；降级本身允许（裁 3 V1：A 主 B 降级） |
| tokens 日汇总 | 看板项，无硬线 | §15 成本治理按 profile 分组汇总 |
### 7.4 采集口径
- 每次调用都记；`batch_size` 决定 latency 归属（单条 vs 整批），日汇总按 `batch_size=1` 分组看单条 P95、其余看批量 P95。
- 与 chat 共用 §4 日汇总管线（按 profile_name 分组 sum/mean/P50/P95/max），但**分表**（`embed_*` 不进 chat 表）。
- `llm.embed_error` 的 `error_kind` 沿用 §4 枚举（timeout/connection/http_4xx/http_5xx/rate_limit），`error_hint` 同规则不落堆栈全文。
