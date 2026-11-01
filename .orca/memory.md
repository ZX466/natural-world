# memory.md — 两树最小恢复卡

> 2026-10-25/26 多轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态（2026-11-01 第十五轮收编后）

- **main HEAD**：`28e8ac9`（第十五轮合并提交，双父 `17b4c94` + `47f9e80`）。
- **codex HEAD**：`47f9e80`（第十五轮实现），工作区干净，**无在途任务**。
- **协议**：**`1.14`**（第十轮挖深字段升级）；双落点同改
  （`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts::PROTOCOL_VERSION`
  ↔ `sim/tests/test_protocol_version.py::EXPECTED_VERSION` + README 徽章 + `shared/openapi.json`）。
  第十一～十五轮均未动协议字段（渲染、UI、持久层、音效、离线内部）。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单/架构/质量/收编复核/日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现、安全合规。
  - 只走各树 `.orca/talking.txt`；不直接对话。
- **远程**：origin/gitee 均在 `3603ecb`（**主树领先 7 提交未推**，推送仍由用户决定）。
- **在飞**：**无**。第十五轮已收编（`28e8ac9`）。
  未派：V3.5 内容包 / V4-3D。
- **第十五轮留给用户的四件事**（不是 codex 欠账，是**用户保留项**）：
  1. 音效主观听感（codex 明确没验，`manual_listening: pending user`）
  2. T5 完成率阈值定线（基线 1.0，**没设阈值**）
  3. soak 流失阈值定线（对照 0 / 危险 4.0，**常量仍是 0**）
  4. 真实 `world.db` 正式迁移（须先备份）
- **待人工验收**（9 条，已过 4 条，**剩 5/6/7/8/9 共 5 条**）：
  1. ~~DA-07 失能/恢复真模型长局~~ — **2026-10-31 用户验收通过**
  2. ~~V3 画面观感~~ — **2026-10-31 用户验收通过**
  3. ~~走路是否还飘（`INTERP_MS` 200）~~ — **2026-10-31 用户验收通过**
  4. ~~V4a 挖放观感~~ — **2026-10-28 已通过**
  5. V4b 三材料挖放观感（行囊土/石/木三行，为 0 不显示）
  6. 地形可走面观感：可走 820→3947 格，房子/河/树是否还挡得住
  7. **移动操作手感**：点击/长按/拖拽/键盘是否顺手
     （2026-10-29 曾因拾取器用错导致「完全动不了」，单测全绿但真机是死的）
  8. **土坎观感（第十一轮）**：1568 格隐形墙是否一眼可辨
  9. **前端画面（第十二轮）**：侧栏收起是否顺手、小屏是否还挤压世界

> **记录订正**：用户 2026-10-31 先发「1 2 3观感已验收」、随后「3都已验收」，
> 均指验收清单**第 1/2/3 条**。我最初误记为第 8/9 条，已改回。第 8/9 条**尚未验收**。

## 1. 门禁（2026-11-01 第十五轮收编后主树独立实测）

| 项 | 结果 |
|---|---|
| pytest `-m "not bench"` | **3061 passed** / 0 failed / 121 skipped（400.34s） |
| ruff check / format | clean（379 files） |
| pyright | 0 errors, 0 warnings, 0 infos |
| client typecheck / lint / prettier | EXIT 0 |
| client vitest | **337 passed / 47 files** |
| gen:protocol:check | EXIT 0（协议 1.14） |
| build_height_map --check | 逐字节一致 |
| build_block_atlas --check | 逐字节一致 |
| `tools/check_implementation_status.py` | 未发现缺口 |
| `uv lock --check` | 一致 |

> 第十五轮动的是 `sim/world/offline.py`（新）+ `sim/core/persistence/` + `sim/api/main.py`
> + 整个 `client/src/game/audio/`，故两侧全套必跑。
> 3061 − codex 自测 3056 = 5 条 = 主树第十四轮的 `test_schema_self_heal.py`（codex 分支不含那笔提交）。

## 1d. 收编复核纪律的一条实证（2026-11-01）

**codex 的交付回执会说谎，而且是无意的。** 第十五轮回执写「tsc、eslint、prettier 全过」，
主树复跑 `npm run typecheck` 实为 **EXIT 2**：

```
src/game/audio/__tests__/world-audio.test.ts(48,18): error TS2345:
  Argument of type '{ unlock: Mock<Procedure | Constructable>; ... }'
  is not assignable to parameter of type 'AudioBackend'.
```

修法按仓库既有约定（`client/src/game/__tests__/runtime-map.test.ts:14,18` 的
`vi.fn<签名>()`）给每个 mock 显式签名 + `import type { EffectId }`。复跑 EXIT 0。

**教训**：`npm run typecheck 2>&1 | tail -3; echo $?` 报的是 **tail 的退出码**，
不是 npm 的。必须 `cmd > log 2>&1; echo "EXIT:$?"`。这条对任何管道都一样。

## 1b. 已关闭但代码不支撑的承诺（主树 2026-10-31 审计，**新对话先读**）

六里程碑 2026-10-05 宣告收官（`abbe765`），下列五条实测当时是空的。**这些不是 bug，
是「宣告了但没做」**，任何新方向裁定前必须知道。**2026-11-01 第十五轮后：四条已有实现
或取证，只剩残余项**（音效主观听感、T5/soak 阈值定线、真实库迁移仍归用户）。

