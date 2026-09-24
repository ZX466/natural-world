
# memory.md — 多 Agent 记忆合集（分节收录各工作树各自的记忆）
> 用户规则 #7（main `3e320b9` 裁决：memory.md 入库）。本文件 = 五树 + 主树记忆的**融合合集**；
> 跨树收编由主导方（Claude）合并。各树本地副本是其对应节的**权威来源**，收编冲突时以各树版本为准。
> 新对话先读：.orca/talking.txt → 本文件**自己那一节** → .orca/workflow.txt + .orca/agent-registry.md。

## ① Claude（主工作树 / 主导）
> 新对话恢复序：talking.txt（任务单）→ 本节 → git log --oneline -15（轮次勾账）→ docs/arch/m3-plan.md §6。
- 主导/组织：架构/代码质量/逻辑/测试 + 前端/体验/发布/运维；评审 cline 与 kilo 的工作。
- 收编由我执行（merge 各 ZX466/* 分支 → uv run pytest 全量+bench+ruff/pyright → 裁决 → 推 origin+gitee → 六树 `git merge main` 同步）；派单写目标树 talking.txt，回执收主树；**不用 orca-cli 发消息**；上下文 50% 提醒切换。
- **M0+M1 全量收官；M2 全收官（九轮全收编，main `4e381c0` 前态 1003 passed）**；裁决 1-12 全落地（1 advisory 门/2 RNG330/3 V1V4V6/4 baseline 漂移 25%/5 {anchor_id}/6 cline 修正/7 pi 四红线/8 E1+knowledge 列/9 cline 口径/10 B3 七列/11 机型重对账/12 kilo 8.1-8.8）。
- **我 A2 批次链**：第二批 `59ffd86`（向量化）→ 第三批（smell/runtime 接线）→ 第四批 `805166e`（m3-plan 骨架）→ 第五批 `3bf49be`（批次 B 细化+B1 双列）→ 第六批 `1ae9e54`（E1 事件层+evidence.py+propagation.py，26 钉子转绿）→ 第七批 `f1c0c35`（reflection.py+society.py+relationship_store+budget 回填）→ **第八批 `64b7390`（2026-09-24，批次 B 生产面收口）**：①F2 收口=NpcRuntime.tick 第 0 步 delta 装配发 hidden_emerge_event（先于 NPC_ACT=证据链根先行，attr_ids 排序保 C5，bench/soak 调用形零回归）；②F1=工厂 witnesses 收窄 Sequence[str]+isinstance 拒 str/bytes/dict（codex S5 的 dict→ghost 键洗白向量封口）；③B-B2=run_world_driver 增 on_day_switch 钩子（**跨越判定逐日补发**，非 reflection_due 等值判定——帧驱动一帧 0..N tick，等值点 75-94% 被整帧跳过）+ reflection.make_day_switch_reflector 适配器（钩子 1-based→run_reflection 0-based 换算；ws.py 零 sim.npc 依赖）。新钉子 test_m3_e1_wiring.py 17 用例；全量 **1020 passed / 0 RED**，bench 36，pyright 全仓 0，ruff clean。
- **坑（实测过）**：①日切判定必须跨越式（prev_day≠new_day），等值式在帧驱动下丢日切；②工厂收窄 isinstance 须先查 str/bytes（str 本身是 Sequence）；③NPC 事件身份进 payload 不设 actor_id（npc_act_event 同口径，actor_id 是世界事件字段）；④pyright reportUnnecessaryTypeIgnoreComment=error——ignore 须落在真报错行，负例越型用 `Any` 中转变量而不是猜 ignore 规则名；⑤钩子回调同步形（run_reflection 无 IO），on_flush 是 async 形；⑥witnesses 装配在感知层（evidence.witnesses_of_emerge），runtime 无感知帧留空=fail-closed（witnessed 三要素齐才 0.9）。
- 【2026-09-24 第十轮快照｜opencode M3-D4 收编 + codex M3-S5 终验全过（main `d8fe2b0`）】**D4 收编**（`30dd087` → ff `3b560b9`）：knowledge 治理七列+0005 迁移（batch_alter_table 落 CHECK×3）+ KnowledgeStore（invalidate_by_source|row 沿 source_knowledge_id 广度递归，继承失效不继承替代，幂等+分支隔离+session= 同事务）+ X7 写入门（memory_scan 抽 decide() 唯一判梯，write/scan_fact 共用）+ T1 钉子 20 用例。**S5 终验四项我主树实测全过**：①R1 三硬断言（supersede→失效 count=1 / told 链下行级联 / 链断后 judge_third_party_hidden 拒收 reason=told_teller_knowledge_invalidated）②X7 grep 零裸 INSERT（Knowledge( 构造仅在 knowledge_store.py，tests 外零处）③裁10④ session= 同事务口在 ③裁10④ 接线点形态在（write_fact/invalidate 均有 session= 入参，调用方串联，存储层互不依赖）④alembic 0005→0004→0005→0002→0005 往返零漂移（scratch DB 实测；world.db 本地仍无版本记录=正常，迁移仅测试/生产路径用）+ F1 Sequence[str] 收窄复验（hidden_emerge+knowledge_cascade 46 passed）。**门禁：1076 passed / 56 skipped / 0 failed**（新增 T1 20 用例；skip 55→56=新增 1 条环境门），pyright 全仓 0，ruff ok，bench 绿。**批次进度：B 双收口 / C1+C2+C4 ✅ 剩 C3 / D 未开工**。
- M3 进度：批次 A ✅ / **批次 B 双收口（架构+生产）** / C 过半（C1/C2/C4 ✅，剩 C3）/ D 未开工；M5 接口锚点待施工（kilo 对表+8.7 首修）。MVP ≈99%，全项目 ≈67%。
- 待办：**批次 C3**（opencode：chunk 失效正确性量化验收 map.py:67 dirty_chunks 占位恒空 + §19.4 注册持久化提案）→ **批次 D**（Claude 主线：D1 不成文规矩 v0 + D2 空间迷雾 + D3 端到端 T5 golden，codex 出探针）；kilo 提醒 M5 施工时订正 openapi_ext.py:17 与 ADDED_SCHEMAS 两处 M2-K3 遗留注释。
- 规则速记：#4 除 .orca 外点文件夹不入 git（.orca 下新增文件 git add -f）；#7 各树 memory.md 各存各的记忆（tracked，收编分节融合，各树本地版权威）；talking.txt gitignore 各树本地；npm/venv 删除先问用户；Python 必用 uv；playwright 只用 D:\develop\hermes\chrome；GitHub 走代理 127.0.0.1:7897；提交尾 `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。

## ② cline（依赖 / 配置 / 文档域）
- 【2026-09-24 第九轮快照｜M2-C8 全闭环已收编】README §5 表至第八轮 47×5 行 + §2 文档地图补 m3-plan/m3-evidence-chain；卡片勘误（M3-D1 真身 opencode `4da190d`）。C1-C8 全收编。**active 约定**：CI 门禁按文件路径接不用 -m（P04 教训）；`perf/` 目录须 mkdir（git 不跟踪空目录，C5 根因）；Windows CRLF 假红已根除（.gitattributes，自检 `git ls-files --eol | grep -c 'w/crlf'` 期望 0）；`.orca/` 下新增文件须 `git add -f`（catch-all `.*/` 未豁免，规则 #4 语义）。**待命**：M3 收官时补 §5 M3 分节（现混装 M2/M3 行，等批次 B/D 收口后分节改名）。§2 遗留四行（m3-retrieval-budget/anchors-api/t1-sampling-10k/ci-calibration-m2p6）仍待裁。
- 【2026-09-23 第五轮快照｜新对话按此继续】**M2-C5 nightly 红灯修复已交付待收编**（`db092ed`）：硬红灯根因 = `perf/` 目录不入库（git 不跟踪空目录）→ pytest-benchmark 收尾 `save_json` 抛 `FileNotFoundError: perf/bench.json`（**4/4 跑必现**）→ 修=nightly「跑基准」step 先 `mkdir -p perf`；并给 artifact 上传加 `if: always()`（原来红灯时被 skip → 四轮全 0 产物、证据与 CI 档位数字全丢）。残留 4 个微基准断言越线（apply/perception/rng/smell，**每轮失败集合都不同**、边缘超 2–9%）＝ ubuntu runner 档位/负载抖动，非代码回归；阈值真相源在 pi 域（`sim/tests/bench/thresholds.py` + `harness.py`），已交 Claude 裁决（重定标 CI 档位 or 加 env 门走「归档+相对基线漂移」口径）。**CI 端到端验证（3 次 dispatch 于本分支 `d68885a`）**：①`35815742469` FileNotFoundError 消失、JSON 38,024B、首次上传 artifact、pytest 首次打印完整汇总（2 failed/27 passed/1 skipped in 254.75s）；②`35816176126` artifact 非 0、红 1 例（smell 哨兵 2.939ms vs 3.0＝超 2%）；③`35816437844` artifact 含 `perf/bench.json` 38,597B **+ `docs/perf/runner.txt`**（第三处修复：档位随 artifact；ubuntu-latest/nproc4/AMD EPYC 9V74/py3.12.3/uv0.12.18）、红 1 例（听觉 3.932ms vs 3.6＝超 9%，mean 11.546＝抖动 3×）。**「跑基准绿」未达成＝非管道问题**：7 组数据失败集合每轮不同、均边缘超 2–9%、mean 为 median 3–4× → 共享 runner 负载噪声（pi 域阈值口径）。本机双向对照同结论（无目录→同指纹崩溃；建目录→JSON 落盘 37KB）。**M2-C4**（09-22，`1772f3a`，已收编）：①codegen.md §4.1 切源暂缓声明 + gen-protocol 头注；②baseline 评估=暂缓（已有首个 CI 档位产物，仍等 Claude 确认再入库）。**M2-C6**（09-23，`4470fd0`，待收编）：`docs/README.md` §2 文档地图 +5 行（m3-preplan/vec-preplan/ws-message-diff/m2-p4-budget-preplan/l1-spec）+ §5 M2 表 +5 行第五轮终态（C5 `dd8e253`/S5 `3c69158`/D5 `ee70aad`/P5 `7cfe842`/K3 复验 `e10c6cd`）+ 同表 5 处过期状态校正（S3/D3/P3/K2/A2 第三批→✅ main）；遗留 gap：§5 第四轮行（C4/S4/D4/P4/K3 清单）与 A2 第四批 `805166e` 未入表，已回执请裁。教训：任务卡给的摘要注意回文档原文核对（ws-message-diff「M5 放行」实为「不阻塞 M5」）。**M2-C7**（09-23，`0eff1e9`，待收编）：§5 补齐 **11 行**——第四轮 5 行（C4 `525f970`/S4 `38a7f63`/D4 `e77d25c`/P4 `1813cbb`/K3 清单 `d7f066f`）+ A2 第四批 `805166e`（按时间序放第五轮之后）+ 第六轮 5 行（C6 `4470fd0`/M3-S1 `2daa644`/D6 `414acb5`/P6 `8fd9a17`/M5-K1 `b849025`，结论列补注收编 merge `7328dfc`/`8470f3b`/`3c20b7c`/`db46b9e`）；K2 行状态消重改 ✅ 已回执（`d7f066f` 归 K3 清单独立行）；§5 标题→「第一至第六轮」。验证：36 行×5 列一致、无冲突、11 commit 均 is-ancestor main、8 文件路径 Test-Path 全在。**表已无已知缺行**；第七轮照此格式续加。**M2-C8**（09-23，`925b39d`，待收编）：§5 补第七轮 5 行（C7 `0eff1e9`/M3-S2 `d81cf11`/M3-D1 `4da190d`/M3-P1 `1d09581`/M5-K2 `5cf58c9`）+ 第八轮 6 行（M3-D2 `caddcdd`/M3-P2① `48db6cf`/M3-S3 `56a6fa4`/M5-K3 `c25b979`/A2 第五批 `3bf49be`/A2 第六批 `1ae9e54`）；§2 补 `docs/arch/m3-plan.md` + `docs/security/m3-evidence-chain.md`。**卡片勘误已按 git 修正**：卡里「M3-D1 = 2daa644（收编 7328dfc）」实为 codex M3-S1（C6 已入表），M3-D1 真身是 opencode `4da190d`（收编 `d7178fe`）——未把同一 commit 写两行。验证：§2 29×4、§5 47×5、无冲突、16 路径全在、11 commit 均 is-ancestor main。**遗留**：§2 仍缺 `m3-retrieval-budget.md`/`anchors-api.md`/`t1-sampling-10k.md`/`ci-calibration-m2p6.md` 四行（已提示待裁）；§5 现混装 M2 轮次与 M3/M5 交付。
> 新对话开场先读本节 + .orca/workflow.txt + .orca/agent-registry.md。能力域：依赖/配置/CI/文档域；评审 codex 与 pi 的工作；评审 Agent=Claude。
> **本文件已入库**（main `3e320b9` 裁决，规则 #7）——改动走提交；跨分支同路径由 Claude（主导）收编合并。
> 另读：`.orca/talking.txt`（任务指派）、`docs/dev-workflow.md`（含 **§7 Windows 行尾假红**——本机格式类检查报错先看那节）。

### 我已交付（全部已收编）
- **M2-C1**（收编 main `19e3a88`）：docs/README §5 M2 区块 + M2 依赖对账（**零新包**）+ ci.yml M2 占位步骤 + nightly M2 红线接入点注释 + `.gitattributes` 正式提议。
- **M2-C2**（收编 `b1f3d6c`）：`sim/world/weather.py` 风场（`wind_at(tick, rng)` 纯函数可重放 + `daily_reseed_due` 每日天气注入点；`sim/tests/test_m2_weather.py` 31 用例）+ ci.yml M2 步骤填实（glob `sim/tests/test_m2_*.py`，命名约定即契约）+ dev-workflow §7 重签出手册 + **六树重签出执行**（w/crlf 全 0，prettier/gen-protocol 假红消失）。
- **M2-C3**（纯校验，无提交）：M2 glob 实选 6 件/113 用例 ✓、5 个命名门禁无重复接 ✓、SOAK step/env 门/5 条红线对账 ✓、768 passed 口径 ✓、六树 crlf=0 ✓；**揪出 P0=README §5 未解决合并冲突标记进了 main**（Claude 修 `cbf40ee`），P1/P2 口径过期由 codex 代修。
### 已内化教训（实测过，别再踩）
1. **Windows CRLF 假红**（根因已消除）：`.gitattributes`（`* text=auto eol=lf`）已裁决落地（main `3ab8c71`），各树一次性重签出后 161 个 `w/crlf` → `w/lf`，本机 `prettier --check` / `gen:protocol --check` 不再假红。**自检一条命令**：`git ls-files --eol | grep -c 'w/crlf'` 期望 0（>0 = 该树没重签出）。重签出**只有** `git rm -r --cached . && git reset --hard` 管用（`git checkout-index -f -a` 实测无效；先 commit/stash，未跟踪文件不受影响）。操作手册在 `docs/dev-workflow.md` §7。
   - M2-C2 六树实测（2026-09-21，仅对**干净树**执行）：`w/crlf` main 115 / cline 158 / codex 159 / pi 150 / opencode 151 / kilo 151 → **全 0**；重签出后 `npx prettier --check .`（"All matched files use Prettier code style!"）与 `gen-protocol --check` 均 EXIT 0 —— P05 时代的假红确认消失。
2. **CI 门禁按文件路径接，不用 `-m xxx`**（P04 教训：marker/addopts 一变就被静默排除成假绿灯）。M2 现状＝glob `sim/tests/test_m2_*.py`（**命名约定即契约**，新 M2 验收测试落该前缀自动进门禁）+ `-m "not bench"` + `timeout-minutes: 15` 双护栏；完整 604,800 tick 跑在 nightly（**方案 A 已裁决落地**：step 跑 `test_bench_soak.py::test_m2_full_7day_acceptance`，env `PI_M2_FULL_SOAK=1`，timeout 60）。**我的挂账义务：里程碑后把该 step 迁出为周频独立 workflow**（nightly 注释 + m2-acceptance §4 已写明）。
3. **跨域代改须留言**：opencode D03 的 3 文件 ruff 格式偏差属数据域文件，修复前在其树 talking.txt 留言说明（f775b91）。
4. **与主导方裁决冲突时，以 main 实际决策为准**：memory.md 入库裁决（`3e320b9`）推翻我此前「移出跟踪」提交（cb2d85e），已在 76d6a03 反转并恢复入库。
5. **量纲先算再写门槛**：写 CI/验收前先按 DESIGN 推 tick 数。M2 完整验收「50 NPC × 7 游戏日」= 604,800 tick（1 tick = 1 游戏秒），**不属于每提交 CI**——所以 M2 步骤是占位 + `timeout-minutes: 15` 护栏，而不是写死路径。
6. **别在他域分支上重复接门禁**：codex 的 M2-S1 已自带 ci.yml 步骤（其分支内），M2 占位步骤不重复接同一文件；同一门禁两处维护会漂移。
7. **`.gitignore` 的 catch-all `.*/` 会挡住 `.github/`、`.orca/` 下的新增文件**：已跟踪文件不受影响（改 ci.yml / memory.md 正常），但**新增**文件 `git add` 会失败并提示 ignored，须 `git add -f`。**已裁决部分**：`.github/` 补了例外（`!.github/` + `!.github/**`，main `3ab8c71`，新增 workflow 现在可正常 `git add`）；**`.orca/` 未补**：`.orca/` 下新增文件继续用 `git add -f`（要改规则得再请裁——它属用户规则 #4 语义）。
8. **纯函数优先于「推进式 RNG」**：`sim/world/weather.py` 若用 `RngRegistry.generator(name, cache)` 抽签就会**推进状态**（调用顺序影响结果，回放/bench 不可重算）。正解＝从 `rng.draw_key(流名)`（材料指纹，含熵注入）派生档位种子 → 每次新建 `Generator` 抽，得到「同 (rng, tick) 恒同风」。写任何「按 tick 派生的物理量」都照此办。
### 常用命令（M2-C4 口径）
- 本树开工第一步：`git merge origin/main`（常落后 main，P05/P04 都遇到过）。
- 全量：`uv run pytest -m "not bench"`（main `7d63210` 口径 **805 passed / 55 skipped**；纯 collect 核数法：collect-only 847 全收集，`-m "not bench"` 选中数 − skipped = passed）；bench：`uv run pytest -m bench`。
- M2 门禁复演：`uv run pytest sim/tests/test_m2_*.py`（我的文件＝test_m2_weather.py）。
- 行尾自检（应 0）：`git ls-files --eol | grep -c 'w/crlf'`。
- `.orca/` 下**新增**文件要 `git add -f`（catch-all `.*/` 兜底；改已跟踪的 memory.md 不受限）。
- nightly 取证/触发（本机 `gh` 已认证 ZX466，scopes 含 repo+workflow；调用前须 `$env:HTTPS_PROXY='http://127.0.0.1:7897'`）：`gh run list --workflow nightly-bench.yml`、`gh run view <id> --log-failed`（**注意**：bench step 红时 pytest 汇总可能未打印，改用进度行 `test_bench_*.py` 的 `.`/`F` 标记判失败集合）、`gh workflow run nightly-bench.yml --ref ZX466/cline`。
### 未决项
- **M2-C4 / M2-C5 已交付待收编**（C4 `1772f3a`、C5 `db092ed`）：详见本节快照与本树 talking.txt 回执；收编后本行删除。
- **nightly 残留次因待裁（pi 域）**：4 个微基准断言在 ubuntu-latest 上**轮换**越线（逐轮集合不同、边缘超 3–8%）＝档位口径问题。我的 CI 侧修复已让红灯时也归档 `perf/bench.json`+`runner.txt`，pi 可据此定标/放红线。baseline.json 入库仍顺延至首个绿色 run（入库前留言板报 Claude）。
- **里程碑后 soak 完整跑迁出**：nightly step → 周频独立 workflow（我迁，已在 nightly 注释/m2-acceptance §4 挂账）。
- `.orca/` 例外不补（裁决维持）：新增文件一律 `git add -f`。
- 嵌入模型选型（M3）：走已锁 openai 客户端＝零新包；本地模型须先过依赖评审。

（以下各节由对应 agent 维护——cline 节以上为 2026-09-20 收编版。）

## ③ opencode（数据 / 数据库域）
- 【2026-09-24 第九轮快照｜D4 已交付待收编】**M3-D4 已交付**（B3 实施，裁 10 全采 + codex 预审 7 要点，分支 `30dd087` 基于main `4e381c0`，已补推双远程）。**0005_m3_knowledge_governance**：knowledge `add_column`×7（subject_npc_id/subject_attr_id/evidence_seq/source_knowledge_id + source_memory/invalidated/invalid_reason）+ 索引×3 + CHECK×3（source 取值域/confidence 值域等可表达约束）；`KnowledgeStore.invalidate_by_source|invalidate_by_row` 级联 + `write_fact` 走 X7 写入门 + T1 钉子 test_t1_m3_knowledge_cascade。
- 【B3 实施三条纪律留痕】①**继承失效不继承替代**：`_cascade` 沿 `source_knowledge_id` 广度递归，只置 `invalidated=1`+`invalid_reason`，表内无替代指针（钉子断言 `superseded_by not in cols`，codex 预审①）；已失效行不覆写 invalid_reason、不重复计数（幂等）但仍向下遍历（下游可能尚未失效）。②**X7 写入门**：`memory_scan` 抽出 `decide()` 为唯一判梯，`write()`（记忆）与 `scan_fact()`（知识）共用——知识表不可能成为扫描面旁路；改写放行落清洗后文本（`decision.content`），落原文=绕过 S3。③**evidence_seq 复用 seq_by_index**：`fill_evidence_seq` 只按 M2-D3 投影缝映射回填，不读 max(seq) 不自行分配（否则 witnessed 知识锚到不存在的 seq）。
- 【踩坑：`_cascade` await 种子】`invalidate_by_row` 初版传同步 lambda，`_cascade` 里 `await seeds_fn(session)` → TypeError；修=两个种子源都改 async。`session.execute(update())` 的 Result 无 rowcount（pyright）→ 先 select 判状态再 UPDATE，免 type-ignore。
- 【踩坑：知识 CHECK 形状】`witnessed ⇒ evidence_seq NOT NULL` / `told ⇒ source_knowledge_id NOT NULL` 表达不了 DB CHECK，落应用层（`write_fact` 的 `_check_shape`/`_check_evidence_shape`）；旧 `test_knowledge_insert` 直插 ORM 不经应用层仍绿——**ORM 直插只保低层存储测试，生产必经 write_fact**。
- 【历史】第八轮 D3（B3 提案+C2 重放逐位相等，`90cc1e9`）、第七轮 D2（A4 治理 JOIN 收口+裁 7 四红线+materialize_matter，923 passed）、第六轮 D1（C2 域约束 29/29+VectorIndex 骨架）见各自快照原文（git log .orca/memory.md）。

- 【C2 逐位相等留痕】§19.3 判据：快照路径（直读 `matter_state`）与重放路径（折叠 events）产出**逐位相等** `MatterLedger`。实测 `snap._items == rep._items` True（含 COLLAPSE 终态 / decay_rate 携带 / 多事件序列）。**关键**：折叠规则单一来源 `fold_matter_snapshot`（新对象 durability<0→1.0 且 decay_rate<0→0.0；旧对象 durability<0 沿用 integrity、decay_rate<0 沿用率；is_rubble 只增不减）——两路径**不得各写一套**，否则分叉。新增测试 `sim/tests/test_m3_matter_replay.py` 6 用例（逐位相等×3 + 过滤/分支隔离/纯读）。
- 【门禁】`pytest -q --ignore=sim/tests/bench` = **959 passed / 55 skipped / 0 failed**；ruff ok；**pyright 5 error（= main 基线，均 Claude A2 `test_t1_m3_hidden_emerge.py` pin 的既有错，本批零新增）**；alembic 零漂移（B3 提案阶段模型未动，autogenerate 仅 `pass`）。
- 【2026-09-23 第七轮快照】**M3-D2 已交付**（A4 收口 + 裁 7 四红线 + C1 materialize_matter）。分支 `ZX466/opencode`：**R2 钉子 3 RED → 0（全绿 5/5）**——`vec_candidate_ids` 召回 SQL 内联 `JOIN npc_memories ON m.id = v.rowid` + `WHERE superseded_by IS NULL AND invalid_reason IS NULL`（治理过滤**进打分缝前**，push-down 到 vec0 查询同句；supersede 落库后同连接直读无缓存 → 即时生效）。**裁 7 四红线进 `sim/tests/bench/thresholds.py`**：`VEC_CANDIDATE_PER_NPC_LIMIT_MS=0.30` / `RETRIEVAL_SCORE_PER_NPC_LIMIT_MS=0.30` / `RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS=2.00`（退化哨兵）/ `RETRIEVAL_TICK_LIMIT_MS=12.0`（依据 `docs/perf/m3-retrieval-budget.md §1.3`；合计 0.60 不新增行仅注释）。**C1 `NpcStore.materialize_matter(matter_ids=None) -> MatterLedger`**（§19 快照路径照抄）：一次 SELECT `matter_state` WHERE `branch_id` 隔离，`subject_id→matter_id`/`integrity`/`decay_rate`/`is_rubble` 直通，显式 id 未知者不在结果，纯读零迁移。整改全绿：`pytest -q --ignore=sim/tests/bench` = **923 passed / 55 skipped / 0 failed**、ruff ok、pyright 0 error、alembic 零漂移（fresh DB autogenerate 仅 `pass`）。
- 【A4 召回 push-down 留痕】`vec_candidate_ids` 不再经 `SqliteVecIndex.knn`（纯接口保留 rowid+distance 无治理），而自持治理-aware SQL——治理过滤必须在候选生成句内完成（R2 契约 2：不能召回后再放行），故 vec0 `MATCH ... k=?` 与 `JOIN npc_memories` 同句。A4 后勿把过滤拆到 Python 侧（会破坏「占比恒 0 + 无窗口期」两条契约）。
- 【C1 rubble 重建留痕】`MatterLedger.register` 不设 `is_rubble`，故 `materialize_matter` 对 `is_rubble=True` 行追加 `mark_rubble`（置 integrity=0.0）——DB 不变式 `is_rubble ⟹ integrity==0.0`（`_project_matter` 保证）使其与逐位列等价（§19.3 逐位重建）。
- 【2026-09-23 第六轮快照】**M3-D1 已交付**（C2 MatterPayload 域约束 + A3 VectorIndex 接口草案）。分支 `ZX466/opencode`：**C2 钉子 29/29 GREEN**（`Field(ge/le)+allow_inf_nan=False` 于 x/y/amount/durability/decay_rate，factory 与 `validate_store_row` 同源传导，insert/update 双路径覆盖）；**R2 钉子 4 RED → 3 RED**（仅剩治理 JOIN 未接：`test_candidates_view_excludes_governed_entries`/`test_supersede_cascade_immediate`/`test_query_join_filters_governed_rows_sql`；shape 与 rowid 契约 `test_shape_unchanged_entries_are_memory_entry`/`test_rowid_keying_contract` 转绿）。A3 落地 `VectorIndex` Protocol + `SqliteVecIndex`(A 主)/`NumpyCosineIndex`(B 降级) 骨架 + `VecCandidateSource`/`vec_candidate_ids`（治理过滤 JOIN 留 A4）。整改全绿：`pytest -q --ignore=sim/tests/bench` = **919 passed / 55 skipped / 3 failed（皆 R2 治理，预期最小 RED）**、ruff ok、pyright 0 error、alembic 零漂移。
- 【C2 钉子修正留痕】codex 原 `TestMatterEndToEndBounds` 把 `matter_event(...)` 写在 `pytest.raises` **之外**，与 `test_factory_rejects_nan_durability`（同调用要求抛 `ValidationError`）**自相矛盾**，无任何实现可 29 全绿。经 Claude 裁决：工厂调用移入 `with` 并放宽为 `(EventValidationError, ValidationError)`（工厂/store 任一层拒绝即过，defense in depth）。钉子头部已留修正说明。
- 【R2 候选身份约定】`VecCandidateSource.candidates()` 产出的 `MemoryEntry.id` = **vec rowid**（= `npc_memories.id`），非 `npc_memories.entry_id`——R2 钉子以 rowid 为候选身份（`_insert_memory` 返回 rowid 与 `c.id` 集合比对）。已在 `vector.py::_rowid_to_entry` 留档 + `# type: ignore[arg-type]`（A4 接治理 JOIN 时勿改此约定，否则钉子的集合比对失配）。
- 【2026-09-22 第五轮快照】M2-D5 已收编（`ee70aad`）。**M2-D6 已交付分支 `414acb5`**（docs 型、零代码零迁移）：`vec-preplan.md §7 裁决栏`落地——**已裁 3**：V1（sqlite-vec 主 / numpy 余弦降级，同接口两实现）、V4（vec 表为准，`npc_memories.embedding` 仅写缓存）、V6（治理过滤召回端红线，JOIN+过滤 superseded/invalid/abandoned，codex R2）；**挂起 4**：V2/V3/V5/V7（V3 改 schema 须提案、V7 触 S1 须 codex 复核）。裁结对比表已去冗余（§2 合并为结论行）。`schema.md §19` 注册≠落库补核对（与 V6 无交集，matter 域 vs 记忆域）。任务单=本树 talking.txt。

