# memory.md — 两树最小恢复卡

> 2026-10-25/26 多轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态

- **main HEAD**：`446db42`（docs：本卡指针）；**代码收编点仍是 `e2e1250`**
  （merge codex 体素挖土降层与等距增量渲染）。
- **codex HEAD**：`16489c3`，**已被主树收编**；与 main **无分叉**（`merge-base --is-ancestor`
  实测），落后 22 个提交但可 `merge --ff-only main` 同步。
- **协议**：`1.12` 现状；**第七轮 V4b 派单要求升 1.13**
  （`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts` 必须同改）。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单/架构/质量/收编复核/日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现、安全合规。
  - 只走各树 `.orca/talking.txt`；不直接对话。
- **在飞**：**V4b 材料分类**（2026-10-28 派 codex，协议升 1.13）。
- **未派**：V3.5 内容包 / V4-3D。
- **待人工验收**：① DA-07 失能/恢复真模型长局；② V3 画面观感；④ 走路是否还飘。
  **③ V4a 挖放观感已于 2026-10-28 由用户验收通过。**

## 1. 门禁（2026-10-26 第五轮 merge 后主树实测）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | **2948 passed** / 121 skipped / 72 deselected / 0 failed（289s） |
| ruff check / format | clean（363 files） |
| pyright | 0 errors, 0 warnings |
| client typecheck / lint / prettier | EXIT 0 |
| client vitest | **250 passed / 39 files** |
| gen:protocol / height map / block atlas | 本单未动协议与素材，未跑 |

> codex 自报 246 passed；主树收编后独立复跑得 250（多出主树自己的用例）——数字不同正常，
> 收编只采信主树读数。

## 2. 第七轮派单（2026-10-28）V4b 材料分类

**为什么选它**：`VoxelEditedPayload.material_id` 写死 `Literal["earth"]`，挖树挖石屋都只进「土」。
主树实测可挖格（碰撞 0 且静态 h>0）**12511 格**，按静态高度正好三档：
h=1 土 5083 / h=2 石 5102 / h=3 木 2326。数据面已够，**不需要新素材或新采样脚本**。

**裁决要点**（详见 codex 树派单）：
1. 材料 = 目标格静态高度（h=1 earth / h=2 stone / h=3 wood），复用已加载的 `voxel_height`。
2. **place 消耗目标格所属材料**（挖石得石、放石耗石，往返净值 0）。
3. 协议升 **1.13**：`VoxelInventory` 扩 `{earth, stone?, wood?}`，stone/wood 可选缺省 0（旧端兼容）。
4. `MaterialMoveReason` **不改**；`MaterialBalance` 按 `(branch,ref,material)` 建键，**零迁移**。
5. 不做：材料选择 UI、`effectiveHeight`、挖放高度近似、高度表/图集产物。

**否决的候选**：V4a 精确深度（边角缺陷，需改协议，性价比低，用户已验收观感）/
V3.5 内容包（需外部素材与录音管线）/ V4-3D（DESIGN §10.2 三条启动条件均不成立）。

## 2b. 第五轮成果（2026-10-26）

**A｜挖土看得见（推翻决策 9）** —— codex
- `client/src/game/render/iso.ts::effectiveHeight`：`dig → max(0, h-1)`、`place → min(3, h+1)`，
  built/collapsing footprint 仍优先返回 2。
- 挖到 0 时**不再留悬空深色菱形疤**（主树收编解冲突时落地：`height === 0 → continue`，
  疤贴在**降后**顶面）。
- **碰撞真相不变**：仍是 `TileMap.collision`；dig 后仍可走、place 后仍不可走。sim 与协议 0 改动。
- **已知近似**：`VoxelEdit` 无编辑深度字段，先 `place` 再 `dig` 可能掉两层。精确解需改协议，未做。

**B｜等距渲染增量** —— codex
- `WorldMirror.terrainVersion` 失效标记 → `WorldScene` → `IsoTerrain`，静止帧零遍历。
- 脏区裁剪重绘，画布贴图保留；40×40 地图单格 dig 的 CPU fill **4800 → 67（-98.6%）**（codex 自测）。
- **未测的**：浏览器实际 FPS；变更帧仍比较一次全部表面缓存，Phaser refresh 仍可能全画布上传。

**C｜计划看板退役** —— main `bb871f2`
- `state_delta.plan` 条目**全部**来自 NPC 的 defers（`sim/npc/runtime.py` → `set_plan_from_expression`），
  文本恒为「先去别处，等会儿再回来」，不是陈默的计划。
- 面板**直接删除**，未并入心之声（并入会把 NPC 打算误挂成陈默内心）。
- 协议 `PlanDelta` 与 `uiStore.plans` **保留**，只撤 UI。`DESIGN.md` 三形态 → 两形态。

