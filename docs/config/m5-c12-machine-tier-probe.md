# Xeon 判机型零凭据巡检（M5-C12 第②件·pi P13 甲案落地）

> 维护：cline（依赖/配置/文档域）｜执行日：2026-10-03｜**零 yml 零代码**（只发只读 GET）
> 案来源：**pi M5-P13 `docs/perf/m6-perf-preplan.md` §5.4 甲案「零 yml」**（commit `1316c08`，176 行）。
> **性质：只读巡检**——不发写请求、不改 workflow、不改他人域文档（`docs/perf/` 归 pi 域，本单只引用不改）。

---

## 0. 结论速览

| 问 | 答 |
|---|---|
| 甲案（零 yml）能跑吗 | ✅ **能，已跑通**——三步匿名 GET 实测取到机型，**零凭据零 gh** |
| 最近 nightly 机型 | **AMD EPYC 7763 64-Core Processor**（与 EPYC 基线**一致**）——**Xeon 本轮未命中** |
| P12「无法判机型」 | **已由 P13 撤回**；根因＝**端点用错**（`/check-runs/{id}` 的 `output` **不含 `annotations` 数组本体**，须顺 `annotations_url` 再发一跳） |
| 需不需要改 yml | **不需要**。机型回传能力 C6（`f52858d`）早已在 step summary 里发 `::notice::机型一致：<brand>` |
| 建 Xeon 基线 | **仍需丙**（`GET /actions/artifacts/{id}/zip` 实测 **401**，`gh run download` 依赖不变） |

---

## 1. 三步配方（P13 §5.2，本机实测通过）

```bash
# 步 1  取 nightly-bench 的 run 列表（workflow id 361944466）
GET /repos/ZX466/natural-world/actions/workflows/361944466/runs?per_page=8
# 步 2  取该 commit 的 bench check-run（name 含 pytest-benchmark）
GET /repos/ZX466/natural-world/commits/{head_sha}/check-runs?per_page=50
# 步 3  ★读专用子端点——机型 annotation 在这里（P12 缺的就是这一跳）
GET /repos/ZX466/natural-world/check-runs/{id}/annotations
```

**步 3 是关键**：`GET /check-runs/{id}` 的 `output` 对象只有 `annotations_count` / `annotations_url` / `summary` / `text` / `title`（P13 实测 keys），**没有 `annotations` 数组**⇒ 顺着 `annotations_url` 再发一跳才有正文。

## 2. 本机实测（2026-10-03）

| run | 创建(UTC) | head_sha | check-run | 机型 annotation |
|---|---|---|---|---|
| `37067388197` | 10-02 21:31 | `76dd14a` | `111038495916` | `notice 机型一致：AMD EPYC 7763 64-Core Processor（本次 median 漂移可直接与基线比较）` |
| `36932896240` | 10-01 22:05 | `8c4f8a7` | `110606273418` | `notice 机型一致：AMD EPYC 7763 64-Core Processor（本次 median 漂移可直接与基线比较）` |

- **与 P13 表逐字吻合**（含 check-run id）⇒ 配方可复用，非一次性巧合。
- 每次 check-run 共 **3 条 annotation**，机型那条 `annotation_level=notice`。
- **最近一次 nightly 仍是 10-02 21:31 UTC**（cron `0 18 * * *` UTC ＋ 排队）⇒ 台账口径**截至 10-02**。
- **Xeon 未命中**：最近两轮均为 EPYC，与 `baseline-epyc7763.json` 同档 ⇒ 本轮 median 漂移**可直接比较**。

## 3. 两条使用边界（P13 §5.3，登记必写）

1. **时间下界**：机型防漂 step 由 **M5-C6（`f52858d` 2026-09-30 16:04，`959ccaf` 补 `::error::`）** 引入 ⇒ **该时刻之前的 run 没有 annotation**（P13 已举 `36670751263` 为例：它是 C5 记录的 Xeon run，**只能靠 artifact/其它手段判定**）。本配方**不能回溯判 09-30 16:04 之前的机型**。
2. **annotation 语义**：`notice 机型一致：<brand>` 只在**本轮 runner == 基线 `machine_info.cpu.brand_raw`** 时打；不一致则打 `warning` ＋ `::error title=基线不可比::`（**绝不判红**，判红仍只由 `median:25%` 决定）⇒ 台账口径须写「**与 EPYC 基线一致**」，**不是「绝对机型是 EPYC」**。

## 4. ⚠️ 限流实测：**走代理会 403，直连才有料**（P13 未记的新约束）

| 出口 | core 配额 | 结果 |
|---|---|---|
| **走代理** `127.0.0.1:7897`（exit `59.125.68.205`） | limit 60 / **remaining 0** | ❌ **HTTP 403 rate limit exceeded** |
| **直连**（无代理） | limit 60 / **remaining 19 → 用后 14** | ✅ HTTP 200 正常取数 |

⇒ **匿名配额是「按源 IP」而非「按调用方」**。代理出口 IP 为**多树共用**，余量被旁流吃光 ⇒ P13 §5.2「60 req/h 足够 3 个调用」在**单会话**成立，**在六树共用代理出口下不成立**。
**本配方跑法**：**必须直连**（`Remove-Item Env:HTTPS_PROXY,Env:HTTP_PROXY`），一轮约 **6 次调用**（1 列表 ＋ N 次 check-runs ＋ N 次 annotations）。配额窗口按小时重置（实测 reset `2026-10-03 20:51`）⇒ **日频安全，不要并发多树同时跑**。

## 5. 仍需凭据的唯一一件事（丙）

`GET /actions/artifacts/{id}/zip` 实测 **401 Requires authentication** ⇒ **建 Xeon 基线（P7 八步第 2 步 `gh run download`）依赖不变**。命中 Xeon 全绿 run 时才需要，别时无需求。

## 6. 本单变更清单与边界

| 文件 | 性质 |
|---|---|
| `docs/config/m5-c12-machine-tier-probe.md` | **新**：本巡检记录（配方＋实测＋边界＋限流约束） |
| `.orca/memory.md` | **+1 行**：②节本轮快照 |

**未做（刻意）**：改 `.github/workflows/nightly-bench.yml`（**零 yml 是甲案本身的要求**；且基线自动选择会改门禁语义，属 pi 域判断）／改 `docs/perf/*`（**pi 域**，含 P13 与 P12 台账）／改 `sim/`、`client/`、`docs/README`。

**只读性**：全程仅 6 次匿名 `GET`（**零写请求、零凭据、零 `gh`**）；临时 JSON 已删；未跑 pytest（零生产码）。