### 已内化教训（M2-D2/D3 实测，别再踩）
- **`.orca/talking.txt` 是 worktree-local（gitignored）**；`.orca/memory.md` 是 tracked。给本树的回执写 talking.txt；给**他树**的回执写**对方树**的 talking.txt。收编方=Claude（merge 各 ZX466/* → origin+gitee 双远程）。
- **Windows 行尾**：新文件一律 LF、无 BOM（`git ls-files --eol | grep -c w/crlf` 期望 0）；CJK 控制台会显示乱码但文件字节正常，别被吓到。
- **零漂移纪律**：任何 schema 改动前先 `uv run alembic upgrade head` → `revision --autogenerate` 看迁移体是否仅 `pass`；「投影回既有列」不产生新迁移（M2-D2 LOD 投影回 `npc_profiles.lod` 即无 0005）。
- **S1 唯一写入口**：所有 `MemoryEntry` 必须经 `MemoryWritePipeline.write()`（S1 守卫测试 `test_memory_scan.py::TestS1Guard` 扫仓内绕过点）；测试造数据也用 pipeline，别直接 `store.persist` 写正文。
- **append 收窄**：`SqlEventStore.append` 默认 `validate=True`（走 `event_validation.validate_store_row`）；低层存储机制测试（合成 payload）必须显式 `validate=False`，否则被 payload 白名单拒。
- **projection 缝**：投影回调在 commit 前**同一 session** 执行，异常整批回滚（无半写）；`EventStore` Protocol 与 `flush_events`（无投影）行为不变。
- **读侧 only**：检索/打分层（`sim/npc/memory.py`）不写库、不碰写路径与守卫；偏差逻辑（cognition）后期以 `Scorer` 钩子注册，**不写死**。
- **pyright 全绿要点**：`async_sessionmaker[AsyncSession]` 注解要显式（否则 property 返回 Unknown）；测试里 pydantic 模型 `category` 等 str 字段从 DB 读出要 `# type: ignore[arg-type]`。
- **验证命令**：`uv run pytest -q --ignore=sim/tests/bench`（门禁）；bench 单独 `uv run pytest sim/tests/bench -q`（7 日 soak 需 `PI_M2_FULL_SOAK=1`，默认 skip）；`uv run ruff check sim/ && uv run ruff format --check sim/`；`uv run pyright sim/`。in-file 测试类标 `@pytest.mark.t1`，文件名 `test_m2_` 前缀自动进 CI 门禁。
- **flake**：`test_bench_soak` p99 阈值对 CPU 争用敏感——与其他命令并发跑会假红，单独或正常整套跑即可。
- **matter 投影缺口（M2-D4 实测）**：`matter_state.decay_rate` 列 §14 已存在但投影从不写（新建硬编码 0.0、update 不碰）——账本 `decay_rate` 是**静态率、无任何事件承载**，且 `jitter` 未落 payload 无法反解 → §14「回放逐位重建」不成立。修法**无需新列/迁移**（列已在），只有方案 A：`MatterPayload` 增可选 `decay_rate` + factory/结算携带 + 投影写列（改冻结事件基线，须先报裁）。对账表见 `schema.md §17`。
- **对账表方法论**：三方对账 = 逐字段判「能否从事件流重建」（§14 判据）；`is_rubble` 靠 `COLLAPSE∨integrity≤0` **推导一致**（非显式承载，当前等价）；`subject_kind/material/quality/load_bearing/supported_by` 是账本无源的占位（归 M4/M5，非缺口）。
- **pyright 遗留基线**：`test_m2_cognition.py`(source Literal) 与 `test_m2_runtime_assemble.py`(dict[str,object] 取值) 有 3 个**既有**错（Claude M2-A2 第三批文件，非本域），改动前先确认不是自己引入的。
- **多行 CJK docstring 的 ruff E501**：行宽按字符数计，CJK 表格行/长句易超 100——拆行或去冗余；docstring 里 Markdown 表格的 `\|` 会被 Python 当非法转义（W605），改用「或 None」「和」等文字表述。
- **M3 向量检索缝（预研内化）**：`npc_memory_vec` 在 M3 只是**候选生成器**——新增 `CandidateSource` 协议换候选源，`Scorer` 打分链一字不改（§18 硬边界）。**`sqlite-vec>=0.1.6` 已是 pyproject 依赖且已装**（别重复装）；脚手架 `sim/core/persistence/vector.py`（load/create/exists）已备，DDL 在 Alembic 范围外（需 LOAD EXTENSION）。量级 50×1000=5万条非瓶颈，**成本在 embedding 生成**；embedding 挂 `LlmClient.embed(profile, texts)`（复用 ProfileSnapshot + llm.* 监控 + K3/K4），chat 模型不产 embedding → §10 或需第二条 profile 缝。详见 `docs/data/vec-preplan.md`。
- **matter 读路径（M3 预研）**：`materialize_matter()` 对镜 `materialize`（一次 SELECT、禁止逐对象）；快照路径（直读表）vs 重放路径（snapshots+事件重放）两入口**同产物**，重放器须复用 `_project_matter` 同一折叠规则避免语义分叉；**注册≠落库**（新建对象未产事件前不在表）。详见 `schema.md §19`。
- **V 系裁决采结（M2-D6，M3 实现据此）**：**V1**=sqlite-vec 主 + numpy 余弦降级（同接口两实现 `SqliteVecIndex`/`NumpyCosineIndex`）；**V4**=vec 表为准（`npc_memories.embedding` 仅写路径缓存，读不参与）；**V6**=治理过滤在**召回端**（候选必须 JOIN `npc_memories` 过滤 superseded/invalid/abandoned——**codex R2 红线**，不允许「写入时不同步」旁路）。挂起：V2 维度（随模型锁）、V3 profile 缝（改 schema 须提案）、V5 召回时机、V7 embedding 挂写路径（触 S1，须先提案+codex 复核）。见 `vec-preplan.md §7`。
- **裁决栏落法（文档惯例）**：任务说「落裁决栏 + 去冗余防误导」= 新增 `## 裁决栏` 节（已裁表+挂起表，挂起注明理由/触发时点），并把被裁结的**对比/建议表**合并为「结论行」、删掉「倾向 X / 最终裁决留 M3」这类过期措辞；原结论节顺延编号。


> ——以下为 opencode 树 memory.md 原文（收编于 3309c0f）——
> **新对话开场先读**：`.orca/workflow.txt` + `.orca/agent-registry.md` + 本文件 + `.orca/talking.txt`。
> 我的能力域：**数据/数据库**。上游派单：Claude；评审 Agent：Codex。
> 本文件（用户规则 #7）保存我自己的记忆，供新对话继续任务。**已入库**（`.orca/` 属规则 #4 的例外，
> `.orca/memory.md` tracked；仅 `.orca/talking.txt` 为 worktree-local 忽略）。

---

## 规则速记（用户规则 #4 / #7）

- **规则 #4**：除 `.orca/` 外，所有 `.` 开头文件夹（`.agents` `.claude` `.codex` `.opencode` `.codegraph` `.kiro` 等）
  **不入 git、不推送**。但本地必须存在：
  - `.codegraph`、`.agents` → **每个**工作树都要有；
  - `.claude` / `.opencode` / `.codex` → 在**对应**工作树要有；主工作树全有。
- **规则 #7**：各工作树 `.orca/memory.md` 分别保存各 agent 记忆（本文件）。除 agent 自带记忆外，不强制另造。
- `.gitignore` 已固化：`.orca/` 仅忽略 `talking.txt`；其余 dot-folder 全忽略。

---

## 项目状态（2026-09-20 同步自 main `3e320b9`）

- **M0 + M1 全部收官**，TASK-004 五路（opencode/codex/cline/pi/kilo）全部交付并收编。
- 全量测试：**589 passed, 55 skipped**（571 passed + bench 18 passed 分开跑；详见「验证」）。
- 我的 **D04 已收编进 main**（merge `f73bc04`）。本树 HEAD = `3e320b9`（与 main 齐），无未合并提交。
- 项目：`natural-world`，LLM 驱动 NPC 生活模拟；核心威胁=污染循环（LLM reason 不可信 → 闸门/记忆扫描拦截）。
- 技术栈：Python 3.12 / **uv** / pytest / ruff / pyright / SQLAlchemy 2.0 async + aiosqlite / Alembic / structlog。

## 我已完成的工作

- **TASK-004 / D04（记忆段数据落库）**：
  - `MemoryStore` Protocol 接口化 + `InMemoryStore`（默认，零破坏）+ `make_entry` 唯一构造工厂
    （`sim/llm/memory_scan.py`，S1 守卫保持）。
  - `SqlMemoryStore` 落 `npc_memories`（`sim/core/persistence/memory_store.py`，同步 sqlite3）。
  - 迁移 `0003_memory_write`：`entry_id`(unique)/`source`/`superseded_by`/`invalid_reason` + `idx_memories_visible`。
  - `entropy_log.event_seq` 回填：`flush.py`→`event_index`→`store.append` 同事务回填。
  - 测试 `sim/tests/test_memory_store.py`（10 项）。
- **更早**：TASK-001~003 数据域全链路参与（crypto、M3 预留表 0002 等，详见 `git log` 与 `docs/data/`）。

## 当前任务

待命（M5-K4 已闭环：ws-dispatch 提案 264 行，裁 12 全采）。

## 进行中

(空 — M5 anchors 施工时按 K4 对表 [T]/[O]/[C] 三类断言验收；8.7 sync_request 回错型列 M5 首修。下一单等 Claude 经 talking.txt 派发。)


## 留言板

- 读 Claude 经 `.orca/talking.txt` 写来的任务指派。
- 已挂账提醒：structlog 需挂 `redact_sensitive` processor（crypto 域，若尚未接线）。
- 潜在方向：M3 嵌入（锁 embedding model → 建 `npc_memory_vec` → 向量检索，关联语义已固化）；
  生产装配把 `MemoryWritePipeline(store=SqlMemoryStore(...))` 接到实际写入点。

---

## 数据域关键契约（速查）

- **MemoryEntry**：`id`(uuid hex,= `npc_memories.entry_id`) / `npc_id` / `content`(唯一受扫描保护) /
  `source∈{reason,dialogue,event,interoception}` / `event_seq`(NULL=推理转述) / `importance` /
  `emotion_tag` / `superseded_by` / `invalid_reason`。
- **写入唯一入口** `MemoryWritePipeline.write()` → `WriteResult(accepted, entry, action, hits, reason)`；
  拒写**不落库**（S4）。**S5**：supersede 只动治理列，永不改 content；iter_visible 过滤被取代；get 审计可见。
- **npc_memories**（0001? no，0002 + 0003）：见 `docs/data/schema.md`。
- **向量关联**：`npc_memory_vec` 是 vec0 虚拟表（alembic 外，需 `LOAD EXTENSION`）；
  业务键 `(event_seq, entry_id)`，rowid = `npc_memories.id`；`DEFAULT_EMBEDDING_DIM=384` 占位待 M3。
- **crypto**：`LZ_MASTER_KEY` 缺失/非法 → 拒绝启动；`encrypt/decrypt_api_key` + `redact_sensitive`。

## 踩坑记录

1. S1 守卫 grep：非 `memory_scan.py` 禁止出现 `MemoryEntry(` → store 必须走 `make_entry(...)`。
2. `MemoryEntry.id`(uuid hex) ≠ `npc_memories.id`(int 自增)；业务句柄统一用 `entry_id`。
3. `.orca/talking.txt` gitignored；`.orca/workflow.txt`、`.orca/agent-registry.md`、`.orca/memory.md` tracked。
4. PowerShell 显示 UTF-8 中文会花屏；用 Python `open(...,encoding='utf-8')` 或 .NET 读，别信控制台。
5. bench 是 wall-time 断言，全量并发跑会抖动偶失败 → **bench 单独跑**；功能套件用 `--ignore=sim/tests/bench`。
6. alembic autogenerate 校验：`upgrade head` → `revision --autogenerate` 看 upgrade() 是否只剩 `pass` → 删临时文件。
7. `WORLD_DB_URL` 控 alembic 目标库（测试用 tmp_path，别动 `world.db`）。
8. Git：提交归属 `ZX666X <zx19836980213@outlook.com>`；推 `origin` + `gitee`；未要求不提交。

## 验证命令

```powershell
uv run pytest -q --ignore=sim/tests/bench     # 571 passed, 55 skipped
uv run pytest sim/tests/bench -q              # 18 passed（单独跑）
uv run pytest sim/tests/test_memory_scan.py sim/tests/test_persistence_m3.py sim/tests/test_memory_store.py -q
uv run ruff check . --output-format=concise
uv run pyright sim/
```

## 已完成任务链

| 任务 | 内容 | 状态 |
|------|------|------|
| M0 | 事件溯源核心 + 0001 | ✅ 收编 |
| TASK-003/D03 | crypto + M3 预留表 + 0002 | ✅ 收编(`52967ed`) |
| TASK-004/D04 | MemoryStore 接口化 + SqlMemoryStore + 0003 + entropy 回填 | ✅ 收编(main `f73bc04`) |

> 每次完成后更新本文件「当前任务 / 进行中 / 已完成」；过时内容删掉。

## ④ codex（安全 / 合规 / 风险域）
- 【2026-09-24 第九轮快照｜M3-S5 已交付（提案层）】B3 验收+F1 复核完毕（零代码）。**D4 未落地（验时点）→ 交付提案层对表+D4 验收清单**。D3 提案对预审 7 要点 7/7 过：命名对齐（无 replacement 列）/级联接口沿 source_knowledge_id 递归有界幂等/invalidated 键与 evidence 闭环/0005+CHECK+downgrade/全 branch_id/落库走写入门（grep 实证现态零裸 INSERT）/R3 口径同 iter_visible。⚠️ 一项待实施落实：evidence_seq 回填须点名复用 seq_by_index 不造第二套（opencode D4 已照办）。**F1 复核实测留痕**：str→["b"] 与 dict→["ghost"]（迭代键洗白成见证人，新发现向量）均 ACCEPTED；123→TypeError、["ok",5]→ValidationError fail-closed 好；store 行级仍拒裸 str（纵深未破）。**验收形已落地**（main `64b7390`：Sequence[str]+isinstance 拒 str/bytes/dict）。D4 收编后按清单终验：R1 端到端三硬断言+X7 grep 审计+裁10④接线点+0005 downgrade 零漂移。
- 【E1 二阶 RED 语义保留】test_t1_m3_hidden_emerge.py 的二阶拒绝指纹（先断言 kind 已注册再断言拒绝原因串）是防「红灯被错误实现满足」的机制，永久保留勿简化。
- 【历史】M3-S4 转绿双绿复验+F1/F2 advisory（`e33642a`）、S3 E1 钉子 26 RED（`56a6fa4`）、S2 证据链契约（`d81cf11`）、S1 双钉子（`2daa644`）、安规预研 m3-preplan（`b650882`）见 git log 原文。
- 【2026-09-22 第四轮快照】M2-S3 已收编（`3c79465`，通过结论；2 MEDIUM 已被 opencode 修：`4a11d0f` event_validation.py + materialize_hidden）。M2-S4 已交付（`38a7f63`，origin+gitee 已推，等收编）：t1-sampling-10k.md 口径 + test_m2_t1_sampling_10k.py harness（10k 采样 7 用例 1.1s；判据=零直陈泄露+零误伤+全覆盖+可重放；S1 文件零改动；test_m2_ 前缀自动进 CI glob）。全量 862 passed + 55 skipped。

> 本树工作簿：用户级技能 `security-worktree`（~/.agents/skills/，含环境坑/评审配对/回写纪律）。
> 能力域：安全/合规/风险；评审配对：cline 评审我，我评审 Claude（架构+前端）与 opencode（数据/库）。

### 项目状态（2026-09-20 同步自 main `4323c9e`）
- M1 全量收官（TASK-004 S04 已收编，578 passed + 55 skipped）；M2 已派单。
- 本树分支 ZX466/codex；M2-S1 交付后工作区干净，等 Claude 收编。

### 你已完成的工作（最近一轮）
- **M2-S3 M2-D2 安全评审（2026-09-21 交付）**：结论=通过（0 CRITICAL/HIGH + 2 MEDIUM + 2 观察 + 4 正面确认），
  落 `docs/security/m2-d2-review.md`；增补 3 条测试到 test_m2_runtime_store.py（拒写 reason/hits 结构化、
  触发放行、混合拒写）→ 18 用例全绿。MEDIUM：M1=SqlEventStore.append 裸 dict 绕过 payload 模型校验（opencode），
  M2=materialize 不加载 npc_health 隐藏行（升格装配缺半边，opencode+Claude）。
- **M2-S2 L1 动作白名单 + 升格隐藏属性契约（2026-09-21 交付，29 个新 T1 用例，全量 675 passed）**：
  - `docs/security/l1-whitelist.md`：白名单审查结论（W1-W7）+ HiddenState 契约 + runtime 调用点 + 维护责任。
  - `sim/npc/contract.py`：HiddenState（profile+triggered 快照）——evaluate 重估 / check_reason 降级检查 / gate_kwargs / memory_kwargs / empty() 恒等值。
  - `sim/tests/test_t1_l1_whitelist.py`：29 用例（白名单锁定 / payload 键 / 升格传递 / 降格写回不降防线 / 降级检查一致性 / 零回归）。
  - `.github/workflows/ci.yml`：按文件路径新增 T1 L1 白名单门禁。
- **M2-S1 自我未知安全边界（2026-09-20 交付，28 个新 T1 用例，全量 606 passed）**：
  - `docs/security/self-unknown.md`：隐藏属性标注规范（健康档 疾病/旧伤/成瘾/残疾 + 创伤应激触发条件）+ 情境触发浮现 + 闸门/记忆写入扩展口径 + opencode 0004 数据表协调。
  - `sim/npc/hidden.py`：HiddenAttribute/HiddenProfile 标注模型 + `evaluate_triggers` 触发评估 + `hidden_leak_scan` 直陈泄漏扫描（闸门与记忆写入共用同一工具）。
  - `sim/agent/gate.py`：`revalidate_at_execution` 增加 hidden/triggered 参数与「自我未知」检查——reason 直陈未触发属性 → `hidden_attribute_leak` 拒绝；hidden 缺省 None 与 M1 行为一致。
  - `sim/llm/memory_scan.py`：`write()` 增加 hidden/triggered 参数与直陈拒写（`REASON_HIDDEN_LEAK`），记忆检索默认结果防线。
  - `sim/tests/test_t1_self_unknown.py`：双路径采样（未触发零泄露 / 触发正常浮现）+ 行为暗示可议 + 语料卫生 + 感知帧/装配 prompt 面零泄漏。
  - `.github/workflows/ci.yml`：按文件路径新增 T1 自我未知门禁独立红灯信号（沿用 test_t3_gate.py 做法）。
- 更早累计：TASK-001~004（m1-checklist/threat-model/t3-corpus/memory-scan + T3 实弹 + W6 WS 鉴权 + M1-D reason 禁词门）；详见 git log 与 docs/security/。

### 当前任务
- M2-S4 已交付（`38a7f63`，等收编），等下一波派发。

### 进行中
- (空)——等下一波派发（第三批评审等 Claude 通知）。

### 留言板
- (读 Claude 经 talking.txt 写来的任务指派；给他树留言写对方树 talking.txt)

## ⑤ pi（性能域）
- 【2026-09-24 第九轮快照｜M3-P2 全闭环已收编】①四红线 bench 进 thresholds.py（VEC_CANDIDATE/RETRIEVAL_SCORE 0.30 / FULL_SCAN 2.00 / TICK 12.0，依 m3-retrieval-budget §1.3）；②**baseline.json 入库 + nightly 切 `--benchmark-compare-fail=median:25%` 相对漂移制**（裁 4/裁 11）。机型切换观察（EPYC 7763 vs 9V74，median 1.71）已进 bench-plan §4.1 step6 边界注记。**active 纪律**：25% 相对漂移限「跨 run 同档位」；机型迁移重对账；检索防呆红线（决策/prompt 驱动触发，禁每 tick 全量——反证数据是母本）；thresholds.py 唯一真相源，硬断言只在定标机。**待命**：下批=①nightly 新判定首跑观察（首个 --benchmark-compare run 漂移数字）；②A4 sqlite-vec 真实现后候选红线复核对账（参考实现 1.29x 余量偏紧，预期真实现更省）。
- 【历史】M2-P3（l1-spec 对账+L1 feeder+p99 信息性守护 `1e3e36e`）、M2-P4（budget 预案+SMELL_WIRED 1.0 `82efcc2`→已收编）、M3-P1（四红线预研）、P2①（四红线落地 `48db6cf`）见 git log 原文。perf-worktree 技能（~/.agents/skills/）可完整恢复工作状态。

> ——以下为 pi 树 memory.md 原文（收编于 50b0ebb）——
> 新对话开场先读本文件 + .orca/workflow.txt + .orca/agent-registry.md。你的能力域：性能域。
> 配套技能：`perf-worktree`（用户级 ~/.agents/skills/，含环境坑/基准口径/常用命令）——新对话若发现本文件
> 不足以恢复上下文，读该技能全文可完整续上工作状态。

## 项目状态（2026-09-20 同步自 main `3e320b9`）

- M0+M1 全部收官（TASK-004 五路全部交付并收编），589 passed 55 skipped。
- 你的 TASK-004 交付已收编（收编回执曾写在你树 talking.txt，现已轮换清空；结论可查 git log「merge: 收编 pi」）。
- 本树已 merge main `3e320b9`，工作区干净，待 M2/TASK-005 派发。

## 你已完成的工作（最近一轮）

- **M2-P3 交付（2026-09-21，分支 ZX466/pi）**：L1 算法规格落盘 + soak feeder 升级方案。
  - `docs/perf/l1-spec.md`（新）：原型 `_L1Load`（numpy 数据布局/矩阵形状/打分公式/常量表）
    ↔ 真实实现 `sim/npc/utility.py`（NEED_ORDER 3 / ACTION_ORDER 6 / `_GAIN (3,6)` / HABIT_BONUS 0.05 /
    _EXTRAVERSION_CHAT_BIAS 0.3）逐项对账；未落地项清单（PAD/关系/记忆/候选集/NPC_ACT handler）。
  - `sim/tests/bench/test_bench_l1_utility.py`：加 `test_l1_real_*`（真实 utility_scores_matrix / evaluate_batch /
    NpcRuntime.tick / 单 NPC + 形状契约 + 确定性）。
  - `sim/tests/bench/soak.py`：加 `make_l1_feeder`（mock → 真实 L1 两阶段接线；NPC_ACT 未注册时只折
    move/wander 成 MOVE，其余丢弃；第三批接线后 `translate=lambda _a: True`）。
  - `docs/perf/m2-acceptance.md` §3.1：feeder 升级方案（两阶段表 + 约定 + 两份 feeder 定位）。
  - `thresholds.py`：L1 红线常量未动，注释回填实测。
  - **修漏（自己的假红）**：长跑 `test_soak_nightly_steady_p99_below_tick_line` 用 8.3ms 硬门禁造成反复假红
    （均值 2.3ms / p99 8.6ms = 调度噪声）。改为**硬预算 16.6ms 信息性守护**；回归检测交给
    分窗均值漂移 + 资源增长判据。8.3ms 的固定容身之处仍是短基准 `test_bench_clock.py`。
  - 另修一坑：pytest-benchmark 计**调用墙钟**、不吃返回值，单 NPC 用量必须用 1-NPC 批次（别除 n）。
  - 实测：`utility_scores_matrix` 0.206ms / `evaluate_batch` 0.273ms / `NpcRuntime.tick` 0.747ms /
    单 NPC 0.0124ms（红线 6.0 / 0.12ms，余量 8~29x）；soak L1 feeder 稳态 mean ~0.9ms。
  - CI：bench 44 passed/1 skipped；`-m "not bench"` 770 passed/55 skipped；ruff/format/pyright 绿。
- **M2-P2 交付（2026-09-21，分支 ZX466/pi，commit `7080e1e`+`b033995`）**：7 日自转验收口径 + 长跑预压测。
  - `docs/perf/m2-acceptance.md`（新）：604,800 tick 验收口径——崩溃判定 C1–C10（进程/tick/RSS/句柄/GC/缓存/实体/漂移/确定性/延迟）；降采样断言三级（CI 缩样 / nightly 30k / 里程碑完整 604,800）；
    nightly 接法提案 §4（方案 A nightly step vs 方案 B 独立 workflow，交 cline 裁决）。
  - `sim/tests/bench/soak.py`（新）：窗口化长跑 harness——跨平台进程探针（RSS/句柄/GC 对象）+ `run_soak` 分窗统计 + 确定性持续走动 mock 喂给。
  - `sim/tests/bench/test_bench_soak.py`（新）：CI 缩样冒烟（1,200 tick）+ 探针/量纲契约；`@bench` nightly 30k tick 漂移/p99/缓存/确定性；完整 604,800 环境门 `PI_M2_FULL_SOAK=1`（默认 skip）。
  - `thresholds.py`：加 `SOAK_STEADY_MEAN_LIMIT_MS=6.2` / `SOAK_MEAN_DRIFT_RATIO_LIMIT=1.5` / `SOAK_RSS_GROWTH_LIMIT_MB=128` / `SOAK_GC_OBJECT_GROWTH_LIMIT=20000` / `SOAK_HANDLE_GROWTH_LIMIT=64`。
  - `budget.md` §4 补 M2-P2 对账；`hotspots.md` 加 H-7 长跑隐性累积；`bench-plan.md` §1/§2/§3/§4 补长跑；bench README + docs/README.md 同步。
  - 实测（50 NPC + 感知 + 持续走动 mock，100k tick）：均值无漂移（1.86→1.86ms）、RSS/句柄/GC 有界、缓存封顶。未发现 O(n) 累积/泄漏。
  - CI：bench 36 passed/1 skipped；`-m "not bench"` 649 passed/55 skipped；ruff/format/pyright 绿。
- **M2-P1 交付（2026-09-20，已收编 e42b979）**：L1 效用 + 嗅觉传播预算与 bench 红线。
  - `docs/perf/budget.md`：§1 表新增「嗅觉传播（M2）0.05/0.15」+ 新增「合计（M2）7.05/12.50」；§1.2 M2 分解表；§2.4 补 L1 实测；新增 §2.9 嗅觉；§3/§4 对账补 M2。
  - `docs/perf/bench-plan.md`：§1 清单加 npc.utility / perception.smell；§3 阈值表加 L1 全量/单 NPC/断线兜底/嗅觉四行。
  - `docs/perf/hotspots.md`：H-1 补嗅觉延伸（Eulerian 网格 vs 逐对）。
  - `sim/tests/bench/thresholds.py`：新增 `L1_UTILITY_TICK_LIMIT_MS=6.0` / `L1_UTILITY_PER_NPC_LIMIT_MS=0.12` / `L1_OFFLINE_FALLBACK_LIMIT_MS=0.20` / `SMELL_TICK_LIMIT_MS=0.15` / `SMELL_NAIVE_SENTINEL_MS=3.0`。
  - 新 bench：`test_bench_l1_utility.py`（4 bench + 2 契约）、`test_bench_smell.py`（4 bench + 1 契约）。
  - 实测（暖态中位·本机）：L1 向量化 ~0.02ms / 单 NPC ~0.0004ms；断线兜底 ~0.001ms；嗅觉扩散 ~0.009ms + 采样 ~0.001ms。逐对哨兵：L1 scalar ~4.4ms、嗅觉 naive ~4.6ms。
  - bench 全量 29 passed；`-m "not bench"` 581 passed / 55 skipped；ruff/format/pyright 全绿。
- 感知 bench 红线复核（F06 暖态中位口径采纳）+budget 4x 对账+bench 方法论沉淀（warmup/中位/冷启动诊断）。
  红线口径定案：暖态中位（`assert_median_threshold` + `warmup_rounds=1` 剔 LOS 冷启动 7.6-8.2ms），
  `PERCEPTION_TICK_LIMIT_MS=3.6`（预算目标 3.00ms 另一口径）；RNG 1M 警戒线 300ms、真预算每 tick 200 draws ≤0.10ms。
- 更早累计：TASK-001~003 全链路参与（budget.md/hotspots.md/bench-plan.md + bench 脚手架；详见 git log 与 docs/perf/）。

- **M2-P4 交付（2026-09-22，分支 ZX466/pi，commit `82efcc2`，等 Claude 裁决后收编）**：第三批预算预案。
  - `docs/perf/m2-p4-budget-preplan.md`（新）：三项任务逐一回答 + 预算拆表 + 断言方案 + 上界建议。
  - 拆分口径：smell 场推进（源=全体实体）与旧「纯网格 K=20」口径分离；新红线提案
    `SMELL_WIRED_TICK_LIMIT_MS=1.0`（实测 50 源 0.451ms / 100 源 0.976ms），旧 `SMELL_TICK_LIMIT_MS=0.15`
    保留改注释（不再上浮而是补行）。
  - 最大热点 = `SmellField.inject` 逐源 `np.clip` Python 循环（50 源 0.330ms；`np.add.at` 0.0024ms
    ≈140x 且同格累加语义等价）→ 交架构域改（性能域不越界）；次热点 = `others_max` 逐 observer
    O(N²) 扫描（50×50 = 0.107ms）→ 全局 max + 次大值 O(1) 提案（待语义等价裁决）。
  - flush 断言三件套（探针零触发 / 计时器注入 / flush 与 tick 分开累计）+ 帧级警戒 20ms +
    structlog `perf.flush_ms` 字段；实测 flush_tick 50 条：内存库 2.6ms / 文件库 7.8ms
    （说明一旦误进 tick = 半帧预算，动机成立）。
  - cognition 上界：检索缝 0.15ms/次（实测两钩子净增 0.054）、效用缝 0.01ms/NPC（实测 0.0004）、
    HiddenState.evaluate 0.30ms/tick（实测 0.10）；合计增量 ≤0.20ms/tick 进 L1 行不新增行。
  - 防呆提醒：检索缝必须维持「决策/装 prompt 驱动」频次；若退化成每 tick 每 NPC 全量检索
    ≈27ms/tick 直接破 16.6ms 总预算。
  - 验证：`-m "not bench"` 855 passed/55 skipped；`-m bench` 29 passed/1 skipped（首轮 2 例抖红，
    单跑复绿=机器调度噪声，非回归；已按 bench-plan §0「bench 不进每提交红线」口径记录）。

- **M2-P5 交付①（2026-09-22，分支 ZX466/pi，commit `00bea5c`，等收编）**：SMELL_WIRED 红线 + 嗅觉接线版 bench 用例。
  - `thresholds.py` 新增 `SMELL_WIRED_TICK_LIMIT_MS=1.0`；旧 `SMELL_TICK_LIMIT_MS=0.15`
    保留、注释改「纯网格参考口径（K=20 活性物质源）」；文件头注明两口径**勿混用**。
  - `test_bench_smell.py`：`test_smell_world_step_50_entities`（50 实体硬红线）+ 
    `test_smell_world_step_100_sources_headroom`（100 源上界哨兵）+ 
    `test_smell_world_step_tick_amortized`（非 bench：每 tick 摊销 ≤ 红线/2，
    盯 `tick.py::_PERCEPTION_EVERY_N_TICKS=2` 失效）。
  - 复测（inject 向量化 `653d395` 后，np.add.at）：50 源 **0.116ms** / 100 源 0.135 /
    200 源 0.151 / 500 源 0.335 —— P4 的 50 源 0.451ms 已被向量化淘汰；红线按裁决原值
    1.0 不缩（覆盖 ~10x L1 上界，50 源余量 ~8.6x）。
  - 验证：smell 文件 `-m bench` 6 passed；`-m "not bench"` 904 passed/55 skipped；
    ruff check+format、pyright（sim/tests/bench）全绿。
  - 附带告警（非回归）：全量 bench 首跑 `test_rng_1m_draws_per_call` 中位 300.084ms >
    300.000ms 警戒线（差 0.084ms，单跑复绿 = 贴边抖动）。已提案 300→330 待 Claude 裁决。

- **M2-P6 交付（2026-09-23，分支 ZX466/pi，commit `8fd9a17`，等收编）**：advisory 门（裁 1）+ RNG 330（裁 2）+ CI 定标提案。
  - `harness.py`：`ADVISORY_ENV="PI_BENCH_ADVISORY"` + `advisory_mode()`（调用时读 env）；
    `assert_threshold`/`assert_median_threshold` 改 advisory 语义——置 "1" 越线只
    structlog warning（`bench.advisory.threshold_exceeded`/`median_exceeded`）并返回 True；
    未越线 False；缺省仍 AssertionError（`raise AssertionError(...)`，非 `assert False`
    以过 B011 lint）。采集逻辑零改动。
  - `test_bench_advisory_gate.py`（新，9 例，TDD 先 RED）：env 语义（仅 "1" 为开）×
    越线/未越线 × advisory 开关；冒牌 `_FakeStats` 只提供 `.stats.median/.mean`（秒）。
  - `nightly-bench.yml`：「跑基准」step 传 `PI_BENCH_ADVISORY: "1"`；「基线对比」step
    注释补契约（真相源唯一 thresholds.py；advisory 下回归判定 = 相对基线漂移）。
  - `RNG_1M_DRAWS_LIMIT_MS` 300→330（本机全量中位 300.084ms 贴边，+10% 余量；聚合
    警戒线非 tick 硬预算）。
  - **P6② 定标提案**（`docs/perf/ci-calibration-m2p6.md`，**未动 thresholds**）：已从
    run 35816437844 下载 artifact（EPYC 9V74 / nproc4 / py3.12.3）与本机同 commit 对照
    → CI/本机稳定档 **median 1.14**（区间 0.86–1.35）；Python 侧项 CI 慢 1.13–1.35x、
    numpy 侧项 CI 快 0.86–0.92x。唯一红项感知听觉 CI 3.93 vs 3.6（+9% 在档位区间内），
    同 run mean 11.5ms = median 2.9x（被抢断）→ 负载噪声非回归。提案 P-A：建
    `docs/perf/baseline.json` + nightly `--benchmark-compare-fail=median:25%`（等 advisory
    合入后首个全绿 run）；P-B 备选 = nightly 只归档。共同前提 = thresholds 不放宽。
  - 验证：门单测 9 passed；`-m bench` 31 passed/1 skipped（advisory 关）；
    `PI_BENCH_ADVISORY=1 -m bench` 31 passed/1 skipped + 构造越线用例验证 advisory 生效；
    `-m "not bench"` 913 passed/55 skipped；ruff check+format、pyright 全绿。

- **M3-P1 交付（2026-09-23，分支 ZX466/pi，commit `1d09581`，等收编）**：检索缝预算案 + embed 监控 + baseline 流程（零代码）。
  - `docs/perf/m3-retrieval-budget.md`（新）：实测本机多轮中位——候选生成 numpy 余弦 **0.019ms/NPC**（600 可见）；
    打分链 600 候选×2 钩子 **0.862ms** / 3000 候选 4.91ms / 30000 候选 57.8ms；M3 正常形态（k=20 候选
    + 只打 20 条）≈ **0.05ms/NPC**。红线提案（待裁，随 A4 进 thresholds.py）：`VEC_CANDIDATE_PER_NPC_LIMIT_MS=0.30` /
    `RETRIEVAL_SCORE_PER_NPC_LIMIT_MS=0.30` / `RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS=2.00`（600 全量退化哨兵）/
    `RETRIEVAL_TICK_LIMIT_MS=12.0`。
  - **防呆红线延续反证数据**：每 tick 全量检索 50 NPC = 43.1ms/tick（600 候选）/ 245.5ms/tick（3000）= 破
    16.6ms **2.6x / 14.8x**；每 tick 广播只候选也 1–9.3ms/tick。V5 建议 = 按需为主 + 批量窗口可选
    （窗口一次 2.65ms/50NPC，摊销 2.65/N）。反直觉：50 NPC 批量矩阵比 50 次串行 matvec **慢**（2.65 vs 0.91ms，
    小 n BLAS 开销）——批量优化须先 bench 证伪。
  - `llm-monitoring.md` §7（A6）：`llm.embed_request/response/error/cache_hit` 族 + 字段（batch_size/dim/
    total_tokens/latency_ms/degraded/cache_hit；禁记向量本体与明文）+ 独立阈值（单条 P95<300ms / 批量≤32
    P95<2s / cache_hit>60% / 降级>10%）。chat 族口径零改动。
  - `bench-plan.md` §4.1（裁 4 执行件）：baseline.json 建8 步 + 触发前提 3 条 + 禁令 3 条。
  - `budget.md`：§1.2 指针 + §2.10 新节。
  - 验证：`-m "not bench"` 917 passed + 30 RED（M3-S1 钉子，同 main `db46b9e`）/ 55 skipped；ruff docs 通过。

- **M3-P2（2026-09-23，分支 ZX466/pi，commit `48db6cf`，等收编）**：检索缝四红线 bench 配套。
  - `sim/tests/bench/test_bench_retrieval.py`（新，8 用例）：4 红线 + 3 契约守卫（候选形状 / 治理 JOIN 最小自证 /
    哨兵区分度）+ 1 反模式探针。参考实现 = A4 同语义治理 JOIN（minimal 直建表 + 80 参 IN-JOIN + 4x 过取）。
  - 实测对账（暖态中位）：候选 **0.233ms**/0.30（1.29x，偏紧）；打分 20 候选 **0.057ms**/0.30（5.3x）；
    退化哨兵 600 全量 **0.970ms**/2.00（2.06x）；常态 tick 总量（决策驱动 10 次）**2.9ms**/12.0（4.1x）。
  - **④ 拆两口径**：反模式（50 NPC 广播）= 探测量不设硬断言——实测 **16.8ms = tick 预算 101%**
    （无-JOIN 38.9ms=234% / 全表掩码 131.2ms=790% → 三种实现全破线=防呆论据）。
  - **M3-P1 模型修正**：按纯 numpy 估 50NPC=2.5ms，实测 A4 语义参考 0.29ms/NPC = **低估 6~52x**
    （要回填 m3-retrieval-budget.md §2；结论不变=触发必须决策驱动）。
  - thresholds.py 同步四常量（opencode `caddcdd` 已落同值）。
  - 验证：retrieval 8 passed；`-m bench` 36 passed/1 skipped（2 例首跑抖动、单跑复绿=调度噪声）；
    `-m "not bench"` 948 passed + 3 RED（R2 钉子=A4 未收编 main）/ 55 skipped；ruff+pyright 全绿。
  - baseline.json（M3-P2 ②）**未执行**：nightly 迄今 7 跑全 failure（最新 35816437844 = advisory 门前旧跑）
    → 首个 advisory=1 全绿 run 未出现；等跑出现按 bench-plan §4.1 八步执行。

