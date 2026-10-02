# M5-C7 workflow 台账巡检 + T4 接线两口径预研

> 能力域：依赖 / 配置 / 文档（cline） | 状态：**审计 + 预研稿（提案制），零 workflow 改动、零生产码**
> 派单：Claude 主树 `.orca/talking.txt`「M5-C7」（2026-10-02，基线 main `8c4f8a7`）
> 门禁：只动 `docs/config/`（新建目录）+ `docs/README.md` 两行登记 + 自树 `.orca/memory.md`；
> **未改任何 `.github/workflows/*.yml`**（两口径均只预研，等用户裁决后才出施工单）。
> 依据：`.github/workflows/` 全量四文件逐行实读；`docs/dev-workflow.md` §3；`docs/security/t4-corpus.md` §5；
> `docs/arch/m4-plan.md` §4 + 裁 14-4；`docs/security/m4-closure-preaudit.md` L54–65；
> `sim/tests/test_t4_probes.py`（三把防烧钱锁）；`docs/perf/bench-plan.md` §4.1。

---

## 0. 速览：派单前提需要纠偏（**先读这一节**）

派单转述 codex 收编时的提醒：**「t4-nightly 探针 step TODO + env 写 claude-sonnet-5」**。
本轮对 `.github/workflows/` 全量实读后，**这两条均已在 main 闭合**，属过期项：

| codex 的提醒 | main 实测（`8c4f8a7`） | 证据 |
|---|---|---|
| `t4-nightly.yml` env 写 `claude-sonnet-5` | ✅ 已是 `T4_MODEL: Deepseek-v4-flash` | `t4-nightly.yml:44`；提交 `d1940e4`（M4-C6，2026-09-27） |
| `t4-nightly.yml` 探针 step 是 TODO | ✅ 全仓 `.github/workflows/` 命中 `TODO/FIXME/TBD/待接线` **0 处**；探针段不是 TODO，是**显式裁定的注释态**（「长期保持注释」，`t4-nightly.yml:96–112`） | 提交 `c21c781`（M4-C2 收官存照）；`docs/security/m4-closure-preaudit.md:60–65` 已自记该两条闭合 |

⇒ **「两口径冲突」不在 yml 层，而在文档层**：唯一真实冲突是
`docs/arch/m4-plan.md` §4（+ 裁 14-4）仍把「T4 全绿」定义为「**锁定模型版本下 nightly 连续通过**」，
而 2026-09-27 用户改约后 `docs/dev-workflow.md` §3 与 `t4-nightly.yml` 存照已把验收口径改为
「**本地跑一轮真模型探针 ＝ 等效验收**」。同一句验收词，两个真相源。
（`m4-plan.md` 属 Claude 域，**本单只报不改**。）

---

## 1. 台账核对清单（`.github/workflows/` 全量四文件）

