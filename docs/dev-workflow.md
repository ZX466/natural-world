# 开发流程（docs/dev-workflow.md）

> 能力域：依赖 / 配置 / 文档（cline）。本文只讲「怎么跑」，讲「为什么」看 `DESIGN.md`。
> 环境硬约束：Python 一律用 **uv** 建虚拟环境；playwright 调浏览器只用 `D:\develop\hermes\chrome`；
> **删除 npm 包或 venv 前必须先问用户**；agent 配置目录（`.agent/.agents/.claude/.codex/.kiro/.opencode/.codegraph`）
> **不入 git 也不推送，但本地须存在**（用户规则 #4：所有工作树都要有 `.codegraph`+`.agents`，
> `.claude/.opencode/.codex` 只在对应工作树，主树全有）；`.orca` 例外——`workflow.txt`/`agent-registry.md`/
> `memory.md` 入库（main `3e320b9` 裁决），仅 `talking.txt` 本地保存。

## 1. 环境与一次初始化

```bash
uv sync                 # 建 .venv 并按 uv.lock 安装（首次 / 依赖变更后）
uv sync --frozen        # CI 式：严格按锁文件，不解析新版本
uv lock --check         # 校验 uv.lock 与 pyproject.toml 一致
```

- Python 版本由 `.python-version` 固定（3.12）；解释器由 uv 管理，不依赖系统 Python。
- 前端（Node ≥ 20，本地实测 v24）：

```bash
cd client
npm ci                  # 按 package-lock.json 精确安装（首次或 lock 变更后）
npm install <pkg>       # 新增依赖后请提交 package-lock.json
```

- 前端依赖锁定：`client/package-lock.json` 入库；`node_modules/` 与 `.venv/` 均被 .gitignore 排除。

## 2. 每提交必跑（本地 = CI 同款）

| 检查 | 本地命令 | CI 步骤 |
|---|---|---|
| 锁文件 | `uv lock --check` | Python job |
| Lint | `uv run ruff check` | Python job |
| 格式 | `uv run ruff format --check` | Python job |
| 类型（Python） | `uv run pyright` | Python job |
| 测试 | `uv run pytest -m "not bench"` | Python job |
| 类型（TS） | `cd client && npx tsc --noEmit` | Frontend job |
| Lint（TS） | `cd client && npx eslint .` | Frontend job |
| 格式（TS） | `cd client && npx prettier --check .` | Frontend job |
| 测试（TS） | `cd client && npx vitest run --passWithNoTests` | Frontend job |

一键本地全跑（PowerShell，失败即停）：

```powershell
uv lock --check; uv run ruff check; uv run ruff format --check; uv run pyright; uv run pytest -q -m "not bench"
Push-Location client; npx tsc --noEmit; npx eslint .; npx prettier --check .; npx vitest run --passWithNoTests; Pop-Location
```

## 3. 测试分级怎么跑（DESIGN §16）

| 级 | 跑什么 | 命令 | 频率 |
|---|---|---|---|
| T1 | 六类不变量断言（无 LLM，秒级） | `uv run pytest -m t1` | 每次提交（CI 含） |
| T2 | 回放确定性（无 LLM） | `uv run pytest -m t2` | 每次提交（CI 含） |
| T3 | 闸门对抗样本（录制 fixture，codex S03-3；**无 marker，按文件选**） | `uv run pytest sim/tests/test_t3_gate.py` | 每次提交（随 `-m "not bench"` 全量跑；ci.yml 另有命名独立门禁步骤，已实跑 45 passed） |
| T4 | 出戏探针（真模型，烧钱） | nightly（无 CI 门禁） | 每日，锁定模型版本 |
| T5 | golden 场景（10 种子 × 10 游戏日） | `uv run pytest -m t5` | 每日 |
| bench | 性能基准 | `uv run pytest -m bench` | **nightly，不进每提交 CI** |

- CI 里 pytest 一律带 `-m "not bench"`：性能基准抖动大，放进来只会把 CI 变成红灯制造机（`docs/perf/bench-plan.md` §0）。
- marker 在 `pytest.ini` 注册，`--strict-markers` 生效：写测试必须带正确 marker，拼错会直接失败。
- **M1 指标跑分**（`sim/tests/test_m1_metrics.py`：差事完成率 / 链路 P95 / 单决策 tok / T3 出戏，假 LLM 零网络，纯 T1 秒级）：本已随 `-m "not bench"` 全量跑，ci.yml 另有命名步骤「pytest M1 指标跑分」——两个命名门禁步骤（T3 对抗、M1 指标）都按**文件路径**选择，不用 marker，以免 marker/addopts 变化把门禁静默排除成假绿灯。实测数字见 `docs/README.md` §4。
- **M2 指标跑分（占位，M2-C1）**：ci.yml 已有命名步骤「pytest M2 指标跑分（占位）」——按**文件路径** glob `sim/tests/test_m2_*.py` 选择（纪律与 T3/M1 同源）。文件未落库时只 `::warning::` 留痕、不假绿；落库即自动生效。
  - 命名约定：M2 的 CI 级验收测试落 `sim/tests/test_m2_*.py`，**无 LLM、秒级~分钟级**；步骤内显式 `-m "not bench"`（性能红线是抖动域，属 nightly）。
  - ⚠ **不要**把完整验收「50 NPC × 7 游戏日自转无崩溃」做成 `sim/tests` 下无 marker 的普通测试：DESIGN §10「1 tick = 1 游戏秒」⇒ 7 游戏日 = **604,800 tick**，它会被 `-m "not bench"` 全量 CI 收集，把每提交 CI 拖成小时级（ci.yml 该步骤的 `timeout-minutes: 15` 就是这道护栏）。完整跑接 `nightly-bench.yml`（接法待 Claude 裁）。
  - M2 四路依赖对账与交付盘点见 `docs/README.md` §5。

