# M6 性能开题预研（M5 收官性能复核 + 定标就位 + M6 候选面优先序与判据 + 无凭据判机型路径）
> 性能域（pi），2026-10-03。任务：M5-P13（**零代码**：`sim/`、`thresholds.py`、既有 bench、`docs/README`、**任何 yml 零改动**）。
> 基线：main `8491659`（= 本树 HEAD，开工前同头确认；2226 passed / 121 skipped 系主树口径）。
> 依据：P12 台账 `m5-closure-perf-ledger.md`（本档是其 M6 续页，不重复其内容）+ 三案预算案 P9/P10/P11
> + cline C10 `m5-c10-closure-inventory.md`（挂账 B1–B6）+ DESIGN §17 L482（M6 定义）/§18 L491（可砍序）/§7 L384（动物=M6 最高风险）。
> **范围判断归 Claude**：本档只给「性能视角的优先序 + 每面 2–3 条判据建议」，不替 M6 圈定范围。
> ⚠ **本档 §5 撤回并纠正 P12 的一条结论**（原「无 gh 无法判机型」= 端点用错，非能力缺口）——先读 §5。

## 0. 结论速览
| # | 问题 | 结论 |
|---|---|---|
| 1 | M6 性能面的**优先序**？ | **P0 三案定标轮（已排队）→ P1 批次 E 物化读档 → P2 动物三只（感知 profile）→ P3 生命始终（撞既有 soak 契约，见 §3.2）→ P4 身体会坏 → P5 P5 措辞/LLM 面 → P6 节气/日历（近零成本，只需一条防呆）**。排序依据 = **是否已有前置投入**（P0/P1 已备好案）×**冷路径倍率**（P2/P3 各有一个量级风险）。§3 |
| 2 | 三案定标轮在 M6 的触发点？ | **重申两条硬门**（P12 §2.1）：①批次 C 接线 **且** 批次 D 机制面落盘 ⇒ 才派定标执行单；②开工第一件事仍是 `throttle_probe` ≤ 2.0。当前（main `8491659`）实测三案前置**仍未满足**（§2.1 复述 + §4 复核表）。 |
| 3 | `MATERIALIZE_LIMIT_MS=50.0` 提案的判定前置？ | **不是「读档面施工后实测」这么轻**——需三条前置同时成立才落数（§2.2）：施工落盘 + 窗口上限 `W` 定死 + **读档在真实 WS/HTTP 面被触发**（否则测的是纯函数不是路径）。当前**只能保持 advisory**。 |
| 4 | 动物三只的性能风险具体在哪？ | 感知候选数 ∝ **半径²**（不是线性）：human `vision_radius=12.0/hearing_radius=14.0` 是**已定标红线 `PERCEPTION_TICK_LIMIT_MS=3.6` 的标定基**；若猫/犬/鸦按 DESIGN 拿更大半径（夜视/嗅觉/视野），**单者成本按面积放大 1.8–4x**，且实体数 50→53 还叠加 N² 配对项。§3.1 |
| 5 | **⚠ 生命始终会撞既有 soak 契约**（本轮最有价值的发现） | `test_bench_soak.py:146/:163` **硬断言「实体数不漂移」**（`assert result.entity_count_end == result.entity_count_start`，两处：nightly 全量口径 + CI 冒烟口径）。M6「生命始终」若让 NPC 死亡 ⇒ **7 日 soak 与 nightly 30k 必然判红**，且这是**契约冲突不是性能回归**。⇒ 必须**在 M6 机制施工之前**先改口径（改成「只减不增 + 有界」或按存活集重算），否则收官后的第一份 nightly 红会被误读成性能退化。§3.2 |
| 6 | 无凭据怎么判 Xeon？ | **P12 记错了**：正确端点是 `GET /check-runs/{id}/annotations`（专用子端点，**匿名可访问**）——本机实测连续 4 次 nightly 全部读到 `机型一致：AMD EPYC 7763`。⇒ **判机型不需要 gh/token**；真正需要凭据的只有 **artifact 下载**（建基线八步用）。§5 |

---

## 1. M5 收官性能面复核清单（**收官轮可直接引用**）
> 用法：收官轮逐行核对「现状」列；凡「应为」列未达成，**在收官声明里显式写成已知限制**，不留空。

