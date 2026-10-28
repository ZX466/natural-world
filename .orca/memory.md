# memory.md — 两树最小恢复卡

> 2026-10-25/26 多轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态

- **main HEAD**：`ba68e88`（V4b 收编完成，**fast-forward，无 merge commit**）。
- **codex HEAD**：`ba68e88` = main，**两树已同步**（ff 收编）。
- **协议**：**`1.13`**（V4b 升级）；双落点已同改
  （`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts::PROTOCOL_VERSION`）。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单/架构/质量/收编复核/日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现、安全合规。
  - 只走各树 `.orca/talking.txt`；不直接对话。
- **在飞**：无。**未派**：V3.5 内容包 / V4-3D。
- **待人工验收**：① DA-07 失能/恢复真模型长局；② V3 画面观感；④ 走路是否还飘。
  **③ V4a 挖放观感已于 2026-10-28 由用户验收通过。**
  **新增 ⑤ V4b 三材料挖放观感（行囊显示土/石/木三行）——需肉眼验收。**

## 1. 门禁（2026-10-28 V4b 收编后主树独立实测）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | **2969 passed** / 121 skipped / 72 deselected / **0 failed**（339s） |
| ruff check / format | clean（363 files） |
| pyright | 0 errors, 0 warnings |
| client typecheck / lint / prettier | EXIT 0 |
| client vitest | **259 passed / 39 files** |
| gen:protocol:check | EXIT 0（协议已动，必须跑） |

> codex 自报 2969P/259P，与主树独立复跑一致——本轮两边数字对上了。

## 2. 第七轮成果（2026-10-28）V4b 材料分类 —— codex，已收编 `ba68e88`

**问题**：`VoxelEditedPayload.material_id` 写死 `Literal["earth"]`——挖树挖石屋都只进「土」。
主树实测可挖格（碰撞 0 且静态 h>0）**12511 格**，按静态高度正好三档：
h=1 土 5083 / h=2 石 5102 / h=3 木 2326。

**落地**：
- `voxel_exec.py`：`_MATERIAL_BY_HEIGHT = {1: earth, 2: stone, 3: wood}`；`_validate` 返回材料，
  `_inventory`/`_reserved` 改为三材料字典；`_pending` 存 `(action, material)`。
- **place 消耗目标格所属材料**——挖石得石、放石耗石，往返净值 0；缺料 fail-closed
  （`行囊里没有石料了。`，不落库）。
- 协议 **1.13**：`VoxelInventory` 保留必需 `earth`，新增可选 `stone`/`wood`（缺省 0，仍封闭对象）。
  `MaterialMoveReason` 不改，`MaterialBalance` 零迁移。
- HUD 三行，为 0 不显示；**行囊仍只进 HUD，不进 prompt / 世界事件**（C3）。

**主树独立验证**（不只是跑测试，另写探针实跑）：
- h=1/2/3 各挖一次 → `material_id` 分别 earth/stone/wood，行囊 `{earth:1, stone:1, wood:1}` ✅
- 在 h=2 格放置 → stone 1→0 ✅；再放一次 → 拒绝「行囊里没有石料了。」✅

**codex 自报的告警**：全量跑有 `test_m4c_llm_driver::...test_seed_inserts_profile_and_idempotent`
的 aiosqlite `Event loop is closed`；单独复跑 1P/1.81s 未重现，**未声称已修复**。
主树本轮 2969P/0F 也未见该失败——按间歇性处理，若复现再查。

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
- **`.orca/talking.txt` 永远不进 git**（`.gitignore` 第 73 行：per-worktree local inbox）。
  `729921a` 曾误 `git add -f` 入库，后果是 codex 执行 `merge --ff-only main` 时被
  **静默覆盖掉派单**（已实验复现）。2026-10-28 已 `git rm --cached` 修正；
  改完不要 `git add`，提交里不该出现这个路径。
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

