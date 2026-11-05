# memory.md — 两树最小恢复卡

> 2026-10-25/26 多轮大整理：历史正文已删除，考古用 git history。
> 文档入口 `docs/README.md`；命令 `docs/dev-workflow.md`。

## 0. 当前状态（2026-11-05 第二十三轮主树部分已完工 · B2/B3 派 codex）

- **主树在飞：无**。第二十三轮主树部分已全部提交（`c7b7d1d` 设计+计划 →
  `c3e2a2b` 实现收口）。**B2/B3 已派 codex 树**（派单说明在该树 `.orca/talking.txt`），
  主树待收编复核。
- **本轮做了什么**（用户验收驱动，原话：世界空空如也 / npc 只会聚集 / llm 除寻路无法执行 /
  石头等材料不能用 / 主角老说有奇怪气味）：
  - **A 等距烘焙**（`9b83d79`..`c3e2a2b`）：真实 tileset 像素烘进地面画布（`tile-projection.ts`
    新增）；高格顶面注册 `tile-<gid>` 帧。验收截图三档均见桃花林/草地/石阶/水面。
  - **B1 气味**（`3e915b5`/`4bea378`）：`SMELL_SOURCE_STRENGTH=0.04` + 新增独立旋钮
    `smell_floor=0.08`（与 `hearing_floor` 解耦）；`narration_cache.py` 跨帧抑制重复气味行。
    实测：聚集 50 人 50/50 可闻，稀疏 0/10，独行 0.0628 不可闻。
  - **B4 主体**（`6a008fa`）：prompt 里 `96×96` → **`140×100`**；集合差测试钉死
    `IntentAction - M1_SUPPORTED_ACTIONS == {demolish, use}`。`take`/`give` 按用户裁定单列。
  - **两处实机缺陷**（都不是计划里的）：① 心声/街谈巷议面板每次重连整屏重复——
    `full_snapshot.monologue_history` 被逐条追加，改为 `onMonologueHistory` +
    `replaceMonologues/replaceChatter` 整组替换（`d95696e`）；② 脏矩形裁剪只有 4×4 图的
    等价测试（脏矩形≈整幅=没测），补 16×16 图回归钉（`c3e2a2b`）。
  - **门禁**：pytest **3503P/121S** · ruff/format 全过 · pyright **0/0/0** ·
    client typecheck/eslint/prettier EXIT 0 · vitest **423P/56F** · 两资产 byte-identical ·
    协议 **1.14 未动** · 拾取与基线逐项相同（448/448 · 3947/3947 · 7141/7373）。
- **🚨 本轮事故（已处置）**：`sim/api/main.py:69` 硬编码 `WORLD_DB_PATH = Path("world.db")`，
  **不读同名环境变量**。用 `WORLD_DB_PATH=<临时路径> uv run uvicorn` 起验收后端，实际写的是
  真实档 48 分钟（14:03–14:51，+1,274,454 events、tick 66000→309910、快照 2→12）。
  已按 `seq 341740` 边界回滚：events **341,740** / snapshots 1 / knowledge 62 /
  relationships 151（按事件重放重建，值与存库 83/83 零误差）/ npc_memories 384；
  `integrity_check: ok`，`restore_world` 实测恢复 **tick 66000 / 54 实体**。
  备份保留：`world.db.bak-20261105-203825`（回滚前）、`world.db.polluted-20261105-150143`（取证）。
  **下次起验收后端：`cd` 进空目录，或 monkeypatch `main.WORLD_DB_PATH`。**
- **第二十二轮（codex，土坎拾取）已收编**：`pickVoxel` 增可选第六参 `isBank(x,y)`；
  `WorldScene` 传实时 `collision===0`。只有 h=1 土坎的**实际三道斜纹像素**
  （`|x-2y|<=5 && |3x+4y|<=5`，offset -7/0/7）与高块同池，按 `depthKey+.5` 与绘制同序；
  烘焙顶面空白/侧面/普通地面保留低池。**不能全局深度优先**（普通低地面会抢房屋侧面），
  也**不能整块顶面提升**（空白处实际显示身后房屋侧面）。旧五参 `pickVoxel` 保持旧行为。
  - 实测（同张未改静态图，主树独立复跑 `measure.cjs` 得到同读数）：土坎自命中
    149/448 → **448/448**；高块 7141/7373 不变；可走 3947/3947 不变；`pickGround` 逐字未动。
  - 门禁：typecheck/lint/prettier/gen:protocol 全 EXIT 0；vitest 360P/49F（codex 树）；
    主树合并后 399P/53F。协议 1.14。后端未改。
- **主树转述归因修复（`74fe95c`，2026-11-04）**：`ChatLedger.remember` 增必填 `speaker`，
  记忆条目变 `(tick, text, speaker)`；转述取最新一条**不是自己说的**记忆（`_heard_mems`），
  无外人之言则不转述；署记忆里的原说话人。实机双口径 0 自指（浏览器 39 条、事件表 136 条）。
  第一版只补 speaker 时实机仍 37/62 自指——**单测抓不到，实机才抓到**。

## 0a. 上一轮（第二十一轮）记录

- codex 第二十一轮 `78e5c09` 已 `--no-ff` 收编（合并提交 `1d55179`；
  1 冲突：`memory.md` 取主树版本）。主树 D3–D6 已分三提交落地（`551f1af` / `5f890bd` / `fca7a3f`）。
  **门禁读数（收编后主树实测）**：pytest **3486P/0F/121S**（453.34s）· ruff/format 403 ·
  pyright 0/0/0 · client **388P/51F** + 四件 EXIT 0 · 两资产 byte-identical · lock 一致 · 协议 1.14。
- **第二十一轮（codex，D1+D2）已收编**：成功读档按**请求保留的连接 `ControlState`**
  重新投影 `clock`（暂停 0、否则 `effective_speed`），失败仍 fail-closed 冻结；
  `session_state` 改**按连接定向投递**（`manager.send_to_control`），`paused` 不再从全局
  `clock.speed == 0` 推断；`set_speed` 在暂停态也写 `speed_before_pause`。队列与执行中
  都按 `anchor_id` 防重，重复立即 `load_failed`，`finally` 释放可重试。
  - **收编冲突 1 处**：`.orca/memory.md`（codex 侧只有 §7 且是旧快照）→ 取主树版本。
  - **收编时补修一处**：`single_save` 夹具只 patch `broadcast_json`，而 `session_state`
    改成定向投递后漏帧 ⇒ 改为真 `ConnectionManager` + `_recording_socket`（与 `saved_world` 同款）。
    这是主树自己的测试跟不上新架构，不是 codex 的缺陷。
- **主树 D3–D6（2026-11-04，TDD，已提交）**：读档等待态改**帧驱动**（`loadPending`
  由 `loadAnchor` 置、`full_snapshot`/`error{ref:load_anchor}`/掉线收尾清），面板出
  「片刻后……」+ 三按钮真禁用；`session_state.notice`/`anchor` 接进面板与顶栏；
  `set_control` 被拒补顶栏 `role="alert"` 位（白名单 bad_speed/bad_action/bad_advance）；
  favicon 落地 + 存档默认名改「现存最大编号+1」+ 基线文件旧路径订正。
  **清单外另补三条**：断线时 `loadAnchor` 拒发并给可见文案；读档途中掉线由 `onStatus` 收尾；
  在途中再点一次直接丢弃（`disabled` 要等 React 重渲染才生效，双击可同帧跑完两次 onClick，
  只有请求侧判重拦得住第二个 fork）。**自查另修一条既有泄漏**：`player_impulse` 的错误
  分支原样透传 `msg.message`，而服务端用消息 type 当 ref ⇒ `bad_channel` 会把
  "channel mismatch" 送进念头栏（`ws.py:995`）。
- **已修并关闭：D1 失败读档后世界永久冻结（2026-11-04 探针实测 → codex 第二十一轮修复）**：
  一次读档失败之后再成功读档，`load_outcome=True` / `world_source_ready=True`，但
  `loop.clock.speed` 仍为 **0**，广播的 `session_state` 是 `{speed:1, paused:true}`，
  而点「继续」回 `bad_action`「本来就没停。」（因为每连接 `ControlState.paused` 是 False）。
  - 根因：失败路径 `main.py:1289-1290` 置 `world_source_ready=False` + `set_speed(0)`；
    **成功路径 `main.py:1273` 只置回 ready，从不恢复 `clock.speed`**；而
    `main.py:1279` 用 `loop.clock.speed == 0` 推断 `paused`（与 `ControlState` 分裂）。
  - 既有测试 `test_projection_failure_stops_world_without_sending_success` 只锁「失败要冻」，
    **缺「成功要解冻」**——这是同一根因的另一半（第二十一轮已补）。
  - 可达窗口：`activated=True` 之后 `rebuild_tile_map` / `load_health_snapshot` /
    `restore_voxel_edits` 抛错。**冻结本身是故意的 fail-closed，别为凑绿取消它。**