| 缺口 | 实测证据 |
|---|---|
| **音效** | ~~全仓 0 个 `.mp3/.ogg/.wav`、0 处 `this.sound`~~ → **2026-11-01 第十五轮已收编（`28e8ac9`）**：Phaser 3.87 内置 WebAudio，`client/src/game/audio/{synth,world-audio,index}.ts`；零新 npm 依赖、零资产文件、协议不变。默认静音 25% 音量、8 音轨上限、8 格衰减、120ms 节流；只消费可观测的 `voxel_edits`/actor 位移/`combat_event`/`lights`，不碰独白。**仍未做**：用户亲听验收；真实火场音效外发（用户裁定为独立缺口） |
| **`npc_health`** | ~~有模型/迁移/读路径，但**零写入**~~ → **2026-10-31 第十四轮已收编并修好启动自愈（`1d4bfa9`）**：事件→总线→同事务健康投影→感知触发→陈默闸门/记忆已接通；6 条内容种子；真实 `world.db` 副本启动实测 code 列补齐、events 187857 零丢失。**仍未做**：真实库正式迁移（需备份）、历史锚点 fork 的 severity/active 还原、每日严重度演进、第三方浮现见证链、`npc.lod_change` 持久化 |
| **离线推进** | ~~`sim/world/offline*.py` 不存在~~ → **2026-11-01 第十五轮已收编（`28e8ac9`）**：`sim/world/offline.py::advance_offline` 复用现有 `TickLoop`；墙钟只在启动边界采样一次（`_offline_wall_time`）；水位取 `snapshots/branches.created_at`（控制元数据，不进事件流与 `state_hash` ⇒ **C5 安全**）；批上限 240 tick、`MAX_CATCHUP_REAL_SECONDS=4.0`、上限 1 游戏日（`TICKS_PER_GAME_DAY=86400`，超限记 `offline.capped`）；同墙钟重启零补跑。主树实测：60s→3600 tick、30 天→86400 tick 且丢弃 2590560s、两遍重放 hash 相同、玩家档零写。**仍未做**：真实 `world.db` 上跑一次真实停机补偿（需备份） |
| **T5 差事完成率** | ~~`errands_rate.py` 明写「本轮不设阈值」~~ → **2026-11-01 第十五轮已取证（`28e8ac9`）**：10 seed × 4 用例 = 40/40 通过，完成率 **1.0**（中位与最差都是 1.0），确定性复测相等，全套 123.82s。**阈值仍未设** —— 定线是用户的事，`errands_rate.py` 仍无硬阈值。基线 `.orca/audits/t5-baseline-2026-11-01/baseline.json` |
| **soak 实体流失** | ~~`SOAK_ENTITY_LOSS_PER_GAME_DAY = 0`，从未抬高~~ → **2026-11-01 第十五轮已取证（`28e8ac9`）**：对照场景 3 游戏日 **0 流失**，危险场景（每小时真实 `CombatLedger` 结算 + `npc.death`）**4.0 实体/游戏日**（12 死 / 3 天），确定性复测相同。**常量仍是 0** —— 定线是用户的事。数据 `.orca/audits/soak-loss-2026-11-01/measurement.json` |

**另一个口径缺口**（不算未实现，但要注意）：战斗表现层协议有 `Hit`/`Projectile`
schema，`ws.py:1619` 只发 `posture_visual`，客户端 `ws.ts:216` 只计数——
**用户已明确裁定不做**，别再提案。

## 1c. 用户已裁定**移除**的功能（不是缺口，别再提案）

审计时最容易误判的一类：代码里「找不到」的功能，有些是**用户主动砍的**，不是没做完。
下面这些**不要再当成缺口提**，也不要再排期：

| 已移除 | 裁决时间 | 落地 | 现在的状态 |
|---|---|---|---|
| **迷雾 / 空间未知** | **2026-10-12 用户裁决**（playtest-4） | `0363769`（协议 1.7→**1.8** 减法变更） | 内核不再产 `fog.reveal`；WS `fog` 键与 `FogState` schema 删；前端 fog 罩全撤；`m3_fog`/`m4d17_fog`/`fix_fog_spawn` 三个测试文件随葬 |
| **战斗表现层**（弹幕/翻滚/受击） | 用户明确裁定不做 | — | 协议有 `Hit`/`Projectile` schema，只发 `posture_visual`；客户端只计数 |
| **计划看板**（UI 面板） | 2026-10（第五轮） | `bb871f2` | 面板删除；`PlanDelta` 协议与 `uiStore.plans` **保留**（只是不显示） |

**迷雾的残留（合法，不要「清理」）**：
- `EventKind.FOG_REVEAL` + `FogRevealPayload` + `PAYLOAD_MODELS` 登记 + `_apply_fog_reveal` no-op
  —— **C4 事件不可销毁**：老日志里有 `fog.reveal` 行，删 kind 会让历史流重放直接炸。
  `sim/core/world.py:269` 的 docstring 已写明「no-op 即重放安全」。
- `sim/tests/test_m6_content_events.py` 仍锁 `FOG_` 前缀 —— 它锁的是**事件登记存在**，
  不是迷雾功能存在。删掉这条测试才是错的。
- `DESIGN.md` §13/§17 仍列「空间迷雾」（**冻结基线不回写**，见 §19/§20 的冻结声明）——
  DESIGN 是历史契约，不随裁决改；真相在 `docs/api/versioning.md` 的 1.8 行。
  真实库 `world.db` 里 `fog.reveal` 事件 **0 条**（生产从没发过）。

## 2-newest. 第十～十五轮（2026-10-29 → 11-01）

全部已收编，主树独立复核，**无在飞任务**。

**第十五轮｜音效 / 离线推进 / T5 基线 / soak 取证（`47f9e80` codex → `28e8ac9` 合并）**

四条「宣告收官但没做」的缺口，本轮补齐可验证部分：

- **音效**（`client/src/game/audio/`）：Phaser 3.87 自带 WebAudio，零新 npm 依赖、
  零资产文件。`synth.ts` 用确定性 xorshift 噪声合成 5 种效果（step/dig/place/combat/
  collapse）+ fire 循环氛围；`world-audio.ts` 默认 `muted: true, volume: 0.25`、
  8 音轨上限、8 格距离衰减 `1/(1+d*0.45)`、120ms 节流、`generation` 守卫迟到解锁、
  `audible` 门（connected && hasSnapshot && unlocked && !muted）。只消费
  `voxel_edits`/actor 位移（≤4 格）/`combat_event`（按 rtoken+exchange+posture 去重）/
  `mirror.lights kind==='fire'`；**明确不消费独白/thoughts/tasks**（C3 沉浸规则）。
  `SettingsPage` 加「世界音效」开关；`WorldScene` 在 pointerdown/键盘解锁、blur 暂停。