- **M3-P2② 交付（2026-09-24，分支 ZX466/pi，commit `ee05ab0`，等收编）**：baseline.json 八步执行 + AGENTS.md 清账。
  - runner 5 字段（run 35918283944 artifact 原样）：ubuntu-latest / nproc 4 / **AMD EPYC 7763 64-Core** / py3.12.3 / uv 0.12.18；
    head=main `372153a`，conclusion success。
  - `docs/perf/baseline.json` 入库：21 benchmarks + `machine_info.baseline_meta`（source_run/branch/commit/判据说明）；
    严格可解析 JSON（说明走 meta 字段，不破坏 json.load）。
  - nightly-bench.yml「基线对比」step：echo 提示 → `uv run pytest -q -m bench
    --benchmark-compare=docs/perf/baseline.json --benchmark-compare-fail=median:25%`；yml 仍不复制阈值。
  - **档位观察**：本 run 是 EPYC 7763（上轮 M2-P6② 是 9V74，微软换了机型）→ CI/本机中位比 median **1.71**
    （1.08–1.93，21 项）vs 上轮 1.14。25% 相对参数适用边界 = **跨 run 同档位**比较；档位切换需重新对账
    （已写进 yml 注释 + bench-plan §4.1 step 6 注记）。
  - AGENTS.md 13 行残账随本批提交，工作区干净。
  - 验证：`-m "not bench"` 981 passed/55 skipped；`-m bench` 36 passed/1 skipped；bench ruff+pyright 全绿；
    nightly-bench.yml YAML 解析通过。

