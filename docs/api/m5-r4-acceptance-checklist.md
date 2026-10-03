# M5 R-4 施工复验清单（合入即用｜docs/api/m5-r4-acceptance-checklist.md）

> 用途：Claude 的 R-4 取值施工（`sim/api/anchors.py` 两处同改）合入 main 后，**照本单逐条跑**即可完成复验。
> 上游依据：`docs/api/anchors-api.md` §1.6（条款 R-4.1~R-4.7 + **R-4.1-S 状态码裁定**）
> 与 §5.2（六钉验收对表 + 跨钉总闸）。本单是那两节的**执行态**：钉号 / 命令 / 预期 / 判红判据一行一条。
> 已有钉：`sim/tests/test_m5_anchors_branch_source.py`（opencode A6，**skip-locked**，锁信号
> = `anchors.py` 代码里出现 `current_branch_id` 或 `is_current`）。本单**不新增生产码、不改 A6 钉**——
> 只指明「A6 钉 ↔ §5.2 钉号」映射与**三处 A6 未覆盖、必须补确认的口径缺口**（§3）。
> 环境纪律（沿用 A5/A6）：测试用 `monkeypatch.chdir(tmp_path)` 落临时库；**绝不碰仓根 `world.db`**
> （那是开发库，版本行会撒谎——A4 血的教训）。

## 0. 执行时机与一句话判据

- **时机**：R-4 施工合入 main 后（A6 的 skip-locked 钉自动解锁，无需人工摘标记）。
- **判据**：A6 全绿 **且** §3 三处缺口逐条确认 **且** §4 总闸三条全绿 ⇒ 收编；
  任一红 ⇒ 打回并按 §6 登记（**红要说清是「新缺陷」还是「半成品」**——A6 的
  `test_lock_signal_agrees_with_redline` 就是防这个的：只删字面量不接真源会被它抓住）。

## 1. 前置三条（不合规就别开跑）

| #   | 前置          | 判据                                                                                                                                                                                                                                                                                                  |
| --- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **同头**      | `git fetch origin main && git merge origin/main` 后 `git log --oneline -1` 与施工方 head 一致                                                                                                                                                                                                         |
| 2   | **A6 已解锁** | `uv run pytest sim/tests/test_m5_anchors_branch_source.py -q` 的 **skip 数 = 0**（2026-10-03 实测基线：**5 passed / 6 skipped**，6 锁分布于 `TestRedLineNoMainLiteral` 2 + `TestCursorTripleCoherence` 2 + `TestFailClosed` 2）。**skip 仍在 ⇒ 施工没落到代码里**（锁信号未现），此时任何"绿"都是假绿 |
| 3   | **库隔离**    | 复验**不得**在仓根跑会起 app 的用例；若已在仓根跑过，确认 `world.db` 未被测试改写（`git status` 里它应被忽略且 schema 版本行不参与断言）                                                                                                                                                              |

## 2. 六钉逐条复验（钉号 = `anchors-api.md` §5.2）