### bench 跑法（性能域）

```bash
uv run pytest -m bench                                   # 跑基准（pytest-benchmark）
uv run pytest -m bench --benchmark-json=perf/bench.json   # 出基线文件
uv run pytest -m bench --benchmark-compare=perf/baseline.json --benchmark-compare-fail=median:20%
```

- GitHub 上由 `.github/workflows/nightly-bench.yml` 每天 02:00（北京）自动跑并归档机器档位 + 结果 JSON。
- M2 新增 bench（pi M2-P1）：`sim/tests/bench/test_bench_l1_utility.py` / `test_bench_smell.py`，随 `-m bench` 自动纳入 nightly，**无需改 yml**；红线常量集中在 `sim/tests/bench/thresholds.py`（单一真相源，别在 yml 或文档里抄数值）。
- 阈值与机器档位口径见 `docs/perf/budget.md` §1 与 `docs/perf/bench-plan.md` §3；跨机器不要直接比绝对值。
- 所有 bench 必须固定 seed（C5：禁 `random.*`，ruff banned-api 会拦）。

## 4. 协议类型生成（接口域）

```bash
npm run gen:protocol         # 生成 shared/protocol.ts（banner + prettier 已含）
npm run gen:protocol:check   # 漂移检测：生成到临时文件比对，不一致则非零退出（已接进 ci.yml）
```

- 真相源是 sim 端 pydantic 模型；`shared/protocol.ts` **只读、不手写**（DESIGN §19）。
- 脚本本体 `tools/gen-protocol.ts` 由接口域（kilo）维护；M0 阶段源为手写 mock `shared/openapi.json`，sim 起服务后切真实导出（切换点见 `docs/api/codegen.md`）。
- **要求 Node ≥ 24**：脚本以 `node` 直接运行 `.ts`（无旗标类型剥离；`engines` 与 CI 的 setup-node 均已对齐）。
- 前端引用一律走 `@shared/protocol`（ESLint 已禁相对路径引 `shared/`）。

## 5. 密钥与本地配置

- 复制 `.env.example` → `.env` 后填写；`.env` 不入 git，`.env.example` 只含键名（安全清单 G4）。
- `LZ_MASTER_KEY`（Fernet 主密钥）缺失时后端必须拒绝启动（安全清单 K2），禁止静默生成落盘。
- 任何情况下不要把 key、token、日志文件、数据库文件提交进仓库（`.gitignore` 已排除 `*.log` / `*.db` / `*.sqlite`）。

## 6. 提交与协作

- Conventional Commits：`feat|fix|refactor|docs|test|chore|perf|ci`。
- 每个 agent 只在自己的工作树改自己能力域的东西；跨域需求走 `.orca/talking.txt` 间接留言。
- **新增文件落点注意（M2-C1 实测，2026-09-21）**：`.gitignore` 的 catch-all `.*/`（用户规则 #4）会把 `.github/`、`.orca/` 目录一起标为 ignored —— **已跟踪文件不受影响**（改 ci.yml / memory.md 正常），但在这两个目录下**新增**文件时 `git add` 会失败并提示 ignored，需 `git add -f`（例：`git add -f .github/workflows/<新 yml>`）。**未决**：是否补 `!.github/` `!.orca/` 例外，交用户裁；裁定前按 `-f` 走。
- 提交身份：`ZX666X <zx19836980213@outlook.com>`（全局已配）；推送双远程 `git push origin <branch>` + `git push gitee <branch>`（GitHub 走 `127.0.0.1:7897`）。

## 7. 本机检查陷阱：Windows 行尾（CRLF）假红

> 2026-09-20（cline P05）实测记录。**Windows 上跑本机检查前先读本节**——否则会把假红当真红去改代码，或反过来放过真红。

- **成因**：仓库 `core.autocrlf=true` 且**无 `.gitattributes`** → 检出后工作副本是 CRLF，而 git 索引与 CI（ubuntu）是 LF。
- **典型假红（LF 内容下实际全过，不要改代码）**：
  - `cd client && npx prettier --check .` —— 一次报了 17 个文件「code style issues found」；
  - `node tools/gen-protocol.ts --check` —— 报「生成物与提交不一致」（生成器写 LF、工作副本 CRLF，逐字节比对必然不等）。