- **读档恒失败缺陷已修并已提交（2026-11-03 修 / 2026-11-04 提交）**：
  `ae20518` 后端 + `8394856` 前端 + `2db91ff` 恢复卡。门禁 pytest 3460P/0F/121S
  （479.61s）· vitest 360P/48F · ruff/format 403 · pyright 0/0/0 · 两资产一致 · 协议 1.14。
  详情见下（保留原记录）：
  1. **后端 `locate_anchor` 的 `AND protected = 0` 是错的**（`fork_orchestration.py`）：
     `protected` 只表达「不许删这个档」（`anchors-api.md` §1.4），与能否载入无关。
     新建档必是末梢（`create_item` 写 `protected=True`），且读档成功后 `fork.py`
     把载入的档回写为 `protected=1`（读档即成为当前游标）⇒ **「存完立刻读」与
     「读过再读」两条主路径恒回 `load_failed`**，玩家看到「这个档读不出来了。」
     该过滤是 `5755a62`（2026-09-28）遗留，早于 `protected` 写入路径。
     **既有测试为何没抓到**：`saved_world` 夹具存了**两档**，旧档自动降级为
     `protected=False` ⇒ 永远只测非末梢档。新增 `single_save`（只存一档）夹具
     + 2 条 e2e + 1 条单元钉（RED 3 失败 → GREEN）。
  2. **前端读档失败无任何提示**（`runtime.ts::onError`）：`ref=load_anchor` 的
     error 帧被静默丢弃 ⇒ 点「读档」面板毫无反应（实机就是这个现象）。服务端
     早已备好文案，只是没接到 UI。新增 `uiStore.loadError` + `SaveLoadPanel`
     复用 `role="alert"` 提示位；`loadAnchor()` 发请求时先清旧文案；空串不渲染空框。
     - **文案有两个来源，别混**：生产 drain 路径走 `main.py:1301` 的**硬编码
       字面量**（`_error_frame("load_anchor", "load_failed", "这个档读不出来了。")`，
       K16 白盒钉要求字面量）——**不过** `scan()` 终扫；`ws.py::_load_failed_frame`
       是**同步路径**的构造器，那条才做终扫并可能产出空串。当前两处文案相同。
     - **只认两种 code**（2026-11-03 code review）：`load_failed` / `bad_anchor` 可直显，
       `bad_channel`（"channel mismatch"）等工程措辞走戏内兜底——否则英文原文会
       漏进玩家面板。`onSnapshot`（世界已恢复）清 `loadError`，避免成功后仍挂着旧失败。
  - **实机复核（隔离库 `p7verify-20261103`，ms-playwright chromium-1252）**：
    **11/11 PASS**——存一档→立刻读／读过再读／未注册 id 面板出文案／**失败后成功
    读档旧文案已清**／**bad_channel 未泄漏英文**／无 4xx/5xx。截图 `V1~V5`。
    > 大库读档要重放 20s+，脚本必须**轮询等 `full_snapshot`**；死等 6s 会假红
    >（第一次重跑就踩了，5 条假失败）。别照旧脚本的固定 `waitForTimeout`。
  - **门禁（主树实测，code review 后重跑）**：pytest **3460 passed / 0 failed /
    121 skipped**（469.33s，三次独立复跑同读数）· ruff/format 403 files · pyright 0/0 ·
    vitest **360 passed / 48 files**（+7）· client 四件 EXIT 0 · 两资产 `--check` 一致 ·
    `uv lock --check` 一致 · 协议 **1.14** 未动。
  - 契约同步：`docs/api/anchors-api.md` §1.4 增「`protected` 与可读性无关」；
    §4.3 订正「`load_anchor` 不返回 error 帧」的自相矛盾说法（一律走 WS error 帧）；
    `docs/api/ws-protocol.md` §4.5 增可见位条 + `message` 只在戏内文风 code 下可直显。
- **主树本批（2026-11-02，用户问「还有什么问题」后按建议顺序做的前三条 + 顺带一条）**：
  1. **1A 身份锚自洽**（`villagers.py::_profile_row`）：`identity_anchor` 改与同行
     `name`/`occupation` 同源。修前三个专属角色库里「赵铁·镖师」配锚
     「我是赵铁柱，农人。」——`npc_l2.py:243` 把这个锚当 prompt **第一条 system
     消息**，模型与玩家头顶名牌对不上。新增 6 条钉子。
     **真实库（只读）实测**：54 行里严格比对 **7 行**不符，其中真缺陷 **3 行**
     （三个专属角色）；另 4 行是合法不同形——陈默的故意长锚 + 灰/黑子/鸦
     走 `animals.py:27` 的 `我叫{name}。`。**别把 7 当缺陷数**。
  2. **2A 读档清心声账本**（`ws.py::monologue_history_clear()`）：`_MONO_HISTORY`
     修前全仓无 `.clear()`，读档后旧分支最近 20 条随快照灌进新世界面板
     （D 只过滤「别人的」，没管「旧世界的」）。新增 4 条 + 端到端 1 条。
  3. **4A 意愿独白按动作分口径 + 扩街巷句库**：`will.py::_ACTION_TEMPLATES`
     （5 动作 × 3 档 × **≥12 句**，与通用池同宽）+ `willingness_expression(..., action=)`；
     `dialogue.py` 粗 2→9 / 文雅 2→7（文雅每句必带「您」）。新增 **53 条**。
     - `action=""` 与修前逐位一致；**`move`/`build`（无专属池）也必须逐位一致**
       ——首版只回落池、仍用 `(npc, action)` 作键，会静默换句，已修 + 钉死。
     - 池宽**必须 ≥12**：真实库 `npc.act` rest **87,864 次**是绝对主力，
       专属池 4 句 = 比它替换掉的 12 句通用池**更复读**，本末倒置。
     - **命中面实测**（真实库 `npc.monologue` 60 条 thought 按同人前一动作配对）：
       rest **33** / wander **18** / work **6** / eat 1 / request_chat 1 / move 1
       ⇒ 新专属池覆盖 **85%**（rest+wander），`move` 几乎不产 band>0，
       其回落修正属正确性保险而非热点。
  4. **顺带修（同一子系统，查证时撞见）**：`npc/roles.py::role_events` 把
     `narrate_sound` 的**完整句**（自带句号）直接拼进 `听见{clue}，…` ⇒
     真实库 `npc.monologue` 实测：**209 条里 60 条**含「句号/问号/感叹号紧跟逗号」
     （= thought 面**全部** 60 条，bubble 面 149 条无一命中），形态是
     `听见传来一阵脚步声，像是奚船家。，先记在心里。`。
     加 `_as_clause()` 只剥一层尾标点，5 条参数化钉子（RED 4 失败 → GREEN 5）。
- **第二十轮已收编（codex `bb0647e` + `3012063` → 主树 `66637b7`）**：
  每日健康严重度演进（`health_evolve.py`）+ 三处播种分支过滤（`seeding.py`）。
  两条真缺口均已关闭。主树独立复跑 **3457P/0F/121S**（= 基线 3350 + 107），
  逐条对上；冲突 2 处按预定口径解决（`villagers.py` 保留主树 1A 同源修复 +
  采纳 codex 的 `branch_id` 形参；`memory.md` 取主树版本）。
- **第十八+十九轮（codex，2026-11-02）：已 `--no-ff` 收编 `e28e144`**。
  第十八轮 = 锚点读档按游标重建 `npc_profiles`（独立 profile 快照段）；
  第十九轮 = **L2 真实调用路径接齐**（有限单步，不是多步规划器）。详见 §7 与 §1。
  - ⚠️ **可用性变化（须知会用户）**：缺 profile 副本的**旧锚点包**现在统一
    `corpus_mismatch`、在 hooks 前拒绝 ⇒ **旧存档读不出来**。属 fail-closed 取舍
    （`npc.death` 只有 ID，重建不出已删的 26 列），已登记 `docs/data/schema.md §24.2`。
    本树实测 `world.db` 里 `anchor_packages` **0 行**，所以实际影响面为零——但
    codex 树/别的副本若有旧包会读不出来。
  - **L2 只在「人在主角 3 格内 + 有可用模型配置 + 有身份锚」时升格**；默认 60 真实秒
    / 每 NPC、全村 4 次/60 秒、单并发、8 秒超时、192 输出 token、单 HTTP 尝试。
    `NPC_L2_CALLS_PER_MINUTE=0` 可一键关。**暂停/离线/历史回放零模型调用**。
- **第十九轮（主树，2026-11-02）：A social 需求闭环 + D 心声历史私密面**。
  用户问「模型能控制人物吗 / 心声和街巷太乱」，实测结论见 §1g；本轮只修
  两条**真缺陷**（用户裁定 A+D，B 真接 L2 与 C 扩池未动）。
  1. **A**：`needs.py::REMEDY_RELIEF` 加 `request_chat → social -0.3`；
     `sim_exec.py` 开口成功后回写（与 D3「吃了才算吃」同口径）。
     修前 social 只涨不降 ⇒ 第 0 日 0.31 / 第 1 日 0.81 / **第 2 日起恒 1.00**
     ⇒ 全场 band 3（满屏「这活儿我实在打怵」而人实际在闲逛）。修后实测
     第 0~5 日 band>0 恒 **2%**（修前第 2~5 日 **100%**），social 稳在 0.05。
  2. **D**：`ws.py::_MONO_HISTORY` 改存 `(actor_id, 帧)`，
     `monologue_history_payload` 按 `_protagonist_id(loop)` 过滤——
     `bubble`/`plan` 广播面全可见，`thought` 只出本人视角（与 `route_monologue` 同源）。
     修前村民/三专属角色的 thought 随每次 full_snapshot 落进陈默心之声面板
     （20 条缓冲约 19 条是别人的）。
  3. 新增 **13 条** pytest（`test_social_need_relief.py` 8 +
     `test_monologue_history_privacy.py` 5），RED 9 失败 → GREEN 13 通过。
- **第十九轮门禁（主树独立实测）**：pytest `-m "not bench"` **3114 passed / 0 failed
  / 121 skipped**（428.88s）· ruff 385 files · format 385 files · pyright 0/0 ·
  client gen:protocol:check/typecheck/lint/prettier EXIT 0 · vitest **353 passed / 48 files** ·
  两资产 `--check` 逐字节一致 · `uv lock --check` 一致 · 协议 **1.14** 未动。
  > pytest 3100 → 3114 = **+14** = 第十九轮 13 条 + `02e3b10` 的
  > `test_A_health_seam_equal` 1 条（3100 是第十七轮收编时的读数，
  > 早于 `npc_health` 修复那笔提交）。vitest 不变（353）——本轮零前端改动。
- **收编后门禁（主树独立实测，2026-11-02）**：pytest **3280 passed / 0 failed / 121 skipped**
  （419.73s）· ruff/format **394 files** · pyright 0/0 · client 四件 EXIT 0 ·
  vitest **353 passed / 48 files** · 两资产 `--check` 逐字节一致 · `uv lock --check` 一致 ·
  协议 **1.14**。完整表见 §1。

- **main HEAD**：`git log -1 --oneline` 现测（**别记哈希**，记录本身就会产生新提交）。
  第十八+十九轮收编 = 本文件本次提交的父提交（`--no-ff` 合并 `e28e144`）。
- **codex HEAD**：内容交付 `3012063`（A）+ `bb0647e`（B），记录提交 `69444db`。**已收编**；codex 树仍未同步 main。
- **第十八+十九轮：已收编**（`--no-ff` 合并 `e28e144`，merge-base `16b7eae`）。
  - **2 处冲突**（预测 4 处；`main.py`/`fork.py` 自动合并，已复查主树修复仍在）：
    1. `sim/npc/sim_exec.py` —— **两边都保留**：先 codex 的 `note_dialogue`（L2 降格判据），
       再主树单次 `apply_remedy(..., "request_chat")`。codex 回执 §4 明确要求如此；
       L2 服务侧不写 social ⇒ 不会重复扣账。
    2. `.orca/memory.md` —— 取主树版本后补记（本节 + §7）。
  - **自动合并后复查（第十七轮活例）**：`main.py::ensure_schema`（`:42,208`）在；
    `fork.py::_clone_health_at_cursor`（`:559` 调用 / `:797` 定义，`02e3b10`）在；
    `ws.py` D 的 `_MONO_HISTORY` 视角过滤（`:578,597,617`）在。三处均未丢。
  - **收编后首跑 1 红，已修**：`test_m5_fork_replay.py::test_A_health_seam_equal`
    （主树 `02e3b10` 钉子，codex 分支不含那笔提交 ⇒ codex 不知道这个手搓夹具）。
    修法见 §1 注。修后 **3280P**。
