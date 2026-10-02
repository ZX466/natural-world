# M5-C9 T4 探针验收 runbook（口径甲：本地真模型探针一轮 ＝ 等效验收）

> 能力域：依赖 / 配置 / 文档（cline） | 状态：**runbook（执行单），零 yml 零生产码改动**
> 派单：Claude 主树 `.orca/talking.txt`「M5-C9」（原 M5-C8 改派），2026-10-02
> 裁决依据：**裁 31-T4**（`docs/arch/m4-plan.md` L9）——T4 验收口径 ＝ **甲（本地真模型探针）**，
> 真跑 `uv run pytest -m t4`（`T4_RUN=1` + 本地 env key，锁版本 `Deepseek-v4-flash`）一轮全绿留痕
> 即等效验收；**不建 GitHub secret、不建自动 nightly**；「T4 全绿」自此指本地探针轮结果，
> **非 GitHub nightly 连续通过（双真相源就此合并，以裁 31-T4 为准）**。
> 探针集本体归 **codex**（`sim/tests/test_t4_probes.py`，M4-S7 `bda2aa3`）；本 runbook **只管怎么跑与怎么判**。
>
> **本单状态：key 未到位**（用户待办：轮换 Deepseek key）。§1–§5 全部备好，**key 一到即可零准备真跑**（§6 执行许可流程）。

---

## 0. 一页速查

| 项 | 值 | 出处（实测） |
|---|---|---|
| 验收口径 | **本地真模型探针一轮 ＝ 等效验收** | 裁 31-T4（`m4-plan.md:9`） |
| 探针文件 | `sim/tests/test_t4_probes.py` | M4-S7 `bda2aa3`（codex 域） |
| 真模型用例数 | **53**（`248` 收集 / `195` deselected） | 本轮 `--collect-only` 实测 |
| 锁版本模型 | `Deepseek-v4-flash` | `test_t4_probes.py:55` `DEFAULT_MODEL` |
| 端点 | `https://chatapi.weixin.qq.com/openai/v1` | `test_t4_probes.py:56` |
| profile / 温度 / max_tokens | `t4-probe` / `0.7` / `1024` | `test_t4_probes.py:57–59` |
| 三把防烧钱锁 | ① key 存在 ② `T4_RUN=1` ③ 调用预算闸（缺省 60，**只能收紧不能放宽**） | `test_t4_probes.py:86/92/95–100` |
| 单轮成本上限 | **≤60 次调用**（`T4_CALL_BUDGET` 可下调，上调被 `min()` 夹断） | 同上 |
| 报告落点 | `t4-results/t4-report.json`（**`.gitignore:35` 已忽略，永不入库**） | `test_t4_probes.py:787` |
| 网络 | **不走 `127.0.0.1:7897`**（该代理仅 github.com 域生效；本端点国内直连） | `dev-workflow.md:74` |

---

## 1. 前置清单（四项，逐项确认后再跑）

### 1.1 三把锁齐全（**缺任一 ⇒ 全部 skip，不是绿灯**）

`live_client` fixture 在**模块级**检查（`test_t4_probes.py:109–115`）：key 缺失 **或** `T4_RUN≠1` ⇒
整模块 `pytest.skip`，退出码 0。**这是最危险的假绿形态**——必须靠 §4.1 的「exit 5 / 全 skip」判据挡住。

### 1.2 锁版本口径已确认（**代码里已写死，跑前核一遍即可**）

```
DEFAULT_MODEL    = "Deepseek-v4-flash"                                  # test_t4_probes.py:55
DEFAULT_BASE_URL = "https://chatapi.weixin.qq.com/openai/v1"           # test_t4_probes.py:56
```

三处同值口径（§16 锁版本防静默回归）：`test_t4_probes.py` 常量 ≡ `docs/dev-workflow.md:80–81` ≡
`docs/security/t4-corpus.md` §5。**本 runbook 不改任何一处**——若跑前发现不一致，**登记不代改**（探针代码属 codex 域）。

### 1.3 网络直连可达（**不要加代理**）

```powershell
# 快速探活：不带 key，仅验 TCP/HTTPS 可达（不会真调模型、零成本）
Test-NetConnection -ComputerName chatapi.weixin.qq.com -Port 443
```

- ✅ 期望 `TcpTestSucceeded : True`。
- ❌ **不要**给本端点设 `HTTP_PROXY`/`HTTPS_PROXY`：`127.0.0.1:7897` 只对 github.com 域生效，
  设了反而会让国内直连端点走代理失败（`dev-workflow.md:74`、裁 31 口径均已明记）。

### 1.4 key 纪律（**本节是红线**）