| 复核项 | 收官时**应为**状态 | 当前实测（main `8491659`） | 判定 |
|---|---|---|---|
| 三案红线是否进 `thresholds.py` | **允许不进**，但必须有「为什么不进」的一句书面理由（= 前置未满足） | `grep CHAOS/POWER/FIRE/MAX_BIAS/REGRESS thresholds.py` 零命中；P12 §1 已给书面理由 | ✅ 成立（理由在案） |
| M5 唯一入库的新行 | 只有 `FAST_FORWARD_FRAME_LIMIT_MS=0.90` / `..._REQUEST_DURATION_LIMIT_S=42.0`（P3/P5 共担） | 同（thresholds.py:197 段） | ✅ |
| 两簇门 2.0（降频判据） | 收官声明引用**两簇数据**（健康 1.2–1.7 / 降频 6.6–8.4），不是只写「门=2.0」 | P12 §3.1 时间线 5 点齐 | ✅ |
| 计数恒等式 | 收官基准总数 = 当轮 `--collect-only` 全量，并与分档口径互验 | **本单实测（main `8491659`）**：全量 **2347 collected** = not-bench `2277 collected / 70 deselected` ⇒ 恒等式 2277+70 = 2347 ✓（P12 的 2267 已过时，+80 = R-4/K14/S11/C11 收编新增） | ✅ **已重算**（collect-only 只读，不违「不重跑 bench」） |
| 留痕三件套纪律 | 写进 `docs/perf/bench-plan.md` 或 budget.md（性能面唯一真相源），而非只存预算案 | 目前只在 P11/P12 文档内 | ⚠ **待落位**（M6 开工单建议顺手落，归性能域施工） |
| Xeon 基线 | 如实登记「未命中/未建」；**且判机型路径已通**（§5），被动台账可无凭据自转 | P12 记「无法判机型」⇒ **该结论已被 §5 推翻** | ⚠ **P12 §5 需按本档更正**（一行改动，随下轮收编） |
| soak 门级联 skip | 收官声明写「bench passed 数随降频门浮动（幅度可达 3）」，禁止据此判回归 | P11 判例 + P12 §3.1 机理结案 | ✅ |
| 定标 runbook | 备好即用（P12 §2 五步 + 断言映射 8 行） | 在案 | ✅ |
| 裁 31–34 裁决文字落库 | **收官前落进 `docs/arch/m5-rulings.md` 正文**（否则台账「采况」只能标推断） | P12 §3.3 实测：`grep 裁决 3[1-4] docs/arch/` 零命中 | ⚠ **归架构域**（只报不改，M5 收官阻断项之一） |

**小结**：M5 性能面**可以收官**，但需带 3 条明确限制（三案 advisory + Xeon 未建 + 计数恒等式待用新总数重算）+ 2 条移交（留痕三件套落位、裁 31–34 落正文）。

---

## 2. 定标执行单就位确认（P12 §2 runbook 在 M6 的触发点重申）

### 2.1 触发点（**两条硬门，缺一不派**）
```
门 1（内容）：批次 C 权力核心接线（PowerStore → utility 权重传导）落 main
             且 批次 D 火灾机制面落盘（sim/world/fire*.py 存在 ⇒ S9 D-1 skip 自动解除）
             ── 当前（main 8491659）实测：sim/npc 零 power 消费、无 fire*.py ⇒ 未达
门 2（机器）：uv run python -m sim.tests.bench.throttle_probe ⇒ throttle_ratio ≤ 2.0
             未达 ⇒ 不跑（跑了也不算数，绝对阈值必假红，P6 仲裁）
```
满足即派 **M6-P1（定标执行单）**，内容 = P12 §2.3 断言映射 8 行 + §2.4 翻转五步（顺序不可换）。
**批次 A 收口（混沌接线）可独立触发 CHAOS 那一行**——不必等 C/D，三案可分三批定标（P12 已按案拆分）。

### 2.2 `MATERIALIZE_LIMIT_MS = 50.0` 提案的判定前置（**比「施工后实测」更严**）
A3 预估 ≈20–40ms 是**部件拼装的量纲**（展开 0.4 + 窗口重放 ≤14.8 + 语料灌入 6.1 + fork 克隆）。要在 M6 收口成硬红线，三条前置**同时**成立：
1. **施工落盘**：`anchor_packages` 表 + 读档函数存在（批次 E，opencode；**迁移号须待实际 head 定，勿先占 0015**——cline C10 B3 已钉）；
2. **窗口上限 `W` 先定死**：重放项 = `W tick × e 事件/tick × 0.74µs`；`W=1000, e=20` ⇒ 14.8ms。
   ⇒ **红线数值依赖 `W`，而 `W` 归架构域裁**；`W` 若改（例如按档 10 日窗口 ⇒ 1.728M 事件 ⇒ **1.28s**），50ms 这条线立即失效 ⇒ **不可先写死**；