- **第十七轮：已收编**（物种知识门 + 名牌重叠）。
  - 收编为 `--no-ff` 合并，**3 处冲突**按预定口径解决：
    1. `sim/api/main.py` —— 取 codex 侧后**补回主树的 `ensure_schema`**（`main.py:42,208`）。
       codex 分支自 `820c653` 起不含该提交，丢掉则真实库启动即崩。
    2. `sim/core/persistence/social_projection.py` —— add/add，取 codex 侧（主树侧为纯子集）。
    3. `.orca/memory.md` —— 取主树版本（codex 侧停在 10-31 旧状态），本节即补记。
  - **自动合并未静默丢主树修复**：已核对 `evidence.py` 的 `display_name_of` 反查 +
    重名 fail-closed、`frame.py` 过时注释订正、`main.py:346,649,668` 三处传参全部在。
  - 主树独立复跑（**不采信自测**）：`test_species_knowledge.py` +
    `test_m3_social_wiring.py` → **31P**；`name-labels.test.ts` → **16P**；
    新增数对得上：pytest 3069→**3100**（+31）、vitest 337→**353**（+16）。
- **第十六轮：已收编 + 生产已通**。原判「不可收编」的根因是
  `witnesses` 恒空 ⇒ `knowledge` 恒 0；修法见 §1e 尾段（`display_name_of` 反查 +
  重名 fail-closed + 真跑 `lifespan` 的集成测试）。
  **Playwright 实机验证（隔离库）**：`knowledge` 22 行 / `relationships` 116 行 /
  `hidden_emerge.witnesses` 有内容；挖掘、放置、移动、昼夜循环全链路正常。
- **真实 `world.db` 已回滚**（2026-11-01 19:47）：本轮我的手写探针曾绕过 `conftest`
  直写真实库（+741567 events / knowledge +27）。已用备份
  `world.db.bak-20261101-150615` 覆盖，`seq 1..187857` SHA256 与备份逐字节一致
  （`a39c046c…`），`knowledge`/`relationships` 归零，无伪造脏数据。
  污染态另存 `world.db.polluted-20261101-194706`（已 gitignore，供取证）。
- **协议**：**`1.14`**（第十轮挖深字段升级）；双落点同改
  （`sim/api/ws.py::_PROTOCOL_VERSION` ↔ `client/src/net/ws.ts::PROTOCOL_VERSION`
  ↔ `sim/tests/test_protocol_version.py::EXPECTED_VERSION` + README 徽章 + `shared/openapi.json`）。
  第十一～十七轮均未动协议字段（渲染、UI、持久层、音效、离线、社会层内部）。
- **两棵树**：
  - 主树 `E:/zxdevelop/project7`（`main`）：拆单/架构/质量/收编复核/日常小改。
  - codex 树 `E:/zxdevelop/.orca/worktrees/project7/codex`（`codex`）：复杂/跨层实现、安全合规。
  - 只走各树 `.orca/talking.txt`；不直接对话。
- **远程**：origin/gitee 均在 `3603ecb`（**主树领先未推**，推送仍由用户决定）。
  现测：`git rev-list --count origin/main..main`——**不要记数字**，每提交一次它就变。
- **在飞**：**无**。第二十轮已收编（`66637b7`）。未派：V3.5 内容包 / V4-3D。
  第十八+十九轮**已收编**；主树 1A/2A/4A **已做完**。
  §1g 的 C 项（扩池 + 动作语境）已由 4A 关闭。

> **第十九轮派单的三个硬约束**（主树已查实，写给收编时的自己）：
> 1. `NpcProfileData`（`sim/npc/model.py:40`）**没有 `identity_anchor` 字段**，
>    `_row_to_profile_data`（`npc_store.py:73`）没读那一列——L2 的硬前提，
>    必须先在 model/persistence/assemble 三层补上。
> 2. 用户裁定实现形态 = **LLM 输出落事件、回放读事件**（不是回放跳过 L2）。
>    现有 `NPC_MONOLOGUE`/`NPC_CHAT` 已是 state 层 no-op（`world.py:237,250`），
>    新事件照这个口径走，T2 口径不变。
> 3. 离线推进「不调用网络/墙钟」（`offline.py:37`）**必须保持**。
> 若 codex 交半接线状态，按派单末尾「允许的垂直切片」核对其切点。
- **第十五轮留给用户的四件事 → 2026-11-01 已完成三件**：
  1. ~~T5 完成率阈值定线~~ → **已定 1.0**（用户裁定，见 §1b）
  2. ~~soak 流失阈值定线~~ → **已裁定：良性保 0 + 「流失须被死亡解释」契约**（见 §1b）
  3. ~~真实 `world.db` 正式迁移~~ → **已迁移**（备份 `world.db.bak-20261101-150615`，
     版本 `0015_health_code`，events 187857 / snapshots 3946 零丢失）
  4. ~~音效主观听感~~ → **2026-11-01 用户验收通过**（「音效已可以」）。至此第十五轮
     留的四件事**全部关闭**。
- **待人工验收**（9 条，已过 4 条，**剩 5/6/7/8/9 共 5 条**；音效另计已过）：
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

> **第十九轮新增待验收（观感类，与上面 5 条同性质）**：
> 10. **心声/街巷是否还乱**：A 修后街巷从 75.2 → 56.5 条/分钟、换屏 6.4→8.5 秒，
>     心之声面板不再被别人的内心话冲掉（D 修）。**4A 后句库 9 句（粗）+ 每动作
>     每档 ≥12 句专属独白**，动作与独白同口径。验收时看：同一场景下 rest 的人
>     还会不会嘟囔「这活儿讨价还价也没人听」（4A 前必现，4A 后不该出现）。
> 11. **L2 是否真的「有脑子」**（第十八+十九轮收编后新增）：现在主角 3 格内的村民
>     会走模型。看两点：①升格村民的心声/对白是否明显比模板有人味；
>     ②模型失败/超时是否干净退回模板（不卡顿、不空窗、不重复说同一句）。
>     **默认预算很紧**（每 NPC 60 秒一次、全村 4 次/分钟），观察需要耐心。

> **记录订正**：用户 2026-10-31 先发「1 2 3观感已验收」、随后「3都已验收」，
> 均指验收清单**第 1/2/3 条**。我最初误记为第 8/9 条，已改回。第 8/9 条**尚未验收**。

## 1. 门禁（**2026-11-03 第二十轮收编后主树独立实测**；第十六轮复核见 §1e）

> **第十六轮在 codex 树实测（独立复跑，非采信自测）**：
> pytest `-m "not bench"` **3074 passed / 0 failed / 121 skipped**（394.51s）·
> ruff/format EXIT 0 · pyright 0E/0W · 协议仍 1.14 · client/shared/uv.lock/DESIGN 零 diff。
> bench **2F 属既有基线**：主树**无本轮代码**同样 2F（`test_perception_sound_50npc`
> 与 `test_retrieval_full_scan_degraded_sentinel`），且两条单跑均通过 ⇒ 抖动，非回归。
> 回执称「sound baseline passes」是错的。

| 项 | 本批实测（2026-11-03，读档缺陷修复后） |
|---|---|
| pytest `-m "not bench"` | **3460 passed** / 0 failed / 121 skipped（469.33s，三次独立复跑同读数） |
| ruff check / format | clean（**403 files**） |
| pyright | 0 errors, 0 warnings, 0 infos |
| client gen:protocol:check / typecheck / lint / prettier | EXIT 0 |
| client vitest | **360 passed / 48 files** |
| build_height_map --check | 逐字节一致 |
| build_block_atlas --check | 逐字节一致 |
| `uv lock --check` | 一致 |
| 协议 | **1.14**（双落点同值） |

> **读档修复新增 3 条**：3460 − 3457 = **3** = `test_m5_fork_orchestration.py`
> `test_protected_tail_anchor_is_locatable` 1 + `test_historical_world_load.py`
> `single_save` 夹具下 `test_load_the_only_anchor_after_saving_it` /
> `test_reloading_a_previously_loaded_anchor` 2。vitest 360 − 353 = **7** =
> `runtime-impulse.test.ts` 5（loadError 路由／发新请求清旧文案／code 白名单／
> 空串原样透传／成功后清文案）+ `SaveLoadPanel.test.tsx` 2（提示框/空串不渲染）。
> pytest 新增数不变（e2e 的 `ref`/`code` 断言是补钉，不是新用例）。

> **第二十轮收编 `66637b7` 后读数（历史）**：pytest 3457P/0F/121S（434.12s）·
> ruff/format 403 files · pyright 0/0 · vitest 353/48。

> **本批新增数对得上**：**3457 − 3350 = 107**，与 codex 回执的独立审查读数
> **B 50P + A 57P** 精确吻合（B = 模块 47P + 生产冷 child/故障态 3P；
> A = 模块 51P + 真实日切 live 6P）。
> ruff 397 → **403 files**（+2 新源文件 `health_evolve.py`/`seeding.py`，其余为本轮测试文件）。
> 关键回归文件单跑 **98P**；fork 相关 39P/1S。vitest 仍 **353/48**（本轮零前端改动）。

> **上一批（主树 1A/2A/4A/roles，2026-11-02）新增 70**：3350 − 3280 = **70** =
> `test_villager_identity_consistency.py` **6** + `test_monologue_history_fork_reset.py` **4**
> + `test_willingness_action_context.py` **53** + `test_roles.py` **+5**（2→7）
> + `test_historical_world_load.py` 端到端 **1** 条 × `saved_world` 两个 `params` = **2**。

> **收编后门禁（上一轮实测，2026-11-02）**：pytest **3280 passed** / 0 failed / 121 skipped
> （419.73s）· ruff/format **394 files** · pyright 0/0 · client 四件 EXIT 0 ·
> vitest **353 passed / 48 files** · 两资产逐字节一致 · `uv lock --check` 一致 · 协议 1.14。

> **收编后首跑 1 失败，已修**：`test_m5_fork_replay.py::TestR2SeamConsistency::test_A_health_seam_equal`
> —— 该测试是主树 `02e3b10` 的钉子，codex 分支**不含那笔提交**，所以 codex 不知道
> 这个文件里还有一个手搓 `_minimal_package` 调用点；合并后第十八轮新加的 fail-closed
> 判据（`package.profile_rows is None` ⇒ `ForkError`）把它撞了。修法：夹具增
> `profile_rows` 形参 + `_profile_rows_at()` 从库导全列（该夹具的世界**有** chenmo，
> 不能像另两个空名册夹具那样填 `()`）。修后该文件 20P，全套 3280P。
> **这正是「收编必独立复跑」的活例**：codex 自测 3253P 全绿，主树一合就红。