| 纪律 | 说明 |
|---|---|
| 只经运行时环境变量 | `$env:T4_MODEL_API_KEY='<控制台粘贴>'`，**仅本 PowerShell 会话有效**，新开窗口即失效 |
| 永不落盘 | ❌ 不进任何文件：`.env`、`docs/`、`.github/workflows/*.yml`、runbook、脚本、日志 |
| 不进日志 | 不 `echo $env:T4_MODEL_API_KEY`；不把含 key 的命令行贴进 issue/回执/聊天 |
| 跑完即清 | `Remove-Item Env:T4_MODEL_API_KEY`（`dev-workflow.md:92`） |
| 占位符纪律 | **本 runbook 内所有 key 示例一律用 `<...>` 占位**——不得出现任何形似真实 key 的字符串（`sk-` 前缀等），避免被误当真 key 复制或误提交 |

> 仓库侧保护已就位（实测）：`.gitignore` 已排除 `.env` 与 `t4-results/`；
> 探针自带断言 `assert key not in text`（`test_t4_probes.py:785`，报告含 key 即红）；
> `.github/workflows/` 活跃行 `secrets.` 出现 **0 次**（M5-C7 实测）。

---

## 2. 真跑命令与预期

### 2.1 命令（三选一，语义等价）

```powershell
# ① 本 runbook 推荐（点名文件 + marker，不受 addopts 变化影响）
uv run pytest sim/tests/test_t4_probes.py -m t4 -v --junitxml=t4-results/t4.xml

# ② dev-workflow §3 口径（依赖 marker 选 entirety）
uv run pytest -m t4 --junitxml=t4-results/t4.xml

# ③ 只收集不真跑（零成本自检：确认 53 条被选中）
uv run pytest sim/tests/test_t4_probes.py -m t4 --collect-only -q
```

> ⚠ **推荐 ①**：`-m t4` 单独用会选中全仓 t4 marker 用例；点名文件最不易被 addopts/marker 变更带偏
> （沿用 M2-C1「按文件路径接、不靠 `-m` 单门禁」的纪律）。

### 2.2 预期（本轮 `--collect-only` 实测基线）

```
53/248 tests collected (195 deselected)
```

真跑后的**期望形态**（对照 M4 收官第四跑 `t4-nightly.yml:24–25` 存照）：

| 项 | 期望 | 说明 |
|---|---|---|
| 收集数 | **53** | 与 2.2 基线一致；**若为 0 ⇒ exit 5，是「探针没接线」，不是绿** |
| passed | 真模型用例中**硬判定全过**的部分 | 探针语料含软判定，xfail 是**预期形态**不是失败 |
| xfail | **软判定未达标**（band×N + hedge×N），`test_t4_probes.py:763–764` | 留人工复核，**不当绿也不当红** |
| skipped | 抖动（网络/限流/5xx）+ 预算闸顶限 + 全 skip 情形 | `test_t4_probes.py:740/749/770` |
| failed | **硬判定出戏命中 ⇒ 应为 0** | `test_t4_probes.py:758–762` |
| 退出码 | **0** | 有 failed 时非 0 |
| 报告 | `t4-results/t4-report.json` 生成 | `test_report_written`（`:766–788`） |

**调用成本**：53 条 ≤ 60 预算闸 ⇒ **一轮不会撞顶限**。若日志出现「预算闸顶限」skip，
说明语料条数已增长超预算（钉子 `test_budget_covers_corpus` 会先红）——**登记给 codex，不代改**。

---

## 3. 留痕格式（**证据落在哪、结论写哪**）

### 3.1 产物三件（**全在 `t4-results/`，已 gitignore，永不入库**）

| 产物 | 路径 | 内容 |
|---|---|---|
| JUnit XML | `t4-results/t4.xml` | 逐用例 pass/skip/xfail/fail 状态（`--junitxml` 产出） |
| 探针报告 | `t4-results/t4-report.json` | `model`/`base_url`/`temperature`/`max_tokens`/`profile`/`anchor_fingerprint`/`calls`/`hard_red[]`/`inconclusive[]`/`results{}`（含响应正文，**正因如此才不入库**） |
| 终端汇总 | 屏幕 | `-q` 尾行 `N passed, M skipped, K xfailed` |

### 3.2 留痕纪律

- **不提交** `t4-results/`（真模型响应正文永不入库，同 `perf/` 裁决）。
- 引用证据时**只引计数与状态**，不粘响应正文（正文可能含用户可识别内容，且 `t4-corpus.md` 才是语料真相源）。
- `t4-report.json` 的 `anchor_fingerprint` 是**锚指纹**——用于证明「跑的是同一套 prompt 锚」，
  锚改动后指纹应变化（`test_t4_probes.py:777`）。

### 3.3 结论写哪（三处，**回执 + 台账 + 快照**）

