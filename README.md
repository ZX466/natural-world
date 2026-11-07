# 临河镇（linhe-town）

LLM 驱动的像素小镇模拟。玩家通过念头、移动与挖放交互参与世界；世界状态由 sim 的事件流决定。

[![protocol](https://img.shields.io/badge/protocol-1.15-blue)]()

[设计基线](DESIGN.md) · [文档索引](docs/README.md) · [开发流程](docs/dev-workflow.md)

## 启动

需要 Python 3.12+、uv、Node.js 24+。在仓库根目录安装依赖：

```powershell
uv sync
Push-Location client; npm ci; Pop-Location
```

后端终端在**仓库根目录**运行（首次启动会新建 `world.db` 并写入创世事件）：

```powershell
uv run uvicorn sim.api.main:app --reload
```

另一个终端启动前端：

```powershell
cd client
npm run dev
```

打开 `http://127.0.0.1:5173`。后端用 `8000`，前端固定 `5173`（端口被占直接报错，不会静默换端口）；HTTP 经 Vite 代理，WS 直连后端。

**后端必须在仓库根目录启动**：`world.db` 路径是相对当前工作目录的 `Path("world.db")`，在别处启动会新建一个空库而不是读到现有世界。想在临时库上试跑，就在一个空目录里启动（需设 `PYTHONPATH` 指向本仓库），现有 `world.db` 不会被触碰。

模型连接在设置页配置。未连接后端时界面保持断线状态，不会生成演示世界。凭据与主密钥要求见[安全模型](docs/security/threat-model.md)：主密钥从环境变量 `LZ_MASTER_KEY` 读取，缺失时回退到 `~/.linhe/master.key`（首次引导自动生成）。

> 仓库没有引入 dotenv，`.env` **不会**被自动读取（`.env.example` 只是键名清单）。请在启动终端里直接设置环境变量；`uvicorn --env-file` 同样不可用，它内部依赖的 `python-dotenv` 没有安装。

## 操作

- **念头**：底部输入条往陈默心里放一个念头（≤64 字），这是玩家唯一的主动对话入口。
- **移动**：左键点地面走过去，按住拖动连续换目标；`W/A/S/D` 或方向键八向连续移动，`Esc` 取消。走不过去时右下角给提示。
- **挖放**：左键按住不可走的格挖（1x 下按下到挖成约 0.65 秒，提前松手取消），按该格材料产出土/石/木；右键在可走格放一块，消耗 1 份**当前选中的材料**（行囊里点一行切换，默认土）。限主角 4 格（曼哈顿距离）内；水面、结构占格、材料不足会被拒绝。
- **高度**：挖一次降一层；放置按材料决定高度——土 1、石 2、木 3，且都阻挡通行。挖掉放下的块会返还原材料并回到可走高度 1。可走格只能放、不能挖；落地后的碰撞以服务端 `tile_changed` 为准。右下角行囊按材料分行，为 0 不显示。
- 顶栏可暂停、恢复或调整倍速（1x/4x/16x）；「手札 / 存档」按需展开侧栏，再点一次或按 Esc 收起，窄屏（<900px）默认收起。存档面板创建和读取存档，读档会建立新分支。

## 视图与渲染

- **默认是 three.js 自由视角世界**（透视相机、贴地、天空雾），2026-11-07 经实机验收后切换为默认。
  - 操作：短按移动、长按挖掘、右键放置、右拖/中拖转视角、滚轮缩放，`W/A/S/D` 与方向键同样可用。
  - 主角视野（半径 12 + 视线遮挡）：墙后的角色不绘制，够不着的目标不给高亮。
- `?terrain=phaser` 退回 Phaser 等距世界（回滚开关，仍是完整可玩路径）；`?renderer=flat` 在那条路径上切换平铺视图。两套是**互相独立的画布与场景**，`?renderer=` 不影响 three。

移动采用回放缓冲插值：服务端每格一个权威样本，渲染落后约一格（1x 约 0.28 秒、16x 约 0.05 秒）在两个真实样本之间插值，因此不空等、不超速；代价是恒定的视觉延迟。两条渲染路径共用同一份缓冲实现。

## 验证

门禁与 CI 同款（`npm run build` 仅本地；分级测试 T1–T5、bench、T4 探针见[开发流程](docs/dev-workflow.md)）：

```powershell
uv lock --check; uv run ruff check; uv run ruff format --check; uv run pyright; uv run pytest -q -m "not bench"
uv run python -m sim.content.build_height_map --check; uv run python -m sim.content.build_block_atlas --check
Push-Location client; npm run gen:protocol:check; npm run typecheck; npm run lint; npm run format:check; npm run test; npm run build; Pop-Location
```

- 改地图或图集资产时，后两条 `--check` 必须逐字节一致。
- 性能基准按[基准方案](docs/perf/bench-plan.md)显式运行；付费真模型探针按[T4 说明](docs/security/t4-corpus.md)启用。
- 协议版本落在三处且必须同步：`sim/api/ws.py`、`client/src/net/ws.ts`、`sim/tests/test_protocol_version.py`。

## 排障

| 现象 | 先查 |
|---|---|
| 页面打开但世界不出现 | 后端是否在 8000 跑；`http://127.0.0.1:8000/api/health` 应返回 `status: "ok"` |
| WS 一直重连 | 前端是否仍是 5173；WS 握手用固定 Origin 白名单（`localhost` / `127.0.0.1` 的 5173 与 8000），换域名或端口会被拒 |
| 启动报端口占用 | `strictPort` 生效，先释放 5173 / 8000 |
| 世界是空的、人物全无 | 后端可能是在别处启动的，写进了新建的空库 |
| 依赖版本莫名变动 | 用 `npm ci`（按锁文件）而不是 `npm install` |

## 代码与数据入口

| 路径 | 职责 |
|---|---|
| `sim/core/` | 确定性时钟、事件、状态与持久化 |
| `sim/world/`、`sim/npc/`、`sim/agent/` | 世界结算、NPC 与主角决策/执行 |
| `sim/perception/`、`sim/llm/` | 感知帧与信息边界、LLM 客户端与记忆扫描（感知帧目前只在服务端计算，尚无出站通道） |
| `sim/content/` | 地图与地形分类、素材构建脚本 |
| `sim/api/` | HTTP、WS、设置和存档入口 |
| `client/src/game/` | 世界镜像、Phaser 场景与渲染 |
| `client/src/game/render/motion-buffer.ts` | 两条渲染路径共用的移动回放缓冲（样本队列 / 时刻插值 / 延迟爬升） |
| `client/src/game/render/three/` | three.js 自由视角世界（地形、角色、相机碰撞、拾取） |
| `client/src/ui/`、`client/src/store/` | React 界面与低频 UI 状态 |
| `shared/` | 协议快照及生成类型 |
| `tools/` | 协议生成与实现状态复检脚本 |

地图与素材的来源、许可和重建方式见[内容说明](sim/content/README.md)及[第三方声明](THIRD-PARTY-NOTICES.md)。素材原件不随 Git worktree 创建而复制；缺少原件时，按内容说明补齐再运行相关构建测试。

阶段计划与预研文档已从工作树清理，需要考古时使用 Git 历史。按轮次归档的实测证据保留在 [`.orca/audits/`](.orca/audits/)（`plan.md` + `acceptance.json` + 截图），它们是复现口径的证据，不是设计真相源。现行开发入口以本 README 与[文档索引](docs/README.md)为准。
