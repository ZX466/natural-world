# 开发流程

> 本文只讲「怎么跑」；「为什么」看 `DESIGN.md`。
>
> 环境硬约束：Python 一律用 **uv** 建虚拟环境；**只有用户明确要求时才用浏览器自动化/渲染验证**，
> Playwright 只用 `C:\Users\zx198\AppData\Local\ms-playwright` 内的浏览器，不干扰用户自己的浏览器；
> **删除 npm 包或 venv 前必须先问用户**；agent 配置目录（`.agent/.agents/.claude/.codex/.kiro/.opencode/.codegraph`）
> 不入 git 也不推送，但本地须存在（`.codegraph`、`.agents` 所有工作树都有；`.claude/.opencode/.codex`
> 只在对应 agent 树；`.pi` 当前不创建，按需再补）。`.orca` 例外：`workflow.txt` / `agent-registry.md` /
> `memory.md` 入库，`talking.txt` 与 `archive/` 本地保存。

## 1. 环境与初始化

```bash
uv sync                 # 建 .venv 并按 uv.lock 安装
uv sync --frozen        # CI 式：严格按锁文件
uv lock --check         # 校验 uv.lock 与 pyproject.toml 一致

cd client
npm ci                  # 按 package-lock.json 精确安装
```

- Python 版本由 `.python-version` 固定（3.12）；解释器由 uv 管理。
- 前端 Node ≥24；`node_modules/` 与 `.venv/` 均不入库。

## 2. 每提交必跑（本地 = CI 同款）

| 检查 | 本地命令 |
|---|---|
| 锁文件 | `uv lock --check` |
| Lint | `uv run ruff check` |
| 格式 | `uv run ruff format --check` |
| 类型（Python） | `uv run pyright` |
| 测试 | `uv run pytest -m "not bench"` |
| 类型（TS） | `cd client && npx tsc --noEmit` |
| Lint（TS） | `cd client && npx eslint .` |
| 格式（TS） | `cd client && npx prettier --check .` |
| 测试（TS） | `cd client && npx vitest run --passWithNoTests` |
| 协议漂移 | `cd client && npm run gen:protocol:check` |
| 高度表 | `uv run python -m sim.content.build_height_map --check` |
| 方块图集 | `uv run python -m sim.content.build_block_atlas --check` |

一键全跑（PowerShell，失败即停）：

```powershell
uv lock --check; uv run ruff check; uv run ruff format --check; uv run pyright; uv run pytest -q -m "not bench"
Push-Location client; npx tsc --noEmit; npx eslint .; npx prettier --check .; npx vitest run --passWithNoTests; npm run gen:protocol:check; Pop-Location
```

## 3. 测试分级（DESIGN §16）

| 级 | 跑什么 | 命令 | 频率 |
|---|---|---|---|
| T1 | 不变量断言（无 LLM，秒级） | `uv run pytest -m t1` | 每次提交 |
| T2 | 回放确定性（无 LLM） | `uv run pytest -m t2` | 每次提交 |
| T3 | 闸门对抗样本（录制 fixture，无 marker，按文件选） | `uv run pytest sim/tests/test_t3_gate.py` | 每次提交 |
| T4 | 出戏探针（真模型，烧钱） | 见下节 | 本地手动一轮 |
| T5 | golden 场景（10 种子 × 10 游戏日） | `uv run pytest -m t5` | 每日 |
| bench | 性能基准 | `uv run pytest -m bench` | nightly |

- CI 一律 `-m "not bench"`；`--strict-markers` 生效，marker 拼错直接失败。
- `t3-corpus.md`、`t4-corpus.md` 是测试运行时读取的真相源，改语料先改文档。
- 命名门禁按文件路径选择（T3、M1 指标、M2 验收），不靠 marker，避免被 addopts 静默排除。

### T4 本地探针一轮（真模型，锁版本）

三件套 env 只在本会话有效，不落盘：

```powershell
$env:T4_MODEL='Deepseek-v4-flash'
$env:T4_MODEL_BASE_URL='https://chatapi.weixin.qq.com/openai/v1'
$env:T4_MODEL_API_KEY='<控制台粘贴，不入库不入日志>'
$env:T4_RUN='1'

uv run pytest -m t4 --junitxml=t4-results/t4.xml
```

- `T4_RUN=1` 必填：key 存在 + `T4_RUN=1` + 预算闸，三把锁缺一即 skip。
- key 只走环境变量；跑完 `Remove-Item Env:T4_MODEL_API_KEY`。
- 全 skip / 退出码 5 = 没跑成，**不是绿灯**。
- 判读：硬红 = 真回归，不放宽断言；inconclusive = 留人工复核；全 pass = 本轮等效验收。

### bench（性能域）

```bash
uv run pytest -m bench
uv run pytest -m bench --benchmark-json=perf/bench.json
uv run pytest -m bench --benchmark-compare=docs/perf/baseline-epyc7763.json --benchmark-compare-fail=median:25%
```

- 基线按机型分文件（`baseline-<machine_key>.json`）；runner 与基线机型不一致时 nightly 只告警不判红。
- 红线常量只在 `sim/tests/bench/thresholds.py`；不要在文档或 yml 抄数值。
- bench 必须固定 seed（C5：禁 `random.*`）。

## 4. 协议类型生成

```bash
cd client
npm run gen:protocol         # 生成 shared/protocol.ts（banner + prettier 已含）
npm run gen:protocol:check   # 漂移检测，不一致非零退出（ci.yml 已接）
```

- 真相源是 sim 端 pydantic 模型；`shared/protocol.ts` 只读、不手写。
- 协议版本真相源：`sim/api/ws.py::_PROTOCOL_VERSION`；`client/src/net/ws.ts` 与 `sim/tests/test_protocol_version.py` 同步。
- README 徽章必须与代码版本一致（`tools/check_implementation_status.py` 会查）。

## 5. Git 与远程

- 提交身份（仓库实测）：`ZX666X <223049848+ZX466@users.noreply.github.com>`。
- 远程：
  - `origin` = `https://github.com/ZX466/natural-world.git`
  - `gitee` = `https://gitee.com/ZX666X/natural-world.git`
- 推送：`git push origin main; git push gitee main`。GitHub 走代理 `127.0.0.1:7897`（仅 github.com 域）。
- 除 `.orca` 外，点号目录一律不入 git、不推送。

## 6. 排障

- `pytest -m t4` 收集 0 用例、退出码 5：没设 key 或探针文件缺失，不是绿。
- 前端连不上：先看 `/api/health`，再看顶栏状态；客户端断线时不做假数据。
- `gen:protocol:check` 失败：先跑 `gen:protocol`，检查 `shared/protocol.ts` 是否被手改。
- 构建卡住：Python 侧先 `uv sync --frozen`；前端删 `node_modules` 前先问用户。