## 当前任务

（空——M3-P2 ①② 均已交付，等 Claude 收编；下一步等 M3 批次 A4/embedding 相关派单（A1 定 V3 后 embed 监控事件族由 opencode 客户端照抄 llm-monitoring §7））

## 进行中

（无）

## 留言板

（收编回执见 .orca/talking.txt 留言板）

## ⑥ kilo（接口 / 兼容性域）
- 【2026-09-24 第九轮快照｜M5-K4 全闭环已收编】ws-dispatch-proposal 264 行交付，**裁 12 全采 8.1-8.8**：applied 恒 true 占位 / speed 容忍忽略 / 冲突度归 LLM 域 / load_anchor 同步发快照 / **8.5 handler 增 tile_map 参数＝已裁「改」但未落地**（2026-09-24 复核：`ws.py:189-191` 签名仍为 `(raw, loop, pf)`）/ move_request 只修非法类型 / **8.7 sync_request 回错型列 M5 首修**（sync_request 应回 full_snapshot 而非 control_ack；复核 `ws.py:258-267` 仍回 control_ack）/ error code 小写 snake。**裁 12 ≠ 已施工**：以下均**未落地**——`handle_client_message` 无 `set_control` 分发块（白名单+channel 仅无语义）、`player_impulse`/`load_anchor` 仍未注册（L33/L271 无）。**active 约定**：K3 关键修正=subject 整删 + ext 侧 nullable=0 红线；切源解禁两条件（codegen.md §4.1）=M5 锚点路由落地 + sim 全局 404 声明。**待命**：M5 anchors 施工时按 K3 对表验收 + 8.7 首修 + 8.5 签名变更；另提醒 M5 施工时订正 openapi_ext.py:17「anchors 不施工」与 test ADDED_SCHEMAS 白名单两处 M2-K3 遗留注释。
- 【历史】M2-K2 复核 6 类全采信（切源暂缓，mock 源唯一真相源）；M2-K3 ext↔快照 diff 明细（17 schema 差异表+21 缺失 HTTP schema+nullable oneOf:null 修法）=ext 返工验收清单，返工已完成 K3 复验通过（M5 放行）；M5-K1 anchors 契约稿 306 行（`b849025`）；M5-K2/K3 复验链见 git log。