> 第十五轮动的是 `sim/world/offline.py`（新）+ `sim/core/persistence/` + `sim/api/main.py`
> + 整个 `client/src/game/audio/`，故两侧全套必跑。
> 3069 − 3061 = 8 条 = 定线新增（5 条 soak 契约 + 3 条 T5 阈值）。
> 3061 − codex 自测 3056 = 5 条 = 主树第十四轮的 `test_schema_self_heal.py`（codex 分支不含那笔提交）。
> **第十七轮：3100 − 3069 = 31 条**（`test_species_knowledge.py` 6 + `test_m3_social_wiring.py` 25）；
> vitest 353 − 337 = **16 条**（`name-labels.test.ts`）。两边新增数与主树复跑读数逐条对上。
> **第十八+十九轮：3280 − 3114 = 166 条**（codex 自测 3253 与本树 3280 的 27 差 =
> 主树第十九轮 A/D 的 13 条 + 主树 02e3b10 的健康游标钉子等主树专有提交）。
> vitest 仍 **353/48**（两轮未动前端）。

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

## 1e. 第十六轮复核：测试全绿但生产不通（2026-11-01）

**这是 §1d 那条教训的升级版**：不是回执说谎，是**测试根本没跑生产路径**。

codex 交付 `820c653`（+886 行，18 条新测试），门禁全绿，但：

```
真实 lifespan 600 tick：events 0→3775，relationships 0→25 ✅，knowledge 0→0 ❌
主树真实库副本：        events 187857→191674，relationships 0→37 ✅，knowledge 0→0 ❌
```

**根因一条**：`sim/perception/senses.py:271` 把 `Observation.subject` 设成**中文显示名**
（同一个 `label` 既作叙事文本又作 subject），而 `witnesses_of_entity_emerge`
（`evidence.py:157`）拿 `rtoken_of(subject)` 去比 ⇒ **永不匹配** ⇒ `witnesses` 恒空
⇒ `npc.knowledge_learned` 零产生 ⇒ `knowledge` 表恒 0。`told` 路以 knowledge 行为源，
同根因被堵死。`frame.py:37` 的 `subject: str  # rtoken` 注释是**过时的**。

**为什么 18 条测试没抓到**：全部手造 `PerceptionFrame`（`subject=rtoken_of(...)`），
**没有一条跑真实 `lifespan`**。测试用的帧形态与生产形态不同 ⇒ 测的是另一个世界。

**教训（写进纪律）**：验收面凡写「实况跑起来后 X 表有行」，
就**必须有一条真跑 `lifespan` 的集成测试**；纯函数单测证明不了接线通。

**bench 2F 的真相**：主树**无本轮代码**同样 2F（`test_perception_sound_50npc` /
`test_retrieval_full_scan_degraded_sentinel`），两条单跑均通过 ⇒ 抖动，非回归。
回执里「sound baseline passes」是错的。

**codex 树 `world.db` 是坏的**：有 **83 个 `world.create`**，而 `restore_world`
（`world_restore.py:166`）要求恰好 1 个 ⇒ 该树真实库**无法恢复**。主树库健康
（1 genesis / 187857 events / tick 36001 可恢复）。两树库是不同文件，别互用结论。

**✅ 已修（主树 2026-11-01，TDD 红→绿→重构）**：
- `witnesses_of_entity_emerge` 新增 `display_name_of` 形参，在**戏外边界**用
  entity_id→显示名 反查；`Observation.subject` 语义**未动**（叙事仍说人话）。
- **重名 fail-closed**：显示名不唯一 → 返回 `([], None)`，宁缺勿错；无显示名的
  实体按 rtoken 作词面（`senses` 同一默认分支），不误判歧义。
- 调用点 `main.py:664` 传入 `_display_names`；`frame.py:37` 过时注释已改正。
- **真跑 `lifespan` 的集成测试**已补（`test_lifespan_witnesses_knowledge_from_real_perception`），
  且**照抄生产执行序**（先 `_run_npc_runtime` 后 `_run_perception`，`tick.py:94-96`）
  ——我第一版写反了，会把当帧帧喂给 `frame.tick < tick` 过滤器而必然全拒。
- 实测（零注入，真实地图）：`witnesses` 9 人 / `knowledge` 落库带 `evidence_seq` / `conf=0.9`。
- 门禁：pytest **3091P/0F/121S**（404.88s）、ruff 0、format 0、pyright 0/0、
  client tsc/lint/prettier 0、vitest 337P、两资产 + protocol + lock + impl 全过。

**⚠️ 同一会话的事故（须记）**：手写探针 `import sim.api.main` 起 `lifespan` 时**绕过
`conftest` 的 `WORLD_DB_PATH` 重定向**，直接写了主树真实 `world.db`：events
187857→929424、max tick 36000→178270（`offline.capped` 补推 86400）、knowledge 0→27、
relationships 0→591。已核：`seq 1..187857` 的 payload/witnesses SHA256 与备份**逐字节一致**；
备份里用户操作事件仅 `tile_changed: 30`，追加段内 `tile_changed/structure_*/npc.death/
player_anchor` **全为 0** ⇒ **未丢用户操作**。但追加段含我伪造的 9 行
`fact="小满: 肩头旧伤"`（attr_id 却挂真实 `health_night_fear`）= 脏数据。
**回滚待用户裁定**（备份是迁移前形态，缺 `npc_health.code`，需 `ensure_schema` 自愈）。
**纪律**：任何起 `lifespan` 的脚本必须自己把 `main.WORLD_DB_PATH` 指到临时库，
或干脆写成 pytest 用例走 `conftest` 夹具。

## 1f. 锚点读档「复制父分支未来态」根因族（2026-11-01，**第十八轮派单依据**）

**一个根因，两处受害。** `fork.py` 的 `kind="anchor"` 分支里，`_BOUNDED_TABLES`
各表靠一串 `if table == ...` 特判；**没被特判的表落到 `_clone_bounded`**——
`INSERT … SELECT … WHERE p.branch_id = :pid`，复制父分支**当前 head 行**，
完全不看锚点游标。锚点之后父分支若继续推进，子分支读档就拿到「未来」。

已特判的表（正确）：`fires:533`、`structures:540`、`npc_health:547`（本轮新加）、
`material_balances:555`、`relationships:562`（跳过，按包写）。
**未特判而受害**：`npc_profiles`（`fork.py:53` 起，26 列宽表）。

**✅ 已修（主树，`02e3b10`，TDD 红→绿）**：`npc_health`。

- RED 实测：锚点 tick=1 处 severity=0.2，父 head（tick=5）处 0.8 ⇒ 子分支拿到 **0.8**。
- 修法 `_clone_health_at_cursor`（`fork.py:789`）：按 seq 重放 `npc.health_changed`
  （复用 `_project_health`，折叠规则单一来源）+ 补齐无事件源的创世种子行
  （判据 `created_at_tick <= fork_tick`）。
- **踩到的坑（写进纪律）**：`npc_health` 是**混合表**——创世种子
  （`content/health.py::seed_health`）直接 INSERT、**无事件源**，事件投影只增量改行。
  我第一版只重放事件 ⇒ 丢掉全部种子行，被既有
  `test_m6_death_profiles_contract::test_fork_does_not_clone_dead_health_row` 抓出。
  **别照抄 `structures` 的纯重放写法**。

**✅ 已修（第十八轮 `8b6b702`，主树收编 `bdeeb19`）**：`npc_profiles`，后果比健康表重——**丢整个 NPC**。

主树对照实验（临时内存库，唯一变量 = 锚点后父分支是否推进）：

```
A 锚点 tick=1，tick=5 死亡  → child=[('a',2)]              ← 'd' 凭空消失
B 锚点 tick=1，tick=5 lod 1→2 → child=[('a',2),('d',1)]    ← 'a' 的 lod 是未来值
对照（锚点后不推进）        → child=[('a',1),('d',1)]      ← 正确
```

**生产可触达**：玩家读档 → `main.py:1056 orchestrate_materialized_load_anchor`
→ `fork_orchestration.py:228 kind="anchor"`。

`npc_profiles` 写入面（已查实，**只有两条事件**）：`NPC_LOD_CHANGE`（改 `lod`+
`updated_at_tick`）、`NPC_DEATH`（**删行**）。其余 24 列无运行时写入路径，只由种子直插。

**顺带发现（第二十轮任务 B，已修，主树收编 `66637b7`）**：
`seed_villagers`（`villagers.py:320`）幂等判据原本是 `select(NpcProfile.id)` **无 branch
过滤**，`_profile_row` **硬编码 `branch_id="main"`**（`villagers.py:291`、`protagonist.py:37`），
`seed_animals`（`animals.py:13`）是同一缺陷的**第三处**（复用 `villagers._profile_row`）。
主树 5 组临时内存库实测（修前）：**(main0,child0)→main50；(main0,child50)→新增0；
(main0,child49)→main1/child49；(main50,child49)→新增0；(main50,child50)→新增0**
⇒ **只补 main，子分支永远补不上**。

**修后（codex `bb0647e`）**：三处播种都按 `(branch_id, id)` 判存在，`_profile_row`
的 `branch_id` 由调用方传入（`villagers._profile_row(p, *, branch_id="main")`、
`protagonist._profile_row(*, branch_id="main")` 仍零参可调）。新增
`sim/content/seeding.py::read_branch_death_ids`：`main.py` 用**既有 store** 一次读取
**有界祖先死亡前缀**（`read_branch_history` 沿 `forked_from_branch` 拼），同一个
`frozenset` 传给三个播种函数；独立调用（`dead_ids=None`）时用
`SqlEventStore(session_factory)` 只读 wrapper 自算，不另开 SQL 驱动。
**祖先分叉游标之后的死亡不纳入**（父分支未来死的人不算子分支的死者）；缺祖先 /
缺 cutoff / 循环 / 孤儿事件一律拒绝盲补。
**故障态不猜 main**：`current_branch is None` 且**库里已有 Branch 行** ⇒ 判为故障、
不播种（只有真正空库才当创世写 `"main"`）。
**修后实测**（codex，主树已复跑同组）：目标分支语义下 5 组全对；
十个目标分支组合第二次调用均 0（幂等）；本线与祖先死者三类都不补。

> ⚠️ **主树 2026-11-03 收编实测**：真实冷 child 场景 `main 54` 不变、`child 49` 补
> 3 个缺失活人后 `52`，两名已死者仍缺行。**这是正确行为**（死者不复活）。

