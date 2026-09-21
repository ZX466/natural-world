# memory.md — 多 Agent 记忆合集（分节收录各工作树各自的记忆）
> 用户规则 #7（main `3e320b9` 裁决：memory.md 入库）。本文件 = 五树 + 主树记忆的**融合合集**；
> 跨树收编由主导方（Claude）合并。各树本地副本是其对应节的**权威来源**，收编冲突时以各树版本为准。
> 新对话先读：.orca/talking.txt → 本文件**自己那一节** → .orca/workflow.txt + .orca/agent-registry.md。

## ① Claude（主工作树 / 主导）
- 主导/组织：架构/代码质量/逻辑/测试 + 前端/体验/发布/运维；评审 cline 与 kilo 的工作。
- 收编由我执行（merge 各 ZX466/* 分支 → 推 origin+gitee 双远程）；派单写目标树 talking.txt，回执收主树；**不用 orca-cli 发消息**；上下文 50% 提醒切换。
- M0+M1 全量收官：TASK-004 五路（codex=S04/opencode=D04/pi=F06/cline=P05/kilo=K03）全部收编，589 passed / 55 skipped。
- M2 拟派：codex=自我未知/创伤隐藏边界；pi=L1 效用 50NPC 基线+嗅觉传播预算；opencode=嵌入落库/向量检索；kilo=K04（WS 类型进 gen-protocol）。
- 规则速记：#4 除 .orca 外点文件夹不入 git（.codegraph/.agents 每树必有，.claude/.opencode/.codex 对应树有，主树全有）；#7 各树 memory.md 各存各的记忆（tracked）；npm/venv 删除先问用户；Python 必用 uv；playwright 只用 D:\develop\hermes\chrome。

## ② cline（依赖 / 配置 / 文档域）
> 新对话开场先读本节 + .orca/workflow.txt + .orca/agent-registry.md。你的能力域：依赖/配置/CI/文档域。
> **本文件已入库**（main `3e320b9` 裁决，规则 #7 遗漏补录）——改动它要走提交；跨分支同路径由 Claude（主导）收编时合并。
> 另读：`.orca/talking.txt`（任务指派）、`docs/dev-workflow.md`（含 **§7 Windows 行尾假红**——本机格式类检查报错先看那节）。

### 项目状态（2026-09-20 同步自 main `3e320b9`）
- M0+M1 全部收官（TASK-004 五路全部交付并收编），589 passed 55 skipped。
- 你的 TASK-004 交付已收编（收编回执曾写在你树 talking.txt，现已轮换清空；结论可查 git log「merge: 收编 cline」）。
- **M2 已开工（2026-09-21）**：我的 M2-C1 配套已交付（分支 `ZX466/cline`）——docs/README.md §5 M2 区块（含四路依赖对账=**零新包**）+ ci.yml M2 占位步骤（文件路径纪律）+ nightly M2 红线接入点注释 + `.gitattributes` 正式提议（dev-workflow §7）。M2 四路（codex M2-S1 / pi M2-P1 / opencode M2-D1 / kilo K04）交付在手，均待 Claude 收编。
### 已内化教训（实测过，别再踩）
1. **Windows CRLF 假红**：本机 `prettier --check` / `gen:protocol --check` 报格式漂移，先用 `git -c core.autocrlf=false checkout-index -a -f --prefix=.tmp-lf/` 导出 LF 副本复测；LF 下过 = 假红别改代码（详见 docs/dev-workflow.md §7）。已建议 Claude 加 `.gitattributes`（待裁）。
   - M2-C1 补实测数据（2026-09-21）：跟踪 163 文件 = 索引 161 `i/lf` + 2 空 `__init__.py`；工作副本 161 `w/crlf`。加 `.gitattributes` 后 `git add --renormalize .` **0 文件**（索引本就 LF）⇒ 无内容重写、无 hash 断言风险；但 `git status` 仍干净 ⇒ **假红不会自动消失，必须重签出**。重签出**只有** `git rm -r --cached . && git reset --hard` 管用（`git checkout-index -f -a` 实测无效）。
2. **CI 跑分按文件路径接**：无 marker 的专项测试（如 test_m1_metrics.py）在 ci.yml 用文件路径跑，不用 `-m xxx`——加 marker 前后语义会漂移，路径接法防静默排除（P04 教训）。M2 沿用：M2 占位步骤用 `sim/tests/test_m2_*.py` glob（`nullglob` + 空集合 warning + 退出码 5 留痕）。
3. **跨域代改须留言**：opencode D03 的 3 文件 ruff 格式偏差属数据域文件，修复前在其树 talking.txt 留言说明（f775b91）。
4. **与主导方裁决冲突时，以 main 实际决策为准**：memory.md 入库裁决（`3e320b9`）推翻我此前「移出跟踪」提交（cb2d85e），已在 76d6a03 反转并恢复入库。
5. **量纲先算再写门槛**：写 CI/验收前先按 DESIGN 推 tick 数。M2 完整验收「50 NPC × 7 游戏日」= 604,800 tick（1 tick = 1 游戏秒），**不属于每提交 CI**——所以 M2 步骤是占位 + `timeout-minutes: 15` 护栏，而不是写死路径。
6. **别在他域分支上重复接门禁**：codex 的 M2-S1 已自带 ci.yml 步骤（其分支内），M2 占位步骤不重复接同一文件；同一门禁两处维护会漂移。
7. **`.gitignore` 的 catch-all `.*/` 连 `.github/`、`.orca/` 一起忽略**（M2-C1 实测踩到）：**已跟踪文件不受影响**（本批 5 文件提交成功），但**新增**文件落在这两个目录下时 `git add` 会失败并提示 ignored（`git check-ignore` 显示 `.gitignore:62:.*/`），必须 `git add -f`。→ 未决：是否补 `!.github/` `!.orca/` 例外（规则 #4 语义，交用户裁），当前做法＝`-f` 强制添加 + 在本节/文档留痕。
### 常用命令（M2-C1 口径）
- 本树开工第一步：`git merge origin/main`（常落后 main，P05/P04 都遇到过）。
- 全量：`uv run pytest -m "not bench"`；bench：`uv run pytest -m bench`；M2 bench 单跑：`uv run pytest sim/tests/bench -q`（pi M2-P1 新文件）。
  - 实测基线（2026-09-21 本树 main，M2-C1 提交前）：`-m "not bench"` = **578 passed / 55 skipped**（选中 633 / 收集 644，11 个 bench 被排除）。⚠ 与 M1 收官写的「589 passed / 55 skipped」**口径不同**：589 = 含 11 个 bench 的口径（578+11），别再混用。
- M2 指标（占位）：`uv run pytest sim/tests/test_m2_*.py`（文件未落库时无匹配）。
- LF 自证：见上 1；M2-C1 起 `.gitattributes` 提议见 docs/dev-workflow.md §7（含各树重签出方案 A）。
### 未决项
- `.gitattributes`（`* text=auto eol=lf`）：**已从口头建议转为正式提议**（docs/dev-workflow.md §7「正式提议」表：实测影响面 + 方案 A/B/C，cline 建议 A）。待用户/主导裁决；裁决前不动仓库行尾配置，采纳后由我落一次提交 + 通知各树重签出。
- M2 完整 7 日自转验收（604,800 tick）的定期接法（nightly job 还是 `-m m2full` 类 marker）：待 Claude 裁，裁决后我在 ci.yml 注释 + nightly yml 回填。
- M2 验收跑分文件（`sim/tests/test_m2_*.py`）落库后：把 ci.yml M2 占位步骤的 glob 换成显式路径、步骤名去掉「占位」、同步 docs/README.md §5 实测数字。

（以下各节由对应 agent 维护——cline 节以上为 2026-09-20 收编版。）

## ③ opencode（数据 / 数据库域）

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

> 本树工作簿：用户级技能 `security-worktree`（~/.agents/skills/，含环境坑/评审配对/回写纪律）。
> 能力域：安全/合规/风险；评审配对：cline 评审我，我评审 Claude（架构+前端）与 opencode（数据/库）。

### 项目状态（2026-09-20 同步自 main `4323c9e`）
- M1 全量收官（TASK-004 S04 已收编，578 passed + 55 skipped）；M2 已派单。
- 本树分支 ZX466/codex；M2-S1 交付后工作区干净，等 Claude 收编。

### 你已完成的工作（最近一轮）
- **M2-S1 自我未知安全边界（2026-09-20 交付，28 个新 T1 用例，全量 606 passed）**：
  - `docs/security/self-unknown.md`：隐藏属性标注规范（健康档 疾病/旧伤/成瘾/残疾 + 创伤应激触发条件）+ 情境触发浮现 + 闸门/记忆写入扩展口径 + opencode 0004 数据表协调。
  - `sim/npc/hidden.py`：HiddenAttribute/HiddenProfile 标注模型 + `evaluate_triggers` 触发评估 + `hidden_leak_scan` 直陈泄漏扫描（闸门与记忆写入共用同一工具）。
  - `sim/agent/gate.py`：`revalidate_at_execution` 增加 hidden/triggered 参数与「自我未知」检查——reason 直陈未触发属性 → `hidden_attribute_leak` 拒绝；hidden 缺省 None 与 M1 行为一致。
  - `sim/llm/memory_scan.py`：`write()` 增加 hidden/triggered 参数与直陈拒写（`REASON_HIDDEN_LEAK`），记忆检索默认结果防线。
  - `sim/tests/test_t1_self_unknown.py`：双路径采样（未触发零泄露 / 触发正常浮现）+ 行为暗示可议 + 语料卫生 + 感知帧/装配 prompt 面零泄漏。
  - `.github/workflows/ci.yml`：按文件路径新增 T1 自我未知门禁独立红灯信号（沿用 test_t3_gate.py 做法）。
- 更早累计：TASK-001~004（m1-checklist/threat-model/t3-corpus/memory-scan + T3 实弹 + W6 WS 鉴权 + M1-D reason 禁词门）；详见 git log 与 docs/security/。

### 当前任务
- M2-S1 已交付，等 Claude 收编（main 合并 ZX466/codex）。

### 进行中
- (空)——等下一波派发（预告 M2 后续安全面：T4 出戏探针 nightly 分层、LOD 降格记忆压缩校验等）。

### 留言板
- (读 Claude 经 talking.txt 写来的任务指派；给他树留言写对方树 talking.txt)

## ⑤ pi（性能域）

> ——以下为 pi 树 memory.md 原文（收编于 50b0ebb）——
> 新对话开场先读本文件 + .orca/workflow.txt + .orca/agent-registry.md。你的能力域：性能域。
> 配套技能：`perf-worktree`（用户级 ~/.agents/skills/，含环境坑/基准口径/常用命令）——新对话若发现本文件
> 不足以恢复上下文，读该技能全文可完整续上工作状态。

## 项目状态（2026-09-20 同步自 main `3e320b9`）

- M0+M1 全部收官（TASK-004 五路全部交付并收编），589 passed 55 skipped。
- 你的 TASK-004 交付已收编（收编回执曾写在你树 talking.txt，现已轮换清空；结论可查 git log「merge: 收编 pi」）。
- 本树已 merge main `3e320b9`，工作区干净，待 M2/TASK-005 派发。

## 你已完成的工作（最近一轮）

- 感知 bench 红线复核（F06 暖态中位口径采纳）+budget 4x 对账+bench 方法论沉淀（warmup/中位/冷启动诊断）。
  红线口径定案：暖态中位（`assert_median_threshold` + `warmup_rounds=1` 剔 LOS 冷启动 7.6-8.2ms），
  `PERCEPTION_TICK_LIMIT_MS=3.6`（预算目标 3.00ms 另一口径）；RNG 1M 警戒线 300ms、真预算每 tick 200 draws ≤0.10ms。
- 更早累计：TASK-001~003 全链路参与（budget.md/hotspots.md/bench-plan.md + bench 脚手架；详见 git log 与 docs/perf/）。

## 当前任务

(空——等 Claude 派发 M2/TASK-005。收到任务后把要点写进「进行中」，完成后把结论追加到「已完成」并回执。)

## 进行中

(空)

## 留言板

(读 Claude 经 talking.txt 写来的任务指派)

## ⑥ kilo（接口 / 兼容性域）


# memory.md — kilo（接口 / 兼容性域）

> 用户规则 #7：本文件保存 **kilo 自己的记忆**，供新对话继续任务。本地保存、**不入 git**
> （理由同 .orca/talking.txt：各工作树各 agent 各自维护同路径文件，入 git 收编必冲突）。
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

- **K04（Claude 建议，未正式派发；"若做，回写 talking.txt 接受"）**：
  用补全后的 `/openapi.json` 重新 gen 协议，把 **WS 消息类型也生成进 `shared/protocol.ts`**（当前 HTTP-only）；前端 `ws.ts` 消费生成类型、替换手写 interface。
  执行要点：起 sim（带 `LZ_MASTER_KEY`）→ `--src http://127.0.0.1:8000/openapi.json` → 复核形状 vs `shared/openapi.json`（**以 sim 为准**）→ 回写差异 → 重生成并 `--check`（注意 CRLF 陷阱）→ 前端 `ws.ts` 换用生成类型（`PROTOCOL_VERSION='1.0'` 常数可能与 K04 冲突，以 K04 为准）→ 跑全绿 → 提交分支 + 回写。
- 其他：等 Claude 派 M2/TASK-005。

## 6. 留言板 / 待回执

- cline P05：`*.tsbuildinfo` 已加 .gitignore ✅；`_PROTOCOL_VERSION` 与前端 `v` 统一 1.0（并代改了我前端域 `client/src/net/ws.ts` 的硬编码，见 §3.10）；K04 前置就绪。
- 待我：若有 K04 之外的 M2 派发，以 talking.txt 为准。