> ——kilo 树 memory.md（更新于 5f5f525：K04 完成回执 + 跨域发现）——
> 用户规则 #7：本文件保存 **kilo 自己的记忆**，供新对话继续任务。**已入库**（main `3e320b9` 裁决），改动走提交；跨树融合由主导方（Claude）收编时合并（本树本地版 = 权威来源）。
> 新对话开场先读：`.orca/talking.txt`（Claude 派活/回执）→ 本文件 → `.orca/workflow.txt` + `.orca/agent-registry.md`。

## 0. 我是谁 / 在哪

- 能力域：**接口 / 兼容性**（评审 Agent = Claude）。
- 工作树：`E:/zxdevelop/.orca/worktrees/project7/kilo`，分支 `ZX466/kilo`。
- 收编由 Claude 执行；我 **只提交本分支，不自行 push/merge 到 main**；用 `git merge origin/main` 同步。
- 上下文达 50% 时提醒用户切换新对话。

## 1. 项目一句话

临河镇：2D 像素 LLM 模拟世界。设计基线 `DESIGN.md`（v2.1 冻结）。多 agent：Claude 主导/组织（架构·质量·逻辑·测试·前端），cline=依赖/配置/文档，codex=安全/合规/风险，pi=性能，opencode=数据/库，kilo=接口/兼容性。沟通靠各树 `.orca/talking.txt`（本地保存不入库）。