3. **测真实触发路径**：读档须**经 API/WS 面被调用**才算数（否则测的是纯函数，漏掉序列化/DB 往返/连接池）。⇒ bench 口径应为「调读档入口」而非「调内部折叠」。
⇒ **当前判定：保持 advisory**；收口时机 = 三条前置齐 + 定标机探针 ≤2.0，届时按 `实测 ×1.7` 给值（可能 ≠50.0，**不预支**）。
⇒ **进档档别已定**：一次性操作档（比照 `SNAPSHOT_LIMIT_MS=500.0`），**绝不进 tick 预算**（P6 anchors 先例：不进 `_tick_once` ⇒ 不加 tick 行）。

---

## 3. M6 候选面的性能输入（优先序 + 每面 2–3 条判据建议）

### 3.0 优先序总表
| 优先级 | 面 | 为什么是这个位 | 施工归属 |
|---|---|---|---|
| **P0** | 三案定标轮（CHAOS/POWER/FIRE） | 已有案、已有 runbook、只差接线 ⇒ **纯排期问题，成本最低** | pi |
| **P1** | 批次 E 物化读档 | M5 遗留设计稿已可施工；且**首次引入「一次性操作档」红线体例**（M6 其他一次性面可复用） | opencode + pi |
| **P2** | 动物三只（独立感知 profile） | DESIGN §7 L384 自标「M6 最高风险」；**成本 ∝ 半径² 会直接冲撞已定标的 `PERCEPTION_TICK_LIMIT_MS=3.6`** | Claude + pi |
| **P3** | **生命始终（死亡）** | **撞既有 soak 契约**（§3.2）——不改口径 ⇒ 第一轮 nightly 必红且被误读为性能回归。**必须在机制前处理** | Claude + pi |
| **P4** | 身体会坏 | 与既有 needs 同构（`advance_needs` 3.2µs/人），量级安全；风险只在「别做成逐对象第二套」 | Claude |
| **P5** | P5 措辞生成载体（挂账 B2） | LLM 面成本，受既有 `LLM_SCHED_TICK_LIMIT_MS=0.20` 约束；**性能面小，语义面大** | Claude |
| **P6** | 节气/世界日历（§17 可砍序末位） | 纯计算低频，近零成本；**唯一防呆 = 别每 tick 查表/算天文** | Claude |
| — | 美术音效打磨 | 客户端/资产面，**内核 tick 成本≈0** ⇒ 本域不展开 | cline/前端 |

### 3.1 动物三只（P2）——**性能判据建议**
现状事实（实测）：感知 profile 是**物种级**（`sim/perception/profiles/base.py`），人类一套 `HUMAN = vision_radius 12.0 / hearing_radius 14.0 / max_observations 12`；`PERCEPTION_TICK_LIMIT_MS=3.6` **是按 human 标定的**。
1. **判据①「候选数按面积而非线性」**：配对候选数 ∝ `r²`。实测几何比（密度不变）：r=16 → **1.78x**、r=18 → **2.25x**、r=20 → **2.78x**、r=24 → **4.0x**。
   ⇒ 建议：**新物种 profile 的半径上调幅度须给「等效 human 数」换算**（鸦若 20 视野 ⇒ 一只 ≈ 2.78 个人类的感知工作量），红线**按等效工作量断言**而不是按实体数。
2. **判据②「实体数增加带来的 N² 项」**：50 human + 3 动物 ⇒ 配对检查基数从 `C(50,2)` 变 `C(53,2)`（+12%），**但跨物种的观测是双向不对称的**（我听得到你 ≠ 你听得到我）⇒ 建议红线口径 = 「**新增物种 3 只，感知总成本增幅 ≤ 25%**」（实测三只异半径额外配对占 human50 基线的 18–31%）。
3. **判据③「不要新开感知通道」**：`max_observations` 是 **prompt 体积治理阀**（base.py 注释）。若为动物新增第四通道（如嗅觉 profile 专用），感知 + 嗅觉 + LLM prompt 三处同时膨胀 ⇒ 建议**复用既有三通道（视觉/听觉/触觉）参数化**，零新通道。
> **红线归位建议**：**不新建 `ANIMAL_PERCEPTION_LIMIT_MS`**——并入 `PERCEPTION_TICK_LIMIT_MS=3.6` 同一行（同 P9/P10/P11 的「不新造预算轴」裁定；扩实体数=同一条线的负载变量）。