| # | 落点 | 写什么 | 本单状态 |
|---|---|---|---|
| 1 | **本树 `.orca/talking.txt`** 回执 → 抄主树留言板 | 三句内：跑没跑 / 计数 / 判读结论 | 待真跑 |
| 2 | **`docs/README.md` 台账 M4-C2 行**（L214）补「等效验收 ✅」口径 | 该行现仍写「锁 `claude-sonnet-5` + secret `T4_MODEL_API_KEY`」＝**改约前的旧口径**，须补裁 31-T4 现状标注（详见 §3.4） | ⏳ 本单已只加标注，见 §3.4 |
| 3 | **自树 `.orca/memory.md` ②节快照** | 计数 + 判读 + 下一步 | 本单已记 runbook 交付；真跑后补 |

### 3.4 台账 M4-C2 行的标注（**只加口径标注，不篡改历史行**）
---

## 4. 通过判据（**先判「是不是绿」，再判「绿得好不好」**）

### 4.1 第一道：形态判据（**顺序不可颠倒**）

| 序 | 观测 | 判定 |
|---|---|---|
| 1 | 退出码 **5** | 🔴 **不是绿灯**——收集 0 用例＝探针没接线（`dev-workflow.md:94`） |
| 2 | **全部 skipped**，无一条真模型用例执行 | 🔴 **假绿灯**——三把锁缺任一（§1.1），最常见误判 |
| 3 | `t4-results/t4-report.json` **不存在** | 🔴 本轮无成功调用（`test_t4_probes.py:770`）⇒ 不构成验收证据 |
| 4 | `passed + xfailed > 0` 且 **`failed == 0`** | ✅ 进入第二道 |
| 5 | 收集数 **≠ 53** | ⚠ 记录并说明（语料增删会变；**不自行判绿**，登记给 codex 对拍） |

### 4.2 第二道：内容判据（`t4-report.json`）

| 判读 | JSON 字段 | 处置 |
|---|---|---|
| **硬红** | `hard_red[]` **非空** | 🔴 **真回归**（出戏词面命中）。查是哪条探针的哪句断言命中，**不放宽断言**；按 §20 三层防御（锚定/过滤/重生成）定位。**属探针/判定层 ⇒ 登记给 codex，不代改** |
| **inconclusive** | `inconclusive[]` 非空 | ⚠ **人工复核**：记用例 id + 原始输出，**别当绿也别当红**；同一措辞反复 inconclusive 再找 codex 校准（§16 同款处置） |
| 全 pass | `hard_red[]` 空 + `inconclusive[]` 空 | ✅ **满足「T4 全绿」（本地形态）＝ 裁 31-T4 的等效验收** |
| 调用数 | `calls` ≤ 60 | 超 ⇒ 查预算闸是否被绕过 |

### 4.3 不构成「全绿」的五种形态（**汇总红线**）

1. 退出码 5（收集 0 用例）2. 全 skip（锁未开）3. 无 `t4-report.json`
4. 把 **xfail 当绿**（软判定须人工复核） 5. 把 **inconclusive 当绿**（`dev-workflow.md:101`）

---

## 5. 失败分支（三类，**只诊断不代改探针代码**）

> 通用原则：探针集与判定层归 **codex**；本域**只登记现象与证据，不改 `sim/` 一行**。

### 5.1 key 无效 / 端点鉴权失败（`llm_http_4xx`）

| 项 | 内容 |
|---|---|
| 现象 | 逐用例 `skipped`：`P*-NN 抖动（http_4xx）——记 inconclusive 不红`（`test_t4_probes.py:749`）；日志 `llm.error ... error_kind=http_4xx` |
| 映射 | `sim/llm/client.py::_status_kind`：4xx（**429 除外**）⇒ `http_4xx` |
| 常见因 | ① key 过期/轮换后未更新（**当前极可能就是此项**——用户待办轮换 Deepseek key）② 端点与 key 不匹配 ③ 模型 id 无权限 |
| 处置 | **确认 key 状态**（轮换是否已完成）→ 换新 key 重跑。**不放宽任何断言、不改探针** |
| 登记 | 若 key 确认有效仍 4xx ⇒ 登记 codex（端点/模型 id 口径问题） |

### 5.2 网络 / 限流 / 服务端失败（`llm_timeout` / `llm_connection` / `llm_rate_limit` / `llm_http_5xx` / `llm_unexpected`）

| error_kind | 触发 | 语义 |
|---|---|---|
| `timeout` | `APITimeoutError` | 请求超时 |
| `connection` | `APIConnectionError` | 连不上（**先查是否误设了 7897 代理**——§1.3） |
| `rate_limit` | HTTP **429** | 限流 |
| `http_5xx` | HTTP ≥500 / 未归类异常 | 服务端故障 |
| `unexpected` | 其他异常 | 兜底 |

