# 开发流程（docs/dev-workflow.md）

> 能力域：依赖 / 配置 / 文档（cline）。本文只讲「怎么跑」，讲「为什么」看 `DESIGN.md`。
> 环境硬约束：Python 一律用 **uv** 建虚拟环境；playwright 调浏览器只用 `D:\develop\hermes\chrome`；
> **删除 npm 包或 venv 前必须先问用户**；除 `.orca` 外 `.` 开头目录不入 git。

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

### bench 跑法（性能域）

```bash
uv run pytest -m bench                                   # 跑基准（pytest-benchmark）
uv run pytest -m bench --benchmark-json=perf/bench.json   # 出基线文件
uv run pytest -m bench --benchmark-compare=perf/baseline.json --benchmark-compare-fail=median:20%
```

- GitHub 上由 `.github/workflows/nightly-bench.yml` 每天 02:00（北京）自动跑并归档机器档位 + 结果 JSON。
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
- 提交身份：`ZX666X <zx19836980213@outlook.com>`（全局已配）；推送双远程 `git push origin <branch>` + `git push gitee <branch>`（GitHub 走 `127.0.0.1:7897`）。