| §5.2 钉                                       | A6 覆盖            | 测试名（`test_m5_anchors_branch_source.py`）                                                                                               | 预期                                                                                                                | 判红判据（照抄即可用）                                                                                                                                     |
| --------------------------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** 分叉后 POST 记档三元组自洽              | ✅                 | `TestCursorTripleCoherence::test_post_branch_and_seq_come_from_true_source`                                                                | `201`；档的 `branch_id == "fork-1"`（头部 7 的当前线）且 `seq == 7`（**不是** `main` 的 3）                         | `branch_id == "main"` ⇒ 建档那处未改；`seq == 3` ⇒ 取 seq 那处未改。**两处只改一处必被抓**（A6 已把两条线头部设成 7/3 不同值，这是「同改警告」的可证伪版） |
| **1b** 记档对当前行只读                       | ✅                 | `TestCursorTripleCoherence::test_post_does_not_move_current_line`                                                                          | 记档前后 `is_current` 标志集**逐字相等**                                                                            | 变了 ⇒ 记一次档就换线（`is_current` 被顺手写了）                                                                                                           |
| **2** anchor-fork（历史点分叉）后落**父**分支 | ❌ **缺**          | —（§3 缺口 G2）                                                                                                                            | 父仍 `active` + `is_current=1`，POST 记档 `branch_id` = 父                                                          | A6 今日无此钉 ⇒ 必须按 §3 G2 补跑                                                                                                                          |
| **3** 歧义 fail-closed                        | ✅（状态码弱）     | `TestFailClosed::test_post_with_ambiguous_active_rows_fails_closed`（fixture ＝ `a1/a2` 两条 `active` + `is_current` 全 0）                | **§5.2 要求的**：`400` 且 `body["type"] == "/errors/world-not-ready"`；`detail` 含「歧义」；`player_anchors` 零新增 | A6 只断言 `status_code >= 400` 且零落行 ⇒ **状态码与机器码需按 §3 G1 手工确认**；返回 `201` ⇒ 又写进了一条猜的线                                           |
| **3b** 无当前行不回退 `'main'`                | ✅                 | `TestFailClosed::test_post_without_current_row_fails_closed`                                                                               | `>= 400` 且零落行                                                                                                   | 返回 `201` ⇒ 猜分支（R-4.1 的原病灶）                                                                                                                      |
| **3c** 白盒负钉                               | ✅                 | `TestRedLineNoMainLiteral::test_no_main_literal_in_code`                                                                                   | `anchors.py` 代码（docstring 除外）零 `'main'` 字面量（含 SQL 串）                                                  | 有命中 ⇒ 硬编码还在（换了个写法也抓到，tokenize 级）                                                                                                       |
| **3d** 锁假开反钉                             | ✅                 | `TestRedLineNoMainLiteral::test_lock_signal_agrees_with_redline`                                                                           | 锁信号与红线**同向**                                                                                                | 不同向 ⇒ 施工只做了一半（字面量删了但真源没接）                                                                                                            |
| **4** `is_current=1` 第二行 ⇒ IntegrityError  | ✅（A5 侧）        | `sim/tests/test_m5_branch_current.py` 两例（msg 断言 `UNIQUE constraint failed: branches.is_current`）+ `PRAGMA index_list` 的 `partial=1` | 两例绿                                                                                                              | 引用即可，不重复造                                                                                                                                         |
| **5** head-fork 交接 + anchor-fork 不抢当前   | ⚠️ **冲突，见 G3** | `TestForkHandoverForm::test_fork_from_current_line_keeps_single_current`（**今天即绿**，断言现状＝父仍当前）                               | 「至多一个当前」恒成立（DB 层）                                                                                     | **若施工把 fork 交接一并落了，这条今天即绿的钉会红**——不是施工错，是 A6 钉的现状断言过期，须由 opencode 更新（G3）                                         |
| **6** 三种 0 行情形各跑一次                   | 部分（1 种）       | `TestFailClosed::test_post_without_current_row_fails_closed` 覆盖「有 active 但无当前行」                                                  | 三种（`branches` 空 / 全 `abandoned` / 唯一 `active` 但 `is_current=0`）均拒绝且零落行                              | A6 覆盖 1 种 ⇒ 另两种按 §3 G2 补跑（尤其「0012 前的历史库形态」最贴近生产）                                                                                |
| —                                             | 今天即绿（正控）   | `TestGateAndTrueSource`（启动开线即当前行 / 读档子线照写不误 / 正控记档 201）                                                              | 全绿                                                                                                                | 红了 ⇒ 施工把正常路径一起拒了                                                                                                                              |

## 3. 三处缺口（**必须补确认，A6 未覆盖或口径过期**）