## 2. 我的交付物与命令（接口域）

交付物：`docs/api/{ws-protocol,openapi,codegen,versioning}.md`｜`shared/openapi.json`（协议快照：HTTP+WS+响应 schema）｜`shared/protocol.ts`（openapi-typescript 生成物，**永不手写**）｜`tools/gen-protocol.ts`（生成脚本）｜`client/src/net/protocol.ts`（前端唯一类型入口，re-export+判别联合）｜`client/src/net/__tests__/protocol-types.test.ts`（出戏边界类型断言）｜`client/src/net/settingsApi.ts` + `client/src/ui/SettingsPage.tsx`（K03 设置页）。

命令（在 `client/` 下）：
- 生成：`node ../tools/gen-protocol.ts`（npm 别名 `gen:protocol`，由 cline 配置）
- 漂移校验：`node ../tools/gen-protocol.ts --check`
- 切真实源：`node ../tools/gen-protocol.ts --src http://127.0.0.1:8000/openapi.json`
- 验收组合：`gen-protocol --check` + `npm run typecheck` + `npm run lint` + `npm run test`(vitest) + `npm run build` 全绿才算过。

## 3. 关键约束与坑（裁决已批）

1. **rtoken** 是不透明渲染替身（`rtoken↔内部 id` 映射表留 sim）；前端**只接触 rtoken，绝不接触真实 id**。`entity_id/source_id/tick/seed/seq/branch_id` 绝不进任何对外字段。
2. 信封 `ws_seq` = 传输序号（丢帧/乱序检测），**不是世界 tick**。
3. **出戏边界**：narrative 通道 `content` 必须第一人称、无数值无系统词；`rtoken` 仅 render 通道出现，不进 narrative。
4. sim OpenAPI 地址是 **`/openapi.json`**（FastAPI 默认，**非** `/api/openapi.json`）。
5. **K5 白名单**：profile 响应 = `{id,name,base_url,model,temperature,max_tokens,active,api_key_hint}`，绝不含 `api_key` 明文/`api_key_enc`/`provider`/`params`。
6. **W7 字段最小化**：`monologue` 删 `anchor_ref`，`impulse_feedback` 删 `delay_ms`。
7. sim 启动需环境变量 `LZ_MASTER_KEY`（Fernet key，codex K2；缺失拒绝启动）。开发用临时 key，勿提交。启动：`uv run uvicorn sim.api.main:app --port 8000`。
8. `gen-protocol.ts` 依赖 **Node ≥ 24**（无旗标类型擦除跑 .ts）；调用 `client/node_modules` 内 openapi-typescript/prettier 真实入口。
9. 前端 HTTP 走 vite dev 代理 `/api`→sim:8000（免 CORS）；WS 直连 `ws://127.0.0.1:8000/ws`。vite 在 Windows 上用 `localhost:5173` 访问（`127.0.0.1` 可能连不上）。
10. **⚠ CRLF 假报漂移**：本机 `core.autocrlf=true` 且无 `.gitattributes`，工作副本 CRLF 而生成器写 LF → `--check` 逐字节比对**假报漂移**。代码无问题；用 LF 索引内容复测即在。cline 已建议 Claude 加 `.gitattributes`（`* text=auto eol=lf`）。
11. **⚠ `.orca/memory.md` 被 main 误追踪**（本地文件却进了 git，`344ae3d` 含它）→ 各树同名文件合并必冲突。应对：本地维护我自己的 memory.md、**不提交**；已请 cline `git rm --cached .orca/memory.md` + `.gitignore` 加 `.orca/memory.md`（配置域）。