## 1b. 已关闭但代码不支撑的承诺（主树 2026-10-31 审计，**新对话先读**）

六里程碑 2026-10-05 宣告收官（`abbe765`），下列五条实测当时是空的。**这些不是 bug，
是「宣告了但没做」**，任何新方向裁定前必须知道。**2026-11-01 第十五轮后：四条已有实现
或取证，只剩残余项**（音效主观听感、T5/soak 阈值定线、真实库迁移仍归用户）。

| 缺口 | 实测证据 |
|---|---|
| **音效**（**已验收**） | ~~全仓 0 个 `.mp3/.ogg/.wav`、0 处 `this.sound`~~ → **2026-11-01 第十五轮已收编（`28e8ac9`）**：Phaser 3.87 内置 WebAudio，`client/src/game/audio/{synth,world-audio,index}.ts`；零新 npm 依赖、零资产文件、协议不变。默认静音 25% 音量、8 音轨上限、8 格衰减、120ms 节流；只消费可观测的 `voxel_edits`/actor 位移/`combat_event`/`lights`，不碰独白。**2026-11-01 用户亲听验收通过**（5 短音 step/dig/place/combat/collapse + fire 循环）。**仍未做**：真实火场音效外发（用户裁定为独立缺口） |
| **M3 社会层** | ~~0 生产调用点~~ → **2026-11-01 第十六轮 `ffa74bd` 已收编并修好根因**：关系真实库副本 0→37 行，知识 22 行（隔离库 Playwright 实测）。根因是 `Observation.subject` 为中文显示名而装配拿 rtoken 去比 ⇒ 恒空；修法 `display_name_of` 反查 + 重名 fail-closed（§1e）。**第十七轮 `16b7eae` 已收编**：物种知识门（`can_hold_knowledge`，仅 human 持有/转述，未知 fail-closed；目击仍留在 `hidden_emerge.witnesses`）+ 名牌屏幕空间避让 |
| **`npc_health`** | ~~有模型/迁移/读路径，但**零写入**~~ → **2026-10-31 第十四轮已收编并修好启动自愈（`1d4bfa9`）**：事件→总线→同事务健康投影→感知触发→陈默闸门/记忆已接通；6 条内容种子。**2026-11-01 真实库已正式迁移（`d64464d`）**：备份 `world.db.bak-20261101-150615`（先副本演练再动真库），版本 `0015_health_code`、`code` 列补齐，events **187857** / snapshots **3946** / max seq 187857 **零丢失**，存档副本启动成功（tick 36001 / 54 实体）。~~**仍未做**：历史锚点 fork 的 severity/active 还原、每日严重度演进、第三方浮现见证链。~~ → **2026-11-03 订正：三条全通**（前两条 11-02，第三条第二十轮收编 `66637b7`）：
  ① **锚点 fork 的 severity/active 还原：已修**（主树 `02e3b10`）——`fork.py:559` 现走
     `_clone_health_at_cursor`（按 seq 重放事件 + 补无事件源的种子行，`created_at_tick <= fork_tick`），
     不再 `_clone_bounded` 复制父 head。钉子 `test_m5_fork_replay.py::test_A_health_seam_equal`。
  ② **第三方浮现见证链：已通**——真实库 `npc.hidden_emerge` 2 条带完整 `witnesses` 列，
     `knowledge` 32 行（`witnessed` 18 / `told` 14），`main.py:672` 的
     `witnesses_of_entity_emerge` + 物种知识门在链上。
  ③ **每日严重度演进：已修**（第二十轮 codex，主树收编 `66637b7`）——新增
     `sim/content/health_evolve.py`：同步无 IO 快照适配器，挂在 `main.py` 的
     `_on_day_switch`（反思先、健康后，两者返回值均丢弃），**只 `loop.enqueue`
     `npc.health_changed` 七键事件、不直写行**（C4），下一帧 drain+flush 落库
     （正常 1 帧延迟）。数值表（严重度/游戏日）：`old_injury -0.05` /
     `disease +0.10` / `addiction +0.02` / `disability 0` / `trauma -0.02`；
     round 12 位后 clip[0,1]；愈合归零后 `active=False` **只发一次**，恶化到 1 饱和
     不重复。`run_world_driver` 签名与同步语义**未改**。
     **离线选 (b)**：`advance_offline` 不演进健康，补跑结束后才建基线，不在首个
     在线日追补离线天数（已写进两处 docstring，**是真缺口、明确保留**）。
     **重症上限只到健康投影**：本适配器不产 `AGENT_INCAPACITATED`——普通 NPC 没有
     生产恢复入口，静默制造永久失能会把世界卡死（不是漏做，是**故意不做**）。
     **本树 fork 侧仍未做**：`fork.py` 走 `_clone_bounded`，没有主树的
     `_clone_health_at_cursor`；codex 按 A5 改钉「事件逐字段相等 + 投影行全列重放相等」
     替代，**未冒称历史健康锚点端到端验收**（收编后主树版本已在，见 ①）。
  > `anchor_package.CORPUS_TABLES` 仍不含 `npc_health`（设计如此：健康是**可折叠族**，
  > 走 `_clone_health_at_cursor` 重放，不进包——第十八轮也只在包里加了 `npc_profiles`）。 |
| **`npc.lod_change` 持久化** | **已完成**（`runtime.py:223` 发射 + `npc_store._project_lod_change` 双键投影）。此前记忆卡写「仍未做」是过时记录，2026-11-01 已订正 |
| **离线推进** | ~~`sim/world/offline*.py` 不存在~~ → **2026-11-01 第十五轮已收编（`28e8ac9`）**：`sim/world/offline.py::advance_offline` 复用现有 `TickLoop`；墙钟只在启动边界采样一次（`_offline_wall_time`）；水位取 `snapshots/branches.created_at`（控制元数据，不进事件流与 `state_hash` ⇒ **C5 安全**）；批上限 240 tick、`MAX_CATCHUP_REAL_SECONDS=4.0`、上限 1 游戏日（`TICKS_PER_GAME_DAY=86400`，超限记 `offline.capped`）；同墙钟重启零补跑。主树实测：60s→3600 tick、30 天→86400 tick 且丢弃 2590560s、两遍重放 hash 相同、玩家档零写。**仍未做**：真实 `world.db` 上跑一次真实停机补偿（需备份） |
| **T5 差事完成率** | ~~`errands_rate.py` 明写「本轮不设阈值」~~ → **2026-11-01 已定线（`d64464d`）**：用户裁定 **`ERRAND_COMPLETION_RATE_MIN = 1.0`**。依据实测 40/40（10 seed × 4 链，中位与最差都 1.0，`.orca/audits/t5-baseline-2026-11-01/baseline.json`）。**不留缓冲的理由**：口径是确定性脚本链（零 LLM/网络/随机），无抖动来源，0.95 只会让真实回退静默通过。**不沿用 M1 的 80%**（单决策口径）。**口径边界写死在模块 docstring**：这是脚本完成率，不是生产 NPC 自主完成率 |
| **soak 实体流失** | ~~`SOAK_ENTITY_LOSS_PER_GAME_DAY = 0`，从未抬高~~ → **2026-11-01 已定线（`d64464d`）**：用户裁定 **良性上界保持 0**，另立契约「**流失须被死亡解释**」（`净流失 - 已记录 npc.death = 无解释流失`，必须为 0）。**为什么不抬到实测的 4.0/游戏日**：那是每小时强制近身互殴的**夹具**，不是自然流失率；现有 soak 用 `make_mock_feeder` **根本没有死亡源**，抬到 4.0 会在 604800 tick 里程碑跑里允许 **28 个实体凭空消失而不报红**，等于把泄漏检测变瞎。契约在 `_assert_entity_stable(..., explained_deaths=...)`，测试 `sim/tests/bench/test_soak_loss_contract.py` |

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

## 1g. 心声/街巷的真实产线（2026-11-02 实测，**B/C 的依据；C 已由 4A 关闭**；L2 段 2026-11-04 订正）

用户问「模型能控制人物吗 / 心声和街巷太乱，感觉模型没发挥作用」。查证结论：

**模型只控制 1 个人**（2026-11-02 实测；**2026-11-04 订正：已有第三处**）。
`self._llm.complete(...)` 现在三处：`sim/agent/driver.py:188`（陈默决策）、
`:282`（陈默对话台词）、**`sim/agent/npc_l2.py:268`（近身村民 L2 决策，第十九轮接入）**。
所以「模型只管陈默」在第十九轮之后**不再成立**——3 格内升格的村民也吃模型。
- 陈默：`main.py::_chenmo_loop` → `driver.decide_once`，`CHENMO_DECIDE_SECONDS`
  默认 **60 秒 1 次**；
- 50 村民：`npc/runtime.py:150 evaluate_batch`（numpy 效用矩阵），每 10 tick；
- 赵铁/小满/苏婉：`npc/roles.py::role_events` 硬编码 f-string，每 600 tick（10 秒）。

**⚠️ 订正（2026-11-04）：本节原写「『升格 L2』是空壳」——已过时。第十九轮就接齐了。**

实测（2026-11-04 复核）：
- `sim/agent/npc_l2_runtime.py:84` 真的判 `profile.lod == 2`
- `sim/api/main.py:684`（升格名单）、`:793`（专属角色）都读 `lod == 2`
- `sim/api/main.py:1003-1024` 装配 `NpcL2Coordinator` + `_npc_l2_loop`；
  `npc_l2_live` 在离线补跑完成后置 true（`main.py:1405`）
- 有界单步、`L2Policy` 默认 min_interval 60s / max_calls 4 / timeout 8s / max_tokens 192
  （env 覆盖 `NPC_L2_MIN_INTERVAL_SECONDS` / `NPC_L2_CALLS_PER_MINUTE` / `NPC_L2_TIMEOUT_SECONDS`）

所以验收第 ⑪ 条「L2 是否真的有脑子」是**观感验收**，不是代码缺口。
原判据「全仓非测试代码没有任何地方读 `lod == 2`」在第十九轮（`bdeeb19`）之后已失效。

**心声（心之声面板）来源**：

| 来源 | 代码 | 性质 |
|---|---|---|
| 陈默 thought | `driver.py:364-371`，`content=intent.reason` | 真模型，~1 条/分钟 |
| 村民嘟囔 | `will.py:90 _TEMPLATES`（每档 12 句）+ `:159 _pick_index(npc_name)` | 纯模板 |
| 三专属角色 | `roles.py:20-27`，三条 f-string | 纯模板 |
| 玩家念头回执 | `ws.py:1293-1295` | **恒为「这话我记下了。」**（2026-11-04 订正行号；cue 仍是 `ws.py:1319-1326` 的标点启发式，真表 `plan_view.py:159 band_to_cue` 未接线） |