- **离线推进**（`sim/world/offline.py`）：见 §1b 行内详情。关键设计是**墙钟只采样一次**
  且**水位存在控制元数据里**（`snapshots/branches.created_at`），因此不进事件流、
  不进 `state_hash` —— 这是它能在 C5 下成立的原因。
- **T5 / soak**：只取证不定线，见 §1b。

**主树复核发现**：codex 回执称 tsc 全过，实测 `EXIT 2`（详见 §1d）。已修并复跑。
自写 16 条不变量探针（`.orca/audits/round15-2026-11-01/main-tree-probe.py`）16/16 通过。

**第十四轮｜`npc_health` 写入路径（`5d937f0` RED → `5a48f7c` 实现 → `1d4bfa9` 启动自愈）**

健康档此前有模型/迁移/读路径但**零写入**。本轮接通：`NPC_HEALTH_CHANGED` 事件 →
`_apply_projection_event` → `npc_store._project_health`（同事务 upsert，未知 NPC /
改类别整批回滚）→ 感知触发 `evaluate_triggers` → 陈默闸门与记忆；6 条内容种子
（2 可见 4 隐藏）；坍塌给幸存者/陈默落可见旧伤。`0015_health_code` 新增 `code` 列
（回填旧 id 文本、NOT NULL、`(branch,npc,code)` 唯一），`attr_id` 改为
`f"{npc_id}.health_{code}"`，fork 复制 `code` 修跨分支漂移。协议仍 **1.14**。

**主树复核发现的阻断缺陷**（codex 自测没撞上，因为它用临时库）：主树 `world.db`
是 `create_all` 建出来的，**没有 `alembic_version` 表**，而 `create_all`
**不给已有表加列** ⇒ `npc_health.code` 永远补不上，真实存档启动直接
`OperationalError: no such column`。修法 `ensure_schema()` 三分支自愈 +
`script_location` 绝对化（抗 `chdir`）+ `WORLD_DB_URL` 用完还原。真实库副本实测
code 补齐 / events **187857 零丢失** / 6 种子行 / 版本 `0015_health_code`。

**第十三轮｜快照治理（`1fd362f` RED → `92fbc1b`）**

DESIGN §12 三条承诺实测全部不符：每 1000 tick 一份 → 实测每 **9.1 tick** 一份
（3946 份 / 36001 tick）；「仅留最近 8 份热 + 每日首份」→ 全仓**零**删除语句；
「abandoned 整体冷归档」→ `is_cold` **从未**置 True。根因是 `846a052`（2026-10-21
崩溃恢复）把落库改成 `flush_world`，事件 + 完整检查点同事务 → 每帧有事件就写一份。
**该改动本身是对的**（解决重启丢状态），缺的是保留策略。

落地：新增 `sim/core/persistence/snapshot_policy.py`（`prune_hot_snapshots` /
`mark_branch_snapshots_cold`，用调用者 session、不自行 commit），接入 `flush_world`
与 `SqlEventStore.write_snapshot`；`fork_from_anchor` 在**真实 head 封存**父线时同事务
整体标冷。**不删 events 一行**（C6），不改 gzip 内容，无迁移/新依赖/新公共方法。

**主树独立复算（不看 codex `acceptance.json`）**：

| 项 | 主树实测 |
|---|---|
| 同日写 1/8/9/10/100/250/1000 次 | 行数 **1/8/9/9/9/9/9**，events 1001 行不动 |
| 跨 3 日 1100 次写 | **11 行**（热 11），日首 tick `0/86400/172800`，最新 8 条 `172803..172810` |
| head-fork 封存 | 行数 **9→9**，全冷，seq/tick/gzip 逐位相同，events 逐行相同，子线全热 |
| 删中间快照后恢复 | `cutoff_seq=38` 已被删；从 tick 0 回放，`WorldCheckpoint` JSON **逐位相同** |
| 无合格快照 | 全量重放 **逐位相同**，快照 0 份 |
| **真实 `world.db` 副本** | **3946 行 → 9 行**，events **187857 行一行未动**，恢复 payload 3768B **逐位相同**，prune **47ms** |
| 真实 `fork_from_anchor(kind="anchor")` + 被裁快照 | 历史点恢复**逐位相同**，父线仍 `active`，冷行 0（anchor-fork 不标冷） |
| 稳态 flush 开销 | 带清理 **4.31ms** / 不带 **3.55ms**（+0.76ms），单独 prune **0.97ms** |

> 恢复耗时 base vs pruned 是噪声（2.64/3.05/2.73s vs 2.20/2.76/2.65s）——两条路径都
> 命中同一最新快照 tick 36001，窗口相同。**删旧快照只影响「从更早游标读档」的耗时**。

**未做（诚实边界，已写进 `docs/data/event-sourcing.md`）**：冷归档只是 `is_cold` 标记、
仍留主库；不导出独立 SQLite；不批量迁移既有存档；不声称主库已达 <2GB 硬上限。
活动分支的旧热行在下一次快照写入时才收敛（生产库当前 3946 行，首 flush 后 → 9 行）。

**第十轮｜悬空修复（`7b1d559` RED → `1895014`），协议 1.13→1.14**

用户真机报「挖完建筑物悬空，人物悬在半空」。根因：服务端挖完发
`tile_changed(gid = 静态 gid)` → 客户端判可走；客户端又本地推算渲染高度 −1。
实测挖一次后 **4562 格**违反 `walkable ⇒ h==1`（2994 格可走却画 2 层高 = 悬空；
1568 格可走却画 0 = 陷地下）。

