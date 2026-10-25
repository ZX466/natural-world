# memory.md — 主树记忆（Claude）

> **2026-10-25 大整理**：历史快照、里程碑流水账与归档已删除，本文件只保留当前有效状态、
> 门禁、踩坑与恢复序。需要历史用 `git log -p -- .orca/memory.md`。
> 文档入口改为 `docs/README.md`（历史 M0–M6 文档已清理）。

## 0. 当前状态

- **HEAD**：`264b8b8` fix(sim,client)：DA-07 坍塌致伤接线 + V4a 挖格疤痕（安全点提交）。
- **进行中**：主树大整理（文档 / 记忆 / 死物 / 本地垃圾）。整理提交前工作区是脏的，
  新对话先看 `git status`；不要假设文档已提交。
- **协议**：`1.12`（真相源 `sim/api/ws.py::_PROTOCOL_VERSION`；`client/src/net/ws.ts` 同源；
  `sim/tests/test_protocol_version.py` 钉住；README 徽章由 `tools/check_implementation_status.py` 校验）。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单、架构/质量判断、收编复核、日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现，安全合规域。
  - 两树不直接通信，只写各树 `.orca/talking.txt`。
- **在飞**：无。codex 树空闲，等下一单。
- **未派**：V3.5 内容包 / V4-3D / V4b（材料分类等）。

## 1. 质量门（2026-10-25 实测基线）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | 2938 passed / 121 skipped / 72 deselected / 0 failed（661s） |
| ruff check / format | clean（365 files） |
| pyright sim/ | 0 errors, 0 warnings |
| client typecheck / lint / format | 全 EXIT 0 |
| client vitest | 221 passed / 39 files |
| gen:protocol:check | 通过（协议 1.12） |
| 高度表 / 图集 `--check` | byte-identical |

> 大整理提交前必须按上表重跑；数字以同场实测为准，不引用旧读数。

## 2. 当前能力与遗留

**已收编**：DA-03…DA-08（读档/账本/目标/结构/主角失能/双控制源）、V1 iso 纯函数与高度表、
V2 billboard/拾取/相机/结构池、V3 深度分层/相位/图集/iso 默认、V4a 挖放 sim+协议 1.12+前端。

**待人工观感验收（非代码缺口）**：

1. DA-07 失能/恢复真模型长局。
2. V3 画面观感（逐格 tint + 图集质感）。
3. V4a 挖放观感（挖后静态高度、土色/疤痕可读性）。

## 3. 踩坑记录（逐条有效）

**代码语义**

- `WorldEvent.payload` 是 dict，不是 pydantic 对象；测试用 `["x"]`。
- `StructureSnapshot` 字段是 `phase`，无 `state` / `integrity`。
- `collision=True` 表示**可走**（反直觉）。
- `_default_map()` 的 (3,4) 是障碍，契约测试不可写死坐标。
- `maintenance.observe` 会 pop REMOVED；派生 tile 事件要抢在它前面。
- 还原值逐格取 `_ground_tile_id`，不能共用首格（水面格仍是水）。
- 火的 ID 两侧必须对齐：`FireCell.fire_id` 与 `fire.ignited` 同一命名空间；
  `fold_fire` 对重复 ignite/extinguish fail-closed。
- `on_flush` 无 try/except（`sim/api/ws.py`）：落库异常会打死世界驱动任务，按「异常即停服」标准衡量。

**前端 / 渲染**

- `Phaser.Scene` 已有 `renderer` 字段；构造参数用 `renderMode`，否则 TS2416。
- `linhe-height.json` 是视觉近似，不是碰撞真相；碰撞真相只有 `TileMap.collision`。
- 任何「按颜色/高度」开 CanvasTexture 都会线性膨胀；正确做法是固定小图集 + tint（V3 已修）。
- iso 覆盖层深度集中在 `ISO_DEPTH`：名牌 300000+/气泡 310000+/雨 400000/夜幕 400001；
  不要再手写 99/100 这类散落数字。

**核查方法**

- 查符号、追调用链、看影响面先用 `codegraph_explore`；它没覆盖的配置/文档/生成物再回退 Read/Grep。
- 门禁数字、探针结果同场实测；不引用旧读数或他人读数。
- 核实类工作先定 3–5 个问题，答完即产出；避免无限扩。

**协作**

- `.orca` 只有 `memory.md` / `workflow.txt` / `agent-registry.md` 入库；`talking.txt`、`archive/` 本地忽略。
- 派单极简，codex 只看「当前任务」；收编后清板，回执归档，两树保持 60–70 行。
- 不推远程；只在本地提交，收编由主树做。

## 4. 恢复序（新对话）

1. 本卡 §0–§3。
2. `git log --oneline -10` + `git status`（主树与 codex 树各一遍）。
3. `.orca/talking.txt`（当前波 + 在飞）。
4. codex 树 `.orca/talking.txt` 的「当前任务」与「回执区」。
5. `docs/README.md`（活文档索引）+ `docs/dev-workflow.md`（命令）。

## 5. 分工与技术栈

- **main（Claude）**：架构 / 质量 / 逻辑 / 测试 / 前端 / 体验 / 发布 / 运维，兼收编。
- **codex**：安全 / 合规 / 风险域；承接连派（用户授权可越域）。
- 后端：Python 3.12 + FastAPI + SQLite，uv 管理；事件溯源唯一写路径（30 类事件，`extra=forbid`）。
- 前端：React 19 + Phaser 3 + Vite + Zustand + Vitest。
- 文档：`DESIGN.md`（v2.1 冻结）+ `docs/`（活文档，见索引）。