- **典型真红（LF 内容下同样失败，必须修）**：`uv run ruff format --check` —— ruff 给的是**内容级**建议（拆行 / 合并行 / 去 BOM），与行尾无关。P05 实测：opencode D03 的 3 个文件就是这样漏过门禁的真红。

**自证办法**（导出 git 索引的 LF 内容再跑检查，一步定性，不必猜）：

```bash
git -c core.autocrlf=false checkout-index -a -f --prefix=.tmp-lf/   # 整仓 LF 副本
uv run ruff format --check .tmp-lf                                   # Python 侧
cd client && npx prettier --check ../.tmp-lf/client                  # TS 侧（配置按文件路径解析，仍读 client/.prettierrc）
rm -rf .tmp-lf                                                       # 用完即删（否则显示为未跟踪）
```

- LF 副本下**仍失败** ⇒ 真红，改代码；LF 副本下**通过** ⇒ 本机行尾假阳性，**不要改代码**。
- `gen:protocol --check` 的假阳性也可用 `node tools/gen-protocol.ts` 重生成消除——内容与提交一致时 `git diff` 为空，**不会产生提交**。
- 同理：`git status` 偶尔把内容未变的文件显示为 ` M`（mtime/stat 缓存假象）。用 `git hash-object <f>` 与 `git rev-parse :<f>` 对比，相同即无实际改动。

**M2-C1 正式提议（2026-09-21，cline）——待裁，未擅自实施**：加 `.gitattributes` 可让本机检查与 CI 逐字节一致。**影响面已实测**（下表），提案放行后由 cline 在 main 落一次提交、各工作树配合重签出。

### 正式提议：新增 `.gitattributes`（`* text=auto eol=lf`）

**提议内容**：仓库根新增 `.gitattributes`，内容一行 —— `* text=auto eol=lf`（索引与工作副本统一 LF）。当前仓库无 `.bat`/`.ps1` 等必须 CRLF 的文件，故无需 `eol=crlf` 例外（日后新增再补一行）。

**实测影响面**（2026-09-21，cline 本机；探针副本置于 `%TEMP%`，**未改动本仓**）：

| 项 | 实测值 | 说明 |
|---|---|---|
| 跟踪文件总数 | 163（161 `i/lf` + 2 空 `__init__.py` 为 `i/none`） | 索引**本来就是 LF**；无 `-text`（二进制）条目 ⇒ 不需要 `binary` 规则 |
| 工作副本现状 | 161 个 `w/crlf` | 假红根因确证（`core.autocrlf=true` + 无属性文件） |
| **索引重写量** | **0 文件**（`git add --renormalize .` 后暂存区为空） | ⇒ **不需要 renormalize 提交、不产生大 diff、不改变任何被 hash/逐字节断言的产物**（现有 sha256 用途全是内存字符串：rng 种子、rtoken、prompt 指纹、state hash） |
| 加属性后 `git status` | 干净 | clean 过滤器把 CRLF 归一化后再比对 ⇒ **假红不会自动消失**，必须一次性重签出（最关键的一条） |
| 重签出方案 A：`git rm -r --cached . && git reset --hard` | 161 文件 `w/crlf` → `w/lf`，`git status` 干净 ✅ | 各树执行一次、秒级；**会丢弃未提交改动 ⇒ 先提交/暂存**；未跟踪文件不受影响 |
| 重签出方案 B：`git checkout-index -f -a` | **无效**（仍 `w/crlf`） | 实测否掉，别再试 |

**收益**：本机 `npx prettier --check .`、`node tools/gen-protocol.ts --check` 的 CRLF 假红消失（与 ubuntu CI 逐字节一致），本节的自证流程（`.tmp-lf/` 导出）日常不再需要；`uv run ruff format --check` 仍是**内容级真红**判据，行为不变。

**代价 / 风险**：六树 + 主树各执行一次方案 A 重签出（需先提交/暂存，避免丢工作）；索引零变化 ⇒ 撤销极简（删掉该文件 + 再重签出一次）；对本机 `core.autocrlf=true` 的既有配置无冲突（`eol=lf` 属性优先）。

**裁决选项**：

- **A（cline 建议采纳）**：加 `.gitattributes`（`* text=auto eol=lf`）。执行链：cline 在 main 落一次提交（`chore(config): 加 .gitattributes 统一 LF`）→ 各树 `git merge origin/main` 后跑一次方案 A → 回执写各树 `.orca/talking.txt`。
- B：不加文件，各树本地 `git config core.autocrlf false`（`--local`）。只治本机、不入库；新克隆/新 agent 仍会复现假红，且六树要各配一次（不推荐）。
- C：维持现状 + 本节自证流程。零风险，但每次格式类检查都要多一步手工，新 agent 必踩（已有 P05/O2 两次踩坑记录）。

**裁决记录**：`待裁`（影响面跨六树重签出，按用户要求交用户/主导裁决）。裁决前 cline 不动仓库行尾配置；若采纳选项 A，本节的成因段与自证流程一并改为「历史记录」。