用户裁决：**服务端记挖深，挖到 h=1 才可走**；**跳跃不做**。落地：`VoxelEdit` 加
`height`（结果高度 0..3 必需）、`VoxelEditedPayload.height` 可选（老事件回退推算）、
`rebuild_tile_map` 重放 `VOXEL_EDITED` 跟踪高度、`walkable = (tile_id != 0 and height == 1)`。
主树独立复核挖 0/1/2/3 轮：**3947 / 8326 / 11320 / 11320，0 违规**。

**第十一轮｜土坎视觉区分（`46ce58e` RED → `6aa0528`）**

用户报「地图仍有不可走的无障碍区域」。根因：`iso-terrain.ts` **完全不读
`map.collision`**，只按高度画 → 阻挡但 h=1 的土坎与可走 h=1 地面渲染完全相同。
实测 **1568 格隐形墙**，其中 269 格 4-邻接可走格（必撞）、91 格是「两片可走区之间的
假通道」、真实出生点 (100,53) 31×31 内 135 格。

**不能改成可走**：`_MATERIAL_BY_HEIGHT[1] = earth` 且 `place` 只对可走格生效
（`voxel_exec.py:124`）—— earth 唯一来源就是「阻挡的 h=1 格」。改成可走 = earth 断源
= 回到「只挖不放」（实测该方案仍留 142 格、土源 730→524）。**故只改渲染**。

落地：`bank = (effectiveHeight == 1) && (collision == 0)` → 画三道明暗土色短斜纹
（`#2c1b10` / `#f1d793`，亮度差 185.8，3.5x 下外纹 7px / 亮芯 3.5px），与「挖过的疤」
（内嵌深色菱形）互斥；retained-set 池化，`changed == false` 的帧零重建。
顺带把 `iso.ts::VoxelEdits` 与 `iso-terrain.ts::Edits` 两条类型路径收敛成
`Pick<VoxelEdit, 'height' | 'action'>`。主树独立复核 **1568 全标 / 0 误标 / 0 漏标**。

**第十二轮｜前端画面优化（用户直派，`bc6739c` RED → `7f89584`）**

原双常驻侧栏压垮小屏、canvas 宽 0 且报 3 次 WebGL framebuffer 错误。改为单一可收起
手札/存档侧栏（桌面默认手札、存档按需，小屏默认关闭、打开时覆盖而不挤压世界）。
世界宽 1440×900 **872→1152（+32.11%）**、1024×768 **456→736（+61.40%）**、
390×844 **0→390×688**。CanvasHost 补 ResizeObserver + `ready` 同步 + 卸载清理。

> **坑（已进 §3）**：Phaser RESIZE 模式必须用 `game.scale.setParentSize`；
> 只调 `scale.resize` 会在 refresh 时从旧 parentSize 回写，手机留下约 46px 底部空隙。

**主树未复核项（诚实说明）**：第十二轮 codex 用真浏览器截的 4 张 PNG 与
`verify-layout.cjs` 结论，主树只核对了 JSON 数值与源码 diff，**没有自己开浏览器**。

## 2-new. 第九轮（2026-10-29）移动操作重做 —— codex 交付 + **主树修掉一个 P0**

用户四症状里的「移动特别局限」，**地图侧已由第八轮修完**（可走 820→3947，出生点 100% 可达）。
第九轮只做**操作侧**，codex 交付 `f74f4af`（RED 测试）+ `04e2175`（实现），主树 ff 收编零冲突。

**codex 落地**：可走格短/长按即走（消死区）、拖拽合并最新目标 100ms 限频、WASD/方向键
逻辑八向、`goalMarker` 到达/换目标/取消即清、`requestMove` 加 `wsStatus` 守卫、
可达性 BFS 与 sim 同八邻禁穿角、墙/断路/断线给戏内提示。新增 `client/src/game/movement.ts`。

**主树收编后发现并修掉 P0「人物完全无法移动」**（`b0d4341`）：

根因——codex 把移动拾取从地面平面换成了 `pickVoxel`，而那是**为编辑设计**的拾取器
（`h>=2` 优先，因为玩家看到的高方块就是要挖/放的那个）。等距投影下 h=3 方块与它
**斜后方 2 格**的 h=1 地面顶面菱形**逐像素重合**（x−y 同、x+y 差 4、高度差 2×ISO.HH），
于是「点空地」被判成「点房子」→ `movementFailure` 全拒 → 一个移动帧都发不出去。

真实地图实测（3947 个可走格，逐格点自己顶面中心）：

| 拾取 | 命中自己 | 落阻挡格 |
|---|---|---|
| 第八轮旧版（纯地面平面） | 0% | 0 |
| codex `pickVoxel` | 80.7% | **763（19.3%）** |
| `b0d4341` 的 `pickGround` | **100%** | 0 |

出生点 13×13 邻域 26 个可走格里 codex 版只有 5 格点得中、**21 格落阻挡**；
十个地标邻域最差 15%（stream_bridge）。

**修法**：新增 `pickGround`（`voxel-picking.ts`）——不做遮挡判定，只把屏幕 y 下移
`WALK_HEIGHT × ISO.HH` 再反投影；单向不变量 `walkable ⇒ h == EARTH` 保证可走面恒在这一层，
故是**精确**反投影而非近似。防御性拒绝高度非 EARTH 的格。`WorldScene` 一次按下同问两个
拾取器：`digTarget`（编辑）、`ground`（移动）；能挖则起计时器，短按抬手仍落回移动。
拖拽与键盘同改走 `groundTarget`。

**教训（已进 §3）**：**单测全绿 ≠ 真机能动**。codex 交付时 290 个前端测试全过、门禁全绿，
但真实地图上 19% 的可走格根本点不中——因为测试夹具造的是「可走格与高块不重叠」的
玩具图，而真实地图上重叠是常态。凡涉及拾取/投影的改动，**必须用真实地图数据实测命中率**。

## 2a. 第八轮（2026-10-29）地形同源重建 —— main，已提交 `37e6a51`

**用户症状**：障碍物可以穿过 / 移动闪现 / 移动特别局限 / 只挖不放。

