# M5 裁决 21（2026-09-27，Claude 主导）——kilo D-1~D-9 + opencode 1~12 + cline 三口径 + pi soak

> 裁决原则：先消歧再施工；零迁移可证伪面先行；冻结基线不破（§18/§19）；跨域复核按注册表。

## A. kilo 协议面（D-1 → D-2~D-5 依赖链）

- **D-1 = ①玩家快进/变速**。§10「时间锁定」已把刻度锁死落地；§13/§17 的「时间刻度」
  在 M5 语境下=玩家侧快进/变速（世界日历内容不在 M5 名下）。**依据**：§17 M5 验收
  原文「离线再回来世界已变」指向的是分叉，不是日历；日历属于 M6 打磨面。
- **D-2 = ①不扩 speed 枚举 + 新 action**。§10 明文锁 {1,4,16}，clock.ALLOWED_SPEEDS
  硬校验；快进走新 action `fast_forward`（长跨度推进、批处理语义，pi 预算红线随附）。
- **D-3 = ①幂等单值**。pause 幂等 / resume 无暂停回 bad_action / 暂停中 set_speed
  只改记忆值不解除暂停。**附带清 K9 记的 `_PRE_PAUSE_SPEED` 模块级全局**——G-1
  （pause→pause→resume 回 speed:0 破 schema）与 G-2/G-3 随此方案一并清（施工时收）。
- **D-4 = ①现形态不触发 + ③登记预留**。M5 不新增 S→C 广播；`rate_change` 只登记
  预留名+触发条件，不定义 schema（死 schema 防线）。
- **D-5 = ②新 session 首帧**（与 D-6 合并一帧）。
- **D-6 = ①新 session 帧**。分叉告知只能叙事化（branch_id 禁出网关）；
  塞 full_snapshot 污染 render-only 边界，纯 HTTP 表达不了「刚才那次读档分叉了」。
- **D-7 = ①重同步一律全量 full_snapshot**。ws_seq 跨连接不连续，diff 需不透明
  catchup_token——**在此之前不预留字段**（同 kilo 主张）。
- **D-8 = ①文档订正、实现不动**。rtoken 稳定派生对渲染缓存有利；订正 ws-protocol §5
  + versioning §8-1 措辞（kilo 域小单，D-1 裁后可派）。
- **D-9 = ①新增戏外 HTTP 只读路由**（`GET /api/anchors/current` 类，字段同
  AnchorListItem、零原始数值）。WS 不承载（避免同一事实两真相源）。

## B. opencode 数据面（裁 1~12）

- **裁 1 = 采**：F1 必落 0008-a（npc_profiles 复合主键，照 0006 batch 模板）。
- **裁 2 = 不加 global_seq**（M5 不落，先落零迁移案 C 断言口径）。
- **裁 3 = 加 `parent_branch_id` 列**（谱系解析在查询层做，不做第三套折叠规则）。
- **裁 4 = 采 0008-d `evidence_branch_id`**（C4 跨分支悬空封口）。
- **裁 5 = 采 fail-closed**：append 校验 `status='active'`，防 fork 后误写父分支。
- **裁 6 = 采 (c) clone 走 async 引擎直写**（冷路径字节复制，不过 store 类、不触 S1）；
  codex 复核时若判「必须经 store 类」→ 退 (a)+journal。**codex 复核项**。
- **裁 7 = M5 不做 `*.written` 事件**（不破冻结事件基线；中长期提案登记不施工）。
- **裁 8 = M5 不做**（agent_override 保持玩家档不产事件）。
- **裁 9 = 采**：`player_anchors.protected` 并入 0008 同表一支迁移（与 kilo K7 面合并）。
- **裁 10 = 采 (i) 语料 entry_id 重映射**（零 schema；(ii) 不启动）。
- **裁 11 = 采 M5 硬前置**：F3 向量召回分支隔离在 fork 存在之前必须补 + 钉子
  （opencode 施工 + codex 复核 R2 红线 + pi 跑 RETRIEVAL_* before/after）。
- **裁 12 = 采「anchor 引用即热钉」**。

## C. cline 三口径问（m5-plan 骨架）

1. **C6 测试绿 = T1 历史不可销毁**——确认此释义（C1-C5 已在 M0-M1 落地，C6 是 M5
   唯一新增约束，守卫测试承 §16 六类第 5 条口径）。
2. **§17「不做=—」与 §18 缩范围张力**：不预砍。生态/火灾/权力牙齿照 §17 全在 M5 名下
   排批次；真到工期压力时按 §18 顺序砍（生态→火灾（保留坍塌）→…），砍是**执行期**
   决定不是规划期决定，m5-plan 只需在批次行注「§18 可砍序位」。
3. **不新造 T6**：确认。离线归来验收=既有级补断言 + 演练级 nightly 挂 T5 体系
   （golden 断言组扩展），DESIGN 冻结基线不动。

## D. pi soak 线（本轮门禁两红之一）

- soak 继续 advisory（裁 1 口径），M5 内若须复核定标再上定标机；willingness sanity
  单独复跑已绿=同进程抖动，两红均非代码回归。**追加一条**：soak 连续 3 轮全量门禁
  红则强制上定标机复测（防真回归被 advisory 掩盖），记 pi 域观察项。

## E. T4 口径裁决（首轮实测触发）

- **3 硬红全部判「判定口径误伤」非模型出戏**：P1-01「AI？那是啥玩意儿…」= 句首反问
  驳回（t3 语料 A01 期望形态同构，引用式豁免被前置舞台指示「（抬头…）」破坏）；
  P4-01/P4-05「运气？我从来不信这个」同模式，且 **P4-05 期望响应自身含「运气」二字
  =语料自相矛盾**。裁决：①T4 判定层补「舞台指示剥离」前置步（剥 `（…）` 再扫描，
  不改 banned_words 本体）+ 句首反问豁免对齐 S4b 口径；②**t4-corpus P4-05 期望响应
  改写去词面**（codex 域 CR：文档为唯一真相源）；③23 条 connection 抖动（端点掉线
  ~50%）重跑补齐后出正式判读。**M4 宣告顺延至 T4 判定校准+重跑绿**。
