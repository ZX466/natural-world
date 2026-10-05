# M6-C6 · M6 收官预检终版（G2 终跑 ＋ G4 终表 ＋ 四道门判定）

> 维护：cline（依赖/配置/文档域）｜基线：**main `0d5db41`**（M6 终波）｜单号：M6-C6（只读预检，**零代码零 yml**）
> 承接骨架：`m6-c5-closure-skeleton.md`（C5 建、本单**在其上追加/收口**，骨架不重写）。
> **纪律**：数字全部亲跑；性能留痕按 P10/P11 四件套（bench 结果 ＋ 同轮 `throttle_probe` 比值 ＋ skip 明细 ＋ 单独复跑对照），**不据 passed 数减少就写「回归」**。

---

## 0. 结论速览

| 门 | 判定 | 一句话 |
|---|---|---|
| **G1 台账** | ⚠️ **技术上不通过** | 113 行中**唯一非 ✅ 仍是 `README.md:314` 的 M5-C10 重复行**（`README.md:240` 同一单已 ✅）——**自 C5 报出后未修** |
| **G2 全量** | ✅ **可判过** | not-bench **2300 passed / 130 skipped / 0 failed**；bench **64 passed / 1 failed / 5 skipped**，**那 1 例判为环境抖动假红**（证据四件套齐全）；ruff/pyright 0；**恒等式 2500 两侧成立** |
| **G3 协议登记** | ✅ **通过** | §7＝**1.0／1.1／1.2**；**POWER 定标翻转未动协议面 ⇒ 无需新行**（正合判据） |
| **G4 挂账有主** | ⚠️ **有主，但新增两类 skip 待解锁** | H1 定标轮 **POWER 行已翻转落地**（CHAOS/FIRE 行未见）；**新增 10 条 skip-locked**（M6 内容面四 kind）＋ 1 条间歇性 |

**与 C5 骨架的差异**：G2 从「待跑」转 ✅；G1 的重复行**仍未修**；G4 因 POWER 翻转落地而推进一项、同时**新增 10 条 skip-locked**。

---

## 1. G2 终版复跑（对照 C13）

### 1.1 两口径

| 口径 | C13 基线（`2bd2bff`） | **C6 终版（`0d5db41`）** | 变化 |
|---|---|---|---|
| `-m "not bench"` passed | 2213 | **2300** | **+87** |
| 同上 skipped | 120 | **130** | **+10** |
| 同上 **failed** | 0 | **0** | **0** |
| 同上 deselected | 70 | 70 | 0 |
| 同上耗时 | 158.66s | 226.91s | +68s |
| `-m bench` passed | 69 | **64** | −5 |
| 同上 **failed** | 0 | **1**（**判为假红**，§1.3） | +1 |
| 同上 skipped | 1 | **5** | +4 |
| 同上 deselected | 2269 | 2430 | +161 |
| `ruff check` | pass | `All checks passed!` | — |
| `pyright` | 0 | `0 errors` | — |
| **恒等式** | 2403 | **2500**＝2300+130+70＝64+1+5+2430 | ✅ **两侧恒等** |

### 1.2 not-bench skip 分型——**逐条对照 C13**

| 型 | 文件 | C13 | **C6** | Δ | 说明 |
|---|---|---|---|---|---|
| T5 golden 全量 | `test_golden_full.py` | 10 | **10** | 0 | §16 设计，默认跳过 |
| T5 golden 冒烟 | `test_golden_smoke.py` | 1 | **1** | 0 | 同上 |
| T3 live-fire | `test_t3_live_fire.py` | 55 | **55** | 0 | 语料面 |
| T4 探针 | `test_t4_probes.py` | 53 | **53** | 0 | 三把锁未开（收官轮若已真跑则应归零） |
| **fire 机制面白盒锁** | `test_m5_fire_state.py` | **1** | **0** | **−1** | ✅ **自动解除**——`sim/world/fire.py` 落盘，**正是 P12 §2.5 预测的「解锁触发」**，实测验证 |
| **M6 内容面四 kind** | `test_m6_content_events.py` | 0 | **10** | **+10** | ⛔ **新增 skip-locked**：「M6 内容面四 kind 尚未登记（Claude 域施工中，对齐 fire.py 体例）」；**锁信号 = `EventKind` 出现 `ECOLOGY_`/`FAUNA_`/`SPEECH_`/`FOG_` 前缀成员，登记后自动解锁**。实测 `sim/core/events.py` **仍无**这些成员 ⇒ 锁有效 |
| **死亡写锁缺页** | `test_m6_death_path_data.py` | 0 | **1** | **+1** | ⚠️ **间歇性**：「本轮探针未复现上游写锁缺陷（**间歇性**）；夹具恢复 driver 形态须在根治合入后人工执行（A11 回执挂账①），**不随探针自动翻转**」 |
| A6 六锁 | `test_m5_anchors_branch_source.py` | 0 | **0** | 0 | 维持归零 |
| **合计** | | **120** | **130** | **+10** | −1 ＋ 10 ＋ 1 |
---