### 3.2 生命始终（P3）——**⚠ 契约冲突，本轮最有价值的发现**
实测代码事实（`sim/tests/bench/test_bench_soak.py`）：
- `:146–147`（nightly 30k `_assert_no_runaway`）与 `:163–164`（CI 冒烟 `_assert_smoke`）**都硬断言实体数不漂移**：
  `实体数漂移 {entity_count_start} → {entity_count_end}` 即红。这条断言**诞生时 M0–M5 世界里 NPC 不会死**，所以恒等成立。
- ⇒ **M6「生命始终」一旦让 NPC 死亡，两处断言必红**，且红的是**契约过期**（不是性能回归）。按本域纪律（P11/P12：passed/skip 变动先查契约与门），这会被读成一晚的性能事故。
**建议（三选一，归 Claude 裁；本域推荐 ①）**：
1. **①（推荐，最小改动）**：把断言从「恒等」改为「**只减不增 + 有界**」：`entity_count_end ≤ entity_count_start` 且 `start − end ≤ 预期死亡上界`（由 7 日 × 存活率给）。既保「无失控新增（泄漏）」的原始意图，又容纳设计内的死亡。
2. **②**：soak 用「存活集快照」重算实体数（改动大，且弱化泄漏判别——新增实体会被存活过滤吃掉 ⇒ **不推荐**）。
3. **③**：M6 施工时给 soak 加 `allow_mortality` 开关（多一条口径 = 双真相源风险，**次选**）。
**附带判据**：
- **死亡事件密度**：若 50 NPC × 平均寿命 ~35 游戏日 ⇒ 7 日 soak 内死亡 ~10 起 ⇒ 每起 1–3 事件（死亡+材料归属/继承），**噪声级**（对齐 `APPLY_P99=0.04`）。⇒ **不需要红线，但需要进 soak 断言的分母**（若把死亡也纳入「实体数」）。
- **T2 回放逐位一致**：死亡时刻必须 `(world_seed, 事件流, tick)` 确定性派生，禁墙钟/`import random`——**这是 C5 契约的新暴露面**（老 code 无死亡 ⇒ 无此钉）。建议 M6 施工同时加一条「死亡不引入非确定性」白盒钉。

### 3.3 身体会坏（P4）——判据建议
1. **复用 needs 形态，别造第二套推进器**：现状 `advance_needs` = **逐对象 Python，3.2µs/人、50 人 175µs**（P10 实测）。身体健康若另起一份逐人循环 ⇒ 直接翻倍同类成本。⇒ 判据：「身体健康推进**并入既有 needs 向量化路径**，增量 ≤ +50%（P10 口径：向量化一列 ≈ +15%）」；
2. **禁逐 NPC `dataclasses.replace`**（P10 反模式实测 81µs/50 人）；
3. 物质守恒：身体损坏的材料去向须走 `material_moved{reason}` 既有枚举（**别为「尸身」新造 reason 而不进守恒**，A9 的 `to_ref="world:burned"` 先例可参照）。

### 3.4 P5 措辞载体（P5）+ 节气（P6）——各一条
- **P5 措辞（挂账 B2，三轮未动）**：性能关注点 = **别把措辞生成本地做成每 tick 或每次 plan 的额外 LLM 往返**；既有 `LLM_SCHED_TICK_LIMIT_MS=0.20` 只卡调度，**不卡 prompt 体积** ⇒ 建议「措辞是**装配期纯函数**（零额外网络往返、零新 LLM 调用）」这一条写进施工判据，性能侧则盯 `prompt 长度不超 M2/M3 定的预算`（`max_observations=12` 同族治理）。
- **节气/世界日历**：现有 `sim/core/calendar.py` 是**纯函数相位计算**（`phase_of_day(tick)`/`is_market_day`，`MARKET_DAY_INTERVAL=5`），零成本。⇒ **唯一防呆判据 = 「节气/日历量必须是 `tick` 的纯函数或 ≤ 每日一次查表，禁每 tick 天文计算/禁落事件流」**（否则 86,400 tick/日 × 新事件 = 事件风暴，同 P11 W-D3 判据的格驱动反例一族）。日历属 M6 打磨面（裁 21-A D-1）。

---