## 4. 进度（2026-09-20 同步 main `3e320b9`）

- M0 ✅、M1 主体 ✅（C06 全部进 main，~310 passed）。
- 我已完成并收编：TASK-001（协议四文档）→ TASK-002/K01（gen 工具+WS 类型+断言；补 MoveRequestMessage）→ TASK-003/K02（`/api/world/map` chunk + M1 三消息定稿 + settings 契约）→ **TASK-004/K03（设置页前端 + protocol 切真实源；收编 `0f06684` 入 main `344ae3d`）**。
- Claude 已按我回写补齐 sim 缺口（`344ae3d`）：settings 四路由挂 `response_model=ProfileListItem`；`sim/api/openapi_ext.py` 注入 `components.wsMessages`（serverToClient: WsFullSnapshot/WsStateDelta；clientToServer: 白名单 4 消息）。**→ `--src .../openapi.json` 现可全量生成。**

## 5. 当前任务 / 进行中

- **K04（2026-09-21 已派发+接受+交付，已收编 main `8dd8355`）**：
  WS 消息类型全量生成进 `shared/protocol.ts`。核验结论：`shared/protocol.ts` 的 `WsMessage`
  判别联合（14 成员：C→S 5 = player_impulse/set_control/move_request/load_anchor/sync_request；
  S→C 9 = full_snapshot/state_delta/perception/monologue/impulse_feedback/combat_event/
  timescale/control_ack/error）早已生成；`client/src/net/protocol.ts` re-export 齐全；
  `ws.ts` 已用生成类型（仅 `WsStatus`/`WsCallbacks` 手写 = 传输层，非协议）。
  交付：`protocol-types.test.ts` 补 K04 #1/#2（WsMessage['type'] 14 枚举 + 每成员必填
  字段形状 + 五通道判别字面量 + 出戏边界），`docs/api/ws-protocol.md` §3.1 补 `move_request`
  行（快照 `c48358f` 早加但文档漏更的偏差）。