**D｜移动不飘** —— main `bb871f2`
- 走环原来只在「换格那一帧」推进，其余帧归站立帧 → 人物站着滑。加 `gliding` 标志修掉。
- 镜头原来被喂新逻辑格，人物还在滑 → 镜头先跳一格。改喂**插值后的逻辑顶面**
  （不含同格错位偏移），并去掉 0.12 跟随缓动（双重滞后）。

## 3. 踩坑（逐条有效）

**代码**
- `WorldEvent.payload` 是 dict；`StructureSnapshot` 用 `phase`；`collision=True` 表示可走。
- `maintenance.observe` 会 pop REMOVED；派生 tile 事件要抢在它前面。
- 火的 ID 两侧对齐：`FireCell.fire_id` 与 `fire.ignited` 同一命名空间；`fold_fire` fail-closed。
- `on_flush` 无 try/except：落库异常会打死世界驱动任务。
- **挖放高度纯属视觉**：`linhe-height.json` 只是近似，碰撞真相只有 `TileMap.collision`。
  **但静态高度是 V4b 的材料判据**（h=1/2/3 → 土/石/木）——同一张表，两种用途，别混淆。
- **「可挖格」= 碰撞 0 且 h>0**：`_validate` 判据是 `is_walkable != (action=="place")`，
  即 dig 要求**不可走**、place 要求可走。别按「所有地面」统计可挖面。
- **`state_delta.plan` 不是主角计划**：全部来自 NPC defers。别再把它接到「心之声」。

**前端**
- `Phaser.Scene` 已有 `renderer` 字段，构造参数用 `renderMode`。
- CanvasTexture 不要按颜色/高度开；用固定图集 + tint。
- iso 覆盖层深度集中在 `ISO_DEPTH`（名牌 30 万+/气泡 31 万+/雨 40 万/夜幕 400001）。
- **走环判据要按「是否在动」而不是「是否换格」**：插值期间不换格，但人在动。
- **镜头目标必须与人物同一插值进度**：喂逻辑格 + 再叠缓动 = 双重滞后 = 飘。

**方法**
- 查符号/调用链/影响面先用 `codegraph_explore`（显式 `projectPath`）。
- 门禁数字同场实测，不引用旧读数；**收编后主树必须独立复跑**。
- **删文件/依赖前先查 `DESIGN.md`**：它写死了承诺（`tests/invariants`、`tests/replay`、
  Hypothesis/tenacity），零 grep 命中≠可删。
- 删/移文档后全树扫旧路径；用脚本抽反引号路径比对存在性最省事。
- 测试夹具共享在 `sim/tests/conftest.py`；只在与共享版真有差异时才本地覆盖。
- 协议版本双落点必须同改：`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts`。
- **两树派单必须写明基线**：codex 曾因 `git diff ... | git apply` 撞二进制删除而阻塞
  （补丁缺 `--binary`）。正确做法是主树先 merge，或让 codex 从同步后的基线开分支。
- **收编的文档冲突按用户最新裁定解**，不按「谁后写谁赢」：本轮 codex 的
  「点号目录本地入 git」与用户 10-26 裁定「维持 gitignore」冲突，取主树侧。
- `.orca/` 在 `.gitignore` 里，但已跟踪文件仍需 `git add -f`。
- Windows 提交时 CRLF 警告正常（`.gitattributes` 为 `* text=auto eol=lf`），忽略。

## 4. 恢复序

1. 本卡 §0–§2。
2. `git log --oneline -10` + `git status`，两树各一遍。
3. 两树 `.orca/talking.txt`。
4. `docs/README.md` + `docs/dev-workflow.md`。

## 5. 分工与技术栈

- 主树：架构/质量/测试/前端/发布/收编；codex：复杂实现、安全合规。
- Python 3.12 + FastAPI + SQLite + uv；React 19 + Phaser 3 + Vite + Zustand + Vitest。
- 文档真相源：`shared/openapi.json`、ORM/迁移、`docs/` 活文档。

## 6. ① Claude｜新对话恢复快照

【2026-10-28 第七轮｜V4b 在飞】用户人工验收通过 V4a 挖放观感 → 派 V4b 材料分类给 codex
（协议升 1.13）。主树实测可挖格三档 5083/5102/2326，作为材料判定依据写进派单。

- **开新对话只需知道**：① 代码全绿、**V4b 在 codex 树**；② 两项待**肉眼**验收
  （走路是否还飘、V3 画面）+ DA-07 长局；③ 协议将变 1.13，未推远程。
- **未推送**：origin/gitee 停在 `2d7c4cf`；main 领先若干提交未推。推送是用户决定，不自动推。
- **配置目录**：维持用户 10-26 裁定「不进 git、不推远程、本地须存在」；主树不建 `.pi`。
- **浏览器**：仅用户明确要求时用，路径 `C:\Users\zx198\AppData\Local\ms-playwright`。
- **全局 git 邮箱**：`zx19836980213@outlook.com`。
- 教训已进 §3：两树派单必须写明基线（本轮 ff 可同步，无分叉）；收编冲突按用户最新裁定解。