| #      | 缺口                                              | 为什么要补                                                                                                                                                                                                                        | 怎么补（不写生产码）                                                                                                                                                                                                                                           |
| ------ | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **G1** | **状态码与机器码未被钉死**                        | A6 的 docstring 写「kilo 契约里 409/503 都可」，但 K10 的 **R-4.1-S 已裁**：0 行与歧义**一律 `400 /errors/world-not-ready`**（复用既有机器码 ⇒ 零快照变更）。若施工按 A6 注释选了 409/503，就是**契约偏离**，前端错误映射要跟着改 | 复验时对歧义 fixture 与 0 行 fixture 各发一次 `POST /api/anchors`，断言 `r.status_code == 400 and r.json()["type"] == "/errors/world-not-ready"`，并确认 `detail` 含「歧义」/「无当前世界线」。**不符 ⇒ 打回**（改施工，别改契约）                             |
| **G2** | **钉 2（anchor-fork 落父）与另两种 0 行情形无钉** | §5.2 把它们列为独立钉（A4 的「历史点分叉 ⇒ 父仍当前」是 R-4.4 的核心分支；三种 0 行里「0012 前历史库形态」最贴近生产）                                                                                                            | 复验时按 §5.2 的 fixture 描述手测：anchor-fork 形态（父 `active`+当前、子 `active`+非当前且头部 seq 更大作诱饵）⇒ 记档落**父**；再对 `branches` 空表 / 全 `abandoned` 各发一次 POST ⇒ 均 `400` + 零落行。**要长期自动化 ⇒ 走 CR 加进 A6 钉组**（不在本单范围） |
| **G3** | **钉 5 与 A6 现状断言的冲突**                     | A6 的 `test_fork_from_current_line_keeps_single_current` 今天断言「父仍当前、子非当前」，并注明「fork.py 交接属 R-4 施工单」。**若本次施工顺手把 fork 交接落了**，这条会红——收编方会误判成回归                                    | 复验前先确认施工是否含 fork 交接：**含** ⇒ 请 opencode 更新该钉为「子当前 + 父 abandoned」（`anchors-api.md` §1.6 R-4.7 钉 5 的口径）；**不含** ⇒ 登记为**已知缺口**（head-fork 后读档侧会报「无当前分支」，0012 docstring 已自述），另立施工单                |

## 4. 跨钉总闸三条（照 §5.2）

| 闸                             | 命令 / 断言                                                                                                                                   | 红 meaning                                                                                               |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **T1 live ≡ 快照**             | `uv run pytest sim/tests/test_m2_openapi_rework.py -q`（结构对拍）+ 手点 `GET /openapi.json` 的 anchors 段与 `shared/openapi.json` 逐字段相等 | R-4 是纯服务端取值改动，协议面**零变化**；live 多了声明而快照没同步 ⇒ 前端类型与文档漂移                 |
| **T2 生成管线**                | `cd client && node ../tools/gen-protocol.ts --check` ⇒ **EXIT 0**，且 `git status shared/` **零 diff**                                        | 这是「复用 400 机器码」换来的好处——红了说明施工顺手加了新 code，把快照面扩了一格（要走 §2.1 登记单流程） |
| **T3 branch-ambiguous 反向钉** | `Select-String`/`rg` 在 `shared/openapi.json`、`sim/api/errors.py`、`shared/protocol.ts` 中数 `branch-ambiguous` ⇒ 各 **0** 次                | §2.1 是**登记单不是契约**；非 0 ⇒ 施工把登记单当施工清单做了（禁忌第 1 条）                              |

## 5. 命令速查（复制即用）

```powershell
git fetch origin main; git merge origin/main; git log --oneline -1
uv run pytest sim/tests/test_m5_anchors_branch_source.py sim/tests/test_m5_branch_current.py -q
cd client; node ..\tools\gen-protocol.ts --check; cd ..
uv run pytest sim/tests/test_m2_openapi_rework.py sim/tests/test_m5_api_anchors.py -q
uv run ruff check sim/; uv run pyright            # 生产码改动后的常规门禁
cd client; npm run test -- protocol-types          # 前端类型面（R-4 应零变更）
```

## 6. 登记格式（打回或留缺口时粘这段）

```
R-4 复验：commit <hash>｜A6 <N 绿>/<M 红>/<K skip>
钉 <§5.2 钉号>：<红/缺口一句话>｜实际：<观测到的行为>｜期望：<契约条款出处>
判定：施工缺陷 / 契约偏离（回 kilo 改钉）/ 已知缺口（另立施工单）
证据：<测试名 + 关键断言值或命令输出行>
```

## 7. 不在复验范围

- **fork 交接本身**（若本次不含，见 G3）；开线闸收紧（A5 已收官，`TestGateAndTrueSource` 今天即绿）。
- **`500 /errors/branch-ambiguous`**：仍是**登记单**（`anchors-api.md` §2.1），本单**不要求**它存在，
  反而要求它**不存在**（T3 反向钉）。
- 批次 D 火灾出站面：另按 `m5-fire-api-prestudy.md` + `sim/tests/test_m5_fire_outbound.py` 复验。
