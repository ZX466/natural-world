# 临河镇（linhe-town）

LLM 驱动的像素小镇模拟。玩家通过念头、移动与挖放交互参与世界；世界状态由 sim 的事件流决定。

[![protocol](https://img.shields.io/badge/protocol-1.12-blue)]()

[设计基线](DESIGN.md) · [文档索引](docs/README.md) · [开发流程](docs/dev-workflow.md)

## 启动

需要 Python 3.12+、uv、Node.js 24+。在仓库根目录安装依赖：

```powershell
uv sync
cd client
npm ci
```

后端终端在仓库根目录运行：

```powershell
uv run uvicorn sim.api.main:app --reload
```

另一个终端启动前端：

```powershell
cd client
npm run dev
```

打开 `http://127.0.0.1:5173`。后端使用 `8000`，前端开发服务固定使用 `5173`；HTTP 经 Vite 代理，WS 直连后端。

模型连接在设置页配置。未连接后端时界面保持断线状态，不会生成演示世界。凭据与主密钥要求见[安全模型](docs/security/threat-model.md)。

## 操作

- 左键短按：请求主角移动到可通行格。
- 左键按住：挖掘目标格；松手取消。右键：消耗 1 土放置方块。
- 挖放限主角附近，水面、结构占格和材料不足会被拒绝；右下角显示土库存。
- 顶栏可暂停、恢复或调整倍速；存档面板用于创建和读取存档，读档会建立新分支。
- 默认等距视图；`?renderer=flat` 切换平铺视图。挖后保留静态高度并改为土面，不保证降低到平地。

## 验证

```powershell
uv run pytest -q -m "not bench"
uv run ruff check .
uv run ruff format --check .
uv run pyright sim/
uv run python -m sim.content.build_height_map --check
uv run python -m sim.content.build_block_atlas --check
```

```powershell
cd client
npm run typecheck
npm run lint
npm run format:check
npm run test
npm run build
npm run gen:protocol:check
```

性能基准按[基准方案](docs/perf/bench-plan.md)显式运行；付费真模型探针按[T4 说明](docs/security/t4-corpus.md)启用。

## 代码与数据入口

| 路径 | 职责 |
|---|---|
| `sim/core/` | 确定性时钟、事件、状态与持久化 |
| `sim/world/`、`sim/npc/`、`sim/agent/` | 世界结算、NPC 与主角决策/执行 |
| `sim/api/` | HTTP、WS、设置和存档入口 |
| `client/src/game/` | 世界镜像、Phaser 场景与渲染 |
| `client/src/ui/`、`client/src/store/` | React 界面与低频 UI 状态 |
| `shared/` | 协议快照及生成类型 |

地图与素材的来源、许可和重建方式见[内容说明](sim/content/README.md)及[第三方声明](THIRD-PARTY-NOTICES.md)。素材原件不随 Git worktree 创建而复制；缺少原件时，按内容说明补齐再运行相关构建测试。

阶段计划、预研与过程审计已从工作树清理，需要考古时使用 Git 历史。现行开发入口以本 README 与文档索引为准。