`_pick_index(npc_name)` **不含 tick / 动作 / 处境** ⇒ 同一 NPC 同一 band 永远同一句
（坏掉的唱片；50 人分 12 句）。且 36 句全是「不想干活」口径，**与动作无关**。

> **4A 已修（2026-11-02）**：动作专属池 `_ACTION_TEMPLATES`（5 动作 × 3 档 × ≥12 句）
> + `willingness_expression(..., action=)`，选取键变 `(npc_name, action)`；
> `move`/`build` 无专属池 ⇒ 池与键**一起**回落（与修前逐位一致）。见 §0。

**街巷（街谈巷议面板）来源**：`dialogue.py:34 template_line`，池
`:18 _CHAT_TEMPLATES` 5 句；但生产语域 `SpeechContext(平民, in_circle=False)` →
`speech_register` 返回「粗」→ `_REGISTER_TEMPLATES["粗"]` **只有 2 句**。
实测 50 人一整天不同台词总数 = **2**。

> **4A 已修（2026-11-02）**：`粗` 2→9 句、`文雅` 2→7 句（每句必带「您」）。
> 真实库 `npc.chat` 实测（278 条）修前「粗」池的两句占了绝对多数
> （「忙着呢，回头再说。」110 次）。见 §0。

> **订正（2026-11-02，我上一轮报错）**：我先前说屏幕上会出现字面量「旁人」——
> **生产不会**。`sim_exec.py:694` 是 `(display_name_of or {}).get(target_id, target_id)`，
> 主树 `main.py:649` 实传 `_display_names`（50 村民 + 陈默 + 动物 + 三专属角色全覆盖），
> 所以真机上署名是戏内真名，退化成 `villager_02` 只在**没传映射的测试替身**里发生。
> 真正的「旁人」兜底在 `driver.py:488`（陈默 L2 侧，`or "眼前的人"`）——那是
> 陈默找不到对方名字时的措辞，属正常兜底，不是缺陷。别照这个去改。

**「乱」的数量根因（3 游戏日 ≈ 72 真实分钟实测）**：

| 项 | 修前 | 修后（A 之后） |
|---|---|---|
| 嘟囔 bubble | 27.8 条/分钟（36 句） | 17.9 条/分钟（19 句） |
| 聊天 chat | 47.4 条/分钟（**2 句**） | 38.6 条/分钟（2 句） |
| 合计 | **75.2 条/分钟** | 56.5 条/分钟 |
| `CHATTER_CAP=8` 换屏周期 | **6.4 秒** | 8.5 秒 |
| 陈默心声 | 1 条/分钟 | 1 条/分钟 |

街巷是心声的 **75 倍**，句库 2 句，6 秒换屏 —— 用户「感觉模型没发挥作用」是准确的。

**根因链（一条解释全部）**：
`REMEDY_RELIEF` 无 `request_chat` → social 只涨不降 → 第 2 游戏日起恒 1.00 →
`synthesize_verdict` 需求冲突维 ≥0.8 → 全场 band 3 → 唯一补救动作 `request_chat`
又被 `sim_exec.py:48` 开口冷却压掉 → 人被逼去 wander/rest/eat（都不 remedy social）
→ 满屏「这活儿我实在打怵」而人在闲逛。**A 已修**（见 §0），第 0~5 日 band>0 恒 2%。

**A 修后仍存在的残留（4A 已于 2026-11-02 修掉前两条）**：
- ~~第 3 日 band>0 只剩 `rest band2` 10,298 + `request_chat band1` 212 次决策，
  文本仍是「不想干活」口径~~ → **4A 已修**（动作专属池）。
- ~~街巷句库 2 句~~ → **4A 已修**（粗 9 / 文雅 7）。
- 「旁人」兜底**不是缺陷**（见上方订正），保持原样。

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

**测试**
- **纯函数单测证明不了接线通**（第十六轮实证）。18 条测试全绿，生产 0 行。
  凡验收面写「实况跑起来后 X 表有行」，必须有一条**真跑 `lifespan`** 的集成测试。
  手造 `PerceptionFrame` 与生产帧形态不同时，测的是另一个世界。
- **`Observation.subject` 是中文显示名，不是 rtoken**（`senses.py:271`，同一个 `label`
  既作叙事又作 subject）。`frame.py:37` 的注释是过时的。任何按 rtoken 匹配 subject 的
  代码都会静默失效——fail-closed，不报错，只是恒空。
- **`flush_for_anchor()` 读 `loop.pending_events`**：先 `drain_events()` 再调它 = 刷空列表，
  探针会假绿（我第一版就这么写的）。
- **`advance_frame(1/60)` 推不动 tick**：时钟累积器吃小数会一直是 0；喂 ≥1 实秒才动。

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

**第十六轮修根因（2026-11-01）**
- **感知帧的 `subject` 是戏内词面，不是 rtoken**。`senses.py` 视觉/听觉填显示名
  （叙事要人话），内感受填自身 rtoken。任何戏外装配（witnesses / 统计 / 回指）
  **必须经 `display_name_of` 反查**，直接拿 rtoken 比会静默恒空。
- **重名必须 fail-closed**：显示名不唯一时无法从词面反推是谁，返回 `([], None)`。
  注意区分「**没**显示名」（按 rtoken 词面，天然唯一，**不是**歧义）与「**多个**同显示名」。
- **手写探针起 `lifespan` 会写真实库**：`conftest.py:15` 的 autouse 夹具只对 pytest 生效。
  脚本里 `import sim.api.main` 直接用默认 `WORLD_DB_PATH=Path("world.db")`，且启动即跑
  `advance_offline`（会补推最多 1 游戏日）。**要么显式改 `main.WORLD_DB_PATH` 到临时库，
  要么写成 pytest 用例。** 2026-11-01 本轮就踩了：真实库 +741567 events / knowledge +27。
- **集成测试必须照抄生产执行序**：`_tick_once` 是 `npc_runtime → maintenance → perception`
  （`tick.py:94-96`），emerge 只能拿**上一帧**。先跑 perception 再跑 npc_runtime 的写法
  会把当帧帧喂给 `frame.tick < tick` 过滤器 ⇒ 永远 `([], None)`，看着像功能没实现。
- **`model_copy` 的字段要走 `update={...}`**：`model_copy(pos=(x,y))` 是 TypeError。

**定线（2026-11-01）**
- **取证值 ≠ 可用的阈值**。soak 的危害夹具实测 4.0 实体/游戏日，但那来自「每小时强制
  一对近身互殴」的人工死亡源；现有 soak 用 `make_mock_feeder` **没有死亡源**，实体结构性
  守恒。把上界抬到 4.0 ⇒ 604800 tick 的里程碑跑允许 28 个实体凭空消失 ⇒ **泄漏检测变瞎**。
  正确做法是把「允许的流失」与「已记录的解释」绑定，而不是给一个绝对数字。
- **确定性夹具不要留缓冲**。T5 的 `chain_runner` 零 LLM/网络/随机，实测 40/40 = 1.0 且
  中位=最差=1.0 ⇒ 无抖动 ⇒ 0.95 只会让真实回退静默通过。有抖动的指标才需要缓冲。
- **定线必须写死口径边界**。T5 的 rate 是**脚本完成率**，不是生产 NPC 自主完成率；
  后者没有基线数据，模块 docstring 里必须写明「本模块不对它做断言」，
  否则下一个人会把 1.0 当成生产指标。
- **真实库迁移的顺序**：备份 → 在**副本**上演练并核对行数 → 确认无损 → 才动真库 →
  迁移后拿备份逐项对账（events 计数 + max seq + snapshots）。备份文件名带时间戳，
  且 `.gitignore` 必须有 `*.db.bak-*`（`*.db` 匹配不到 `world.db.bak-2026...`）。
- **`ensure_schema` 要能重复调用**：迁移后再启动会二次调用，必须幂等
  （`at_head` 分支直接 return）。

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

【2026-11-01 定线与真实库迁移 `d64464d`｜无在途任务】用户裁定三项并已落地：
① T5 完成率 **1.0** 硬阈值（依据实测 40/40，确定性脚本链无抖动故不留缓冲）；
② soak **良性保 0** + 新契约「流失须被死亡解释」（不抬到夹具实测的 4.0——
现有 soak 无死亡源，抬线会把泄漏检测变瞎）；
③ 真实 `world.db` **已正式迁移**：先备份 `world.db.bak-20261101-150615`，
再在副本演练确认无损，最后动真库 ⇒ 版本 `0015_health_code`、`code` 列补齐、
events 187857 / snapshots 3946 / max seq 187857 **零丢失**，存档副本启动
（tick 36001 / 54 实体），`ensure_schema` 二次调用幂等。
`.gitignore` 加 `*.db.bak-*` 防备份入库。
门禁 3069P/0F/121S（391.73s，+8 = 5 soak 契约 + 3 T5 阈值）、ruff 380 files、
pyright 0/0、client 337P/47F、两资产/实现程度/uv lock 全绿；
`PI_T5_FULL=1` 全量 10 seed 通过（178.56s）。
**只剩音效亲听这一件归用户。**

【2026-11-01 第十五轮已收编 `28e8ac9`｜历史】codex `47f9e80` 以
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

- **开新对话只需知道**：① codex `16b7eae`（**第十七轮已交付待收编**）、主树收编后门禁需重跑；
  远程停在 `3603ecb`（主树领先未推，现测 `git rev-list --count origin/main..main`，等用户决定）；
  ② 待**肉眼**验收 9 条，**7/8/9 优先**（见 §0）；主树 2026-11-01 第十六轮
  **开过一次**浏览器（用户明确授权，验社会层接线实机效果，**不是**观感验收）；
  那 5 条观感**仍未验收**，第十二轮的观感只有 codex 的截图证据；
  ③ **§1b 的承诺缺口**：`npc_health`（第十四轮 + 真实库已迁移）、音效/离线推进
  （第十五轮）、T5 与 soak **已定线**（`d64464d`）；**只剩音效未亲听**——
  别以为 M0–M6 收官就等于都实现了，也别以为已实现就等于用户已验收；
  ④ **不变量必须单向**（`walkable ⇒ h==EARTH`），做成双向会立刻回归「只挖不放」；
  ⑤ **移动拾取 ≠ 编辑拾取**，合成一个会在真实地图上死掉 19% 的可走格；
  ⑥ **单测全绿 ≠ 真机能动**，改拾取/投影必须用真实地图实测命中率；
  ⑦ **快照可删、事件不可删**：热保留删的是 `snapshots` 行，`events` 与冷快照一行不动（C6）；
  ⑧ **墙钟只能存在控制元数据里**：离线时长靠 `snapshots/branches.created_at`，
     绝不进事件 payload / `state_hash`，否则 C5 立刻破（第十五轮的设计前提）。