| Workflow | 触发器 | cron（UTC / 北京） | 门禁角色 | TODO / 未闭合项（本轮实测） | 建议动作 |
|---|---|---|---|---|---|
| `ci.yml` | `push`（branches `["**"]`）+ `pull_request`（→ `main`）；`concurrency: ci-${{github.ref}}` + `cancel-in-progress` | —（**无 schedule**，符合「仅 schedule 不进每提交 CI」铁律的反面：每提交门禁本体） | **唯一每提交门禁**：`uv lock --check` → `uv sync --frozen` → `ruff check` → `ruff format --check` → `pyright` → `pytest -m "not bench"`；另 5 条**按文件路径**独立命名门禁（`test_t3_gate.py` / `test_t1_self_unknown.py` / `test_m1_metrics.py` / `test_t1_l1_whitelist.py` / glob `sim/tests/test_m2_*.py`，`timeout-minutes: 15`）；`frontend` job（node 24 / `gen:protocol --check` / `tsc` / `eslint` / `prettier --check` / `vitest`） | **零 TODO**。两条**已知设计性脆弱**（非缺陷）：①`-m "not bench"` **会选中 t4 marker 用例**（L52–53 实测注释），零烧钱**只靠探针自身 env 门**（三把锁），探针若去掉 env 门即真烧钱；②5 条路径门禁在「文件缺失」与「收集 0 用例（exit 5）」时均 `warning + exit 0` ⇒ 文件被误删/改名会**静默降级为绿**（有意取舍：避免误红，须靠 CI 日志肉眼发现） | 保持现状。②的降级路径已由各 step 的 `::warning::` 文案自暴露，不建议改（改动会波及他域门禁语义）。①建议在 `ci.yml` L55 附近补一行指向本审计的指针注释（**待裁**，本单未改） |
| `nightly-bench.yml` | `schedule` + `workflow_dispatch` | `0 18 * * *` = 北京 **02:00** | 性能红线 + M2 完整 soak + 基线对比：机器档位记录 → `pytest -m bench`（`PI_BENCH_ADVISORY=1`）→ M2 7 日自转完整跑（`PI_M2_FULL_SOAK=1`，`timeout-minutes: 60`）→ artifact（`if: always()`）→ runner 机型防漂检查（**只 warning，绝不判红**）→ 基线对比（`--benchmark-compare-fail=median:25%`，同带 `PI_BENCH_ADVISORY=1`） | **零 TODO**。两处**已登记挂账**（非本单新发现）：①基线「按机型分文件」目前只落了 `baseline-epyc7763.json`，**Xeon 8573C 档位基线未建**（`baseline_meta.open_items` ③、`bench-plan.md` §4.1）；②机型不一致时对比 step 仍按 EPYC 基线算漂移并**可判红**，只靠前一步 warning 提示「本轮数值不可用」 | ①属性能域（pi）裁决，**不报改**；②若未来 Xeon run 变多，建议对比 step 前加「机型不匹配则 skip 对比」——**属门禁语义变更，须 pi + Claude 双裁**，本单只登记 |
| `golden-nightly.yml` | `workflow_dispatch` + `schedule` | `30 20 * * *` = 北京 **04:30**（与 bench 02:00、t4 19:30 再错开） | T5 golden ＝ **10 种子 matrix × 10 游戏日**（864,000 tick/种子）；`PI_T5_FULL=1` + `GOLDEN_REPORT_DIR`；`fail-fast: false`、`timeout-minutes: 90`；零 secrets（全 fixture 回放） | **零 TODO**。一处**结构性双写**（非缺陷但无常驻守卫）：种子真相源 `sim/tests/golden/seeds.py::GOLDEN_SEEDS` ＝ yml L42 `seed: [7, 11, 101, 1009, 2003, 3001, 4001, 5003, 6007, 7001]`（本轮实测**逐字一致**），但 **yml matrix 无法从代码读取 ⇒ 改种子必须两处同改，且仓内无常驻钉子锁这个一致性**（`sim/tests/golden/` 无任何用例解析 yml） | 建议加 1 条 T1 钉子（读 yml 的 `seed:` 行 vs `GOLDEN_SEEDS` 断言相等）——**属测试域（codex/Claude），本单只提不写** |
| `t4-nightly.yml` | **仅 `workflow_dispatch`**；`schedule`（`30 19 * * *` = 北京 03:30）**保持注释态** | 注释态 `30 19 * * *` | 「**配置存照 + 端点就绪检查**」：model-lock 证据落 `t4-results/model-lock.txt` → 必填 env 硬失败检查 → **探针段长期注释（零真模型调用、零烧钱）** → artifact（`if: always()`）→ 失败通知 | **零 TODO、零 `secrets.`（活跃行实测 0）**。唯一「未闭合」是**设计性**的：探针 step 不执行 ⇒ 本 workflow **不产出任何 T4 判读证据**，T4 证据 100% 来自本地（`docs/dev-workflow.md` §3）。另：用户待办「轮换 Deepseek key」（该 key 曾在本会话暴露，安全域，codex/用户） | 见 §T4。**本单不改** |

**巡检小结（四条）**

1. **全仓 workflow 零 `TODO/FIXME/TBD`**；唯一的「未执行 step」是 `t4-nightly.yml` 探针段，且它是**显式裁定的长期注释态**（有 5 条接线约定随注释留存），不是遗留待办。
2. **cron 错峰无冲突**：bench 北京 02:00 / t4（注释态）03:30 / golden 北京 04:30。
3. **marker 与路径纪律一致**：所有每提交门禁**只按文件路径**选，不用 `-m xxx`（防「marker 一改即静默假绿」，codex S03 教训）；bench 是唯一用 marker 门（`-m bench` / `-m "not bench"`），阈值真相源唯一 `sim/tests/bench/thresholds.py`，yml 不复制阈值表。
4. **零 secrets 实测**：四个 yml 的**活跃行**（非注释）中 `secrets.` 出现 **0 次**；唯一出现处是 `t4-nightly.yml:103` 的注释（「将来恢复时改回 `${{ secrets.T4_MODEL_API_KEY }}`」）。