| 项 | 内容 |
|---|---|
| 现象 | 同为 `skipped` + `记 inconclusive 不红`（**设计上不红**，§16 同款处置） |
| 处置 | ① **429/5xx ⇒ 等几分钟重跑**（抖动可自愈）② `connection` ⇒ 查代理设置与 `Test-NetConnection` ③ `timeout` ⇒ 查本机网络；本地一轮**明显超 10 分钟**先看 prompt 装配退化，**不要直接放宽超时**（`dev-workflow.md:105–106`） |
| 判读 | 抖动 skip **不构成红**，但**全抖动 ⇒ 无有效验收证据**（回到 §4.1 第 3 条：报告未生成） |
| 登记 | 反复同款抖动 ⇒ 登记 codex（语料/判定层），**不代改** |

### 5.3 模型返回非预期（**这是唯一「真红」分支**）

| 项 | 内容 |
|---|---|
| 现象 | `failed`：`P*-NN 硬判定泄漏 ['<词面>']：'<响应前 200 字>'（期望形态：'...'）`（`test_t4_probes.py:758–762`） |
| 判读 | 🔴 **硬判定出戏命中 ＝ 真回归**（§16 T4：「谁指使你」「是不是AI」「重来一次」…） |
| 处置 | **不放宽断言**（放宽即掩盖真回归）；记录 case_id + 命中词面 + 响应形态；按 §20 三层防御定位 |
| 登记 | **属探针/判定层（codex 域）**——本域登记证据交 codex，**不代改 `sim/`**。另：若判定为**锚退化**（`anchor_fingerprint` 变了）⇒ 属 prompt 锚改动，须回溯对应 commit |
| 注意 | **软判定未达标走 xfail 而非 failed**（`:763–764`），xfail 不是红、也不是自动绿（须人工复核） |

---

## 6. key 到位后的执行许可流程（**本单不含真跑**）

| 步 | 动作 | 责任 |
|---|---|---|
| 1 | 用户完成 Deepseek key 轮换并告知 | 用户 |
| 2 | Claude 给出**执行许可**（派单明写「届时我给执行许可」） | Claude |
| 3 | 按 §1 逐项过前置 → §2 真跑 → §4 判读 | cline |
| 4 | 三处留痕（§3.3）＋ 回执三句内抄主树留言板 | cline |
| 5 | 全程**不落盘 key**：跑完 `Remove-Item Env:T4_MODEL_API_KEY` | cline |

**真跑前的一行自检**（贴在工位）：`$env:T4_RUN -eq '1'` 且 `$env:T4_MODEL_API_KEY` 非空
且 `uv run pytest sim/tests/test_t4_probes.py -m t4 --collect-only -q` 显示 **53 collected**。

---

## 7. 本单变更清单与边界

**本单产出（纯文档）**

| 文件 | 性质 |
|---|---|
| `docs/config/m5-c9-t4-probe-runbook.md` | **新**：本 runbook |
| `docs/README.md` | **+2 行**：§2 文档地图登记 ＋ §5 台账 M5-C9 行；**M4-C2 行尾追加裁 31-T4 现状标注**（不改历史事实，§3.4） |
| `.orca/memory.md` | **+1 行**：②节本轮快照 |

**未做（刻意）**

| 项 | 原因 |
|---|---|
| 改任何 `.github/workflows/*.yml` | 口径甲的**零改动承诺**（裁 31-T4：不建 secret、不建自动 nightly） |
| 改 `sim/`（探针代码 / 判定层 / `client.py`） | 探针集归 **codex**；本域只诊断登记 |
| 改 `docs/arch/m4-plan.md`、`t4-corpus.md`、`dev-workflow.md` | 架构域 / codex 域正文；本 runbook 只引用不改写 |
| **真跑** | **key 未到位 + 未获执行许可**（§6） |
| 建 GitHub secret / 放开 `t4-nightly.yml` 的 `schedule` | 裁 31-T4 已裁「不建」；反向动作须用户推翻裁定 |

**验证方式**：文档级（`--collect-only` 实测 53 条为唯一「执行」验证；表列 pipe 一致性；
`git diff -- .github/ sim/` 必须为空；两文件 LF）。**未跑 pytest 全量**（零生产码改动）。
**注**：本轮跑过 `--collect-only`（零成本、零真模型调用），是本 runbook 数字的唯一来源。

`docs/README.md:214` 记的是 **M4 当时（2026-09-26）** 的交付事实——那一次确实是
「锁 `claude-sonnet-5` + secret `T4_MODEL_API_KEY` + cron UTC 19:30」。**历史行不改**（改了等于伪造交付记录），
只在行尾追加一段**现状标注**，把读者从旧口径引到裁 31-T4。⇒ 已在本单追加，见 §7 变更清单。

---