【2026-10-28 第七轮收编完成｜无在途任务】V4b 材料分类（codex）已收编 `ba68e88`，
fast-forward 无冲突；协议升 **1.13**；主树独立复跑全绿（pytest 2969P/0F、vitest 259P）。

- **开新对话只需知道**：① 代码全绿、两树同步无在飞任务；② 三项待**肉眼**验收
  （走路是否还飘、V3 画面、**V4b 三材料行囊**）+ DA-07 长局；③ 协议已 1.13，未推远程。
- **未推送**：origin/gitee 停在 `2d7c4cf`；main 领先若干提交未推。推送是用户决定，不自动推。
- **配置目录**：维持用户 10-26 裁定「不进 git、不推远程、本地须存在」；主树不建 `.pi`。
- **浏览器**：仅用户明确要求时用，路径 `C:\Users\zx198\AppData\Local\ms-playwright`。
- **全局 git 邮箱**：`zx19836980213@outlook.com`。
- 本轮教训已进 §3：`.orca/talking.txt` 必须保持未跟踪，否则 ff 会覆盖派单。

## 7. ④ codex｜新对话恢复快照

【2026-10-28 第七轮 V4b｜实现与门禁完成，待主树收编】土/石/木由既有静态高度 1/2/3 判定；挖得对应材料、放置扣目标材料。协议 1.13；库存三字段，stone/wood 可选且缺省 0，HUD 零数量不显示。无在途实现；下一步由 Claude 收编复核，本树不推远程。

- 基线：按本轮派单授权先备份 talking，再 fetch + ff 到 `13e2ca7`；talking 确认未跟踪，不要 git add。TDD RED 检查点 `61570c2`，GREEN 实现 `93b9e29`；后续 live schema/版本预期修正及本快照见 git log。收编须取 `13e2ca7..codex` 整段，不只取末次修正提交。
- 关键实现：VoxelRuntime 的库存和未刷盘预留量各按材料计数；pending 保存动作与预留材料，提交后释放原材料额度。事件工厂元数据保留，只以已验证的新材料 payload 作不可变替换；events.py 仅扩 VoxelEditedPayload 的三个字面量，数量/原因枚举不变。重放按历史 material_id，不按当前高度重新分类；零迁移。
- 协议坑：OpenAPI 字段写 `default: 0` 会让现有生成器把 stone/wood 变必填，破坏旧端类型。因此以可选字段 + absent=0 描述定义，客户端补零；不改生成器、不手写 protocol.ts。live OpenAPI 还有 openapi_ext.py 的旧声明，已同步同一库存定义并用对拍测试锁住；FastAPI 自身 version 也升 1.13。README 协议徽标同步，避免状态检查工具报漂移。
- 本轮亲测：pytest **2969 passed / 121 skipped / 72 deselected / 5 warnings，337.00s**；相关链路 110 passed，含真实冷启动、历史分叉、嵌套分叉、鉴权与错材料零写入。ruff check/format 通过（363 files），pyright 0 errors/warnings；gen:protocol:check、client typecheck/lint/format 通过；Vitest **259 passed / 39 files**，生产构建通过。证据在 `.orca/audits/v4b-materials-2026-10-28/plan.md` 及本地日志。
- 警告如实保留：全量测试有一条 aiosqlite worker 在 `test_m4c_llm_driver` 清理阶段的 `Event loop is closed` 警告，未造成失败；未改 driver/LLM 模块。构建仍提示大 chunk。覆盖率工具未配置，未报百分比；浏览器验收未请求、未运行。
- 范围：sim/world、sim/npc、sim/llm、渲染高度/图集产物与依赖均无改动；place 再 dig 的两层视觉近似不变。不启动 V3.5/V4-3D 等未派任务。中文简洁、i-have-adhd 持续启用，CodeGraph 返回源码视作已读；上下文 50% 提醒切新对话，恢复先 workflow → talking → 本节。