---

## T4. T4 接线两口径预研（**只出对比案，不改任何 yml**）

### T4.0 现状事实（两口径的共同起点）

| 项 | main 实测值 | 出处 |
|---|---|---|
| 锁版本模型 id | `Deepseek-v4-flash` | `t4-nightly.yml:44` env、`test_t4_probes.py:55` `DEFAULT_MODEL`、`docs/dev-workflow.md:80` —— **三处同值**（§16 锁版本不许漂移） |
| 端点 | `https://chatapi.weixin.qq.com/openai/v1`（OpenAI 兼容，国内直连，**不走 7897 代理**——该代理仅 github.com 域生效） | `t4-nightly.yml:46`、`test_t4_probes.py:56`、`dev-workflow.md:81` |
| 三把防烧钱锁 | ① `T4_MODEL_API_KEY` 存在 ② `T4_RUN=1` 显式选择 ③ `T4_CALL_BUDGET` 硬闸（缺省 60，钉子 `test_budget_cannot_exceed_ceiling` 锁死不可抬高） | `test_t4_probes.py:86/92/96`、`docs/security/t4-corpus.md` §5 |
| 探针集 | `sim/tests/test_t4_probes.py`（M4-S7 `bda2aa3`，176 用例 = 语料门禁无 marker + 真模型探针 `t4` marker） | `docs/security/m4-closure-preaudit.md:57` |
| 最近终判 | 2026-09-28 Deepseek 第四跑：**18 passed / 0 failed / 23 抖动 skip / 6 xfail（全软判定），exit 0 ⇒ T4 面关闭** | `t4-nightly.yml:24–25` |
| 现 workflow 形态 | 仅 `workflow_dispatch`；探针段长期注释 ⇒ **跑一次只产出 `model-lock.txt`，不产出任何 T4 判读证据** | `t4-nightly.yml:34–40, 96–112` |

**⇒ 关键事实：口径甲（本地跑）与本 workflow 现状是「两不干扰」的**——现状既不替甲产出证据，也不阻拦乙。选哪个口径，**都不需要先改 yml**；只有选乙才需要。

### T4.1 口径甲：本地真模型探针一轮（＝等效验收，**用户 2026-09-27 已裁方向**）

**形态**：`docs/dev-workflow.md` §3 已完整落地——PowerShell 会话内设三件套 env（`T4_MODEL` / `T4_MODEL_BASE_URL` / `T4_MODEL_API_KEY`）+ `T4_RUN=1`，跑 `uv run pytest -m t4 --junitxml=t4-results/t4.xml`；结果按 §3 判读表读（硬红 = 出戏词面命中 / 全 pass = 满足验收 / **inconclusive 留人工复核，不得当绿**）。

**改动面**

| 项 | 内容 |
|---|---|
| 生产码 | **零** |
| workflow yml | **零**（现状即甲；`t4-nightly.yml` 继续作「配置存照 + 端点就绪检查」） |
| 文档 | 建议在 `dev-workflow.md` §3 补一行「最近一轮留痕」指针（本单**未改**，待裁决后一并做） |
| 本地留痕 | `t4-results/`（`.gitignore:35` 已忽略，**响应正文永不入库**，同 `perf/` 裁决） |

**验收判据**

1. 命令退出码 0，且**判读表**逐档核：硬红 0 条（出戏词面零命中）、inconclusive 逐条人工复核并记录结论。
2. 探针**实际被收集且未全 skip**——`-m t4` 在探针文件缺失时会**收集 0 用例并返回 exit 5**，`dev-workflow.md:94` 已明记「那不是全绿，是探针还没接线」，**exit 5 必须判红处理**。
3. `t4-results/t4.xml` 存在（证明确实产出了判读证据，而非空跑）。
4. 零烧钱纪律自检：跑完 `Remove-Item Env:T4_MODEL_API_KEY` 清会话值。

**成本 / 风险**