- **⚠ 跨域发现（K04 回执已写 talking.txt；Claude 已收进架构稿 §6，M2-A2 待办）**：
  1. `sim/api/openapi_ext.py` 的 `components.wsMessages` **openapi-typescript 完全不读**（只读
     `components.schemas`）→ 实测 `--src` 指 sim `/openapi.json` 生成 0 个 WS 类型。该注入对
     前端类型源无效。
  2. 且草图本身不完整/不准：只 6 条（缺 §3 清单 9 条：player_impulse/load_anchor/perception/
     monologue/impulse_feedback/combat_event/timescale/control_ack/error）；形状也不对
     （WsStateDelta 缺 `channel`；WsSetControl 用 `controlled` 而非 `action/speed`）。
  3. `hello`/`hello_ack`（W6 鉴权握手，`sim/api/ws.py` 实发）**故意不进协议清单**（安全域），
     快照联合无它们是正确裁决，勿"补齐"。
  4. 结论：`shared/openapi.json` 的 oneOf+discriminator 联合方式是唯一可行前端类型源；要真正
     消除 sim↔前端漂移，需 sim 侧把 §3 清单写进 `components.schemas.WsMessage`（sim 域改动）。
  5. `sim/api/ws.py` 与快照的另一处差：`error` 消息 sim 不发 `ref`（快照 required 含 ref）。
- **M2-K1（2026-09-21 派发+接受，两项）**：
  1. openapi_ext 复核——**等 Claude 改写 `components.schemas.WsMessage` 的通知**再动手；届时
     验 `--src` 全量生成 14 成员 + `--check`。
  2. language.py 叙事边界复核——**已交付**（意见写 talking.txt 留言板 2026-09-21）。要点：
     - 架构稿 §5.2「LanguageProfile 挂 species/阶层 profile」**会误导成物种级**；数据层既定
       `npc_profiles.knowledge_boundary`（0004 迁移 + `models.py:293` + `sim/tests/test_persistence_m2.py:69`
       夹具）= 每角色 JSON `{"literacy","jargon","class_register"}`。DESIGN §229「人类共用一套」
       指感知参数（`PerceptionProfile`）非语言能力。→ 须按角色构造；`species_language` 才是物种级枚举位。
     - 命名待 sim 域定：`register`（架构）vs `class_register`（夹具，倾向后者）；`jargon: set[str]`
       （架构）vs JSON list（夹具，建议 `Sequence[str]`）。
     - 出戏边界 4 红线：降质文案零数值零系统词（架构三条候选已实测过 `banned_words.scan()` 0 命中）；
       `literacy` 只做阈值绝不进文本；降质只动叙事层文本、`Observation`/`PerceptionFrame` 原始数据
       保持完整（M3 知识传播前提）；挂载点应为 `PerceptionFrame.narrated()` 内而非 `Observation` 构造处。
     - 接口域增量：语言降质文本走现有 `perception` 消息 `content`（string），**schema 不变**；
       `species_language`/`class_register` 等判据不出 WS。K04 的 14 成员联合无需改。
- **M2-K2（2026-09-22 派发，复核 59ffd86 openapi_ext 改写 + 接口三查——已交付）**：
  - 结论：**结构骨架对、成员内容简化过度**。14 成员 + oneOf/discriminator 进 components.schemas ✅、wsMessages 废除 ✅、channel 下沉 ✅、error 无 ref ✅、hello/hello_ack 不进联合 ✅（W6 保持）。sim 侧 test_openapi_ext.py 8 用例本机全过，ruff/pyright 干净。
  - **P0**：`--src <sim>/openapi.json` 全量生成 631 行 vs 提交 830 行——缺 21 个快照独有 schema（Actor/MapInfo/MapChunk/WorldMapResponse/Light/LightDelta/Structure/StructureDelta/Weather/CombatInfo/Projectile/Hit/MonologueReaction/AnchorCreate/AnchorListItem/HealthStatus/ProblemDetail 等）。原因：HTTP 路由（/api/world/map、/api/anchors）仍是裸 dict，sim 只给 settings 四路由挂了 response_model。→ **mock 源 shared/openapi.json 仍是唯一可用真相源**，切源前 sim 须补 HTTP response_model。
  - **P1**：ext 的 12 个成员与 ws-protocol.md §3/§4 + 快照形状不一致（逐条见 talking.txt 留言板 2026-09-22）：perception 缺 form、monologue 用 reaction 对象（W7 曾删）、impulse_feedback 缺 injected/cue/reaction_monologue、combat_event 缺 §4.1 六项、timescale 缺 mode/active 且 channel 错写 render、control_ack 缺 action/speed/applied（ws.py 实发就带）、sync_request 缺 reason。
  - **P1**：OpenAPI 3.1 `{"nullable": true}` 是 no-op（openapi-typescript 不产 `| null`）；快照的 `oneOf:[...,{"type":"null"}]` 才是正确写法。preset/subject/attacker/defender/reaction/note 全中招。
  - **接口三查全过**：①WindVector/weather 不进 WS（openapi_ext 无 wind 字段）；②hidden/triggered 不进 WS（只被 gate/memory_scan 消费）；③perception content 仍 string（frame.py Observation.description: str + narrate.py 纯模板函数）。
  - 本机环境坑：PowerShell 捕获 python/node 的 stdout 会丢中文/整段输出——比对 JSON 用 node 写 .cjs 脚本落文件再 Read。起 sim 用 `LZ_MASTER_KEY` 临时值 + uvicorn :8000。
- 其他：等 Claude 派 M2 后续 / TASK-005。

## 6. 留言板 / 待回执

- cline P05：`*.tsbuildinfo` 已加 .gitignore ✅；`_PROTOCOL_VERSION` 与前端 `v` 统一 1.0（并代改了我前端域 `client/src/net/ws.ts` 的硬编码，见 §3.10）；K04 前置就绪。
- 待我：若有 K04 之外的 M2 派发，以 talking.txt 为准。
