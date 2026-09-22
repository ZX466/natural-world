
# memory.md — 多 Agent 记忆合集（分节收录各工作树各自的记忆）
> 用户规则 #7（main `3e320b9` 裁决：memory.md 入库）。本文件 = 五树 + 主树记忆的**融合合集**；
> 跨树收编由主导方（Claude）合并。各树本地副本是其对应节的**权威来源**，收编冲突时以各树版本为准。
> 新对话先读：.orca/talking.txt → 本文件**自己那一节** → .orca/workflow.txt + .orca/agent-registry.md。

## ① Claude（主工作树 / 主导）
- 主导/组织：架构/代码质量/逻辑/测试 + 前端/体验/发布/运维；评审 cline 与 kilo 的工作。
- 收编由我执行（merge 各 ZX466/* 分支 → 推 origin+gitee 双远程）；派单写目标树 talking.txt，回执收主树；**不用 orca-cli 发消息**；上下文 50% 提醒切换。
- M0+M1 全量收官（TASK-004 五路收编）；M2 三轮全部收编：
  - 第一轮（`8dd8355`：C1/S1/D1/P1/K04）+ 架构稿 M2-A1（`3ab8c71`）+ 两配置裁决。
  - 第二轮（`c49b0b3`：C2/S2/D2/P2/K1，724 passed）+ 三裁决：nightly 完整跑=方案 A / language 挂载点=narrated() 通道分组输出前 / `.orca/` 例外暂不补。
  - 我 A2 第二批（`59ffd86`，768）：schedule/utility/runtime 向量化 + MatterLedger + SmellField + openapi_ext WsMessage 14 成员进 components.schemas。
  - README §5 P0 冲突标记修复（`cbf40ee`，cline C3 揪出）。
  - 第三轮（`7d63210`：S3 安评通过/D3 检索缝+event_validation/materialize_hidden/P3 l1-spec+L1 feeder+p99 信息性守护，805 passed）。
  - kilo K2 复核 6 类问题全采信：**裁决=切源暂缓，mock 源仍唯一真相源**（P0=切源丢 21 HTTP schema；P1=ext 成员需按快照对齐+nullable 3.1 写法）。
- **第四轮已派**（cline C4 切源暂缓落档/codex S4 T1 10k 采样/kilo K3 ext↔快照 diff 明细/opencode D4 matter 投影对账/pi P4 预算预案）；**我 A2 第三批开工序**：smell 接线感知步 → NpcRuntime 接 NpcStore 落库 + HiddenState 每 tick → cognition 六偏差骨架 → openapi_ext 对齐快照返工 → language.py。
- 进度：MVP ≈97%（M0✅ M1✅ M2≈90%）；全项目 ≈55%（M3-M6 各约 1×M2）。
- 规则速记：#4 除 .orca 外点文件夹不入 git；#7 各树 memory.md 各存各的记忆（tracked，收编分节融合，各树本地版权威）；npm/venv 删除先问用户；Python 必用 uv；playwright 只用 D:\develop\hermes\chrome。

## ② cline（依赖 / 配置 / 文档域）
> 新对话开场先读本节 + .orca/workflow.txt + .orca/agent-registry.md。你的能力域：依赖/配置/CI/文档域。
> **本文件已入库**（main `3e320b9` 裁决，规则 #7 遗漏补录）——改动它要走提交；跨分支同路径由 Claude（主导）收编时合并。
> 另读：`.orca/talking.txt`（任务指派）、`docs/dev-workflow.md`（含 **§7 Windows 行尾假红**——本机格式类检查报错先看那节）。

### 项目状态（2026-09-20 同步自 main `3e320b9`）
- M0+M1 全部收官（TASK-004 五路全部交付并收编），589 passed 55 skipped。
- 你的 TASK-004 交付已收编（收编回执曾写在你树 talking.txt，现已轮换清空；结论可查 git log「merge: 收编 cline」）。
- **M2 已开工（2026-09-21）**：M2-C1 配套已收编（main `19e3a88`）；**M2-C2 已交付**（分支 `ZX466/cline`）——`sim/world/weather.py` 风场（纯函数可重放 + 每日天气注入点）+ `sim/tests/test_m2_weather.py`（31 用例）+ ci.yml M2 命名步骤填实 + dev-workflow §7 重签出操作手册 + **六树重签出已执行**。
- M2 进展：第一轮四路（codex M2-S1 / pi M2-P1 / opencode M2-D1 / kilo K04）+ Claude M2-A1 架构稿 / M2-A2 第一批全部收编；第二轮在途（我＝风场+重签出，其余见主树 talking.txt）。
### 已内化教训（实测过，别再踩）
1. **Windows CRLF 假红**（根因已消除）：`.gitattributes`（`* text=auto eol=lf`）已裁决落地（main `3ab8c71`），各树一次性重签出后 161 个 `w/crlf` → `w/lf`，本机 `prettier --check` / `gen:protocol --check` 不再假红。**自检一条命令**：`git ls-files --eol | grep -c 'w/crlf'` 期望 0（>0 = 该树没重签出）。重签出**只有** `git rm -r --cached . && git reset --hard` 管用（`git checkout-index -f -a` 实测无效；先 commit/stash，未跟踪文件不受影响）。操作手册在 `docs/dev-workflow.md` §7。
   - M2-C2 六树实测（2026-09-21，仅对**干净树**执行）：`w/crlf` main 115 / cline 158 / codex 159 / pi 150 / opencode 151 / kilo 151 → **全 0**；重签出后 `npx prettier --check .`（"All matched files use Prettier code style!"）与 `gen-protocol --check` 均 EXIT 0 —— P05 时代的假红确认消失。
2. **CI 跑分按文件路径接**：无 marker 的专项测试（如 test_m1_metrics.py）在 ci.yml 用文件路径跑，不用 `-m xxx`——加 marker 前后语义会漂移，路径接法防静默排除（P04 教训）。M2 沿用：M2 占位步骤用 `sim/tests/test_m2_*.py` glob（`nullglob` + 空集合 warning + 退出码 5 留痕）。
3. **跨域代改须留言**：opencode D03 的 3 文件 ruff 格式偏差属数据域文件，修复前在其树 talking.txt 留言说明（f775b91）。
4. **与主导方裁决冲突时，以 main 实际决策为准**：memory.md 入库裁决（`3e320b9`）推翻我此前「移出跟踪」提交（cb2d85e），已在 76d6a03 反转并恢复入库。
5. **量纲先算再写门槛**：写 CI/验收前先按 DESIGN 推 tick 数。M2 完整验收「50 NPC × 7 游戏日」= 604,800 tick（1 tick = 1 游戏秒），**不属于每提交 CI**——所以 M2 步骤是占位 + `timeout-minutes: 15` 护栏，而不是写死路径。
6. **别在他域分支上重复接门禁**：codex 的 M2-S1 已自带 ci.yml 步骤（其分支内），M2 占位步骤不重复接同一文件；同一门禁两处维护会漂移。
7. **`.gitignore` 的 catch-all `.*/` 会挡住 `.github/`、`.orca/` 下的新增文件**：已跟踪文件不受影响（改 ci.yml / memory.md 正常），但**新增**文件 `git add` 会失败并提示 ignored，须 `git add -f`。**已裁决部分**：`.github/` 补了例外（`!.github/` + `!.github/**`，main `3ab8c71`，新增 workflow 现在可正常 `git add`）；**`.orca/` 未补**：`.orca/` 下新增文件继续用 `git add -f`（要改规则得再请裁——它属用户规则 #4 语义）。
8. **纯函数优先于「推进式 RNG」**：`sim/world/weather.py` 若用 `RngRegistry.generator(name, cache)` 抽签就会**推进状态**（调用顺序影响结果，回放/bench 不可重算）。正解＝从 `rng.draw_key(流名)`（材料指纹，含熵注入）派生档位种子 → 每次新建 `Generator` 抽，得到「同 (rng, tick) 恒同风」。写任何「按 tick 派生的物理量」都照此办。
### 常用命令（M2-C2 口径）
- 本树开工第一步：`git merge origin/main`（常落后 main，P05/P04 都遇到过）。
- 全量：`uv run pytest -m "not bench"`；bench：`uv run pytest -m bench`；M2 bench 单跑：`uv run pytest sim/tests/bench -q`（pi M2-P1 新文件）。
  - 实测基线（2026-09-21 本树 main，M2-C1 提交前）：`-m "not bench"` = **578 passed / 55 skipped**（选中 633 / 收集 644，11 个 bench 被排除）。⚠ 与 M1 收官写的「589 passed / 55 skipped」**口径不同**：589 = 含 11 个 bench 的口径（578+11），别再混用。
- M2 验收测试（命名门禁，ci.yml 按 `sim/tests/test_m2_*.py` 全量接）：`uv run pytest sim/tests/test_m2_*.py`；我的文件＝`sim/tests/test_m2_weather.py`。
- 风场自洽检查（纯函数）：`wind_at(tick, RngRegistry(world_seed=42))` 反复调用结果相同；`daily_reseed_due(tick)` 为真时由世界循环做 `EntropyMixer.mix("world.weather", tick)`。
- 行尾自检（重签出后应为 0）：`git ls-files --eol | grep -c 'w/crlf'`。
### 未决项
- M2 完整 7 日自转验收（604,800 tick）的定期接法（nightly job 还是 `-m m2full` 类 marker）：待 Claude 裁，裁决后我在 ci.yml 注释 + nightly yml 回填。
- `.orca/` 下新增文件仍被 `.*/` 兜底挡（需 `add -f`）：是否补 `!.orca/` 例外待裁（规则 #4 语义）；`.github/` 已补。
- M2 第二轮：风场已交付；`smell.py`（消费我的 `wind_at`）、matter、language 属他域，等收编后我复核 CI/文档口径（G-5 类收编后校验）。

（以下各节由对应 agent 维护——cline 节以上为 2026-09-20 收编版。）

## ③ opencode（数据 / 数据库域）
- 【2026-09-22 第四轮快照】M2-D3 已收编（`4a11d0f`）。**M2-D4 已交付待收编分支 `3853ceb`**（docs 型、零 schema 改动）：①对账表 `docs/data/schema.md §17`——三方全表 + **唯一硬缺口 `decay_rate` 无事件承载**（投影硬编码 0.0 破坏 §14 回放）+ 方案 A/B/C；②契约文档 `sim/npc/memory.py` docstring 扩写（输入输出/公式/Scorer 注入点/M3 npc_memory_vec 边界/读侧 guardrail）+ `schema.md §18`；③`test_m2_matter_projection.py`（integrity+is_rubble 对账锁定 6 passed，decay_rate 缺口 xfail 占位）；④alembic 零漂移自检通过（无 0005）。**待 Claude 裁决方案 A 才动 events.py/matter.py/npc_store.py**（改冻结事件基线）。任务单=本树 talking.txt。

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

(空 —— 等 Claude 经 `.orca/talking.txt` 派发下一单，预计 TASK-005 / M2 相关。)

## 进行中

(空)

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
- 【2026-09-22 第四轮快照】M2-P3 已收编（`1e3e36e`：l1-spec.md 对账 + L1 feeder 两阶段接线 + p99 硬门禁改信息性守护）。**M2-P4 已交付**（`docs/perf/m2-p4-budget-preplan.md`，`82efcc2`，等收编裁决）：① smell 接线预算拆表——`SmellField.inject` 逐源 np.clip Python 循环是全场最大头（50 源 0.330ms，占场推进 73%；`np.add.at` 0.0024ms ≈140x，语义等价，交架构域改），场推进 50 源 0.451ms、100 源 0.976ms → 新增 `SMELL_WIRED_TICK_LIMIT_MS=1.0` 一行，旧 0.15 保留改注释为「纯网格 K=20 口径」；smell 净增 0.68ms/感知步（挖空对照 1.58 vs 0.90ms）→ ≈0.34ms/tick，M2-P2 稳态 1.9→2.25ms/tick 仍 ≪8.3ms 回归线。② flush 不进 tick 断言三件套（探针零触发 + 计时器注入 + flush/tick 分开累计；实测 flush_tick 50 条 内存库 2.6ms/文件库 7.8ms，帧级警戒 20ms）。③ cognition：检索缝两钩子净增 0.054ms/次检索 → 上界 0.15ms；效用缝四偏差 0.0004ms/NPC → 0.01ms/NPC 上界；HiddenState.evaluate（50×3 属性）0.10ms/tick → 0.30ms 上界；合计增量 ≤0.20ms/tick 进 L1 行不新增行。旧任务单详情=本树 talking.txt（已回执）。

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

## 当前任务

（空——M2-P4 已交付，等 Claude 收编裁决；预案未被收编前不改 thresholds.py/budget.md 正文）

## 进行中

（无）

## 留言板

（收编回执见 .orca/talking.txt 留言板）

## ⑥ kilo（接口 / 兼容性域）

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
- 其他：等 Claude 派 M2 后续 / TASK-005。

## 6. 留言板 / 待回执

- cline P05：`*.tsbuildinfo` 已加 .gitignore ✅；`_PROTOCOL_VERSION` 与前端 `v` 统一 1.0（并代改了我前端域 `client/src/net/ws.ts` 的硬编码，见 §3.10）；K04 前置就绪。
- 待我：若有 K04 之外的 M2 派发，以 talking.txt 为准。