| 维度 | 评估 |
|---|---|
| 金钱 | **零持续成本**；仅裁决/交接时按需跑一轮（≤60 调用预算闸） |
| 密钥暴露面 | **最小**——key 只存在于本地 PowerShell 进程环境，永不落盘、不入库、不进日志、不上 GitHub |
| 回归保护 | **弱**：不自动跑 ⇒ 出戏回归可能长期不被发现，直到有人手动跑一轮。**这是甲的真代价**，须由「定期人工跑」补位（当前无任何机制强制） |
| 可复现性 | 中：结果留在本地 `t4-results/`，不入库 ⇒ **跨机器/跨人不可复现**（无 artifact 归档） |
| 抖动 | 23 条抖动 skip 是既有事实（语料/模型温度 0.7 共同作用），人工判读成本存在但可接受 |

### T4.2 口径乙：GitHub 自动接线（`t4-nightly.yml` 修 TODO + secret `T4_MODEL_API_KEY`）

> ⚠ **口径乙的「修 TODO」在本轮实测下无对象可修**——全仓 workflow 零 `TODO`（见 §0）。乙的真实改动是**取消探针段注释 + 注入 secret + 放开 schedule**，且必须**同步修 env 的两处锁**（详见下表「必改项」）。

**必改项（三处，缺一即假绿或零烧钱）**

| # | 改动 | 不改的后果 |
|---|---|---|
| 1 | 取消 `t4-nightly.yml:35–39` `schedule` 注释（UTC 19:30 / 北京 03:30，与 bench 02:00、golden 04:30 错开无冲突） | 每夜自动烧钱的前提缺失 ⇒ 仍是手动 dispatch |
| 2 | 取消 `t4-nightly.yml:96–112` 探针段注释，并按其自带的 5 条接线约定落 step（命令形 `uv run pytest -m t4 --junitxml=t4-results/t4.xml`） | 跑一夜只得到 `model-lock.txt`，**零 T4 判读证据**（＝现状） |
| 3 | **注入 `T4_MODEL_API_KEY: ${{ secrets.T4_MODEL_API_KEY }}` + `T4_RUN: "1"` 到探针 step 的 `env`** | 🔴 **最高风险项**：只注 key 不注 `T4_RUN=1` ⇒ 第二把锁未开 ⇒ **全部用例 skip ⇒ exit 0 的「全绿」是假绿灯**（`test_t4_probes.py` 三把锁设计，`ci.yml:52–57` 已就同类风险留警告）。**这一条必须显式写进验收判据** |

**改动面**：workflow yml 三处（上表）＋ GitHub 仓库 secret 一条 ＋ `dev-workflow.md` §3 增补「CI 形态跑法」（两形态并存，**禁让两处跑法描述漂移**）。**零生产码**（探针已落地、锁已在代码里）。

**验收判据**

1. `gh run list` 证实 **≥3 轮连续 schedule run 全绿**（单轮绿不足以判，防偶发）。
2. 每轮 artifact `t4-result` 内**同时**有 `model-lock.txt` **和** `t4.xml`；且 `t4.xml` 中真模型用例状态为 **passed / 明确 skip**，**不得出现「0 用例被收集」**（exit 5 语义）。
3. 逐轮核 `model-lock.txt` 的 `model_id` ＝ `Deepseek-v4-flash`（§16 锁版本证据链不断）。
4. `T4_RUN=1` 生效反证：日志中真模型用例**出现用例名而非全 skip**。
5. 成本闸：核对实际调用数 ≤ 60，超出即查预算闸是否被绕过。

**成本 / 风险**

| 维度 | 评估 |
|---|---|
| 金钱 | **每夜持续烧钱**（≤60 调用/夜）。用户 2026-09-27 改约的**直接理由就是这条** |
| 密钥暴露面 | **扩大**：key 进 GitHub secret（组织/仓库级），暴露面从「本地单进程」扩大到「托管平台 + 审计日志」。缓解：secret 不回显、**永不在本地 `.env`/yml/文档中出现**（本轮已实测活跃行零 secrets） |
| 回归保护 | **强**：出戏回归每夜自动暴露，这是乙唯一的真优势 |
| 可复现性 | **强**：每轮 artifact 归档 `t4.xml` + `model-lock.txt`，跨机可查（优于甲） |
| 失败模式风险 | 🔴 **假绿灯**（上表 #3）。缓解：验收判据第 2/4 条显式反证 |
| 次生风险 | runner 抖动（23 条 skip 已是既有事实）会制造长期「黄而不红」噪声；`timeout-minutes: 30` 护栏须复核是否仍够 |