- **远程**：origin/gitee 均停在 `3603ecb`；主树领先若干提交（**不记数字**，
  `git log origin/main..main` 查全表）**未推**。推送仍是用户决定，不自动推。
- **配置目录**：维持用户 10-26 裁定「不进 git、不推远程、本地须存在」；主树不建 `.pi`。
- **浏览器**：仅用户明确要求时用。**已改为 `--browser chromium` + 升级打包版（2026-11-01）**：
  - 现状：`.claude/mcp.json` = `@playwright/mcp --browser chromium`；
    `ms-playwright` 内为 `chromium-1252`（Chrome **157.0.8103.15**）。
  - 为什么改：原先是 `--browser chrome`，而 `chrome` 是 **channel 语义不是目录**
    （README 原文 "browser **or chrome channel**"），解析到**已安装的**
    `C:\Program Files\Google\Chrome`。铁证：旧 MCP profile 的 `Last Browser` 就是那条路径。
    实测对比：`--browser chrome` → `Program Files\...\chrome.exe`；
    `--browser chromium` → `ms-playwright\chromium-1252\...\chrome.exe`。
  - **升级方式**：`playwright install chromium`。直连 `cdn.playwright.dev` 被掐断
    （ECONNREFUSED / server closed connection），**必须**带
    `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright`
    （npmmirror 镜像实测可用）。install 会**清理旧 revision**（1248 被删）。
  - **不要在 `mcp.json` 硬编码 revision**：install 换版后硬编码立刻失效。
    `.orca/audits/frontend-visual-2026-10-30/verify-layout.cjs` 已改为
    `playwright.chromium.executablePath()` 动态解析。
  - **用户数据零共享**（实测）：MCP 独立 profile `ms-playwright-mcp/`（History 仅
    `http://127.0.0.1:5173/` 1 行、无 Bookmarks、无登录态）；用户 `User Data` 零写入。
  - 规则已同步：`.orca/workflow.txt` §5 与 `docs/dev-workflow.md`。
- **全局 git 邮箱**：`zx19836980213@outlook.com`（2026-10-31 实测，`dev-workflow.md`
  原记的 `223049848+ZX466@users.noreply.github.com` 已过期）。
- 本轮教训已进 §3：`.orca/talking.txt` 必须保持未跟踪，否则 ff 会覆盖派单；
  **派单里的坐标/数字必须来自代码实测，不能拿 `spawn_candidates` 当运行时出生点**。
- 第十三轮教训已进 §3「持久层」：**收编时在真实库副本上验证，不要只在内存库自测**。
  codex 的 `world.db`（0 快照/10033 事件）与主树的（3946 快照/187857 事件）是**两个不同文件**，
  自测结论不能互相冒用。

## 7. ④ codex｜新对话恢复快照

【2026-11-01 Round17｜已收编】物种知识门 + 名牌重叠，提交 `16b7eae`，主树 `--no-ff` 收编。
- **A 物种知识门**：`sim/npc/evidence.py::can_hold_knowledge(species)` 仅 `"human"` True，
  猫/犬/渡鸦/未知显式物种 False（未知 fail-closed）。目击与 told 两条路径都在知识事件
  生成**之前**检查 runtime profile；told 同时检查来源与接收者。动物保留
  `hidden_emerge.witnesses`——目击是事实，持有/转述是能力，投影不丢弃已发事件。
- **B 名牌重叠**：标签在屏幕空间按实际 Text 矩形避让（复用 `bubbles.ts::placeBubble`），
  主角优先、其余按距离 + token 稳定序，最多上移 36 屏幕像素后隐藏。
  **未动 `isoProject`/`isoUnproject` 数学**。
- **收编冲突 3 处**：`main.py` 取 codex 侧后补回主树 `ensure_schema`；`social_projection.py`
  add/add 取 codex 侧（主树侧为纯子集）；`memory.md` 取主树版本（本树副本停在 10-31）。
- **主树独立复跑**：pytest **3100P/0F/121S**（405.23s）、ruff 383 files、pyright 0/0、
  client 全套 EXIT 0、vitest **353P/48F**、两资产 + protocol + lock + impl 全过；协议 1.14。
  新增 31 + 16 条与两树复跑读数逐条对上。
- **提醒下一轮**：本树 `world.db` 仍是坏的（83 个 `world.create`），别在上面做实验。

[2026-11-01 Round16 | implementation delivered with acceptance limits] M3 witness assembly uses latest completed perception frame and token/entity translation; internal knowledge_learned event holds scanned fact/evidence, flush_world projects knowledge and relationships in one transaction. told validates source holder/branch/content/confidence and receiver own-hidden gate before event generation; per-batch dedup. NormSlice connected to both existing Chenmo prompts (ordinary villagers have utility/templates, no LLM prompt path). relationship_retell event preserves trust drift; hydrate on start/branch load. Real fork test confirms child told links remapped child source. Restore retains/clones knowledge tables; does not reconstruct auto IDs by historical event re-projection. Tests: nonbench3072P/121S; latest security84P/new18P; Pyright0E0W/Ruff/format; client337P/typecheck pass. Bench remains2F (sound50NPC/retrieval degraded sentinel); parent baseline also fails retrieval but sound baseline passes, so no blanket pre-existing claim. Production lifespan fresh persistent rehearsal events0->116,knowledge2,relationships2,witnessseq60/toldparent1. Original world.db copied backup fails startup unique-genesis check; no repair/write; original+backup10033events identical SHA256. Evidence .orca/audits/round16-2026-11-01/{progress.md,gates.json,verify_live.py,live3.log,original-preservation.json}. No push/main sync/shared/lock/DESIGN/registry/fog changes; no browser/paid LLM. Next main review/integration, resolve performance and original-save compatibility separately.

【2026-11-01 新对话交接｜第十五轮技术交付完成，当前无在途开发】用户明确要求保存记忆后开启新对话。本轮基线5a48f7c；RED ffe590f，离线4769418，音效5b35f29，取证7e97a6f。恢复先workflow→talking→本节/registry→git status/log，以最新派单为准；已交付部分不重做、不无故复跑门禁。当前只待主树复核收编、用户亲听与后续定线裁决。不同步main、不推远程；收编保留主树ensure_schema修复1d4bfa9（本树未重复实现）。提交均带派单指定Co-Authored-By。

- **①离线**：sim/world/offline.py只接显式时长；墙钟仅main._offline_wall_time采样一次，offline_store读当前分支checkpoint.created_at（epoch/ISO兼容，旧无时区ISO按UTC）。全确定性钩子装配后、两后台任务之前补跑；固定1x，普通60tick/实秒、战斗1tick/实秒，最多86400tick，每批≤4实秒/240tick。flush_world带checkpoint_at/force_checkpoint，无事件尾部也持久化游标；中间水位按已处理时长、末批置本次墙钟，超限offline.capped丢弃；不写玩家档、不调LLM、不复用WS快进。临时SQLite实测一分钟tick60→3660、events59→18391、玩家档不变；两遍事件重放hash相同、再启动零补跑；30天只86400tick。脚本/JSON在.orca/audits/offline-progress-2026-11-01。
- **②音效**：client/src/game/audio与audioStore，Phaser context自有节点通道，默认每次页面静音/25%；设置明确启用后在场景点击/按键解锁。附近脚步、确认挖放、可见combat_event、rubble转变，8格衰减、120ms节流、最多8音源；断线/静音/失焦/销毁清理，generation守卫拦晚解锁，不close Phaser context。ActorDelta更新省略op，不是update。默认快照/心声/任务提示不发声。无npm依赖/资产文件，固定xorshift噪声可复现。客户端337P/47files、tsc/eslint/prettier/gen:protocol均绿，docs/arch/audio.md说明入口；技术验收不代表用户亲听通过。
- **②用户明确裁定**：服务端snapshot.lights=[]、无fire.ignited出站，本轮先交脚步/挖放/战斗，火声只做客户端映射，真实火场另列缺口；禁止自行为火声扩后端/协议。WorldScene派单44.6K行实为基线1039行/45654字节。记录于audio-2026-11-01/acceptance.json与talking。
- **③T5取证**：原PI_T5_FULL测试10种子×10日全部通过，123.97s（派单1.5h估计过时），seed7额外独立重复，rate与事件总数相同。每种子4/4=1.0，合计40/40，中位/最差1.0；只更新errands_rate过时注释、不定线。必须说明这是10实体mock移动末态跑四条跨日脚本，不是生产50NPC/LLM自主完成率。脚本、first/full逐种子与baseline在.orca/audits/t5-baseline-2026-11-01；measure.py可重跑，--collect-only仅汇总。
- **④soak取证**：npc.death apply真实移出entities，阶段B前提已落地，契约注释已更正但SOAK_ENTITY_LOSS_PER_GAME_DAY仍0。50实体8x8移动场每游戏小时种子SHA选近战对，真实CombatLedger结算并enqueue死亡；3日对照50→50、危害50→38，12死亡/3日=4人每日；重跑死亡轨迹与state_hash一致。受控危害不是自然流失或可接受上界。按原run_soak在内存测、不触库；所有接SQL实验仅临时SQLite。measure.py/measurement.json在.orca/audits/soak-loss-2026-11-01。生产死亡源比派单多坍塌maintenance一处；7份perf文档/14处悬空引用未修、留原引用。
- **门禁/证据**：全量pytest3056P/0F/121S/72D，400.84s；5warnings=4旧弃用+旧test_m4c_llm_driver种子夹具未dispose engine的一次线程警告，未顺手改。离线/E1/快照41P；T5完整10P另跑；soak零阈值契约1P。Ruff378files/Pyright0E0W/client337P/47files与全部门禁通过；两资产byte-identical、实现程度检查、uv lock全绿。round15-2026-11-01/{plan.md,gates.json}已归档。协议1.14，shared、package/lock、冻结DESIGN、registry、迷雾登记不变。真实world.db未读写、未运行其迁移，无浏览器/付费模型。
- **恢复纪律**：workflow→talking→本节/registry；CodeGraph显式本树projectPath先行，已返源码视为已读；协作只本树talking，ignored永不add；memory只改§7、-f add并提交。Python全程uv/UTF8；PS中文脚本须OutputEncoding UTF8，重定向可能UTF16。删npm/venv先问；主树域/第十四轮历史健康还原与LOD等未派事项不展开。i-have-adhd持续，50%提醒已给，后续建议新对话。

