# 临河镇（linhe-town）

> 一个 2D 像素模拟世界。主角是 LLM 驱动、坚信自己是人的 Agent——小镇药铺学徒陈默，有持久的人格、记忆与关系。
> 玩家不控制他，只是他的「直觉」：偶尔让某个念头在他脑中冒出来。
> 世界不可预测、不可控、不可预定。

[![tests](https://img.shields.io/badge/tests-2938%20passed-green)]() [![ruff](https://img.shields.io/badge/ruff-clean-green)]() [![pyright](https://img.shields.io/badge/pyright-0%20new%20errors-green)]() [![protocol](https://img.shields.io/badge/protocol-1.12-blue)]()

设计基线见 [DESIGN.md](DESIGN.md)（v2.1 冻结）；文档入口见 [docs/README.md](docs/README.md)。

---

## 快速开始

### 环境要求

| 工具 | 版本 | 用途 | 安装 |
|---|---|---|---|
| [Python](https://www.python.org/) | 3.12+ | sim 后端 | 官网安装包或 `winget install Python.Python.3.12` |
| [uv](https://docs.astral.sh/uv/) | 最新 | Python 包管理（**不用 pip**） | `winget install astral-sh.uv` |
| [Node.js](https://nodejs.org/) | ≥24 | 前端构建 | 官网 LTS 或 `winget install OpenJS.NodeJS.LTS` |

SQLite 无需单独安装（Python 内置；开发库 `world.db` 首次启动自动创建）。

### 第 1 步：安装依赖

```powershell
# 仓库根目录
uv sync                # 后端：按 uv.lock 装到 .venv/
cd client
npm ci                 # 前端：按 package-lock.json 装到 node_modules/
cd ..
```

### 第 2 步：启动后端（终端 1）

```powershell
uv run uvicorn sim.api.main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即成功。启动即自动建世界；交互式 API 文档在 `http://127.0.0.1:8000/docs`。

### 第 3 步：启动前端（终端 2）

```powershell
cd client
npm run dev
```

浏览器打开 `http://localhost:5173/`。

### 验证跑通

- 顶栏显示「第 N 天 HH:MM」戏内时钟；绿点 = 已连上后端，橙点 = 重连中，红点 = 已断开。
- 世界画面可见地图与主角；点击可通行格走路。
- 直连检查：`http://127.0.0.1:8000/api/health`。
- 默认等距体素渲染；`http://localhost:5173/?renderer=flat` 回退平面渲染。

---

## 这是什么

- **世界**：临河镇，确定性 tick、事件溯源；时间/天气/NPC 日程/建筑结构持续演化。
- **主角**：LLM 驱动的 NPC，拥有记忆、关系、情绪与自我叙事；玩家只能注入「念头」，不能直接操控。
- **玩家**：短按走路；左键按住挖土（30 tick）；右键放置；顶栏可暂停与 1x/4x/16x 变速。
- **存档**：设置面板配置 LLM；存档/读档按「分叉」处理，旧分支不销毁。

## 架构

```text
sim/       Python 3.12 + FastAPI：确定性 tick、事件溯源、感知/认知、LLM、SQLite 持久化
client/    TypeScript + React 19 + Phaser 3：iso 体素渲染 + canvas 外 React UI
shared/    OpenAPI 生成的协议类型（只读，不手写）
tools/     协议生成与实现度检查
docs/      活文档入口
```

## 当前状态（2026-10-25）

- M0–M7 全部收编；等距体素转向 V1–V4a 已收编，协议 **1.12**。
- 已验：移动、心声注入、存档/读档分叉、设置面板、时间/天气/气泡、iso 渲染、结构相位、挖放闭环。
- 待人工观感验收：DA-07 失能/恢复真模型长局、V3 画面观感、V4a 挖放疤痕可读性。
- 未派：V3.5 内容包 / V4-3D / V4b（材料分类）。

## 常用命令

```powershell
# 每提交门禁（CI 同款）
uv lock --check; uv run ruff check; uv run ruff format --check; uv run pyright; uv run pytest -q -m "not bench"
Push-Location client; npx tsc --noEmit; npx eslint .; npx prettier --check .; npx vitest run --passWithNoTests; Pop-Location

# 协议类型漂移检查
cd client; npm run gen:protocol:check

# 性能基准（nightly）
uv run pytest -m bench
```

测试分级、T4 真模型探针、bench 口径与排障见 [docs/dev-workflow.md](docs/dev-workflow.md)。

## 文档

- [DESIGN.md](DESIGN.md) — 冻结基线（六条约束、数据契约、测试分级、禁止事项）
- [docs/README.md](docs/README.md) — 活文档索引
- [docs/dev-workflow.md](docs/dev-workflow.md) — 环境与命令
- [.orca/workflow.txt](.orca/workflow.txt) — 多 Agent 协作规范

历史里程碑文档已于 2026-10-25 清理，需要出处用 `git log --diff-filter=D --name-only -- docs/` 找回。

## 开发约定

- Python 一律用 **uv**；前端 Node ≥24。
- Conventional Commits：`feat|fix|refactor|docs|test|chore|perf|ci`。
- 改代码先写/改测试；提交前跑全部门禁。
- 边界输入必须校验；不提交密钥、不写死模型 id。
- 除 `.orca` 外，点号目录不入 git、不推送。

## License

未定（私有项目）。