### 1.3 bench 那 1 例 failed＝**环境抖动假红**（非回归）

**四件套证据齐全**：

| # | 证据 | 实测 |
|---|---|---|
| 1 | 失败断言 | `AssertionError: 感知听觉 50 NPC（真实引擎·暖态中位）中位超阈值: median 4.519ms > 上限 3.600ms（差值 0.919ms；mean 4.479ms 仅参考）`（`harness.py:129`） |
| 2 | **同轮** `throttle_probe` | **`throttle_ratio 2.463`、`throttled: true`**（burst 20.123 / sustained worst 49.563） |
| 3 | 同轮 skip 明细 | soak 降频自检 **4 次自跳过**，自旋比 **3.059**（×3）与 **2.828**（×1）——**机器在跑 bench 期间自报降频** |
| 4 | **单独复跑**（P10/P11 判别法） | `test_perception_sound_50npc` 单跑 ⇒ **`1 passed in 0.18s`** ✅ |

⇒ **判定：降频导致的假红**。median 超线 **+25.5%**，而同轮自旋比达 **2.8–3.1**（持续段被限），量级相符；单跑 0.18s 绿。
⇒ 与主树自记「bench apply 偶发假红（本轮全量 1 例，复跑绿）——环境抖动判例已记（P6 同源）」**同族**。
**建议判门口径**：按「环境抖动假红」计入，**不判回归**；bench 有效成绩按 **65 passed / 5 skipped** 读（1 例假红另记）。

> **⚠ 一条对 C5 骨架的实测更正**：C5 记 C4 轮「连续 5 笔 ≤2.0 ⇒ 回落、门 2 解除」。**本轮 bench 期间机器又回到降频态**（自旋比 3.059/2.828，同轮外层探针 2.463）⇒ **回落不是稳定态，机器仍会周期性回降**；定标轮**开跑前仍须当场跑探针**（P13 门 2 的「步骤 0」不能省）。

## 2. G4 挂账终表

| # | 项 | 谁 | C5 时状态 | **C6 终态** | 证据 |
|---|---|---|---|---|---|
| **H1** | **定标轮** | pi ＋ Claude | 可派未派 | 🟡 **POWER 行已翻转落地**；CHAOS／FIRE 行未见落地 | `cc77932 feat(m6): POWER_MAX_BIAS 定标翻转 0.2→0.18（pi P5 扫参裁决同 CR）——flip advisory 翻正式 ≤0.25`。**实测其改动面 = `sim/npc/runtime.py`(3) ＋ `sim/npc/utility.py`(12) ＋ `sim/tests/test_m6_power_utility.py`(21)，`thresholds.py` 零改动**；常量落在 `sim/npc/utility.py:55 POWER_MAX_BIAS: Final[float] = 0.18` |
| **H2** | **soak 契约阶段 B** | 生命面给值 ＋ pi | 待值 | ⏳ **仍待值** | 阶段 A 已在（`SOAK_ENTITY_LOSS_PER_GAME_DAY = 0`，`:112`）；阶段 B 值仍待生命面给 |
| **H3** | P9 遗留 `rng_state_persisted=False` 升硬错误 | opencode A2 ＋ pi | 待随定标轮裁 | ⏳ **仍在** | `sim/core/persistence/rng_state.py:23` 与 `outbound_guard.py:75` 可见该字段；**未见升硬错误** |
| **H4** | M6 内容面收尾 | Claude 域 | 未核实 | 🔧 **新增可核项**：`test_m6_content_events.py` **10 条 skip-locked**（四 kind 未登记）⇒ **内容面四 kind 登记是收官前的一项明确待办** | `sim/core/events.py` 无 `ECOLOGY_`/`FAUNA_`/`SPEECH_`/`FOG_` |
| **H5** | **T4 台账追平** | Claude（G1 域） | 待追平 | ⏳ **仍未追平，且出现口径矛盾** | 主树 `05b8f28` 记「T4 真跑收官（hard_red=0）」；但本轮 not-bench **T4 仍 53 条全 skip**（三把锁未开）⇒ **「收官」与「台账/实测」不一致**，需澄清是「跑过一轮留痕」还是「常态可跑」 |
| **H6** | M6-C1/C2/C4/C5 台账登记 | cline 交／Claude 收编 | 零登记 | ⏳ **仍零登记**（`docs/README.md` 无任何 `M6-C*` 行） | 同上 |
| **H7** | **死亡写锁缺页（间歇性）** | Claude 域（A11 挂账①） | — | ⚠️ **新增**：`test_m6_death_path_data.py` 1 条 skip，**间歇性未复现**；文案明写「夹具恢复 driver 形态须在**根治合入后人工执行**，不随探针自动翻转」 | 本轮 skip 明细 |
| **H8** | **G1 重复行** | Claude（G1 域） | 已报未修 | ⚠️ **仍未修**（`README.md:314` M5-C10「⏳ 待收编」 vs `:240` 同单已 ✅） | 台账扫描 |

### 2.1 一条对 C5 骨架的**实测验证**（值得记）