**根因（三条各自独立，但都指向同一个结构性缺陷）**：
1. 源包 `Collisions` 层与 `World Blocks` **逐字节相同**，只画了三条贯穿建筑与河道的
   直线带（820/14000 = 5.9%）。碰撞真相是它，渲染高度却由另一套 HSV 分类器独立推导
   ⇒ **493 格可走却画成实心**（穿模）、**5752 格画成平地却不可走**（移动局限）。
2. `place` 门槛是「目标格必须可走」，而可走面只有 820 格的窄带 ⇒ 想放东西几乎必然
   越界拒绝；即便成功，行囊里也没有 earth。
3. 客户端 `INTERP_MS=250` **正好等于**行走节拍 250±15ms——滑行永远差一点没走完就被下一格
   重置起点，逐格累积落后（实测 57% 帧落后 >0.5 格，最大 1.20 格）⇒ 视觉「闪一下」。

**落地**：
- 新增 `sim/content/terrain_class.py`（唯一分类源）：逐格 16×16 HSV 占比
  （walk/canopy/water）→ 5×5 均值滤波 4 轮 → 只留最大 4 连通块 → 作者真值挖通道。
  一次 `classify()` 同时产出 `linhe-town.json` 的 collision 位、`linhe-height.json` 的 h、
  以及图集基色档。
- `build_height_map.py` 改为**委托** `build_god_town.derive_terrain`，不再自己分类；
  `render()` 成为唯一写出路径（两处共用）。`build_block_atlas.py` 改为直接读
  `linhe-height.json` 的 h 值，不再依赖 `classify_height`。
- **土坎**（`_is_earth_bank`）：阻挡但瓦片本身像土面（**逐瓦片原始** walk ≥0.45，不平滑——
  平滑会把屋顶拉成土色）且 4 邻可走 ≤2 的格标 h=1。**这是 earth 的唯一来源**：
  若把土坎也判 stone，行囊永远挖不出土，`place` 永久缺料 = 「只挖不放」。
- 不变量**单向**：`walkable ⇒ h==EARTH`，反向不成立（土坎可挖不可走）。
  **做成双向会立刻回归「只挖不放」**（阻挡 h==1 变 0 格，实测已验证）。
- `INTERP_MS` 250 → 200（节拍的 80%，留抖动余量；平均落后 0.57→0.43 格，最大 1.20→1.00）。

**结果**：可走 820 → **3947**（28.2%），1 连通块，出生点可达 3947/3947，
90/90 出生候选、10/10 地标可走，高度档 {0:1112, 1:5515, 2:4379, 3:2994}，土坎 1568。
端到端实测：出生点旁 3 格挖土坎得 earth 1 → 平地放置成功。

**连带修的测试**（旧坐标落在新分类的阻挡格上）：`test_e1_talk_to`（走廊移到行 51）、
`test_m4d12_disperse`（不再把 50 NPC 塞同格，改用生产出生路径）、
`test_m4d20_motion`（走廊移到 (105,56)→(111,56)，那里才有垂直抖动空间）。

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
- **地形只有一个真相源**（`sim/content/terrain_class.py`）。碰撞位、渲染高度、图集基色档
  必须同一次 `classify()` 产出。历史上碰撞取源包 `Collisions`（三条直线带）、高度另跑一套
  HSV 分类器，结果是 493 格可走却画成实心、5752 格画成平地却不可走。
- **「可走 ⇒ 土面」是单向不变量**，反向不成立：土坎（阻挡但材质是土）标 h=1，
  是 earth 的唯一来源。**做成双向 ⇒ 阻挡 h==1 归零 ⇒ earth 永不可得 ⇒ 只挖不放**
  （本轮亲自踩过一次并实测复现）。
- **土坎判据用逐瓦片原始 walk 占比，不平滑**：平滑会把屋顶拉成土色，屋顶与田垄就分不开了。
- **客户端插值窗口不得等于服务端节拍**：`INTERP_MS` 曾正好 250 = 行走 250±15ms，
  抖动使滑行永远差一点，逐格累积落后 → 视觉闪现。取节拍的 ~80% 留余量。
- **移动拾取与编辑拾取必须是两个函数**（`pickGround` vs `pickVoxel`）。等距投影下
  h=3 方块与斜后方 2 格的 h=1 地面顶面**逐像素重合**；用编辑拾取器判移动，真实地图
  19.3% 的可走格会被判成阻挡格（实测 763/3947），出生点邻域 26 格里 21 格如此 →
  「人物完全无法移动」。`voxel-picking.ts` 的 docstring 早就写明这个契约，别违反。
- **单测全绿 ≠ 真机能动**。玩具夹具（4×4、可走格与高块不重叠）测不出投影重合。
  凡改拾取/投影/坐标换算，**必须拿真实地图数据实测命中率**（.orca/tmp 写过一次性探针
  再删即可），否则会在「全绿」状态下交付一个死功能。
- **测试夹具不得造违反生产不变量的格**：`iso-live` 曾让 (2,1) 可走却 h=3，
  生产里不可能（`walkable ⇒ h==1`）。夹具违规格会掩盖真实缺陷、也会让修好后误报红。

**前端**
- `Phaser.Scene` 已有 `renderer` 字段，构造参数用 `renderMode`。
- CanvasTexture 不要按颜色/高度开；用固定图集 + tint。
- iso 覆盖层深度集中在 `ISO_DEPTH`（名牌 30 万+/气泡 31 万+/雨 40 万/夜幕 400001）。
- **走环判据要按「是否在动」而不是「是否换格」**：插值期间不换格，但人在动。
- **镜头目标必须与人物同一插值进度**：喂逻辑格 + 再叠缓动 = 双重滞后 = 飘。
- **渲染层不读 `map.collision` 会造成「隐形墙」**：`iso-terrain.ts` 只按高度画，
  阻挡 h=1 与可走 h=1 渲染完全相同（2026-10-30 实测 1568 格）。任何新增「地面长相」
  的渲染都要问一句：这一格能不能走？不能走就得给标记。
