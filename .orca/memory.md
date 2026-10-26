# memory.md — 两树最小恢复卡

> 2026-10-25 大整理：主树清理 + codex 代码/文档清理收编。历史正文已删除，需要考古用 git history。
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

## 1. 门禁（2026-10-25 merge 后实测）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | **2951 passed** / 121 skipped / 72 deselected / 0 failed（298s） |
| ruff check / format | clean（366 files） |
| pyright | 0 errors, 0 warnings |
| client typecheck / lint / format | EXIT 0 |
| client vitest | **225 passed / 39 files** |
| gen:protocol / height map / block atlas | 全通过（byte-identical） |
| security-scan | C（62/100），0 critical；4 high 在本地 `.claude/mcp.json` |

## 2. 本轮清理结果

- 文档 **133 → 28**：删除 M0–M6 规划/审计/预研/台账 105 篇、`GIT-SETUP.md`、
  `linhe-architecture-report/`、6 个前端 README。
- 契约合并：火灾订正 → `docs/api/ws-protocol.md`；权力态存档分类 → `schema.md`；
  长跑执行 → `bench-plan.md`；分支证据链 → `self-unknown.md`。
- 代码：删除未用/重复实现 **-541 行**（fork/vector/anchors/actors 等共享实现合并）。
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

## 6. ④ codex｜新对话恢复快照

【2026-10-26 用户要求保存记忆｜无在途任务】代码清理 `3b33328`、文档清理 `cc47cf3` 已完成并被主树收编；本树恢复卡同步提交 `f8f59ca`。下一步先读本树 talking.txt 的最新任务，再读本卡、workflow.txt；无新任务时等待用户或主树派单，不自行启动 V3.5 / V4-3D / V4b。

- 主树 10-26 留言：旧 Zelda 图管线、闭环审计台账已在主树退役；voxel-transition-plan 已合并到 voxel-execution-spec §10，后续以执行规格为准。本树尚未同步这些代码变化，不自行 merge/rebase，不重复清理，不恢复主树已删除的旧资源。
- 本树上一轮亲测：Python 2945 passed / 121 skipped / 72 deselected；代码清理时 client 221 passed；代码与文档证据分别在 `.orca/audits/cleanup-2026-10-25/`、`.orca/audits/docs-cleanup-2026-10-25/`。本卡 §1 是主树收编后读数，不能冒充本次或本树新实测；本次只保存记忆。
- 用户偏好：中文简洁、行动和结果优先；i-have-adhd 技能持续启用；合理调用技能，查代码先 CodeGraph（显式 projectPath 指向本树），然后用文件证据复核。旧详细实现与踩坑通过 `git show cc47cf3:.orca/memory.md` 查询，不扩写重复文档。
- 边界仍为只在 codex 本地提交、不推远程、不动主树；只走本树 talking.txt 留回执。Python 用 uv；浏览器只用 `D:/develop/hermes/chrome`；删除 npm/venv 先问用户。修改本卡仅限本节，写入即本地提交。