## 4. M6 开题的三条性能前置（**给收官轮的排期输入**）
1. **定标轮排期**：三案红线在 M6 的**第一个性能动作**，且可分批（A 收口 → CHAOS；C 接线 → POWER；D 机制 → FIRE）。**不占设计带宽，只占机时**（每轮 ≈ 探针 30s + bench ~4.5min + 视情 soak）。
2. **契约先于机制（P3 教训）**：凡「改变世界基线集合」的机制（死亡/出生/实体增删），**先改 soak/冒烟断言口径，再落机制**。否则新机制的第一份 nightly 红必然误判。⇒ 建议 M6 排期把「soak 实体数口径」小单排在「生命始终」施工**之前**。
3. **一次性操作档体例（P1 副产品）**：M6 会引入多处「非 tick」重操作（物化读档、断线追赶、7 日演练、完整 soak）。⇒ 建议**统一一条「一次性档」体例**（比照 `SNAPSHOT_LIMIT_MS=500.0`：单次上限 + 「异步不阻塞 tick」接法红线），避免每个面各造一个不可比的绝对阈值。

---

## 5. **无凭据判机型路径**（**撤回 P12 §5「本轮无法判机型」结论**）

### 5.1 P12 错在哪（复盘，单一根因）
P12 查的 sha **没有错**（nightly run 37067388197 的 `head_sha` 就是 `76dd14a`，本会话实测确认）。
唯一根因 = **端点**：P12 读 `GET /check-runs/{id}`，该响应的 `output` 对象**只有 `annotations_count` 与 `annotations_url` 两个字段，没有 `annotations` 数组本体**
（实测 keys：`['annotations_count','annotations_url','summary','text','title']`，且 `title/summary` 皆 null）——
**annotation 正文要顺着 `annotations_url` 再发一跳 `GET /check-runs/{id}/annotations` 才有**。
⇒ P12 据此写「不可达 / 记未知」= **工具用错，不是能力缺口**。**已在本文纠正**（P12 §5 行已同步更正）。

### 5.2 正确路径（**本机 2026-10-03 实测通过，匿名、无 gh、无 token**）
```
步骤 1  取 nightly run 的 head_sha
        GET /repos/{owner}/{repo}/actions/workflows/361944466/runs?per_page=8
步骤 2  取该 commit 的 bench check-run id
        GET /repos/{owner}/{repo}/commits/{head_sha}/check-runs?per_page=50   →  name 含 "pytest-benchmark"
步骤 3  读专用子端点 ← 机型 annotation 在这里（P12 缺的就是这一跳）
        GET /repos/{owner}/{repo}/check-runs/{id}/annotations                  →  message 含「机型」
```
实测结果（Nightly Bench workflow id `361944466`，5 次连续 run）：
| run | 日期(UTC) | head_sha | check-run | 机型 |
|---|---|---|---|---|
| 37067388197 | 10-02 21:31 | `76dd14a` | 111038495916 | `notice 机型一致：AMD EPYC 7763 64-Core Processor` |
| 36932896240 | 10-01 22:05 | `8c4f8a7` | 110606273418 | `notice 机型一致：AMD EPYC 7763` |
| 36780592123 | 09-30 21:37 | `e7706fc` | 110109560165 | `notice 机型一致：AMD EPYC 7763` |
| 36721350832 | 09-30 13:24 | `14aa57f` | 109906989836 | `notice 机型一致：AMD EPYC 7763` |
| 36670751263 | 09-30 04:51 | `ac0d559` | 109745026708 | **无机型 annotation**（见 §5.3：该 step 当日 16:04 才落地） |

⇒ **Xeon 台账可以完全无凭据自转**（被动命中检测每天 3 个 GET 即可）。**仍需要凭据的只有一件事**：artifact 下载（建基线八步）——实测 `GET /actions/artifacts/{id}/zip` **401 Requires authentication** ⇒ P7 八步第 2 步的 `gh run download` 依赖不变。

### 5.3 两条使用边界（**登记时必须写明，别过度宣称**）
1. **时间下界**：机型防漂 step 由 cline M5-C6 引入（`f52858d` 2026-09-30 16:04、`959ccaf` 16:07 补 `::error::`）。⇒ **该时刻之前的 run 没有 annotation**（上表 `36670751263` 即例——它是 P7 记录的 Xeon run，**只能靠 artifact/其它手段判定，annotations 读不到**）。回溯分析早于 09-30 16:00 的 run 时，**不得把「无 annotation」读成「机型一致」或「未落 Xeon」**。
2. **annotation 语义**：`notice 机型一致：<brand>` = 本轮 runner == 基线 `machine_info.cpu.brand_raw`（**相等才打这条**）；不一致则打 `warning` + `::error title=基线不可比::`（**绝不判红**，判红仍只由 `median:25%` 决定）。⇒ 台账口径应写「**与 EPYC 基线一致**」而非「是 EPYC 机器」——若基线文件本身换机，notice 会跟着变（单一真相源在 `baseline-epyc7763.json`）。