- **Phaser RESIZE 模式必须用 `game.scale.setParentSize`**，只调 `scale.resize` 会在
  refresh 时从旧 parentSize 回写（手机留下约 46px 底部空隙）。容器尺寸走
  ResizeObserver，`ready` 后补一次同步，卸载要 `disconnect()` + `off()` + `destroy(true)`。
- **`VoxelEdits` 只有一条类型路径**：`Pick<VoxelEdit, 'height' | 'action'>`
  （`iso.ts` 导出，`iso-terrain.ts` 直接复用）。曾出现 `iso.ts` 定义 `{height}`
  而 `iso-terrain.ts` 走协议 `VoxelEdit`（带 `action`）两条路径，`tsc` 不报错但
  「挖过的疤」判定会静默失效。

**持久层**
- **`create_all` 不给已有表加列**（第十四轮血案）：`Base.metadata.create_all` 只建**缺失
  的表**。本项目 `world.db` 就是它建出来的（**没有 `alembic_version` 表**），于是任何
  「新增列」的迁移（如 `0015` 的 `npc_health.code`）**永远补不上**，真实存档启动直接
  `OperationalError: no such column`。测试用临时/fresh 库天然带新列，**永远撞不上**。
  → 启动必须 `init_database` 之后再 `ensure_schema(engine)`（三分支：无版本且结构已
  匹配只 `stamp`；无版本且结构落后 `stamp` 基线再 `upgrade`；有版本直接 `upgrade`）。
  **「结构已匹配」分支不能省**：新 `create_all` 库已含新列，直接 stamp 基线再 upgrade
  会撞 `duplicate column name`。
- **`alembic.ini` 的 `script_location` 是相对 CWD 的**：本仓库大量测试
  `monkeypatch.chdir(tmp_path)`，直接 `Config("alembic.ini")` 会去 tmp_path 找迁移目录，
  报 `CommandError: Path doesn't exist`。→ 构造 Config 后必须
  `set_main_option("script_location", 绝对路径)`。
- **`alembic/env.py` 调 `asyncio.run`**：不能在运行中的事件循环里直接跑，必须
  `asyncio.to_thread`。`env.py` 从 `WORLD_DB_URL` 读地址，**用完要还原**，否则污染进程环境。
- **快照可删，事件不可删（C6）**：热保留删的是 `snapshots` 行；`events` 与 `is_cold=1`
  的快照一行不动。两者语义不同，别把「热保留」也做成 `is_cold` 标记。
- **删中间快照不会破坏恢复**：`restore_world` 沿祖先回退到更早的合格快照，再重放；
  没有任何合格快照时走 `expand_world({}, history)` 全量重放。**只增加耗时，不改正确性**
  ——真实库副本实测 3946→9 行后恢复 payload 逐位相同。
- **保留集是「最近 8 份热 ∪ 每日首份」**，可重合，故热行上界是 `8 + 覆盖日数`，
  不是恒定 8。同 tick 可有多份快照（主键是 `(branch_id, seq)`），日首份要用
  `row_number() over (partition by tick//86400 order by tick, seq)` 取一条，
  不能按 `MIN(tick)` 全保。
- **`prune_hot_snapshots` 先 `session.flush()`**：`autoflush=False` 的工厂里新快照
  否则对查询不可见。策略函数用**调用者 session、不自行 commit**，失败随事务整体回滚。
- **只有 `Branch.status == 'active'` 才授权删除**：缺失分支行或 abandoned 分支的旧热行
  一律保留（legacy 数据不能因为「看着是热的」就被清掉）。
- **head-fork 封存父线才标冷，anchor-fork 不标**：历史点读档不能把玩家正在跑的线
  变冷。判据是既有的 `parent_status == "active" and kind == "head"`。
- **清理开销实测 +0.76ms/flush**（带清理 4.31ms vs 不带 3.55ms，60 tick/s 下可忽略）。
  若将来 flush 频率再涨，可考虑「仅在行数超阈值时才跑」——本轮**未改**。

**离线推进 / 收编纪律（第十五轮）**
- **墙钟只能存控制元数据**：`snapshots.created_at` / `branches.created_at` 是墙钟，
  但它们**不进事件流、不进 `state_hash`** ⇒ 用它算离线时长不破 C5。反过来，任何墙钟
  值一旦写进 event payload，C5 立刻破。离线路径**只在启动边界采样一次**（`_offline_wall_time`），
  循环里不再取时间。
- **离线推进必须复用 `TickLoop` 的既有节奏**，不要另写一套推进器：批上限
  `_MAX_TICKS_PER_FRAME=240`、`MAX_CATCHUP_REAL_SECONDS=4.0`、1x=60 tick/秒、
  战斗尺度 1 tick/秒；每批之间 `await asyncio.sleep(0)` 让出事件循环。
- **cap 是 1 游戏日（`TICKS_PER_GAME_DAY=86400`）**，超限记 `offline.capped` 并丢弃秒数。
- **重启幂等靠水位**：`last_recorded_at` 读最新 `Snapshot.created_at`，回退到
  `Branch.created_at`。同墙钟再启动 ⇒ `offline_seconds=0` ⇒ 零补跑（主树实测）。
- **`advance_offline` 会强制切到 1x 再还原**，所以调用前必须记下当前倍速。
- **收编合并可能不能用 ff**：codex 从旧基线开分支时，主树的新提交它没有 ⇒
  用 `git merge --no-commit --no-ff` 并逐个解冲突。解完**必须复查主树侧新增章节
  还在**（本轮 §1c 就在解冲突后仍被误判为丢失，实际是没 stage）。
- **管道里的 `$?` 是管道最后一个命令的**：`cmd 2>&1 | tail -3; echo $?` 拿到的是
  `tail` 的退出码。要判真实结果必须 `cmd > log 2>&1; echo "EXIT:$?"`。
  **本轮就是靠这条抓到 codex 回执误报的 tsc 失败。**

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