### T4.3 两口径对照与建议

| 维度 | 口径甲（本地跑一轮） | 口径乙（GitHub 自动接线） |
|---|---|---|
| 与用户 2026-09-27 改约 | ✅ **一致**（改约本身就是「不建 secret、不自动烧钱」） | ⚠ **回退改约**（需用户明确推翻 09-27 裁定） |
| workflow yml 改动 | **零** | 三处（含一处高风险必改） |
| 生产码改动 | 零 | 零 |
| 金钱 | 零持续 | **每夜持续** |
| 密钥面 | 最小（本地进程 env） | 扩大（GitHub secret） |
| 回归保护 | 弱（纯人工，靠纪律） | 强（每夜自动） |
| 证据可复现 | 弱（本地、不入库） | 强（artifact 归档） |
| 主要风险 | 出戏回归长期不被发现 | ①假绿灯（`T4_RUN` 漏注）②持续烧钱 ③抖动噪声 |

**建议（交用户裁决，本单不执行）**

- **默认推荐：维持口径甲**——它是用户 2026-09-27 的明确裁定，现状零改动即该口径，且甲的代价（回归保护弱）可用「定期人工跑一轮」的纪律补位；乙的代价（每夜烧钱 + 密钥面扩大 + 假绿灯风险）是**持续性**的，甲的代价是**间歇性**的。
- **若选乙**：施工单须逐条覆盖 T4.2 必改三项 + 验收判据五条，**特别是 `T4_RUN=1`**；并在 `.github/workflows/t4-nightly.yml` 头注追加一条与 09-27 存照并列的「恢复自动跑存照」，避免后人只读到旧存照而误判当前状态。
- **两口径都不解决的一件事**：出戏回归的**发现**依赖人/时机。若要「既不每夜烧钱、又有回归保护」，第三路是**降低频率**（如每周一次 `schedule` + 乙的接线），但这已超出本单两口径范围，**不在本单裁决**，仅作备选登记。

### T4.4 与本单无关但需点名的两条跨域挂账（**只报不改**）

1. **`docs/arch/m4-plan.md` §4 + 裁 14-4 的「T4 全绿」定义仍是「nightly 连续通过」**，与改约后的「本地一轮＝等效验收」并存 ⇒ **同一验收词两个真相源**。`m4-plan.md` 属 Claude（架构）域，**本单未改**。
2. **用户待办：轮换 Deepseek key**（该 key 曾在本会话暴露）。属安全域（codex）+ 用户动作，**workflow 与文档中零明文 key 已实测**（`.gitignore` 亦已排除 `.env`）。

---

## 2. 本单自检与边界

**已做**

- `.github/workflows/` 全量四文件逐行实读；触发器 / cron（UTC + 北京）/ marker 与路径过滤 / secrets 活跃行 / TODO 命中全部实测取证。
- T4 两口径对比稿（改动面 / 验收判据 / 成本·风险逐项成表），**未改任何 workflow**。
- 本文件 + `docs/README.md` 两行登记（文档地图 + 台账）。

**未做（刻意）**

| 项 | 原因 |
|---|---|
| 改任何 `.github/workflows/*.yml` | 派单明令「只出对比案，不改任何 yml」；口径待用户裁决后才出施工单 |
| 改 `docs/arch/m4-plan.md` 的「T4 全绿」定义 | 架构域（Claude），跨域只报不改（T4.4-1） |
| 轮换 Deepseek key | 安全域（codex）+ 用户动作 |
| 建 golden 种子一致性钉子 | 测试域（codex/Claude），只提不写 |
| 改 bench 机型不匹配时的对比语义 | 性能域（pi）裁决，且属门禁语义变更，须双裁 |
| 跑 pytest / ruff / pyright | **零生产码改动**（只动 `docs/`），本单不需要跑测试门禁 |

**验证方式**：本单验证＝文档级（表列 pipe 一致性、`git status` 复核文件落点、yml 零改动 diff 复核），非测试级。