### 5.4 给 cline 的施工建议（**只出案，本域不改 yml**）
| 方案 | 改动面 | 评价 |
|---|---|---|
| **甲（推荐，零 yml）** | cline 的监控/巡检 job 直接按 §5.2 三步 GET 取机型，写入台账（可日频、匿名、限流友好：60 req/h 未认证足够 3 个调用） | ✅ 即用、无 CI 变更、无凭据；**唯一限制 = §5.3 时间下界** |
| **乙（可选加固）** | nightly 把 `docs/perf/runner.txt` **回写入库**（当前 yml 只在 job 内 `cat` + 归档 artifact，**不 push**；`git log` 实测 runner.txt 仅 `cc21643` 模板一次提交 ⇒ 库里是**模板不是数据**） | ⚠ 需 yml 加 push 步骤 + 写权限（`permissions: contents: write`）= 新增自动提交面，**收益仅等于甲**（甲已能拿机型），**不建议** |
| **丙（要基线才需要）** | 一次性给 `gh run download -n bench-result` 的 token 授权（P7 八步第 2 步） | 命中 Xeon 全绿 run 时**必须**用，别时无需求 |
⇒ **结论：判机型选甲（今天就能跑，零依赖）；建 Xeon 基线仍需丙。M6 若要求「被动台账自动化」，本域建议 cline 按甲落地，不动 workflow。**

---

## 6. 零改动留痕（2026-10-03，本机）
本单**只新增本文档**（+ 自树 `.orca/memory.md`）。`git status` 除本文档外零改动；**未碰** `sim/`、`sim/tests/bench/`、`thresholds.py`、`docs/README.md`、`.github/workflows/*.yml`（卡片明令）。

| 动作 | 结果 |
|---|---|
| `grep "runner 机型防漂检查\|::notice::机型一致" .github/workflows/nightly-bench.yml` | 命中 `:109–141`（step 存在，notice/error 双语义）⇒ §5 路径的依据 |
| `git log --oneline -S "runner" -- .github/workflows/nightly-bench.yml` | 防漂 step = `f52858d`(09-30 16:04) + `959ccaf`(16:07) ⇒ §5.3 时间下界依据 |
| `git log --oneline --follow -- docs/perf/runner.txt` | 仅 `cc21643`（模板入库一次）⇒ 库内 runner.txt **不是 nightly 产物**（§5.4 乙案依据） |
| GitHub REST 匿名三连（5 个 run） | 4/4 近期 run 读到 `机型一致：AMD EPYC 7763`；早于 step 落地的 `36670751263` **无 annotation** ⇒ §5.2/§5.3 实测 |
| `GET /actions/artifacts/{id}/zip`（匿名） | **401 Requires authentication** ⇒ 建基线仍需凭据（§5.2 末） |
| `GET /check-runs/{id}` vs `/check-runs/{id}/annotations` | 前者 `output` 无 `annotations` 字段（仅 `annotations_count`/`annotations_url`）、`title/summary=null`；后者返回 3 条含机型 notice ⇒ **P12 误判根因坐实** |
| 感知 profile 事实核对 | `profiles/base.py`（物种级 + `max_observations=12` 注释=prompt 体积治理）+ `human.py` `vision 12.0/hearing 14.0`；几何 ∝ r²：16→1.78 / 18→2.25 / 20→2.78 / 24→4.0；三只异半径额外配对实测占 human50 基线 **18–31%** |
| soak 契约核对 | `test_bench_soak.py:146/:163` 实体数恒等断言（`==`，两处）在位 ⇒ §3.2 冲突成立 |
| `uv run ruff check .` | **All checks passed** |
| `uv run pyright .` | **0 errors, 0 warnings, 0 informations** |
| `pytest -q --collect-only`（两口径） | 全量 **2347 collected** / not-bench **2277 collected, 70 deselected** ⇒ 恒等式 ✓（与派单板「2226 passed + 121 skipped = 2347」同总数） |
| `throttle_probe` | 本单**未跑**：只读汇总 + 文档，无绝对阈值实测红线；§5 三连 GET 与 §3.1 几何测算**不依赖 CPU 档位** ⇒ 不受降频门影响（特此说明，非疏漏） |