1. 本卡 §0（当前状态）+ **§1b（已关闭但没做的承诺）** + **§1c（用户裁定移除的功能，
   不是缺口）**——后者防的是「把砍掉的功能当没做完，又去重做一遍」。
2. `git log --oneline -10` + `git status`，两树各一遍。
3. 两树 `.orca/talking.txt`（**已精简到 ~70 行，只有当前波**）。
4. `docs/README.md` + `docs/dev-workflow.md`。
5. 需要历史细节才查 §2-newest / §3 / `git log`。

## 5. 分工与技术栈

- 主树：架构/质量/测试/前端/发布/收编；codex：复杂实现、安全合规。
- Python 3.12 + FastAPI + SQLite + uv；React 19 + Phaser 3 + Vite + Zustand + Vitest。
- 文档真相源：`shared/openapi.json`、ORM/迁移、`docs/` 活文档。

## 6. ① Claude｜新对话恢复快照

【2026-11-01 第十五轮已收编 `28e8ac9`｜无在途任务】codex `47f9e80` 以
`--no-ff` 合并（codex 分支不含主树第十四轮 4 个提交，ff 不可用），仅
`.orca/memory.md` §7 一处冲突。主树独立复核：pytest **3061P/0F/121S**（400.34s，
= codex 自测 3056 + 主树自愈测试 5）、ruff 379 files、pyright 0/0、client
tsc/eslint/prettier EXIT 0、vitest **337P/47F**、两资产 `--check` 逐字节一致、
`uv lock --check` ok、`gen:protocol:check` ok、`check_implementation_status.py` 无缺口。
**发现 codex 回执误报**：`npm run typecheck` 实际 `EXIT 2`（`world-audio.test.ts:48`
TS2345），已按仓库 `vi.fn<签名>()` 约定修复。自写 16 条不变量探针 16/16 通过。
复跑 codex 两份取证脚本数字一致（T5 40/40 率 1.0；soak 对照 0 / 危险 4.0）。
**留给用户**：音效亲听、T5 与 soak 阈值定线、真实 `world.db` 正式迁移（需备份）。

【2026-10-31 第十四轮已收编 `1d4bfa9`｜历史】`3603ecb..5a48f7c` ff 收编零冲突；
主树独立复核发现并修复阻断缺陷：**`world.db` 由 `create_all` 建出（无 `alembic_version`），
`create_all` 不给已有表加列 ⇒ `0015` 的 `npc_health.code` 永远补不上，真实存档启动即
`OperationalError`**。修法 `ensure_schema()`（三分支自愈：新库只 stamp、老库 stamp 基线再
upgrade、有版本直接 upgrade；`script_location` 覆盖绝对路径以抗 `chdir`；环境变量用完还原），
启动时调用。真实库副本实测：code 补齐 / events 187857 零丢失 / 6 种子行 / 版本 0015；
异目录 CWD 同样通过。门禁 pytest 3037P/121S/0F、Pyright 0E/0W、client 321P/44F 全绿，
协议仍 1.14。**真实 `world.db` 正式迁移尚未执行**（现在启动会自动升级，需一次备份确认）。

【2026-10-31 第十四轮已派 `671931c`｜历史】用户裁定走 `npc_health` 写入路径、深度端到端，
已写进 codex 树 talking。**派单前主树实探出三个隐藏事实**（不在 §1b 原表里）：
① 读链路在生产中断（`main.py:439` 丢弃 `_hidden_states`，`npc_events_for_tick` 无该参数）；
② `build_default_bus()` 缺 6 个 handler（含 4 个 `matter.*`），接线即崩，主库不炸只因
`matter_state`/`structures` 均为 0 行；③ `attr_id` 用 DB 自增派生、fork 不克隆 `id` ⇒
跨分支漂移，而 evidence 按它匹配。派单含 `code` 列（迁移 `0015`）修法。**协议保持 1.14**
（此前选项里写「预计 1.15」是错的）。收编复核重点见 talking。

【2026-10-31 推送 `671931c`｜无在途任务】用户授权推送，6 个提交双远端直连成功
（origin 直连绕代理、gitee 直连）。

【2026-10-31 第十三轮收编完成 `317460b`｜无在途任务】快照治理 ff 收编零冲突
（`1fd362f` RED → `92fbc1b`）。主树独立复核 pytest 3012P/0F/121S、vitest 321P/44F、
并在真实 `world.db` 副本上实测 **3946→9 行、events 一行未删、恢复逐位相同**。
协议仍 1.14。**两树 talking 已精简**（556 行 → 138 行，只留当前波）。

- **开新对话只需知道**：① 主树 `28e8ac9`、codex `47f9e80`（已收编）、无在飞任务、门禁全绿；
  远程停在 `3603ecb`（主树领先 7 提交未推，等用户决定）；
  ② 待**肉眼**验收 9 条，**7/8/9 优先**（见 §0）；**主树全程没开浏览器**，
  第十二轮的观感只有 codex 的截图证据；
  ③ **§1b 的承诺缺口**：`npc_health`（第十四轮）、音效/离线推进（第十五轮）已有实现；
  **T5 与 soak 只取证、阈值仍空**（第十五轮）；音效**未亲听**——别以为 M0–M6 收官
  就等于都实现了；
  ④ **不变量必须单向**（`walkable ⇒ h==EARTH`），做成双向会立刻回归「只挖不放」；
  ⑤ **移动拾取 ≠ 编辑拾取**，合成一个会在真实地图上死掉 19% 的可走格；
  ⑥ **单测全绿 ≠ 真机能动**，改拾取/投影必须用真实地图实测命中率；
  ⑦ **快照可删、事件不可删**：热保留删的是 `snapshots` 行，`events` 与冷快照一行不动（C6）；
  ⑧ **墙钟只能存在控制元数据里**：离线时长靠 `snapshots/branches.created_at`，
     绝不进事件 payload / `state_hash`，否则 C5 立刻破（第十五轮的设计前提）。
