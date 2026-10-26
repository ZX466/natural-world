# memory.md — 两树最小恢复卡

> 2026-10-25/26 两轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态

- **main HEAD**：本卡所在提交（以 `git log -1 --oneline` 为准）；规则改动 `41427ec`，前序 `6789c5e`/`1a0546f`。
- **codex HEAD**：`621fd38` 双树规则对齐（前序 `145d5be` 记忆快照、`cc47cf3` 文档清理收编点）。
- **协议**：`1.12`（`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts`）。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单/架构/质量/收编复核/日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现、安全合规。
  - 只走各树 `.orca/talking.txt`；不直接对话。
- **在飞**：无。**未派**：V3.5 内容包 / V4-3D / V4b（材料分类）。
- **待人工验收**：① DA-07 失能/恢复真模型长局；② V3 画面观感；③ V4a 挖放观感。

## 1. 门禁（2026-10-26 第三轮整理后实测）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | **2948 passed** / 121 skipped / 72 deselected / 0 failed（319s） |
| ruff check / format | clean（363 files） |
| pyright | 0 errors, 0 warnings |
| client typecheck / lint / prettier | EXIT 0 |
| client vitest | **225 passed / 39 files** |
| gen:protocol / height map / block atlas | 全通过（byte-identical） |
| security-scan | C（62/100），0 critical；4 high 在本地 `.claude/mcp.json` |

## 2. 清理结果（三轮累计）

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
- 合并 `docs/arch/voxel-transition-plan.md` → `voxel-execution-spec.md` §10（决策链/边界/风险），原文件已删。
- 全树清掉失效文档路径引用与 `build_town`/`build_palette`/`sprout-palette` 过期注释；
  协议描述同步 `shared/openapi.json` + 重生成 `shared/protocol.ts`。
- 文档 **26 → 24 篇**（本轮 -2：审计稿、转向方案）。
- 本地垃圾：cdp profiles / tmp / 截图 / `.playwright-mcp` / `_god_map_preview` 等，
  两树合计约 800 MB；保留 `world.db`、依赖与机器基线。

**第三轮（2026-10-26，主树 · `1a0546f`）**
- 删 `sim/world/fog.py`（`FogOfWar`/`fold_fog_reveal` 零消费）+ `fog_reveal_event`、
  `TestFogFold` 三例、`TickLoop.fog_seen` 空字段、`PerceptionEngineLike` 空协议。
  **`FogRevealPayload` 保留**：`event_validation` 的事件重放映射仍在用。
- 夹具去重：`engine`/`store`/`session` 上移 `sim/tests/conftest.py`，
  14 个测试文件逐字副本消除（有差异的变体仍本地覆盖）。
- 文档失真：`m7-render-art.md` §3–§5 标退役（BootScene/tilemap.ts 未实现、
  48×48→140×100、1.3→1.12、mock 分支已删）；`voxel-execution-spec.md` A16 改「全仓已删」；
  `anchors-api.md` 测试路径 4 处；`bench/README` 三处死链；`god-reuse-final.md` 两处改归档。
- 净删 532 行（39 files, +116/−648）。

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
- 查符号/调用链/影响面先用 `codegraph_explore`。**它的返回就是逐字源码 = 已经 Read 过**：
  同一文件/区域禁止再用 Read/Grep 复盘；相关符号一次批量查完，不来回试探。
- 门禁数字同场实测，不引用旧读数。
- 收编后 main 独立复跑证据，不采信对方读数。
- **删文件/依赖前先查 `DESIGN.md`**：它写死了承诺（`tests/invariants`、`tests/replay`、
  Hypothesis/tenacity），零 grep 命中≠可删。第三轮差点删掉两个 DESIGN §5 声明的测试包。
- 删/移文档后全树扫旧路径（本仓文档交叉引用密）；用脚本抽反引号路径比对存在性最省事。
- 测试夹具共享在 `sim/tests/conftest.py`；只在与共享版真有差异时才本地覆盖。
- 协议版本双落点必须同改：`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts`。
- Windows 提交时 CRLF 警告是正常的（`.gitattributes` 为 `* text=auto eol=lf`），忽略。

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

【2026-10-26 第四轮｜规则对齐，无在途任务】用户裁定四项：①点号配置目录**维持 gitignore**
（本地保留、不入库、不推送）——workflow/dev-workflow 措辞已从「入 git 不推远程」改为「不进 git」；
②codex 树补齐 `.agents`+`.codex`（各 20/27 文件，从主树复制）；③主树**不建 `.pi`**（无 pi agent）；
④全局 git 邮箱改回 `zx19836980213@outlook.com`（原为 GitHub noreply，偏离规则 #2）。

- 同时把主树 `docs/dev-workflow.md` 与 `.orca/workflow.txt` 的 Playwright 路径从 `D:\develop\hermes\chrome`
  更新为 `C:\Users\zx198\AppData\Local\ms-playwright`，并补「仅用户明确要求时用浏览器」。
- 两树状态：均干净；main 领先 origin/gitee 未推（现测 `git rev-list --count origin/main..main`）；
  codex 领先主树收编点 3 个提交（纯文档）。
  codex 只余两处文档自纠（workflow §4 措辞、dev-workflow 旧 Playwright 路径），已写入其 talking.txt。
- 主树工作区无改动前刷新过门禁（`1a0546f` 实测：pytest 2948P/121S/72D/0F）。本轮**只改文档与本地配置**，未重跑代码门禁。
