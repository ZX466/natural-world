# memory.md — 两树最小恢复卡

> 2026-10-25/26 两轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态

- **main HEAD**：`d869059` merge codex 清理（前序 `436040a` 主树大整理、`264b8b8` DA-07/V4a）。
- **codex HEAD**：`cc47cf3` 文档清理收编点（前序 `3b33328` 代码去重；docs sync 之后以 `git log` 为准）。
- **协议**：`1.12`（`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts`）。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单/架构/质量/收编复核/日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现、安全合规。
  - 只走各树 `.orca/talking.txt`；不直接对话。
- **在飞**：无。**未派**：V3.5 内容包 / V4-3D / V4b（材料分类）。
- **待人工验收**：① DA-07 失能/恢复真模型长局；② V3 画面观感；③ V4a 挖放观感。

## 1. 门禁（2026-10-26 第二轮整理后实测）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | **2951 passed** / 121 skipped / 72 deselected / 0 failed（315s） |
| ruff check / format | clean（364 files） |
| pyright | 0 errors, 0 warnings |
| client typecheck / lint / prettier | EXIT 0 |
| client vitest | **225 passed / 39 files** |
| gen:protocol / height map / block atlas | 全通过（byte-identical） |
| security-scan | C（62/100），0 critical；4 high 在本地 `.claude/mcp.json` |

## 2. 清理结果（两轮累计）

**第一轮（2026-10-25）**
- 文档 **133 → 28**：删除 M0–M6 规划/审计/预研/台账 105 篇、`GIT-SETUP.md`、
  `linhe-architecture-report/`、6 个前端 README。
- 契约合并：火灾订正 → `docs/api/ws-protocol.md`；权力态存档分类 → `schema.md`；
  长跑执行 → `bench-plan.md`；分支证据链 → `self-unknown.md`。
- 代码：删除未用/重复实现 **-541 行**（fork/vector/anchors/actors 等共享实现合并）。

**第二轮（2026-10-26，主树）**
- 退役旧 Zelda 图管线：删 `sim/content/build_town.py`、`build_palette.py` 与
  `sprout-palette.json` / `sprout-tileset.png`（运行时已换桃花源整图；产物无引用）。
- 删已闭环审计台账 `docs/security/gameplay-integrity-audit-2026-10-21.md`（DA-01..08 全修完）。
- 合并 `docs/arch/voxel-transition-plan.md` → `voxel-execution-spec.md` §10（决策链/边界/风险）。
- 全树清掉失效文档路径引用与 `build_town`/`build_palette`/`sprout-palette` 过期注释；
  协议描述同步 `shared/openapi.json` + 重生成 `shared/protocol.ts`。
- 文档 **26 篇**（本轮 -2：审计稿、转向方案）。
- 本地垃圾：cdp profiles / tmp / 截图 / `.playwright-mcp` / `_god_map_preview` 等，
  两树合计约 800 MB；保留 `world.db`、依赖与机器基线。

## 3. 踩坑（逐条有效）

**代码**
- `WorldEvent.payload` 是 dict；`StructureSnapshot` 用 `phase`；`collision=True` 表示可走。
- `maintenance.observe` 会 pop REMOVED；派生 tile 事件要抢在它前面。
- 火的 ID 两侧对齐：`FireCell.fire_id` 与 `fire.ignited` 同一命名空间；`fold_fire` fail-closed。
- `on_flush` 无 try/except：落库异常会打死世界驱动任务。

**前端**
- `Phaser.Scene` 已有 `renderer` 字段，构造参数用 `renderMode`。
- `linhe-height.json` 只是视觉近似；碰撞真相只有 `TileMap.collision`。
- CanvasTexture 不要按颜色/高度开；用固定图集 + tint。
- iso 覆盖层深度集中在 `ISO_DEPTH`（名牌 30 万+/气泡 31 万+/雨 40 万/夜幕 400001）。

**方法**
- 查符号/调用链/影响面先用 `codegraph_explore`。
- 门禁数字同场实测，不引用旧读数。
- 收编后 main 独立复跑证据，不采信对方读数。

## 4. 恢复序

1. 本卡 §0–§2。
2. `git log --oneline -10` + `git status`，两树各一遍。
3. 两树 `.orca/talking.txt`。
4. `docs/README.md` + `docs/dev-workflow.md`。

## 5. 分工与技术栈

- 主树：架构/质量/测试/前端/发布/收编；codex：复杂实现、安全合规。
- Python 3.12 + FastAPI + SQLite + uv；React 19 + Phaser 3 + Vite + Zustand + Vitest。
- 文档真相源：`shared/openapi.json`、ORM/迁移、`docs/` 活文档。