- **远程**：origin/gitee 均停在 `3603ecb`；主树领先 **7 个提交**（第十四轮 3 + 第十五轮 4）
  **未推**。推送仍是用户决定，不自动推。
- **配置目录**：维持用户 10-26 裁定「不进 git、不推远程、本地须存在」；主树不建 `.pi`。
- **浏览器**：仅用户明确要求时用，路径 `C:\Users\zx198\AppData\Local\ms-playwright`。
- **全局 git 邮箱**：`zx19836980213@outlook.com`（2026-10-31 实测，`dev-workflow.md`
  原记的 `223049848+ZX466@users.noreply.github.com` 已过期）。
- 本轮教训已进 §3：`.orca/talking.txt` 必须保持未跟踪，否则 ff 会覆盖派单；
  **派单里的坐标/数字必须来自代码实测，不能拿 `spawn_candidates` 当运行时出生点**。
- 第十三轮教训已进 §3「持久层」：**收编时在真实库副本上验证，不要只在内存库自测**。
  codex 的 `world.db`（0 快照/10033 事件）与主树的（3946 快照/187857 事件）是**两个不同文件**，
  自测结论不能互相冒用。

## 7. ④ codex｜新对话恢复快照

【2026-11-01 新对话交接｜第十五轮技术交付完成，当前无在途开发】用户明确要求保存记忆后开启新对话。本轮基线5a48f7c；RED ffe590f，离线4769418，音效5b35f29，取证7e97a6f。恢复先workflow→talking→本节/registry→git status/log，以最新派单为准；已交付部分不重做、不无故复跑门禁。当前只待主树复核收编、用户亲听与后续定线裁决。不同步main、不推远程；收编保留主树ensure_schema修复1d4bfa9（本树未重复实现）。提交均带派单指定Co-Authored-By。

- **①离线**：sim/world/offline.py只接显式时长；墙钟仅main._offline_wall_time采样一次，offline_store读当前分支checkpoint.created_at（epoch/ISO兼容，旧无时区ISO按UTC）。全确定性钩子装配后、两后台任务之前补跑；固定1x，普通60tick/实秒、战斗1tick/实秒，最多86400tick，每批≤4实秒/240tick。flush_world带checkpoint_at/force_checkpoint，无事件尾部也持久化游标；中间水位按已处理时长、末批置本次墙钟，超限offline.capped丢弃；不写玩家档、不调LLM、不复用WS快进。临时SQLite实测一分钟tick60→3660、events59→18391、玩家档不变；两遍事件重放hash相同、再启动零补跑；30天只86400tick。脚本/JSON在.orca/audits/offline-progress-2026-11-01。
- **②音效**：client/src/game/audio与audioStore，Phaser context自有节点通道，默认每次页面静音/25%；设置明确启用后在场景点击/按键解锁。附近脚步、确认挖放、可见combat_event、rubble转变，8格衰减、120ms节流、最多8音源；断线/静音/失焦/销毁清理，generation守卫拦晚解锁，不close Phaser context。ActorDelta更新省略op，不是update。默认快照/心声/任务提示不发声。无npm依赖/资产文件，固定xorshift噪声可复现。客户端337P/47files、tsc/eslint/prettier/gen:protocol均绿，docs/arch/audio.md说明入口；技术验收不代表用户亲听通过。
- **②用户明确裁定**：服务端snapshot.lights=[]、无fire.ignited出站，本轮先交脚步/挖放/战斗，火声只做客户端映射，真实火场另列缺口；禁止自行为火声扩后端/协议。WorldScene派单44.6K行实为基线1039行/45654字节。记录于audio-2026-11-01/acceptance.json与talking。
- **③T5取证**：原PI_T5_FULL测试10种子×10日全部通过，123.97s（派单1.5h估计过时），seed7额外独立重复，rate与事件总数相同。每种子4/4=1.0，合计40/40，中位/最差1.0；只更新errands_rate过时注释、不定线。必须说明这是10实体mock移动末态跑四条跨日脚本，不是生产50NPC/LLM自主完成率。脚本、first/full逐种子与baseline在.orca/audits/t5-baseline-2026-11-01；measure.py可重跑，--collect-only仅汇总。
- **④soak取证**：npc.death apply真实移出entities，阶段B前提已落地，契约注释已更正但SOAK_ENTITY_LOSS_PER_GAME_DAY仍0。50实体8x8移动场每游戏小时种子SHA选近战对，真实CombatLedger结算并enqueue死亡；3日对照50→50、危害50→38，12死亡/3日=4人每日；重跑死亡轨迹与state_hash一致。受控危害不是自然流失或可接受上界。按原run_soak在内存测、不触库；所有接SQL实验仅临时SQLite。measure.py/measurement.json在.orca/audits/soak-loss-2026-11-01。生产死亡源比派单多坍塌maintenance一处；7份perf文档/14处悬空引用未修、留原引用。
- **门禁/证据**：全量pytest3056P/0F/121S/72D，400.84s；5warnings=4旧弃用+旧test_m4c_llm_driver种子夹具未dispose engine的一次线程警告，未顺手改。离线/E1/快照41P；T5完整10P另跑；soak零阈值契约1P。Ruff378files/Pyright0E0W/client337P/47files与全部门禁通过；两资产byte-identical、实现程度检查、uv lock全绿。round15-2026-11-01/{plan.md,gates.json}已归档。协议1.14，shared、package/lock、冻结DESIGN、registry、迷雾登记不变。真实world.db未读写、未运行其迁移，无浏览器/付费模型。
- **恢复纪律**：workflow→talking→本节/registry；CodeGraph显式本树projectPath先行，已返源码视为已读；协作只本树talking，ignored永不add；memory只改§7、-f add并提交。Python全程uv/UTF8；PS中文脚本须OutputEncoding UTF8，重定向可能UTF16。删npm/venv先问；主树域/第十四轮历史健康还原与LOD等未派事项不展开。i-have-adhd持续，50%提醒已给，后续建议新对话。

