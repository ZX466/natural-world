# memory.md — 主树记忆（Claude）

> **历史全文已归档**：`.orca/archive/memory-2026-10-21-full.md`（492KB，含 M0–M6 各轮快照、
> 各 agent 树历史、claude/codex/pi/kilo 分节）。**该目录被 `.gitignore:68`（`.*/`）忽略，
> 只在本地存在**；换机器/新克隆时没有它，需要历史就查 git history（`git log -p -- .orca/memory.md`）。
> 本文件只保留**当前有效**的部分。

<!-- ===== 新对话快速恢复卡（2026-10-21 P 单收口）===== -->

## 0. 本会话状态

- **HEAD**：`b929406`（merge codex：O 单 + 审计 + DA-01/DA-02）
- **在飞**：DA-03 已派 codex（含 P0-3 火焰 ID 前置缺陷），回执待收；codex 树已 fast-forward 到 `b929406`
- **未决**：是否推送双远程（本地领先 43 提交，按纪律暂不推）
- **协议**：1.11（真相源 `sim/api/ws.py::_PROTOCOL_VERSION`，前端 `client/src/net/ws.ts` 同源）
- **工作树：两棵**（2026-10-21 用户重申，长期有效）
  - 主树 `E:/zxdevelop/project7` → 分支 `main`（Claude）
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex` → 分支 `codex`（HEAD 随其提交推进，收编前以实际 `git log` 为准）
- **远程**：本地领先 `gitee/main`，按纪律不推

## 1. 里程碑

**M0–M6 全部收官**（M6 于 2026-10-05，G1–G4 全 ✅）；**M7 渲染面**已落（地图/时钟/视角/昼夜）。
代码侧整体完成，剩余是收口型缺口。

## 2. 门禁（2026-10-21 实测）

| 项 | 结果 |
|---|---|
| sim 全量 pytest（`-m "not bench"`） | exit 0 |
| ruff check / ruff format | clean / 343 文件已格式化 |
| pyright sim/ | 0 errors |
| client tsc --noEmit | 0 错误 |
| client vitest | 138 passed / 25 files |
| check_implementation_status | 未发现新缺口 |

## 3. 当前剩余缺口（codex 审计 8 组：2 P0 + 6 P1，已修 2 组）

来源 `docs/security/gameplay-integrity-audit-2026-10-21.md`（codex `974611e`）：

| # | 缺口 | 状态 |
|---|---|---|
| P0-1 | 重启二次创世污染日志 | ✅ `846a052` |
| P0-2 | 历史读档 head-only / 世界态未恢复 | ✅ `de3a8ae` |
| P0-3 | **火格 `fire_id` 双语义**（主树探针新发现，不在 codex 8 组内）：`sim/world/fire.py:136` 蔓延格继承 `parent.fire_id`，`sim/npc/fire_runtime.py:73-78` 却每格自增签发新 `fire-{seq}` → 同一 ID 重复熄灭 → `FireWriteError` 整批拒写；`sim/api/ws.py:1401` 的 `await on_flush(events)` 无 try/except ⇒ **世界驱动直接死** | ⬜ 未修（已并入 DA-03 前置） |
| DA-03 | 余额/火场账本清零未重建 | ⬜ 未修 |
| DA-04 | 人物/中文货名目标不兼容 | ⬜ 未修 |
| DA-05 | 建筑表现跨分支残留 | ⬜ 未修 |
| DA-06 | 坍塌还原未应用实时碰撞 | ⬜ 未修 |
| DA-07 | 主角走 NPC 死亡删除 | ⬜ 未修 |
| DA-08 | 重启后主角双控制源 | ⬜ 未修 |

> **不得称「全部玩法已修」**——codex 明确边界：上述 6 组仍未修；主树另加 P0-3，共 7 组未修。
> 另：`check_implementation_status` 是静态结构检查，不等于玩法验收。
> **已关闭**：O 单（`9447d1b`，心声反馈 + 断线不谎报，客户端 143 passed）。

### P0-3 实测证据（2026-10-21 主树探针，seed=42）

```
IGNITED:     fire-1(10,10) fire-2(11,10) fire-3(9,10) … fire-21(12,9)
EXTINGUISH:  fire-1@(5,10) fire-1@(4,10) fire-1@(4,10) …   ← 同一 fire_id 反复熄灭
flush_tick → FireWriteError: fire_id='fire-1' 已于 tick=… 熄灭，重复熄灭
```

- 触发时间：该种子第一场火在 **tick 183600**（约 2.1 游戏日），60 天内 22 场 ⇒ 实况两天内必崩。
- 漏网原因：`test_m4d5_fire_live.py::test_spread_emits_ignite_events` 只断言「有 ignited 事件」，
  **从未**断言事件 `fire_id` 与内存格一致，也从未跑过落库。
- 修法方向：统一 `fire_id` 语义（蔓延格与事件必须同 ID），**不要**给每个蔓延格发新 ID。

## 4. 本轮已修（P 单四项，读档族清零）

| 项 | 修复 | 提交 |
|---|---|---|
| P-1 `tile_map` 读档不重建 | `rebuild_tile_map` + `read_branch_history` 沿 fork 链取祖先前缀；启动+读档两处 | `4a5dfa3` |
| P-2 `build_runtime` 读档不清零 | `reset()` + `restore_from_events()`，重放 started/checkpoint | `076ed21` |
| P-4 `fire_runtime` 读档不清零 | `reset()`（`cells=()`、`fire_seq=0`）；**更正 main.py 原注释**「火场由 fork 层承担」——fork 层根本不引用 fire | `076ed21` |
| P-6 `derive_tile_events` 零调用 | `on_flush` 里在 `maintenance.observe` **之前**补发逐格 `tile_changed` 还原 | `076ed21` |

## 5. 踩坑记录（血泪，逐条有效）

**代码语义类**
- `WorldEvent.payload` 是 **dict**，不是 pydantic 对象 → 测试断言用 `["x"]`
- `StructureSnapshot` 字段是 `phase: StructurePhase`，**无** `state` / `integrity`
- `collision=True` 表示**可走**（变量名反直觉，别当成墙）
- `_default_map()` 的 (3,4) 恰好是障碍——契约测试不可写死坐标
- `maintenance.observe` 会 **pop REMOVED**，派生 tile 事件必须抢在它前面
- 还原值要逐格取 `_ground_tile_id`，不能共用首格（水面格要仍是水）
- **火的 ID 语义两侧必须对齐**：`FireCell.fire_id`（世界侧）与 `fire.ignited` 事件
  （运行侧）是同一命名空间；`fold_fire` 对重复 ignite/extinguish **fail-closed**，
  一侧漂移就是整批 flush 被拒，而不是静默降级
- **`on_flush` 无 try/except**：`sim/api/ws.py:1401` 的 `await on_flush(events)` 任何异常
  都会直接打死世界驱动任务（没有降级、没有重试、没有前端告知）。写落库相关代码要按
  「异常即停服」的标准衡量风险

**核查方法类**
- **核库后再报**：小写 grep 会漏驼峰符号 → 查符号用 codegraph 或大小写不敏感
- **门禁数字同场测**：不引用旧读数，不用文档自述
- **探针现测**：不引用他人读数
- **skip 分型**：逐条读原始 SKIPPED 行
- **汇报前先核库**：git log + Test-Path，此前有过虚构汇报的教训

**协作类**
- **两棵树是常态**：主树 `main` + codex 树 `codex`，不要再按「唯一树」记（2026-10-21 用户重申）
- agent 间**只走 talking.txt**：**不直接向 codex 发消息**、不查终端、不用 orca-cli 通知；
  派单/回执一律写对方工作树的 `.orca/talking.txt`（2026-10-21 用户明示）
- 派单要**极简**：codex 只看「当前任务」一节，历史压成表格一行
- 不推远程；只在本地分支提交，收编由主树做

## 6. 恢复序（新对话）

1. **本卡**（0–6 节）
2. `.orca/talking.txt`（当前波 + 阻塞）
3. `.orca/status.md`（质量门快照）
4. `git log --oneline -15` + `git status`
5. codex 树 `.orca/talking.txt` 的「回执区」

## 7. 项目长期分工

- **main**（Claude）：架构 / 质量 / 逻辑 / 测试 / 前端 / 体验 / 发布 / 运维，兼收编
- **codex**（第二棵树）：安全 / 合规 / 风险域；承接主树派单（用户授权可越域）
- 两树间**不直接通信**，只经各自 `.orca/talking.txt` 留痕

## 8. 技术栈速查

- 后端：Python 3.12 + FastAPI + SQLite，`uv` 管理，事件溯源唯一写路径（28 类事件，`extra=forbid`）
- 前端：React 19 + Phaser 3 + Vite + Zustand + Vitest
- 测试：pytest（2982 条收集）+ vitest（138 条）
- 文档：`DESIGN.md`（v2.1 冻结）+ `docs/`（128 篇）

---

<!-- ============ 以下为归档索引，正文见 .orca/archive/memory-2026-10-21-full.md ============ -->

## 归档内容索引

本地归档（`.*/` 忽略，仅本机可读）：`.orca/archive/memory-2026-10-21-full.md`

| 内容 | 归档文件内位置 |
|---|---|
| M0–M6 各轮快照 | §56 起 |
| claude 主树历史（①） | 866–1148 行 |
| cline 树（②）— 树已不存在 | 1149–1235 行 |
| opencode 树（③）— 树已不存在 | 1236–1406 行 |
| codex 树（④） | 1407–1459 行 |
| pi 树（⑤）— 树已不存在 | 1460–1778 行 |
| kilo 树（⑥）— 树已不存在 | 1779–2811 行 |
| opencode 专属恢复卡 | 85–244 行 |
| 旧恢复卡（M6 收官态） | 245–860 行 |

**无本地归档时**：`git log -p -- .orca/memory.md` 可取回任一历史版本。

---

# ④ codex 树快照（权威来源：codex 树 `.orca/memory.md`；收编时原样并入）

【2026-10-21 DA-02｜历史读档核心链完成，已收编】DA-01 已独立提交 846a052；本次接真实物化链，临时世界展开/RNG 恢复与存档 tick 对齐，make_current 显式交接当前子线 + seq0 检查点 + 玩家 protected 游标，默认归档分叉不变。请求登记不确认，成功后才发 session_state/timescale/full_snapshot；清旧帧与旧 LLM 等待结果。事务失败保留原世界；提交后投影失败暂停、停止 AI 并拒写命令/存档，保留原无当前线诊断。真实 SQLite 红钉 2F 起步，补跨档决策/投影失败/时间尺/游标红后修绿；定向 79P，事务 43P，错误契约 55P。最终常规集显式排除 2 条既有缺地图素材用例后 2789P/131S/74D（408.25s），ruff/format/pyright 和 gen:protocol:check 全绿。主树 076ed21 不在本树，收编 main.py 时保留主树 P-2/P-4/P-6 恢复/还原代码；本次未重复实现它们。报告 docs/security/gameplay-integrity-audit-2026-10-21.md，日志 .orca/da02-*.log。

【2026-10-21 DA-01｜冷启动恢复完成，已收编】用户直接授权继续修审计缺口。build_loop 只在空库创世，按 is_current 恢复完整世界检查点/事件尾部；非空批次事件与内部检查点同事务落库，含时钟/战斗尺/混沌链/PCG64。重复创世拒绝启动，不删旧日志；无当前指针只留诊断面、停止推进。新增 12 条重启/谱系/回滚/行走回归；红 4F 及子线 seq0 红 1F→定向 41P，附 API/鉴权集 52P；常规集排除 2 条已知缺素材用例后 2774P/131S/74D（399.66s），ruff/format/pyright 全绿。全局 API 夹具隔离临时 world.db 并停用自动模型决策，人工世界夹具已改合法创世/完整快照。报告 docs/security/gameplay-integrity-audit-2026-10-21.md；日志 .orca/da01-*.log。

【2026-10-21 深度复检｜报告完成】基准 main@3cbcd8d 的独立源码快照，未 merge main/改主树/调用真模型。确认 8 组（2 P0+6 P1）：重启重创世污染日志、历史读档 head-only 与旧快照提前确认、资金/火场清零未重建、人物/中文货名目标不兼容、建筑表现跨分支残留、坍塌还原日志未应用实时碰撞、主角走 NPC 死亡删除、重启后主角双控制源。既有相关 62 项+同夹具地图对照 2 项通过；新增 5 条完整性回归全红。复现与 JSON 在 `.orca/audits/20261021-main-3cbcd8d/`。

## 收编踩坑（2026-10-21 merge codex）

- **`world_restore.flush_world` 与 P-6 `_with_structure_tile_restore` 必须叠加**：派生在前
  （`maintenance.observe` 会 pop REMOVED），然后整批交给 `flush_world` 写检查点。
  二选一都会丢东西——只走 `flush_world` 丢坍塌还原，只走 `flush_tick` 丢检查点。
- **codex 树的 `.orca/memory.md` 是旧全文副本**（2797 行），主树已瘦身到 118 行；
  合并时取主树版再人工并入 codex 新快照，不要盲目 `--theirs`。
- codex 树缺 `sim/content/assets/god-packs/taohuayuan-online/tiled-map.json`，
  两条地图确定性生成用例在其树内必失败——**主树有该文件**，合并后不成立。