C5 §3 曾把「待建 `sim/tests/bench/test_bench_fire.py` 漏标记」列为唯一条件性风险。本轮实测：**该文件仍未建**（`Test-Path`＝False）⇒ **该风险尚未触发**。
而实际落地的 POWER 翻转**走了另一条路**：`POWER_MAX_BIAS` 落在**生产代码** `sim/npc/utility.py:55`，其测试 `test_m6_power_utility.py` **无 bench 标记（即在每提交面）但零计时断言**（6 例纯确定数学，实测无 `time.`/`perf_counter`/`assert_median`）⇒ **每提交面安全**。
⇒ **C5 的核心结论「翻转对 not-bench 面零直接影响」获实测印证**；同时补充一条口径观察：**该常量是仿真语义/安规界（bias 系数 ＋ flip ≤0.25），不是性能预算** ⇒ 落 `sim/npc/` 而非 `thresholds.py`，**域归属比 P12 §2.4 第 4 步的字面更正确**（`thresholds.py` 是性能真相源，不该混入仿真语义常量）。

---

## 3. M6 版收官门四道判定与判据索引

### 3.1 四道判定

| 门 | 判据 | 证据出处（可复核） | 判定 |
|---|---|---|---|
| **G1** | 台账零 `⏳` ＋ 零重复行 | `docs/README.md` §5：**113 行**，非 `✅` **1 行**＝`README.md:314`（M5-C10 重复，`:240` 已 ✅） | ⚠️ **技术上不通过**（假 `⏳` 一行） |
| **G2** | 双口径 0 failed ＋ 恒等式 ＋ lint/type 0 | 本轮亲跑：not-bench **2300/130/0**（226.91s）；bench **64/1/5**，1 例经四件套判 **假红**（§1.3）；恒等式 **2500 两侧成立**；`ruff` **All checks passed**／`pyright` **0 errors** | ✅ **可判过** |
| **G3** | §7 有当期登记行 ＋ 版本号与 §3 一致 | `versioning.md:63-65`＝**1.0／1.1／1.2**。**POWER 翻转零协议面改动**（改 `sim/npc/*` 内部常量）⇒ **无需新行**，与「只有 wire 面变更才 minor」的判据一致 | ✅ **通过** |
| **G4** | 剩余项有主、无「等外部条件」悬空 | §2 终表 **H1–H8 八项均有主**；无「等 key」类悬空（T4 已跑过，见 H5 口径问题） | ⚠️ **待收口**（H1 部分／H4 明确待办／H1·H5·H7·H8 待处置） |

### 3.2 判据索引（终版，供收官轮逐条引用）

| # | 判据 | 证据出处 | 终态 |
|---|---|---|---|
| J1 | not-bench 0 failed | `uv run pytest -m "not bench" -q` @`0d5db41` | ✅ **2300 passed / 130 skipped / 0 failed** |
| J2 | bench 失败经四件套判别 | §1.3 四行证据（断言／同轮探针 2.463／skip 自旋比 3.059·2.828／单跑绿） | ✅ **假红，非回归** |
| J3 | 计数恒等式 | **2500**＝2300+130+70＝64+1+5+2430 | ✅ 两侧恒等 |
| J4 | skip 分型稳定性 | §1.2：五型持平、**fire 锁 −1 自动解除**、**新增 M6 四 kind +10**、间歇性 +1 | ⚠️ 结构已变，**已逐条归因** |
| J5 | lint/type | `ruff check`／`pyright` | ✅ pass／0 errors |
| J6 | 协议登记一致 | `versioning.md` §7＝1.0/1.1/1.2；POWER 翻转零 wire 变更 | ✅ 通过 |
| J7 | 台账零 `⏳` ＋ 零重复 | `README.md:314` vs `:240` | ⚠️ **未通过** |
| J8 | 翻转对每提交面零影响 | C5 三条证据 ＋ 本轮 `test_m6_power_utility.py` 6 例零计时 | ✅ **实测印证** |
| J9 | 定标门 2「步骤 0」不可省 | C4 曾连续 5 笔健康，**本轮 bench 期间又回 3.059/2.828** | ⚠️ **回落非稳定态，开跑前须当场跑探针** |

---

## 4. 本单变更清单与边界

| 文件 | 性质 |
|---|---|
| `docs/config/m6-c6-closure-final.md` | **新**：本终版预检稿 |
| `.orca/memory.md` | **+1 行**：②节本轮快照 |

**未做（刻意）**：改 `.github/workflows/`（**零 yml**）／改 `sim/`（跑测试与探针**只跑不改**）／改 `docs/README.md`（G1 归 Claude，**含那处重复行未动**）／改 `docs/perf/`（pi 域）／改 C5 骨架稿（**只引用不重写**）。

**本单亲跑的验证**：两口径全量 pytest ＋ 单独复跑失败项 ＋ 同轮 `throttle_probe` ＋ skip 明细解码 ＋ 计数恒等式 ＋ `ruff`／`pyright` ＋ 台账行扫描 ＋ `versioning.md §7` 核对 ＋ `events.py` 锁信号核对 ＋ 翻转 commit 面核对。