【2026-11-02 Round18+19｜codex 交付，主树已 `--no-ff` 收编】codex 连交两轮：
第十八轮 `8b6b702`（锚点读档按游标重建 `npc_profiles`）、第十九轮 `e28e144`（L2 真实
调用路径接齐）。主树独立复跑读数见 §1；本段记收编口径。

- **第十八轮 `npc_profiles` 锚点读档**：锚点包采用**独立 profile 快照段**，不再复制父分支
  未来 death/LOD 态。**兼容边界（可用性变化，必须告知用户）**：缺 profile 副本的旧锚点包
  统一 `corpus_mismatch`、hooks 前拒绝——旧存档将**读不出来**。已登记
  `docs/data/schema.md §24.2`。主树裁定：接受，属 fail-closed 取舍，非回归。
- **第十九轮 L2 真接线**：`NpcProfileData` 读既有 `identity_anchor` 列（无新列、无 seed 改动）；
  `NpcL2Service` 用稳定身份前缀 + 本人感知/记忆/规矩/已听对话，生成**有限单步**动作
  （eat/rest/work/wander/request_chat）+ 成品 thought/line。异步 coordinator **锁外**等模型，
  下拍经原 `sim_exec` 落 `NPC_ACT`/`MOVE`/`NPC_MONOLOGUE`/`NPC_CHAT`——**无新事件 kind、
  无协议字段**（T2 逐位一致不受影响；`world.py` 三个 handler 仍是 no-op）。
  等待 L2 时近身模板发言暂缓；模型失效回退原模板。世界/LOD 轮次/身份/距离/存活/隐藏窗口/
  听者变化 → 丢弃旧结果。**不是多步长程规划器**，是「有限单步 L2」。
- **成本闸**：新增村民池默认同 NPC 60 真实秒、全村滑动 60 秒最多 4 次、单并发、8 秒超时、
  192 输出 token、单 HTTP 尝试；`NPC_L2_MIN_INTERVAL_SECONDS` / `NPC_L2_CALLS_PER_MINUTE`
  （0=关）/ `NPC_L2_TIMEOUT_SECONDS` 可配，坏值回退保守默认。**暂停/离线/历史回放零模型调用**
  （`offline.py` 的「不调模型」承诺未破）。离开 3 格且最后对话结束 30 游戏秒后降格；
  最近已发结论去重 + 长度压缩经 `MemoryWritePipeline` 当前隐藏闸，无额外模型调用。
- **收编冲突 2 处**（预测 4 处，`main.py`/`fork.py` 自动合并）：
  1. `sim/npc/sim_exec.py` —— **两边都保留**：先 `note_dialogue`（L2 降格判据），
     再主树单次 `apply_remedy(..., "request_chat")`。L2 侧不写 social ⇒ 不会重复扣账。
  2. `.orca/memory.md` —— 取主树版本后补记本轮（本节）。
- **自动合并后复查（必做，第十七轮活例）**：`main.py::ensure_schema`（`:42,208`）、
  `fork.py::_clone_health_at_cursor`（`02e3b10`）、`ws.py` D 的 `_MONO_HISTORY` 视角过滤，
  三处均须仍在——已核。
- **第十九轮自测（codex 侧，不采信）**：pytest 非 bench 3253P/121S/72D、403.86s；
  L2 边界 127P；Ruff 390 files；Pyright 0/0；client 353P/48files；两资产逐字节；
  `uv lock`；全 EXIT 0。两项 Important（中文/Unicode/全角 Roman 数字闸、故障启动后
  L2 动态就绪）RED→GREEN 关闭。**全部 FakeLLM/MockTransport——无付费模型质量验收。**
- **~~只报未修（主树待评估）~~：`seed_villagers` 分支过滤** —— 第十八轮只报未改，
  **第二十轮 `bb0647e` 已修**（详见 §1b 的 `npc_profiles` 条目下方）。
- **证据**：`.orca/audits/round18-*`（如有）、`.orca/audits/round19-2026-11-02/
  {plan.md,progress.md,gates.json,review.md}`；配置与行为记 `docs/perf/llm-monitoring.md §8`。
- **未动**：`ChenmoDriver`、`needs.py`、villager 种子、WS 语义、`fork/_BOUNDED_TABLES`、
  协议 1.14、`shared/`、`package.json`+lock、冻结 `DESIGN.md`、`registry`、迷雾登记。
  默认陈默重试仍 2 次；新村民专用 client 只 1 次并在停服 `aclose`。

【2026-11-03 Round20｜codex 交付 `bb0647e`(B) + `3012063`(A)，主树 `--no-ff` 收编 `66637b7`】
**2 处冲突、本轮 0 红**（不像第十八轮收编后才炸）。

- **B 三处播种分支过滤**（`bb0647e`）：`seed_villagers`/`seed_protagonist`/`seed_animals`
  全改按 `(branch_id, id)` 查与写；`_profile_row` 硬编码 `"main"` 改为 `branch_id="main"`
  关键字形参（`villagers.py` / `protagonist.py`）。新增 `sim/content/seeding.py`：
  `death_ids_from_history()` 从已解码有界历史取 `payload["entity_id"]`，
  `read_branch_death_ids()` 经 `store.read_branch_history` 走祖先分叉点前缀 ——
  **本线与祖先死者不复活、祖先未来死亡不渗入**。缺 Branch 且无任何事件 ⇒ 真空库才开
  `main` 创世；已有 Branch 却无 `is_current` 指针 ⇒ **故障态，不猜 main**。
- **A 每日健康严重度演进**（`3012063`）：新增 `sim/content/health_evolve.py`。
  数值表（单位严重度/**游戏日**）：`old_injury -0.05` / `disease +0.10` /
  `addiction +0.02` / `disability 0.00` / `trauma -0.02`；round 12 位后 clip `[0,1]`。
  愈合到 0 只发一次 `active=False`；恶化到 1 保持 active、饱和不重复。
  **只更新已有健康条目，不建新档**；新伤只有 `created_at_tick` 不晚于该日界才参加。
  接线：**异步批读快照 + 同步闭包**（钩子契约仍是同步无 IO）；`main.py::_on_day_switch`
  先反思、`finally` 健康，**两者返回值都丢弃**；`run_world_driver` 签名与同步语义未改。
  逐日 `loop.enqueue` 七键健康事件，下一帧 `drain_events` + `on_flush` 才落库（一帧延迟）。
  `refresh` 不推进 `last_day`；`reset` 用于换 branch / 建基线。
- **两条明确保留边界（裁定，不是漏做）**：
  ① **离线补跑不演进健康**（选项 b）：`advance_offline` 保持纯引擎路径，不扩签名/内容回调；
  补跑结束后才建健康基线，不在首次上线日切追补离线天数。已写进两处 docstring。
  ② **重症 1 只改健康投影，不产 `AGENT_INCAPACITATED`**：普通 NPC 无失能恢复入口，
  静默制造永久失能会卡死世界。
- **收编冲突**：1. `villagers.py::_profile_row` —— 两边都保留（主树 1A 同源 + codex `branch_id`）；
  2. `.orca/memory.md` —— codex 副本停在第十八轮，取主树版本后补记（本段）。
- **主树独立复跑**：pytest **3457P/0F/121S**（434.12s，= 3350 + 107）、ruff/format **403 files**、
  pyright 0/0/0、client 四件 EXIT 0、vitest 353P/48F、两资产逐字节、`uv lock --check`、
  协议 1.14。关键回归单跑 98P；fork 39P/1S。codex 自测 3360P 与本树 3457P 的差 = 主树专有提交。
- **证据**：`.orca/audits/round20-2026-11-03/{plan.md,progress.md,gates.json,review.md,b-report.md}`。
【2026-11-05 Round23｜codex 交付，主树收编中】基线 c59cb00；B2 `424ec34`，
B3 + 建造安全 `1738e09`；协议 **1.15**。本节记收编口径，读数以主树独立复跑为准。

- **B2**：新landmarks.py单源10地标含中文名/语义标签，主角文案不再漏5处；职业动作9站点，不新增/改序8职业，村塾不指派。home_base_of保留睡眠/出生/本区聊天；日间wander围绕当前片区中心半径12，scatter4与arrival4分开。执行层查钱/空地/需求/忙工地后向runtime.tick注入bonus_of，选build时补x/y再写NPC_ACT；创世50人每人15文coin.grant，冷启动重放不重发；先start再扣40，无静默退账。
- **建造安全**：独立审查实图(12,69)唯一邻格(13,69)被棚封死，1Important已修。BuildRuntime.can_start以候选footprint外沿连通检查保留原可走区域，NPC选址还查可达并避开人/旧路径/地标4格邻域。完工有人占格则等待；旧路径穿新墙以MOVE停止。4条RED→GREEN，相关74P；独立审查另43P，零遗留问题。
- **B3/用户裁定**：请求material可选缺省earth，放土/石/木=h1/h2/h3且均阻挡；新放置块挖一次返原料一份并恢复可走h1，放土不造石、放木不倍增。天然多层格高度递减而保留记录材质，h1地面为earth。_materials与_placed从已有VOXEL_EDITED恢复，TILE_CHANGED投影带material；HUD选材/空库存禁选/阻挡轮廓预览，Scene→bridge→runtime→WS全接。协议八处1.15、openapi_ext与shared快照两schema手改相等、protocol.ts由快照生成；不改SQL schema/依赖/包锁/冻结基线。
- **验证**：pytest notbench3427P/121既有S/72benchDeselected，453.95s，EXIT0；8warnings=2依赖弃用+4旧迁移子进程编码线程警告+2Pydantic弃用，UTF8单跑旧迁移1P/0warnings。client365P/50files；Ruff399files、Pyright0E/0W、typecheck/lint/prettier/protocol/两资产/uv-lock全EXIT0。真实生产hooks+SQL3日259200tick/807.46s：开工2(54320、227120)/完工1，动作站点9、各区distinct7/8/9/8/7，忙工地失败独白0，538笔coin事件与SQL重放均等于50人实况余额。MOVE覆盖10地标邻域含偶然靠近村塾，不是给村塾指派职业。真实网关三材料闭环含石/木2次冷启动通过。
- **交接**：证据 `.orca/audits/round23-2026-11-05/{plan.md,progress.md,gates.json,review.md,
  live-result.json,material-result.json}`；实况脚本 `live_probe.py` / `material_probe.py`，
  每次显式新建审计私库并隔离 world/anchor/profile。**未跑浏览器与付费模型**，
  不能当视觉或旧真库存档验收。收编保留主树 B1 叙事缓存、`74fe95c` 转述 speaker 归因、
  `ensure_schema` 等本树未同步改动。
