
# memory.md — 多 Agent 记忆合集（分节收录各工作树各自的记忆）
> 用户规则 #7（main `3e320b9` 裁决：memory.md 入库）。本文件 = 五树 + 主树记忆的**融合合集**；
> 跨树收编由主导方（Claude）合并。各树本地副本是其对应节的**权威来源**，收编冲突时以各树版本为准。
> 新对话先读：.orca/talking.txt → 本文件**自己那一节** → .orca/workflow.txt + .orca/agent-registry.md。

## ① Claude（主工作树 / 主导）
> 新对话恢复序：talking.txt（任务单）→ 本节 → git log --oneline -15（轮次勾账）→ docs/arch/m3-plan.md §6。
- 主导/组织：架构/代码质量/逻辑/测试 + 前端/体验/发布/运维；评审 cline 与 kilo 的工作。
- 收编由我执行（merge 各 ZX466/* 分支 → uv run pytest 全量+bench+ruff/pyright → 裁决 → 推 origin+gitee → 六树 `git merge main` 同步）；派单写目标树 talking.txt，回执收主树；**不用 orca-cli 发消息**；上下文 50% 提醒切换。
- **M0+M1 全量收官；M2 全收官（九轮全收编，main `4e381c0` 前态 1003 passed）**；裁决 1-12 全落地（1 advisory 门/2 RNG330/3 V1V4V6/4 baseline 漂移 25%/5 {anchor_id}/6 cline 修正/7 pi 四红线/8 E1+knowledge 列/9 cline 口径/10 B3 七列/11 机型重对账/12 kilo 8.1-8.8）。
- **我 A2 批次链**：第二批 `59ffd86`（向量化）→ 第三批（smell/runtime 接线）→ 第四批 `805166e`（m3-plan 骨架）→ 第五批 `3bf49be`（批次 B 细化+B1 双列）→ 第六批 `1ae9e54`（E1 事件层+evidence.py+propagation.py，26 钉子转绿）→ 第七批 `f1c0c35`（reflection.py+society.py+relationship_store+budget 回填）→ **第八批 `64b7390`（2026-09-24，批次 B 生产面收口）**：①F2 收口=NpcRuntime.tick 第 0 步 delta 装配发 hidden_emerge_event（先于 NPC_ACT=证据链根先行，attr_ids 排序保 C5，bench/soak 调用形零回归）；②F1=工厂 witnesses 收窄 Sequence[str]+isinstance 拒 str/bytes/dict（codex S5 的 dict→ghost 键洗白向量封口）；③B-B2=run_world_driver 增 on_day_switch 钩子（**跨越判定逐日补发**，非 reflection_due 等值判定——帧驱动一帧 0..N tick，等值点 75-94% 被整帧跳过）+ reflection.make_day_switch_reflector 适配器（钩子 1-based→run_reflection 0-based 换算；ws.py 零 sim.npc 依赖）。新钉子 test_m3_e1_wiring.py 17 用例；全量 **1020 passed / 0 RED**，bench 36，pyright 全仓 0，ruff clean。
- **坑（实测过）**：①日切判定必须跨越式（prev_day≠new_day），等值式在帧驱动下丢日切；②工厂收窄 isinstance 须先查 str/bytes（str 本身是 Sequence）；③NPC 事件身份进 payload 不设 actor_id（npc_act_event 同口径，actor_id 是世界事件字段）；④pyright reportUnnecessaryTypeIgnoreComment=error——ignore 须落在真报错行，负例越型用 `Any` 中转变量而不是猜 ignore 规则名；⑤钩子回调同步形（run_reflection 无 IO），on_flush 是 async 形；⑥witnesses 装配在感知层（evidence.witnesses_of_emerge），runtime 无感知帧留空=fail-closed（witnessed 三要素齐才 0.9）。
- 【2026-09-24 第十轮快照｜opencode M3-D4 收编 + codex M3-S5 终验全过 + **批次 D 三项全落地**（main `8d17e40`）】**D4 收编**（`30dd087` → ff `3b560b9`）：knowledge 治理七列+0005 迁移（batch_alter_table 落 CHECK×3）+ KnowledgeStore（invalidate_by_source|row 沿 source_knowledge_id 广度递归，继承失效不继承替代，幂等+分支隔离+session= 同事务）+ X7 写入门（memory_scan 抽 decide() 唯一判梯，write/scan_fact 共用）+ T1 钉子 20 用例。**S5 终验四项主树实测全过**：R1 三硬断言（supersede→失效/told 链级联/链断拒收 reason=told_teller_knowledge_invalidated）、X7 grep 零裸 INSERT（Knowledge( 构造仅 knowledge_store.py）、裁10④ session= 同事务口、alembic 0005→0004→0005→0002→0005 往返零漂移（scratch DB；downgrade 须用全 id 如 0004_m2_npc_attributes，裸短 id 报 not valid）+ F1 Sequence[str] 复验。**批次 D（Claude 主线，三提交）**：D1 不成文规矩 v0（`08db7ed`）=sim/npc/norms.py（select_norms 他人属性知识 confidence 降序 top-5 同分行 id 稳定序+norms_text_of fact 直用不改写——X7 写入门是措辞唯一关口不造第二判梯）+ assembler NormSlice/[规矩] 段（[记忆]后[处境]前，messages[0] 锚不动=前缀缓存契约，空集段省略，norms 形参缺省 None 兼容既有调用）+9 T1 用例；D2 区块迷雾 v0（`a452ded`）=sim/world/fog.py FogOfWar frozen（revealed frozenset，reveal/reveal_position 返回新实例幂等，踏入即永久揭示无衰减 M3 最小集，O(chunks) 量级，纯内存不进事件流不进存档=视角投影非世界真相，玩家面 M4 再接）+6 T1 用例；D3 端到端 golden 雏形（`8d17e40`）=test_m3_retell_golden.py 全链闭环（见证 E1+witnesses→B witnessed 知识 write_fact 走门→retell 证据链判定+C 侧复制写记忆→C told 知识 source_knowledge_id 上溯置信 0.9×0.6→supersede 级联 B+C 行失效→链断后 C 再转述被拒）+自我披露链根（subject==holder 免上溯键）2 用例；T5 每日档真实 LLM 探针留 codex 可选跟进。**坑（本批实测）**：①自我披露链根判定 subject_npc_id==holder_id（holder=知识持有者本人，不是听话方），写反撞 _check_evidence_shape；②store.get() 返回 Optional，pyright 须先断言非 None 再取属性。**门禁：1093 passed / 56 skipped / 0 RED**（bench 64 passed 单独跑），pyright 全仓 0，ruff clean，双远程已推（origin 首推超时一次，重试成功）。
- M3 进度：批次 A ✅ / 批次 B 双收口 ✅ / C 过半（C1/C2/C4 ✅，C3 派 opencode 在途）/ **批次 D 三项 ✅**；M5 接口锚点待施工（kilo 对表+8.7 首修）。MVP ≈99%，全项目 ≈69%。
- 待办：收编 opencode C3（chunk 失效+§19.4 提案，任务单在其树 talking.txt）；codex 可选跟进 D3 真实 LLM 探针（T5 每日档，非阻塞）；kilo 提醒 M5 施工时订正 openapi_ext.py:17 与 ADDED_SCHEMAS 两处 M2-K3 遗留注释。
- 规则速记：#4 除 .orca 外点文件夹不入 git（.orca 下新增文件 git add -f）；#7 各树 memory.md 各存各的记忆（tracked，收编分节融合，各树本地版权威）；talking.txt gitignore 各树本地；npm/venv 删除先问用户；Python 必用 uv；playwright 只用 D:\develop\hermes\chrome；GitHub 走代理 127.0.0.1:7897；提交尾 `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。

【2026-09-26 第十六轮｜M4 二波五单收编 + 裁 16/17 + D2/D 批前置全就位】①五分支收编
（main `b9a0b50`）：opencode D2d `7b38afd`（material_balances 投影+0007+derive_tile_events
→C3 失效接线+15 钉子——**D2 四批全收官**）；pi P2 `6e7182e`（11 bench 用例定标，红线
草案转正式，fold 2.0µs/推进 1.75µs/图 6.11ms@10k）；kilo K8 `732e8c8`（NPC_MONOLOGUE
事件进流+payload extra=forbid 挡数值+三形态投递面路由：bubble/plan 广播 thought 定向
本人未知 form fail-closed+defers→plan）；cline C3 `e23e7c5`（T5 脚手架：虚拟时钟+有界
帧驱动+1 种子满日实测 53.98s→10 种子 1.5h，案 A 独立 golden-nightly 主张）；codex S2
`24d858d`（巧合安规：mix.adverse 流名/值零可见/灰区放行/T5 熵 off）。②**裁 16**（S2
V1-V4 全采）+**裁 17**（T5 六条：守恒逐位相等/完成率 10 日重定标/孤儿硬红/种子十枚定版/
golden-nightly 断言就位后建/builder 上提不做）。③门禁（`b9a0b50`）：not-bench
**1330 passed / 0 failed**、ruff 0、pyright 0。④**下一步=Claude 域 D 批行为链开工**：
巧合连锁熵注入（mix.adverse 事件族+感知帧零泄漏断言）+ T5 断言组填充（三断言按裁 17
口径）+ 差事 fixture 多决策续接 + impulse 三扫接线（I 系，codex 出断言）。
【2026-09-26 第十五轮｜M4 首波四单收编 + 裁 15】①四分支全收编（main `d409f29`）：
opencode D2a/b/c 三批（建造事件族六 kind+0006 迁移 structures 瘦身表+**matter_state 改
(branch_id,subject_id) 复合主键**+fold_structure_snapshot 两入口逐位相等+checkpoint
fail-closed+10k SupportGraph 稳定排序 BFS+级联按帧摊还每帧≤100 条跨帧幂等，85 钉子）；
kilo K7（state_delta 顶层 plan 字段——空账本不发键/已清实体发空串/rtoken 出网关；
_impulse_cue 升级钩子缝且 band→cue 真源指回 will.py 跨域衔接一次做对；anchors.py
两路由+register_anchor_id 注入还部署债 #1，852 行 52 钉子）；cline C2（t4-nightly.yml
schedule-only UTC19:30 与 bench 错开+锁模型 env+secrets 骨架期 ::notice:: 不红防「静默
跳过误读全绿」+探针五条接线约定 TODO 指 S1）；codex S1（143 行：念头 WS 入站三扫
I-1 banned/I-2 hidden 按被注入 NPC profile/I-3 操纵感预污染——**WS 是 M1 后新增未扫描
面**；运气 L-1/L-2/L-3 含 PerceptionFrame 无 luck 字段 DESIGN §16 补充断言；4 待裁）。
②**裁 15 四条全落** S1 §10：I-2 采主案（入站即扫脏文本不进口，接线点=impulse 入站
后 prompt 装配前）/熵流 dev 日志留痕 OK 三面禁入/T4 预算 60/夜采/P4P5 排批次 A·D 后。
③门禁（`d409f29` 实测）：not-bench **1273 passed / 0 failed**（复合主键迁移零回归）、
ruff 0、pyright 0。④待办：opencode D2d（材料投影+TILE_CHANGED 接线）待派；pi 转
M4-P2 定标待派；B 批接线（runtime 消费 verdict+impulse 三扫接线）Claude 域在途。
⑤用户侧待办：GitHub 仓库创建 T4_MODEL_API_KEY secret（cline 卡里列明）。
【2026-09-26 第十三/十四轮｜M3 收官 + M4 开工 + 裁 14】①五树交付全收编（main `57e1dc9`）：
codex S6b `686caa8` 收官门动态复验通过——**M3 正式收官**（功能全量 1076 passed/0 failed、
S4 10k 零回归、七钉子+S4 148 passed、bench 11F 判裁 1 抖动）；kilo K6 `13cb5b5` WS 分发块
六类 C→S 全落地 56 钉子（TDD stash 复验真咬；set_control 栈式会话态/impulse 乐观 feedback/
load_anchor 不透明串+失败不断线；两处 LLM 域占位 _impulse_cue/叙事模板待 M4-B 替换；
_ANCHOR_IDS/_ANCHOR_LOAD_HOOK 两处部署债登记在 anchors-api）；cline C1 `4b19f31` m4-plan.md
136 行骨架（A‖C→B→D；T4=锁模型 nightly 连续通过）；opencode D1 `a725a65` 建造域预研
（structures 瘦身/structure 事件族/checkpoint 施工/内存图/MATERIAL_MOVED，7 待裁点）；
pi P1 `88284c3` 预算预研（M4 可用 2.10ms/13%；BFS 成本模型；4 红线草案；与 D1 7 行交叉对账，
硬约束=collapse 事件按帧摊还 10k 级 307% tick）。②**裁 14 六条全落 m4-plan §6**：批次边界
照切 / M4-D1 主干采信+7 点全裁（复合主键同轮修正、phase 入表、rubble=tombstone、quality 归
matter 投影、单材料起步、图触发器=频率×成本、材料同事务守恒）/ 计划看板落前端 / T4=codex
探针+锁 claude-sonnet-5+cline 接 nightly / 运气=只进事件流 / 批次 D 承担 T5 golden。
③门禁（`57e1dc9`）：not-bench **1112 passed / 0 failed**、ruff 清零（裁 13 引入的 E501 我域已修
——codex 判「pi 域」系误判，文件是我写的）、pyright 0。④教训：pi↔opencode 提案交叉对账模式
效果好（性能侧逐条表态设计侧），M4 各域预研继续用。
【2026-09-25 第十二轮｜五树收编 + S6 预审裁决 + M3 收口件】①五分支全收编（opencode C3b `29f9d6c` register 返回 MATTER_BUILD 立账事件+9 钉子；kilo K5 `e763b04` sync_request 改回 full_snapshot 复用 snapshot_payload 不动签名+5 钉子；pi P3 `1a745ea` 失效通路实测+红线提案两行 0.10/2.0 待裁；cline C9 `5e3719d` README 三节拆分+§2 补四行——当场勘误我卡里 D4 hash 笔误；codex S6 `700015a` 收官门静态预审 117 行+5 发现）。②S6 五发现全裁：F-a 采 M3 内补（我主树 test_t1_m3_breakdown_deadend.py 4 钉子：prompt 三段零 bias 词面/白名单无诊断键/persistence+norms 零 breakdown 构造隔离扫描——注意 X2 死路=写入侧不喂，非 norms 二次过滤，BIAS_NAMES 不在 banned 词表是前提）；F-b 采① M3 内补（iter_visible 补 branch_id 过滤+TestBranchIsolationMemorySide 2 钉子；get 保持审计面跨分支）；F-c 采（m3-plan §4 六行 🔴/待派→🟢）；F-d 采（norms 补 TestNormsSelectionBoundary 3 用例对齐记录）；F-e 无动作留痕。③pi 红线提案待裁（失效通路独立行 0.10/2.0 不占 retrieval 预算）——我倾向采，留待收官门后一并落。④pyright 坑：Literal source 别硬编码字符串（"observed" 不在 MemorySource）、SimpleNamespace 喂 ORM 类型须 cast、MemoryHit.breakdown 声明 tuple 别用 += tuple 拼接再传。⑤ruff E501 坑：中文断言行 101 字符必炸，列表字面量拆行。
⑥门禁终态（main `0ee9cb6` 实测两轮）：非 bench **1131 passed / 56 skipped / 0 failed**＝CI 口径全绿；bench 全量跑 16 failed / 单独跑 11 failed，但失败集合轮换且 rng/retrieval 单独复跑全绿（5/5、8/8）＝**负载抖动实证**（第七轮同模式，裁 1 advisory 口径），非代码回归。教训：后台全量跑时源码被并发修改则该轮作废（第二次全量因此重跑）；判定 bench 抖动必须「单独复跑同一文件」对照。
⑦pi P3 红线已裁 13 全采（CHUNK_EVENT_SCAN 0.10 / CHUNK_INVALIDATION_TICK 2.0，独立行不占检索预算）；bench 侧维持 _record_proposal 观察态。
【2026-09-25 第十一轮｜C3 收编 + §19.4 裁决】opencode C3 收编 main（ff `5724aa7`）：
chunk 失效量化通路（TileMap PrivateAttr 脏集 + with_collision 不可变换图断 PrivateAttr 串扰 +
event_tile_position 事件桥 TILE_CHANGED 全量/MATTER x/y≥0/-1 哨兵不标 + Pathfinder
observe_events/invalidate_dirty/observe_map 精确失效）+ 24 钉子（剔1留1/未定位 no-op/封格绕行/全封不可达）。
门禁主树实测：**1117 passed / 56 skipped、bench 64、pyright 0、ruff ok**。
碰撞极性核实：collision 数组语义=M0 遗留存可通行性，with_collision(x,y,walkable) 与既有 is_walkable 一致无反转。
§19.4 裁决（main `16f2983`，matter-register-proposal.md §6）**四点全采主张**：
①采 A register 返回 MATTER_BUILD 立账事件（amount=0/durability=integrity/note="register"）否 A' 新 kind；
②返回事件不注入 EventSink；③structures 表 M3 不建留 M4；④x/y 默认 -1。
实证依据：_project_matter 首事件即建行、折叠按 durability 非 amount；-1 哨兵与 C3 event_tile_position 衔接（纯注册不标脏）。
schema.md §19.4/README/m3-plan 已同步已裁状态。实施放行 opencode「M3-C3 后续件」（register 签名+调用方接线+test_m3_matter_register 钉子）。
坑：cline/pi/kilo merge 冲突均为「当前任务」小节（main 带 opencode 文本 vs 各树待命文本），按各树本地版权威解决；
.orca 在子树也是 gitignore 的，tracked 文件须 `git add -f`。
## ② cline（依赖 / 配置 / 文档域）
- 【2026-09-26 第十四轮快照｜M4-C3 T5 golden 脚手架已交付待收编】新建 `docs/arch/t5-golden-scaffold.md` 提案（形态=**虚拟时钟+有界帧驱动+录制 fixture 回放**；与生产 `run_world_driver` 只差两点：真实 dt→虚拟帧、`while True`→跑满即返回；帧序/日切**跨越判定**逐条对齐）+ 骨架 4 件（`sim/tests/golden/{__init__,seeds,driver,test_golden_smoke}.py`；seeds=10 写死常量+`TICKS_PER_SEED=864000`、driver=`run_golden`+`GoldenRun/DayWindow` **只取数不断言**、smoke=env 门 `PI_GOLDEN_SMOKE=1`+`GOLDEN_SMOKE_TICKS` 切片）+ m4-plan 批次 D「脚手架已立」注记。**runtime 实测（本机）**：满一游戏日 86,400 tick = **53.4 s**（0.62 ms/tick @10 实体）→ 10 游戏日 ≈8.9 min/种子、10 种子串行 ≈1.5 h；50 NPC 口径（0.9–1.9 ms/tick）→ 2.2–4.5 h 串行 ⇒ **主张独立 `golden-nightly.yml` + 种子分片 matrix**，不并入 t4-nightly。**三断言组只给口径未写断言**（纪律）：守恒按物质面逐面枚举 + 逐位相等；差事完成率复用 `fixtures/errands.py` 20 条 + M1 ≥80% 线，**已识别缺口=现 fixture 是单决策场景、需补多决策续接**；无孤儿变更给双向 SQL 骨架 + **必假红坑：方向 B 必须排除 `entropy_inject`**（熵只进事件流，裁 14-5）。**验证**：满一日 `1 passed in 53.98s`、切片 0.55s、默认 env `1 skipped in 0.21s`（不进每提交 CI，**无需改 ci.yml**）、全量 collect 1401 exit 0、ruff/format/pyright 绿。**坑（第二次）**：editor 建文件必带 CRLF——5 个新文件提交前已全部改回 LF，检查动作固化为「新增文件后必跑 `git ls-files --eol` + 字节级 CR 计数」。**待命**：断言组阈值/种子清单/projection 实表名/golden-nightly 落地时机待 Claude 裁。
- 【2026-09-26 第十三轮快照｜M4-C2 T4 nightly 接线已交付待收编】**T4 接线落地**：新建 `.github/workflows/t4-nightly.yml`——触发**仅** schedule（UTC 19:30，与 nightly-bench UTC 18:00 错开）+ dispatch；`env` 锁 `T4_MODEL=claude-sonnet-5`（模型 id **硬编码 env 不进代码**）+ `T4_MODEL_API_KEY`（只经 secrets，**值不落盘/不进日志**；**secret 需用户在仓库侧创建**，未配时骨架期 notice 不红、探针接上后改硬失败）；骨架含 model-lock 证据 / `if: always()` 归档 / 失败通知 / 30min 护栏，**探针步骤留 TODO** 指向 codex M4-S1 `346dfa1`（未收编）。**不进每提交 CI**（§16 铁律，ci.yml 未引用）。`pytest.ini` 补 `t4` marker（`--strict-markers` 要求先注册；`-m t4 --collect-only` exit 5 无 unknown-marker）。`m4-plan.md` 填实（建议→裁 14 已裁 + 每批「已派任务」行 + §4 接线状态 + §7 状态）。**避坑**：Claude 已用更完整细则重写 m4-plan §6（D1 七点/pi 摊还红线/ENTROPY_INJECT）——我的替换未命中即**未动 §6**，改加交叉指针，避免降级覆盖与细则双写漂移。**§2/§5 补行**：补 `m4-plan`/`m3-closure-preaudit` 两行 + 修两处过期状态（`88284c3`/`a725a65` 实已在 main 却仍写 ⏳）+ §5.2 补 M3-S6 + **新建 §5.3 M4 交付状态 6 行**（M5 预备顺延 5.4）。**验证**：YAML 解析通过、五表列数自洽、冲突标记 0、全树 `w/crlf`=0（新 workflow 建完即改回 LF）、DESIGN.md 零改动。**待命**：M4-S1 收编后接探针步骤；M5-K4 仍未入 §5.4。
- 【2026-09-25 第十二轮快照｜M4-C1 计划骨架已交付待收编】新建 `docs/arch/m4-plan.md`（136 行骨架：§0 §17 七件事原文拆条／§1 DESIGN 依据速览／§2 依赖排序 A‖C→B→D／§3 批次 A-D 建议（内容+负责域+依赖+验收口径四列）／§4 **T4「全绿」= 锁定模型版本下 nightly 连续通过（非每次提交绿）** + 探针↔批次对应 + 接线归属／§5 门禁归属速查／§6 待裁 6 条／§7 衔接），全文标「建议」+ 首尾「待 Claude 裁批次边界后才逐行填实」；README §5.2 追加 M3-S6b 收官行（`686caa8`，**状态按 git 改 ⏳ 待收编**——卡片写「在途」，实证 `is-ancestor 686caa8 origin/main`=False）。**关键决定**：T4 定义域写死 nightly 锁版本（§16 + `ci.yml` 头注同口径），T4 接线归我（配置域）但**本单不动 workflow**；DESIGN.md 零改动。**坑（新）**：①editor 新建文件写出 **CRLF 工作副本**（索引被 `.gitattributes text=auto eol=lf` 归一为 LF→提交内容无误，但工作副本违反 M2-C2 纪律），已改回 LF（CR 135→0，全树 `w/crlf`=0）；②PowerShell `Select-String -Pattern \"`r\"` 查 CR **假绿**，行尾一律以 `git ls-files --eol` 为准；③改行尾后 `git status` 可能报幽灵 M（worktree/index/HEAD 三方 hash 实为一致），同路径 `git add` 刷新 stat 缓存即净。**下一步**：等 Claude 裁批次边界后填实骨架；T4 nightly 接法裁到我名下再接 workflow。
- 【2026-09-25 第十一轮快照｜M3-C9 文档收口已交付待收编】README **§5 按里程碑三节拆分**（`5.1 M2` 35 行 / `5.2 M3` 10 行 / `5.3 M5 预备` 3 行；脚本按行首列前缀 M3-/M5-/其余 分组，**既有 46 行内容逐字未改**——diff 删除行只有旧标题 + 6 行移位 + M3-C3 旧状态）+ **§2 补四行**（`m3-retrieval-budget` `1d09581`／`anchors-api` `b849025`／`t1-sampling-10k` `38a7f63`／`ci-calibration-m2p6` `8fd9a17`，hash 全 git 实证）+ **M3 节补三行**（M3-D4 `30dd087`／M3-C3 `5724aa7` 状态由「⏳ 待收编」修正／M3-§19.4 注册持久化裁决 `16f2983` 四点全采：register 产 `MATTER_BUILD` 立账、返回事件不注入 EventSink、structures 留 M4、x/y 默认 -1）。**坑（卡片摘要须对原文，本轮第二次踩到）**：卡里 M3-D4 写 `3b560b9`，git 实为 memory.md 清占位 chore，真身 `30dd087`（Claude 第十轮快照亦记「`30dd087` → ff `3b560b9`」）——**凡 commit 引用一律 `git log` + `merge-base --is-ancestor` 双验**。**核对项**：`docs/data/matter-register-proposal.md` 卡片状态「✅ 已裁」实证通过（文档头「已裁决：采方案 A」+ `16f2983`），未改一字。**验证**：§5.1/5.2/5.3 = 37/12/5 行 × 5 列、§2 = 34 行 × 4 列、冲突标记 0、无 CRLF/BOM、8 路径在盘、7 hash 逐一 is-ancestor main。**待命**：M5-K4 / A2 第七·八批（`f1c0c35`/`64b7390`）/ M3 批次 D 三件（`08db7ed`/`a452ded`/`8d17e40`）是否补表待 Claude 裁（已回执请裁）。
- 【2026-09-24 第九轮快照｜M2-C8 全闭环已收编】README §5 表至第八轮 47×5 行 + §2 文档地图补 m3-plan/m3-evidence-chain；卡片勘误（M3-D1 真身 opencode `4da190d`）。C1-C8 全收编。**active 约定**：CI 门禁按文件路径接不用 -m（P04 教训）；`perf/` 目录须 mkdir（git 不跟踪空目录，C5 根因）；Windows CRLF 假红已根除（.gitattributes，自检 `git ls-files --eol | grep -c 'w/crlf'` 期望 0）；`.orca/` 下新增文件须 `git add -f`（catch-all `.*/` 未豁免，规则 #4 语义）。**待命**：M3 收官时补 §5 M3 分节（现混装 M2/M3 行，等批次 B/D 收口后分节改名）。§2 遗留四行（m3-retrieval-budget/anchors-api/t1-sampling-10k/ci-calibration-m2p6）仍待裁。
- 【历史】第五轮及更早快照（C4-C8 交付/验证/CI 实证细节，约 3k 字）已按 workflow §8 压缩为指针 → 考古命令 `git log --oneline -- .orca/memory.md` + 本树 talking.txt 留言板；现状看上方第九轮快照。
> 新对话开场先读本节 + .orca/workflow.txt + .orca/agent-registry.md。能力域：依赖/配置/CI/文档域；评审 codex 与 pi 的工作；评审 Agent=Claude。
> **本文件已入库**（main `3e320b9` 裁决，规则 #7）——改动走提交；跨分支同路径由 Claude（主导）收编合并。
> 另读：`.orca/talking.txt`（任务指派）、`docs/dev-workflow.md`（含 **§7 Windows 行尾假红**——本机格式类检查报错先看那节）。

### 我已交付（全部已收编）
- **M2-C1**（收编 main `19e3a88`）：docs/README §5 M2 区块 + M2 依赖对账（**零新包**）+ ci.yml M2 占位步骤 + nightly M2 红线接入点注释 + `.gitattributes` 正式提议。
- **M2-C2**（收编 `b1f3d6c`）：`sim/world/weather.py` 风场（`wind_at(tick, rng)` 纯函数可重放 + `daily_reseed_due` 每日天气注入点；`sim/tests/test_m2_weather.py` 31 用例）+ ci.yml M2 步骤填实（glob `sim/tests/test_m2_*.py`，命名约定即契约）+ dev-workflow §7 重签出手册 + **六树重签出执行**（w/crlf 全 0，prettier/gen-protocol 假红消失）。
- **M2-C3**（纯校验，无提交）：M2 glob 实选 6 件/113 用例 ✓、5 个命名门禁无重复接 ✓、SOAK step/env 门/5 条红线对账 ✓、768 passed 口径 ✓、六树 crlf=0 ✓；**揪出 P0=README §5 未解决合并冲突标记进了 main**（Claude 修 `cbf40ee`），P1/P2 口径过期由 codex 代修。
### 已内化教训（实测过，别再踩）
1. **Windows CRLF 假红**（根因已消除）：`.gitattributes`（`* text=auto eol=lf`）已裁决落地（main `3ab8c71`），各树一次性重签出后 161 个 `w/crlf` → `w/lf`，本机 `prettier --check` / `gen:protocol --check` 不再假红。**自检一条命令**：`git ls-files --eol | grep -c 'w/crlf'` 期望 0（>0 = 该树没重签出）。重签出**只有** `git rm -r --cached . && git reset --hard` 管用（`git checkout-index -f -a` 实测无效；先 commit/stash，未跟踪文件不受影响）。操作手册在 `docs/dev-workflow.md` §7。
   - M2-C2 六树实测（2026-09-21，仅对**干净树**执行）：`w/crlf` main 115 / cline 158 / codex 159 / pi 150 / opencode 151 / kilo 151 → **全 0**；重签出后 `npx prettier --check .`（"All matched files use Prettier code style!"）与 `gen-protocol --check` 均 EXIT 0 —— P05 时代的假红确认消失。
2. **CI 门禁按文件路径接，不用 `-m xxx`**（P04 教训：marker/addopts 一变就被静默排除成假绿灯）。M2 现状＝glob `sim/tests/test_m2_*.py`（**命名约定即契约**，新 M2 验收测试落该前缀自动进门禁）+ `-m "not bench"` + `timeout-minutes: 15` 双护栏；完整 604,800 tick 跑在 nightly（**方案 A 已裁决落地**：step 跑 `test_bench_soak.py::test_m2_full_7day_acceptance`，env `PI_M2_FULL_SOAK=1`，timeout 60）。**我的挂账义务：里程碑后把该 step 迁出为周频独立 workflow**（nightly 注释 + m2-acceptance §4 已写明）。
3. **跨域代改须留言**：opencode D03 的 3 文件 ruff 格式偏差属数据域文件，修复前在其树 talking.txt 留言说明（f775b91）。
4. **与主导方裁决冲突时，以 main 实际决策为准**：memory.md 入库裁决（`3e320b9`）推翻我此前「移出跟踪」提交（cb2d85e），已在 76d6a03 反转并恢复入库。
5. **量纲先算再写门槛**：写 CI/验收前先按 DESIGN 推 tick 数。M2 完整验收「50 NPC × 7 游戏日」= 604,800 tick（1 tick = 1 游戏秒），**不属于每提交 CI**——所以 M2 步骤是占位 + `timeout-minutes: 15` 护栏，而不是写死路径。
6. **别在他域分支上重复接门禁**：codex 的 M2-S1 已自带 ci.yml 步骤（其分支内），M2 占位步骤不重复接同一文件；同一门禁两处维护会漂移。
7. **`.gitignore` 的 catch-all `.*/` 会挡住 `.github/`、`.orca/` 下的新增文件**：已跟踪文件不受影响（改 ci.yml / memory.md 正常），但**新增**文件 `git add` 会失败并提示 ignored，须 `git add -f`。**已裁决部分**：`.github/` 补了例外（`!.github/` + `!.github/**`，main `3ab8c71`，新增 workflow 现在可正常 `git add`）；**`.orca/` 未补**：`.orca/` 下新增文件继续用 `git add -f`（要改规则得再请裁——它属用户规则 #4 语义）。
8. **纯函数优先于「推进式 RNG」**：`sim/world/weather.py` 若用 `RngRegistry.generator(name, cache)` 抽签就会**推进状态**（调用顺序影响结果，回放/bench 不可重算）。正解＝从 `rng.draw_key(流名)`（材料指纹，含熵注入）派生档位种子 → 每次新建 `Generator` 抽，得到「同 (rng, tick) 恒同风」。写任何「按 tick 派生的物理量」都照此办。
### 常用命令（M2-C4 口径）
- 本树开工第一步：`git merge origin/main`（常落后 main，P05/P04 都遇到过）。
- 全量：`uv run pytest -m "not bench"`（**最新口径见 ① Claude 节**：main `64b7390` = 1020 passed、bench 36；本节旧数 805/847 已作废）；bench：`uv run pytest -m bench`。
- M2 门禁复演：`uv run pytest sim/tests/test_m2_*.py`（我的文件＝test_m2_weather.py）。
- 行尾自检（应 0）：`git ls-files --eol | grep -c 'w/crlf'`。
- `.orca/` 写入一律 `git add -f`：catch-all `.*/` 未豁免，**已跟踪的 memory.md 更新也须 -f**（workflow §8 明确要求）——否则 `git add` 只报 ignored 提示，文件容易漏进提交。
- nightly 取证/触发（本机 `gh` 已认证 ZX466，scopes 含 repo+workflow；调用前须 `$env:HTTPS_PROXY='http://127.0.0.1:7897'`）：`gh run list --workflow nightly-bench.yml`、`gh run view <id> --log-failed`（**注意**：bench step 红时 pytest 汇总可能未打印，改用进度行 `test_bench_*.py` 的 `.`/`F` 标记判失败集合）、`gh workflow run nightly-bench.yml --ref ZX466/cline`。
### 未决项
- **C4–C8 全部收编**（`1772f3a` / `db092ed` / `4470fd0` / `0eff1e9` / `925b39d`），旧挂账已清；nightly 残留次因亦了结：裁 1 advisory 门 + 裁 2 RNG 330 已由 pi 落地（P6 `8fd9a17`）。baseline.json 入库按裁 4 走 pi 主导流程，我域只配合 workflow 侧。
- **里程碑后 soak 完整跑迁出**：nightly step → 周频独立 workflow（我迁，已在 nightly 注释/m2-acceptance §4 挂账）。
- `.orca/` 例外不补（裁决维持）：新增文件一律 `git add -f`。
- 嵌入模型选型（M3）：走已锁 openai 客户端＝零新包；本地模型须先过依赖评审。

（各节由对应 agent 维护；快照纪律见 workflow §8：交付后在**自己节**顶部写一行快照 `【日期 轮次｜状态】`，旧快照压缩为 `git log --oneline -- .orca/memory.md` 指针，不无限堆积。）

## ③ opencode（数据 / 数据库域）
- 【2026-09-26｜**M4-D2d 已交：D 批数据面收官**】新增 `MaterialBalance` + `0007_m4_material_balances`（PK branch/ref/material，索引 branch/material）；`npc_store` 加 `_MaterialEventFields`、`fold_material_balance`（from 减/to 加单折叠）、`_project_material_moved`、快照/重放两 `materialize_material_balances*`。守恒口径：同材料净额和为 0（测试容差 1e-9），`world:*` 外部供给基准允许净负，`npc/structure` 余额不足 fail-closed；MATERIAL_MOVED 与 structures/events 同批事务，失败三面零写。`structure.py` 加纯函数 `derive_tile_events`：仅 COMPLETED/COLLAPSED/REMOVED 按 snapshot.tiles（已排序）逐 tile 产 TILE_CHANGED，tile_id 由调用方从静态 TileMap 给；15 T1 钉子含精确 chunk 剔1留1/重复幂等。门禁：功能全量 **1288 passed / 55 skipped**、ruff 全仓 ok、pyright 0、0007 scratch autogenerate 仅 pass。**已知接线缝（架构域）**：world.py EventBus 仍拒 TILE_CHANGED 且未注册 STRUCTURE_*/MATERIAL_MOVED；生产 Pathfinder 仍是每 WS 连接新建、无 world 级持有者；事件不携 previous_tile_id（还原靠静态地图）；MaterialMoveReason 无 collapse sink。**M4-D2/D 批数据面全收官。**
- 【2026-09-26｜**M4-D2c 已交：10k 承重图 + 按帧摊还级联**】新增 `sim/world/support_graph.py`：`SupportGraph` 从 `(branch_id, StructureSnapshot)` 一次物化正/反向图（dependents 稳定排序）；建图拒绝混合分支/重复 id/悬空/自环/重复边/环（Kahn 全量处理计数）/planned|building 承重，支撑必须 active+load_bearing。`CascadeState/CascadeStep` 游标按 id 堆序推进，每帧最多 `CASCADE_EVENT_BUDGET_PER_FRAME=100` 条 STRUCTURE_COLLAPSED，跨帧续跑且完成后幂等零事件；support_path 只记**直接失去的支撑**（避免 10k 深链 O(n²) 复制）。12 T1 钉子含 10k 节点链=100 帧全量摊还（0.3s）。门禁：功能全量 **1221 passed / 55 skipped**、ruff 全仓 ok、pyright 0、scratch autogenerate 仅 pass。**M4-D2 三批完成**；下一单 D2d 材料守恒 + TILE_CHANGED 派生/chunk 接线。
- 【2026-09-26｜**M4-D2b 已交：structure 单折叠/重放 + checkpoint 纯函数**】新增 `sim/world/structure.py`：`StructurePhase`、`StructureSnapshot`、`BuildProgress`；`advance_build` 按 `build_rule_version` 选 v1 线性规则（未知版本 `UnknownBuildRuleError`，绝不回落），`next_checkpoint_tick/checkpoint_due/mark_checkpoint/build_checkpoint_event` 以每游戏日 86400 tick 且相对上次 checkpoint 分桶（同日只发一次），`recompute_tail` 确定性重算。`npc_store` 新增严格 JSON codec + `_StructureEventFields`（投影/重放共用解码）、`fold_structure_snapshot`（STARTED→building/重复拒、CHECKPOINT 保相、COMPLETED→active+built_at、COLLAPSED→rubble tombstone、REMOVED→None 删行；orphan 拒）+ `_project_structure` + `materialize_structures` 快照路径 + `materialize_structures_replay` 纯读路径（与投影共用 `_STRUCTURE_KINDS` 与单折叠）。25 钉子：全生命周期/坍塌/移除两入口逐位相等、NULL↔""、同批 started+checkpoint、分支同 id 异拓扑、orphan/重复回滚、坏 JSON fail-closed、cadence/重复抑制/未知版本/尾部精确。门禁：功能全量 **1209 passed / 55 skipped**、ruff check 全仓 ok、pyright 全仓 0、scratch DB autogenerate 仅 pass（无迁移）。**下一批 D2c**：内存承重图（10k 验收）+ 级联按帧摊还/事件预算。
- 【2026-09-26｜**M4-D2a 已交：事件族 + 0006 迁移/分支身份**】EventKind 追加 6 kind（structure.started/checkpoint/completed/collapsed/removed + material.moved；MATTER_COLLAPSE 折叠未动），6 payload 全 extra=forbid + id/坐标/时长/数值域/枚举 cause/reason + 无 note + 工厂拒 str/bytes/dict 洗白，PAYLOAD_MODELS 登记且加「所有 kind 必有 payload 模型」全登记钉子（52 用例）。`Structure` 瘦身 ORM：branch/structure 复合主键 + tiles/kind/material/phase/load_bearing/supported_by/owner/built_by/built_at，**不存** integrity/quality/decay_rate/is_rubble；`MatterState` 主键改 `(branch_id, subject_id)`，`_project_matter` 与 10 处测试 `session.get` 同步改双键；既有 `test_replay_branch_isolated` 升级为同 matter_id 跨分支各重建。迁移 `0006_m4_structures` 用 naming_convention 命名 0004 旧 PK 后 batch 改主键 + 建表/三索引，schema/migration/build-preplan/README 同步。schema/迁移 8 用例含同 id 跨分支共存、0006 往返。门禁：功能全量 **1184 passed / 55 skipped**、相关 102、ruff check 全仓 ok、pyright 全仓 0、scratch DB autogenerate 仅 pass；`-m not bench` 唯一红为既有 `test_soak_ci_smoke_stability` 本机性能档位漂移（均值/漂移互漂，窗口不同）。**下一批 D2b**：structure 投影/重放单折叠 + checkpoint 纯函数逐位相等。
- 【2026-09-25｜**M4-D1 建造域数据面预研已交提案待裁**】新增 `docs/data/build-domain-preplan.md`（286 行，纯文档）：structures 取裁为拓扑/生命周期投影，移除 integrity/quality/decay_rate/is_rubble 重复熵态列；建议 `structure_id` + `(branch_id, structure_id)` 复合主键但与 matter identity 同轮对账。事件流主张 TILE_CHANGED=地图派生、MATTER_*=熵态、新 structure 事件族=建造/拆除/坍塌真相；施工采用「started + 有界 checkpoint + 终态」，否决每 tick 事件（86,400 tick/木棚）与只终态；M4 承重用 `supported_by` JSON 投影的内存正/反向图，不建 SQL 边表；材料用 `MATERIAL_MOVED` 来源→去向事件，与结构/matter 投影同批事务。逐条映射 C1-C13，7 个待裁点：事件族、checkpoint cadence/尾部重算、分支身份、phase/rubble、quality、多材料、图升级触发器、材料 reservation/幂等。README §2 已登记；无 models/迁移/代码改动。门禁：pyright 0；ruff 仅报既有 `sim/tests/bench/test_bench_chunk_invalidation.py:11` E501（本提案未改该文件）。
- 【2026-09-25｜**M3-C3 后续件已实施待收编**】`MatterLedger.register` 增 `tick=0/x=-1/y=-1` 并返回 `MATTER_BUILD` 立账事件（amount=0、durability=夹后 integrity、decay_rate=夹后 rate、note=register）；先构造/校验事件再写账本，非法 payload 不半注册。投影零改动：`MATTER_BUILD` 既有 `_project_matter` 首事件建行 + `fold_matter_snapshot` 单规则。`test_m3_matter_register.py` **9 钉子**：事件形状、flush_tick 快照冷启、flush_events 纯事件重放、仅注册对象两入口逐位相等、amount=0 不扭 integrity、重复注册不替换、非法 payload 原子性、x/y=-1 不标脏、定位坐标透传。生产 grep 无 register 调用点，**不造调用方**；flush 口径写进提案：快照须 `NpcStore.flush_tick`，`flush_events` 只保重放。文档回写 schema §19.4 规范契约、m3-plan C3、README。门禁 **1090 passed / 55 skipped**、ruff ok、pyright 0；零 schema/迁移（scratch DB autogenerate 仅 `pass`）。
- 【2026-09-25 裁决｜§19.4 四点全采（Claude 主树裁决）】C3 已收编 main（ff `5724aa7`，门禁 1117 passed/bench 64/pyright 0/ruff ok）。裁决见 main `docs/data/matter-register-proposal.md` §6：①采 A（register 返回 MATTER_BUILD 立账事件 amount=0/durability=integrity），否 A' 新 kind；②采「返回事件」不注入 EventSink；③structures 表 M3 不建、§9 保留给 M4；④x/y 默认 -1（与 event_tile_position -1 哨兵衔接，纯注册不标脏）。**实施已放行**：按提案 §4 草案动代码（register 签名 + 调用方接线 + test_m3_matter_register.py 钉子 + schema.md §19.4 回写核对），完成后「M3-C3 后续件」交付待收编。
- 【2026-09-24 第十轮｜**M3-C3 已交付待收编**（chunk 失效通路 + §19.4 提案）】分支 `ZX466/opencode` 基于 main `2976cf1`，一次性提交（未推远程等收编）。**①chunk 失效量化通路**：`sim/world/map.py` TileMap 加 `PrivateAttr _dirty`（frozen 几何不动，脏标=瞬时态不进快照）+ `dirty_chunks()` 真实排序返回 + `mark_tile_dirty`/`mark_chunk_dirty`/`drain_dirty` + `with_collision(x,y,walkable)` 不可变换单格且新实例独立脏集（`model_copy` 共享 PrivateAttr，须 `object.__setattr__(new,"_dirty",{key})` 断开——否则新旧图串脏）；`sim/world/pathfinding.py` 加 `event_tile_position`（TILE_CHANGED 全量 / MATTER_* 仅 x/y≥0、-1 哨兵不标 / 无关 None）+ `Pathfinder.observe_events`（标脏+精确失效）/`invalidate_dirty`/`observe_map`（换图消费脏集）。投影与持久层**零改动**。钉子 `sim/tests/test_m3_chunk_invalidation.py` **24 用例**：跨 chunk 剔1留1、定位 matter 失效、未定位/无关 no-op、空批幂等、远端剔0、with_collision 不串脏、封格绕行、窄图全封失效后抛不可达（缓存不吐陈旧路径）。**②§19.4 提案**（文档制未动代码）：`docs/data/matter-register-proposal.md`——**主张 A**：`register` 返回 `MATTER_BUILD` 立账事件（amount=0、note=register）走 C4 唯一写路径，零 schema；**否 B** structures 作注册主路径（表未实现+双真相+拓扑/熵态正交）；默认否 A' 新 kind；structures 留 M4 拓扑投影再议。4 待裁点在提案 §5。交叉引用：schema.md §19.4、m3-plan §6+批次C 行、README §2+§5。**门禁：1081 passed / 55 skipped / 0 failed；ruff ok；pyright sim/ 0 error；alembic 零漂移**（scratch DB autogenerate 仅空 pass，已删临时迁移）。**坑**：本树根 `world.db` 是脏库（alembic_version 缺失但表已存在→upgrade head 撞 branches exists）——零漂移核验必须 `WORLD_DB_URL=sqlite+aiosqlite:///<scratch>`，别用默认 world.db。
- 【2026-09-24 第九轮快照｜D4 已交付待收编】**M3-D4 已交付**（B3 实施，裁 10 全采 + codex 预审 7 要点，分支 `30dd087` 基于main `4e381c0`，已补推双远程）。**0005_m3_knowledge_governance**：knowledge `add_column`×7（subject_npc_id/subject_attr_id/evidence_seq/source_knowledge_id + source_memory/invalidated/invalid_reason）+ 索引×3 + CHECK×3（source 取值域/confidence 值域等可表达约束）；`KnowledgeStore.invalidate_by_source|invalidate_by_row` 级联 + `write_fact` 走 X7 写入门 + T1 钉子 test_t1_m3_knowledge_cascade。
- 【B3 实施三条纪律留痕】①**继承失效不继承替代**：`_cascade` 沿 `source_knowledge_id` 广度递归，只置 `invalidated=1`+`invalid_reason`，表内无替代指针（钉子断言 `superseded_by not in cols`，codex 预审①）；已失效行不覆写 invalid_reason、不重复计数（幂等）但仍向下遍历（下游可能尚未失效）。②**X7 写入门**：`memory_scan` 抽出 `decide()` 为唯一判梯，`write()`（记忆）与 `scan_fact()`（知识）共用——知识表不可能成为扫描面旁路；改写放行落清洗后文本（`decision.content`），落原文=绕过 S3。③**evidence_seq 复用 seq_by_index**：`fill_evidence_seq` 只按 M2-D3 投影缝映射回填，不读 max(seq) 不自行分配（否则 witnessed 知识锚到不存在的 seq）。
- 【踩坑：`_cascade` await 种子】`invalidate_by_row` 初版传同步 lambda，`_cascade` 里 `await seeds_fn(session)` → TypeError；修=两个种子源都改 async。`session.execute(update())` 的 Result 无 rowcount（pyright）→ 先 select 判状态再 UPDATE，免 type-ignore。
- 【踩坑：知识 CHECK 形状】`witnessed ⇒ evidence_seq NOT NULL` / `told ⇒ source_knowledge_id NOT NULL` 表达不了 DB CHECK，落应用层（`write_fact` 的 `_check_shape`/`_check_evidence_shape`）；旧 `test_knowledge_insert` 直插 ORM 不经应用层仍绿——**ORM 直插只保低层存储测试，生产必经 write_fact**。
- 【历史】第八轮 D3（B3 提案+C2 重放逐位相等，`90cc1e9`）、第七轮 D2（A4 治理 JOIN 收口+裁 7 四红线+materialize_matter，923 passed）、第六轮 D1（C2 域约束 29/29+VectorIndex 骨架）见各自快照原文（git log .orca/memory.md）。

- 【C2 逐位相等留痕】§19.3 判据：快照路径（直读 `matter_state`）与重放路径（折叠 events）产出**逐位相等** `MatterLedger`。实测 `snap._items == rep._items` True（含 COLLAPSE 终态 / decay_rate 携带 / 多事件序列）。**关键**：折叠规则单一来源 `fold_matter_snapshot`（新对象 durability<0→1.0 且 decay_rate<0→0.0；旧对象 durability<0 沿用 integrity、decay_rate<0 沿用率；is_rubble 只增不减）——两路径**不得各写一套**，否则分叉。新增测试 `sim/tests/test_m3_matter_replay.py` 6 用例（逐位相等×3 + 过滤/分支隔离/纯读）。
- 【门禁】`pytest -q --ignore=sim/tests/bench` = **959 passed / 55 skipped / 0 failed**；ruff ok；**pyright 5 error（= main 基线，均 Claude A2 `test_t1_m3_hidden_emerge.py` pin 的既有错，本批零新增）**；alembic 零漂移（B3 提案阶段模型未动，autogenerate 仅 `pass`）。
- 【2026-09-23 第七轮快照】**M3-D2 已交付**（A4 收口 + 裁 7 四红线 + C1 materialize_matter）。分支 `ZX466/opencode`：**R2 钉子 3 RED → 0（全绿 5/5）**——`vec_candidate_ids` 召回 SQL 内联 `JOIN npc_memories ON m.id = v.rowid` + `WHERE superseded_by IS NULL AND invalid_reason IS NULL`（治理过滤**进打分缝前**，push-down 到 vec0 查询同句；supersede 落库后同连接直读无缓存 → 即时生效）。**裁 7 四红线进 `sim/tests/bench/thresholds.py`**：`VEC_CANDIDATE_PER_NPC_LIMIT_MS=0.30` / `RETRIEVAL_SCORE_PER_NPC_LIMIT_MS=0.30` / `RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS=2.00`（退化哨兵）/ `RETRIEVAL_TICK_LIMIT_MS=12.0`（依据 `docs/perf/m3-retrieval-budget.md §1.3`；合计 0.60 不新增行仅注释）。**C1 `NpcStore.materialize_matter(matter_ids=None) -> MatterLedger`**（§19 快照路径照抄）：一次 SELECT `matter_state` WHERE `branch_id` 隔离，`subject_id→matter_id`/`integrity`/`decay_rate`/`is_rubble` 直通，显式 id 未知者不在结果，纯读零迁移。整改全绿：`pytest -q --ignore=sim/tests/bench` = **923 passed / 55 skipped / 0 failed**、ruff ok、pyright 0 error、alembic 零漂移（fresh DB autogenerate 仅 `pass`）。
- 【A4 召回 push-down 留痕】`vec_candidate_ids` 不再经 `SqliteVecIndex.knn`（纯接口保留 rowid+distance 无治理），而自持治理-aware SQL——治理过滤必须在候选生成句内完成（R2 契约 2：不能召回后再放行），故 vec0 `MATCH ... k=?` 与 `JOIN npc_memories` 同句。A4 后勿把过滤拆到 Python 侧（会破坏「占比恒 0 + 无窗口期」两条契约）。
- 【C1 rubble 重建留痕】`MatterLedger.register` 不设 `is_rubble`，故 `materialize_matter` 对 `is_rubble=True` 行追加 `mark_rubble`（置 integrity=0.0）——DB 不变式 `is_rubble ⟹ integrity==0.0`（`_project_matter` 保证）使其与逐位列等价（§19.3 逐位重建）。
- 【2026-09-23 第六轮快照】**M3-D1 已交付**（C2 MatterPayload 域约束 + A3 VectorIndex 接口草案）。分支 `ZX466/opencode`：**C2 钉子 29/29 GREEN**（`Field(ge/le)+allow_inf_nan=False` 于 x/y/amount/durability/decay_rate，factory 与 `validate_store_row` 同源传导，insert/update 双路径覆盖）；**R2 钉子 4 RED → 3 RED**（仅剩治理 JOIN 未接：`test_candidates_view_excludes_governed_entries`/`test_supersede_cascade_immediate`/`test_query_join_filters_governed_rows_sql`；shape 与 rowid 契约 `test_shape_unchanged_entries_are_memory_entry`/`test_rowid_keying_contract` 转绿）。A3 落地 `VectorIndex` Protocol + `SqliteVecIndex`(A 主)/`NumpyCosineIndex`(B 降级) 骨架 + `VecCandidateSource`/`vec_candidate_ids`（治理过滤 JOIN 留 A4）。整改全绿：`pytest -q --ignore=sim/tests/bench` = **919 passed / 55 skipped / 3 failed（皆 R2 治理，预期最小 RED）**、ruff ok、pyright 0 error、alembic 零漂移。
- 【C2 钉子修正留痕】codex 原 `TestMatterEndToEndBounds` 把 `matter_event(...)` 写在 `pytest.raises` **之外**，与 `test_factory_rejects_nan_durability`（同调用要求抛 `ValidationError`）**自相矛盾**，无任何实现可 29 全绿。经 Claude 裁决：工厂调用移入 `with` 并放宽为 `(EventValidationError, ValidationError)`（工厂/store 任一层拒绝即过，defense in depth）。钉子头部已留修正说明。
- 【R2 候选身份约定】`VecCandidateSource.candidates()` 产出的 `MemoryEntry.id` = **vec rowid**（= `npc_memories.id`），非 `npc_memories.entry_id`——R2 钉子以 rowid 为候选身份（`_insert_memory` 返回 rowid 与 `c.id` 集合比对）。已在 `vector.py::_rowid_to_entry` 留档 + `# type: ignore[arg-type]`（A4 接治理 JOIN 时勿改此约定，否则钉子的集合比对失配）。
- 【2026-09-22 第五轮快照】M2-D5 已收编（`ee70aad`）。**M2-D6 已交付分支 `414acb5`**（docs 型、零代码零迁移）：`vec-preplan.md §7 裁决栏`落地——**已裁 3**：V1（sqlite-vec 主 / numpy 余弦降级，同接口两实现）、V4（vec 表为准，`npc_memories.embedding` 仅写缓存）、V6（治理过滤召回端红线，JOIN+过滤 superseded/invalid/abandoned，codex R2）；**挂起 4**：V2/V3/V5/V7（V3 改 schema 须提案、V7 触 S1 须 codex 复核）。裁结对比表已去冗余（§2 合并为结论行）。`schema.md §19` 注册≠落库补核对（与 V6 无交集，matter 域 vs 记忆域）。任务单=本树 talking.txt。

### 已内化教训（M2-D2/D3 实测，别再踩）
- **`.orca/talking.txt` 是 worktree-local（gitignored）**；`.orca/memory.md` 是 tracked。给本树的回执写 talking.txt；给**他树**的回执写**对方树**的 talking.txt。收编方=Claude（merge 各 ZX466/* → origin+gitee 双远程）。
- **Windows 行尾**：新文件一律 LF、无 BOM（`git ls-files --eol | grep -c w/crlf` 期望 0）；CJK 控制台会显示乱码但文件字节正常，别被吓到。
- **零漂移纪律**：任何 schema 改动前先 `uv run alembic upgrade head` → `revision --autogenerate` 看迁移体是否仅 `pass`；「投影回既有列」不产生新迁移（M2-D2 LOD 投影回 `npc_profiles.lod` 即无 0005）。
- **S1 唯一写入口**：所有 `MemoryEntry` 必须经 `MemoryWritePipeline.write()`（S1 守卫测试 `test_memory_scan.py::TestS1Guard` 扫仓内绕过点）；测试造数据也用 pipeline，别直接 `store.persist` 写正文。
- **append 收窄**：`SqlEventStore.append` 默认 `validate=True`（走 `event_validation.validate_store_row`）；低层存储机制测试（合成 payload）必须显式 `validate=False`，否则被 payload 白名单拒。
- **projection 缝**：投影回调在 commit 前**同一 session** 执行，异常整批回滚（无半写）；`EventStore` Protocol 与 `flush_events`（无投影）行为不变。
- **读侧 only**：检索/打分层（`sim/npc/memory.py`）不写库、不碰写路径与守卫；偏差逻辑（cognition）后期以 `Scorer` 钩子注册，**不写死**。
- **pyright 全绿要点**：`async_sessionmaker[AsyncSession]` 注解要显式（否则 property 返回 Unknown）；测试里 pydantic 模型 `category` 等 str 字段从 DB 读出要 `# type: ignore[arg-type]`。
- **验证命令**：`uv run pytest -q --ignore=sim/tests/bench`（门禁）；bench 单独 `uv run pytest sim/tests/bench -q`（7 日 soak 需 `PI_M2_FULL_SOAK=1`，默认 skip）；`uv run ruff check sim/ && uv run ruff format --check sim/`；`uv run pyright sim/`。in-file 测试类标 `@pytest.mark.t1`，文件名 `test_m2_` 前缀自动进 CI 门禁。
- **flake**：`test_bench_soak` p99 阈值对 CPU 争用敏感——与其他命令并发跑会假红，单独或正常整套跑即可。
- **matter 投影缺口（M2-D4 实测）**：`matter_state.decay_rate` 列 §14 已存在但投影从不写（新建硬编码 0.0、update 不碰）——账本 `decay_rate` 是**静态率、无任何事件承载**，且 `jitter` 未落 payload 无法反解 → §14「回放逐位重建」不成立。修法**无需新列/迁移**（列已在），只有方案 A：`MatterPayload` 增可选 `decay_rate` + factory/结算携带 + 投影写列（改冻结事件基线，须先报裁）。对账表见 `schema.md §17`。
- **对账表方法论**：三方对账 = 逐字段判「能否从事件流重建」（§14 判据）；`is_rubble` 靠 `COLLAPSE∨integrity≤0` **推导一致**（非显式承载，当前等价）；`subject_kind/material/quality/load_bearing/supported_by` 是账本无源的占位（归 M4/M5，非缺口）。
- **pyright 遗留基线**：`test_m2_cognition.py`(source Literal) 与 `test_m2_runtime_assemble.py`(dict[str,object] 取值) 有 3 个**既有**错（Claude M2-A2 第三批文件，非本域），改动前先确认不是自己引入的。
- **多行 CJK docstring 的 ruff E501**：行宽按字符数计，CJK 表格行/长句易超 100——拆行或去冗余；docstring 里 Markdown 表格的 `\|` 会被 Python 当非法转义（W605），改用「或 None」「和」等文字表述。
- **M3 向量检索缝（预研内化）**：`npc_memory_vec` 在 M3 只是**候选生成器**——新增 `CandidateSource` 协议换候选源，`Scorer` 打分链一字不改（§18 硬边界）。**`sqlite-vec>=0.1.6` 已是 pyproject 依赖且已装**（别重复装）；脚手架 `sim/core/persistence/vector.py`（load/create/exists）已备，DDL 在 Alembic 范围外（需 LOAD EXTENSION）。量级 50×1000=5万条非瓶颈，**成本在 embedding 生成**；embedding 挂 `LlmClient.embed(profile, texts)`（复用 ProfileSnapshot + llm.* 监控 + K3/K4），chat 模型不产 embedding → §10 或需第二条 profile 缝。详见 `docs/data/vec-preplan.md`。
- **matter 读路径（M3 预研）**：`materialize_matter()` 对镜 `materialize`（一次 SELECT、禁止逐对象）；快照路径（直读表）vs 重放路径（snapshots+事件重放）两入口**同产物**，重放器须复用 `_project_matter` 同一折叠规则避免语义分叉；**注册≠落库**（新建对象未产事件前不在表）。详见 `schema.md §19`。
- **V 系裁决采结（M2-D6，M3 实现据此）**：**V1**=sqlite-vec 主 + numpy 余弦降级（同接口两实现 `SqliteVecIndex`/`NumpyCosineIndex`）；**V4**=vec 表为准（`npc_memories.embedding` 仅写路径缓存，读不参与）；**V6**=治理过滤在**召回端**（候选必须 JOIN `npc_memories` 过滤 superseded/invalid/abandoned——**codex R2 红线**，不允许「写入时不同步」旁路）。挂起：V2 维度（随模型锁）、V3 profile 缝（改 schema 须提案）、V5 召回时机、V7 embedding 挂写路径（触 S1，须先提案+codex 复核）。见 `vec-preplan.md §7`。
- **裁决栏落法（文档惯例）**：任务说「落裁决栏 + 去冗余防误导」= 新增 `## 裁决栏` 节（已裁表+挂起表，挂起注明理由/触发时点），并把被裁结的**对比/建议表**合并为「结论行」、删掉「倾向 X / 最终裁决留 M3」这类过期措辞；原结论节顺延编号。


> ——以下为 opencode 树 memory.md 原文（收编于 3309c0f）——
> **新对话开场先读**：`.orca/workflow.txt` + `.orca/agent-registry.md` + 本文件 + `.orca/talking.txt`。
> 我的能力域：**数据/数据库**。上游派单：Claude；评审 Agent：Codex。
> 本文件（用户规则 #7）保存我自己的记忆，供新对话继续任务。**已入库**（`.orca/` 属规则 #4 的例外，
> `.orca/memory.md` tracked；仅 `.orca/talking.txt` 为 worktree-local 忽略）。

---

## 规则速记（用户规则 #4 / #7）

- **规则 #4**：除 `.orca/` 外，所有 `.` 开头文件夹（`.agents` `.claude` `.codex` `.opencode` `.codegraph` `.kiro` 等）
  **不入 git、不推送**。但本地必须存在：
  - `.codegraph`、`.agents` → **每个**工作树都要有；
  - `.claude` / `.opencode` / `.codex` → 在**对应**工作树要有；主工作树全有。
- **规则 #7**：各工作树 `.orca/memory.md` 分别保存各 agent 记忆（本文件）。除 agent 自带记忆外，不强制另造。
- `.gitignore` 已固化：`.orca/` 仅忽略 `talking.txt`；其余 dot-folder 全忽略。

---

## 项目状态（2026-09-20 同步自 main `3e320b9`）

- **M0 + M1 全部收官**，TASK-004 五路（opencode/codex/cline/pi/kilo）全部交付并收编。
- 全量测试：**589 passed, 55 skipped**（571 passed + bench 18 passed 分开跑；详见「验证」）。
- 我的 **D04 已收编进 main**（merge `f73bc04`）。本树 HEAD = `3e320b9`（与 main 齐），无未合并提交。
- 项目：`natural-world`，LLM 驱动 NPC 生活模拟；核心威胁=污染循环（LLM reason 不可信 → 闸门/记忆扫描拦截）。
- 技术栈：Python 3.12 / **uv** / pytest / ruff / pyright / SQLAlchemy 2.0 async + aiosqlite / Alembic / structlog。

## 我已完成的工作

- **TASK-004 / D04（记忆段数据落库）**：
  - `MemoryStore` Protocol 接口化 + `InMemoryStore`（默认，零破坏）+ `make_entry` 唯一构造工厂
    （`sim/llm/memory_scan.py`，S1 守卫保持）。
  - `SqlMemoryStore` 落 `npc_memories`（`sim/core/persistence/memory_store.py`，同步 sqlite3）。
  - 迁移 `0003_memory_write`：`entry_id`(unique)/`source`/`superseded_by`/`invalid_reason` + `idx_memories_visible`。
  - `entropy_log.event_seq` 回填：`flush.py`→`event_index`→`store.append` 同事务回填。
  - 测试 `sim/tests/test_memory_store.py`（10 项）。
- **更早**：TASK-001~003 数据域全链路参与（crypto、M3 预留表 0002 等，详见 `git log` 与 `docs/data/`）。

## 当前任务

**M4-D2 四批已交待收编**（D2a `c719171` / D2b `345d5ae` / D2c `e5d0f65` / D2d 待写入；见 ③节 2026-09-26 快照与 talking.txt 回执）。**M4-D 批数据面收官**；后续等 Claude 派新单。已知生产接线缝（world.py EventBus / world 级 Pathfinder / previous_tile_id / collapse sink）属架构或需裁。


## 留言板

- 读 Claude 经 `.orca/talking.txt` 写来的任务指派。
- 已挂账提醒：structlog 需挂 `redact_sensitive` processor（crypto 域，若尚未接线）。
- 潜在方向：M3 嵌入（锁 embedding model → 建 `npc_memory_vec` → 向量检索，关联语义已固化）；
  生产装配把 `MemoryWritePipeline(store=SqlMemoryStore(...))` 接到实际写入点。

---

## 数据域关键契约（速查）

- **MemoryEntry**：`id`(uuid hex,= `npc_memories.entry_id`) / `npc_id` / `content`(唯一受扫描保护) /
  `source∈{reason,dialogue,event,interoception}` / `event_seq`(NULL=推理转述) / `importance` /
  `emotion_tag` / `superseded_by` / `invalid_reason`。
- **写入唯一入口** `MemoryWritePipeline.write()` → `WriteResult(accepted, entry, action, hits, reason)`；
  拒写**不落库**（S4）。**S5**：supersede 只动治理列，永不改 content；iter_visible 过滤被取代；get 审计可见。
- **npc_memories**（0001? no，0002 + 0003）：见 `docs/data/schema.md`。
- **向量关联**：`npc_memory_vec` 是 vec0 虚拟表（alembic 外，需 `LOAD EXTENSION`）；
  业务键 `(event_seq, entry_id)`，rowid = `npc_memories.id`；`DEFAULT_EMBEDDING_DIM=384` 占位待 M3。
- **crypto**：`LZ_MASTER_KEY` 缺失/非法 → 拒绝启动；`encrypt/decrypt_api_key` + `redact_sensitive`。

## 踩坑记录

1. S1 守卫 grep：非 `memory_scan.py` 禁止出现 `MemoryEntry(` → store 必须走 `make_entry(...)`。
2. `MemoryEntry.id`(uuid hex) ≠ `npc_memories.id`(int 自增)；业务句柄统一用 `entry_id`。
3. `.orca/talking.txt` gitignored；`.orca/workflow.txt`、`.orca/agent-registry.md`、`.orca/memory.md` tracked。
4. PowerShell 显示 UTF-8 中文会花屏；用 Python `open(...,encoding='utf-8')` 或 .NET 读，别信控制台。
5. bench 是 wall-time 断言，全量并发跑会抖动偶失败 → **bench 单独跑**；功能套件用 `--ignore=sim/tests/bench`。
6. alembic autogenerate 校验：`upgrade head` → `revision --autogenerate` 看 upgrade() 是否只剩 `pass` → 删临时文件。
7. `WORLD_DB_URL` 控 alembic 目标库（测试用 tmp_path，别动 `world.db`）。
8. Git：提交归属 `ZX666X <zx19836980213@outlook.com>`；推 `origin` + `gitee`；未要求不提交。

## 验证命令

```powershell
uv run pytest -q --ignore=sim/tests/bench     # 571 passed, 55 skipped
uv run pytest sim/tests/bench -q              # 18 passed（单独跑）
uv run pytest sim/tests/test_memory_scan.py sim/tests/test_persistence_m3.py sim/tests/test_memory_store.py -q
uv run ruff check . --output-format=concise
uv run pyright sim/
```

## 已完成任务链

| 任务 | 内容 | 状态 |
|------|------|------|
| M0 | 事件溯源核心 + 0001 | ✅ 收编 |
| TASK-003/D03 | crypto + M3 预留表 + 0002 | ✅ 收编(`52967ed`) |
| TASK-004/D04 | MemoryStore 接口化 + SqlMemoryStore + 0003 + entropy 回填 | ✅ 收编(main `f73bc04`) |

> 每次完成后更新本文件「当前任务 / 进行中 / 已完成」；过时内容删掉。

## ④ codex（安全 / 合规 / 风险域）
- 【2026-09-26 M4-S2 交付】24d858d：m4-coincidence-preaudit.md——巧合状态存事件流+fold（驳内存/新表）+ T1 四断言（值零可见）+ 不顺判例三档（灰区建议放行）+ T5 熵流三条边界（禁 live/seed 纯函数/seq 序 fold）+ 四条待裁。实测缺口：EntropyMixer 零生产调用方。
- 【2026-09-26 M4-S1 交付】346dfa1：m4-security-preplan.md——三面词面边界（念头注入面 WS 未扫描实测+三扫提案/意愿数值零文本闭合+扩模板CR/运气熵流零可见+PerceptionFrame 无 luck）+T4 探针集 P1-P5 ≥44 条 + profile 提案（t4-probe/claude-sonnet-5/temp0.7/零重试/60 预算）+ T1 钉子建议 2 条 + 四条待裁决。
- 【2026-09-25 M3-S6b 收官门动态复验】686caa8：七钉子+S4 148 绿；S4 7 绿；功能非性能全量 1076/0；bench 批量红按裁 1 advisory（retrieval/rng/smell 单跑全绿）；pyright 0，ruff 仅 pi 域 pre-existing E501。preaudit §7 回填，m3-plan 宣告 M3 收官。
- 【2026-09-25 M3-S6 收官门预审（静态）交付】700015a：m3-closure-preaudit.md——静态门通过（六钉子 137 绿 + S4 10k 144 同跑绿 + 对表 25/28）；5 发现：F-a X2/X3 钉子未落（建议关门 PR 补）、F-b R4 记忆侧 branch 过滤缺（二选一裁决）、F-c/F-d 文档漂移、F-e soak 抖动（pi 域）。动态复验清单 §5 待 C3 后续件收编后执行。
- 【2026-09-24 第九轮快照｜M3-S5 已交付（提案层）】B3 验收+F1 复核完毕（零代码）。**D4 未落地（验时点）→ 交付提案层对表+D4 验收清单**。D3 提案对预审 7 要点 7/7 过：命名对齐（无 replacement 列）/级联接口沿 source_knowledge_id 递归有界幂等/invalidated 键与 evidence 闭环/0005+CHECK+downgrade/全 branch_id/落库走写入门（grep 实证现态零裸 INSERT）/R3 口径同 iter_visible。⚠️ 一项待实施落实：evidence_seq 回填须点名复用 seq_by_index 不造第二套（opencode D4 已照办）。**F1 复核实测留痕**：str→["b"] 与 dict→["ghost"]（迭代键洗白成见证人，新发现向量）均 ACCEPTED；123→TypeError、["ok",5]→ValidationError fail-closed 好；store 行级仍拒裸 str（纵深未破）。**验收形已落地**（main `64b7390`：Sequence[str]+isinstance 拒 str/bytes/dict）。D4 收编后按清单终验：R1 端到端三硬断言+X7 grep 审计+裁10④接线点+0005 downgrade 零漂移。
- 【E1 二阶 RED 语义保留】test_t1_m3_hidden_emerge.py 的二阶拒绝指纹（先断言 kind 已注册再断言拒绝原因串）是防「红灯被错误实现满足」的机制，永久保留勿简化。
- 【历史】M3-S4 转绿双绿复验+F1/F2 advisory（`e33642a`）、S3 E1 钉子 26 RED（`56a6fa4`）、S2 证据链契约（`d81cf11`）、S1 双钉子（`2daa644`）、安规预研 m3-preplan（`b650882`）见 git log 原文。
- 【2026-09-22 第四轮快照】M2-S3 已收编（`3c79465`，通过结论；2 MEDIUM 已被 opencode 修：`4a11d0f` event_validation.py + materialize_hidden）。M2-S4 已交付（`38a7f63`，origin+gitee 已推，等收编）：t1-sampling-10k.md 口径 + test_m2_t1_sampling_10k.py harness（10k 采样 7 用例 1.1s；判据=零直陈泄露+零误伤+全覆盖+可重放；S1 文件零改动；test_m2_ 前缀自动进 CI glob）。全量 862 passed + 55 skipped。

> 本树工作簿：用户级技能 `security-worktree`（~/.agents/skills/，含环境坑/评审配对/回写纪律）。
> 能力域：安全/合规/风险；评审配对：cline 评审我，我评审 Claude（架构+前端）与 opencode（数据/库）。

### 项目状态（2026-09-20 同步自 main `4323c9e`）
- M1 全量收官（TASK-004 S04 已收编，578 passed + 55 skipped）；M2 已派单。
- 本树分支 ZX466/codex；M2-S1 交付后工作区干净，等 Claude 收编。

### 你已完成的工作（最近一轮）
- **M2-S3 M2-D2 安全评审（2026-09-21 交付）**：结论=通过（0 CRITICAL/HIGH + 2 MEDIUM + 2 观察 + 4 正面确认），
  落 `docs/security/m2-d2-review.md`；增补 3 条测试到 test_m2_runtime_store.py（拒写 reason/hits 结构化、
  触发放行、混合拒写）→ 18 用例全绿。MEDIUM：M1=SqlEventStore.append 裸 dict 绕过 payload 模型校验（opencode），
  M2=materialize 不加载 npc_health 隐藏行（升格装配缺半边，opencode+Claude）。
- **M2-S2 L1 动作白名单 + 升格隐藏属性契约（2026-09-21 交付，29 个新 T1 用例，全量 675 passed）**：
  - `docs/security/l1-whitelist.md`：白名单审查结论（W1-W7）+ HiddenState 契约 + runtime 调用点 + 维护责任。
  - `sim/npc/contract.py`：HiddenState（profile+triggered 快照）——evaluate 重估 / check_reason 降级检查 / gate_kwargs / memory_kwargs / empty() 恒等值。
  - `sim/tests/test_t1_l1_whitelist.py`：29 用例（白名单锁定 / payload 键 / 升格传递 / 降格写回不降防线 / 降级检查一致性 / 零回归）。
  - `.github/workflows/ci.yml`：按文件路径新增 T1 L1 白名单门禁。
- **M2-S1 自我未知安全边界（2026-09-20 交付，28 个新 T1 用例，全量 606 passed）**：
  - `docs/security/self-unknown.md`：隐藏属性标注规范（健康档 疾病/旧伤/成瘾/残疾 + 创伤应激触发条件）+ 情境触发浮现 + 闸门/记忆写入扩展口径 + opencode 0004 数据表协调。
  - `sim/npc/hidden.py`：HiddenAttribute/HiddenProfile 标注模型 + `evaluate_triggers` 触发评估 + `hidden_leak_scan` 直陈泄漏扫描（闸门与记忆写入共用同一工具）。
  - `sim/agent/gate.py`：`revalidate_at_execution` 增加 hidden/triggered 参数与「自我未知」检查——reason 直陈未触发属性 → `hidden_attribute_leak` 拒绝；hidden 缺省 None 与 M1 行为一致。
  - `sim/llm/memory_scan.py`：`write()` 增加 hidden/triggered 参数与直陈拒写（`REASON_HIDDEN_LEAK`），记忆检索默认结果防线。
  - `sim/tests/test_t1_self_unknown.py`：双路径采样（未触发零泄露 / 触发正常浮现）+ 行为暗示可议 + 语料卫生 + 感知帧/装配 prompt 面零泄漏。
  - `.github/workflows/ci.yml`：按文件路径新增 T1 自我未知门禁独立红灯信号（沿用 test_t3_gate.py 做法）。
- 更早累计：TASK-001~004（m1-checklist/threat-model/t3-corpus/memory-scan + T3 实弹 + W6 WS 鉴权 + M1-D reason 禁词门）；详见 git log 与 docs/security/。

### 当前任务
- M2-S4 已交付（`38a7f63`，等收编），等下一波派发。

### 进行中
- (空)——等下一波派发（第三批评审等 Claude 通知）。

### 留言板
- (读 Claude 经 talking.txt 写来的任务指派；给他树留言写对方树 talking.txt)

## ⑤ pi（性能域）
- 【2026-09-24 第九轮快照｜M3-P2 全闭环已收编】①四红线 bench 进 thresholds.py（VEC_CANDIDATE/RETRIEVAL_SCORE 0.30 / FULL_SCAN 2.00 / TICK 12.0，依 m3-retrieval-budget §1.3）；②**baseline.json 入库 + nightly 切 `--benchmark-compare-fail=median:25%` 相对漂移制**（裁 4/裁 11）。机型切换观察（EPYC 7763 vs 9V74，median 1.71）已进 bench-plan §4.1 step6 边界注记。**active 纪律**：25% 相对漂移限「跨 run 同档位」；机型迁移重对账；检索防呆红线（决策/prompt 驱动触发，禁每 tick 全量——反证数据是母本）；thresholds.py 唯一真相源，硬断言只在定标机。**待命**：下批=①nightly 新判定首跑观察（首个 --benchmark-compare run 漂移数字）；②A4 sqlite-vec 真实现后候选红线复核对账（参考实现 1.29x 余量偏紧，预期真实现更省）。
- 【历史】M2-P3（l1-spec 对账+L1 feeder+p99 信息性守护 `1e3e36e`）、M2-P4（budget 预案+SMELL_WIRED 1.0 `82efcc2`→已收编）、M3-P1（四红线预研）、P2①（四红线落地 `48db6cf`）见 git log 原文。perf-worktree 技能（~/.agents/skills/）可完整恢复工作状态。

> ——以下为 pi 树 memory.md 原文（收编于 50b0ebb）——
> 新对话开场先读本文件 + .orca/workflow.txt + .orca/agent-registry.md。你的能力域：性能域。
> 配套技能：`perf-worktree`（用户级 ~/.agents/skills/，含环境坑/基准口径/常用命令）——新对话若发现本文件
> 不足以恢复上下文，读该技能全文可完整续上工作状态。

## 项目状态（2026-09-20 同步自 main `3e320b9`）

- M0+M1 全部收官（TASK-004 五路全部交付并收编），589 passed 55 skipped。
- 你的 TASK-004 交付已收编（收编回执曾写在你树 talking.txt，现已轮换清空；结论可查 git log「merge: 收编 pi」）。
- 本树已 merge main `3e320b9`，工作区干净，待 M2/TASK-005 派发。

## 你已完成的工作（最近一轮）

- **M2-P3 交付（2026-09-21，分支 ZX466/pi）**：L1 算法规格落盘 + soak feeder 升级方案。
  - `docs/perf/l1-spec.md`（新）：原型 `_L1Load`（numpy 数据布局/矩阵形状/打分公式/常量表）
    ↔ 真实实现 `sim/npc/utility.py`（NEED_ORDER 3 / ACTION_ORDER 6 / `_GAIN (3,6)` / HABIT_BONUS 0.05 /
    _EXTRAVERSION_CHAT_BIAS 0.3）逐项对账；未落地项清单（PAD/关系/记忆/候选集/NPC_ACT handler）。
  - `sim/tests/bench/test_bench_l1_utility.py`：加 `test_l1_real_*`（真实 utility_scores_matrix / evaluate_batch /
    NpcRuntime.tick / 单 NPC + 形状契约 + 确定性）。
  - `sim/tests/bench/soak.py`：加 `make_l1_feeder`（mock → 真实 L1 两阶段接线；NPC_ACT 未注册时只折
    move/wander 成 MOVE，其余丢弃；第三批接线后 `translate=lambda _a: True`）。
  - `docs/perf/m2-acceptance.md` §3.1：feeder 升级方案（两阶段表 + 约定 + 两份 feeder 定位）。
  - `thresholds.py`：L1 红线常量未动，注释回填实测。
  - **修漏（自己的假红）**：长跑 `test_soak_nightly_steady_p99_below_tick_line` 用 8.3ms 硬门禁造成反复假红
    （均值 2.3ms / p99 8.6ms = 调度噪声）。改为**硬预算 16.6ms 信息性守护**；回归检测交给
    分窗均值漂移 + 资源增长判据。8.3ms 的固定容身之处仍是短基准 `test_bench_clock.py`。
  - 另修一坑：pytest-benchmark 计**调用墙钟**、不吃返回值，单 NPC 用量必须用 1-NPC 批次（别除 n）。
  - 实测：`utility_scores_matrix` 0.206ms / `evaluate_batch` 0.273ms / `NpcRuntime.tick` 0.747ms /
    单 NPC 0.0124ms（红线 6.0 / 0.12ms，余量 8~29x）；soak L1 feeder 稳态 mean ~0.9ms。
  - CI：bench 44 passed/1 skipped；`-m "not bench"` 770 passed/55 skipped；ruff/format/pyright 绿。
- **M2-P2 交付（2026-09-21，分支 ZX466/pi，commit `7080e1e`+`b033995`）**：7 日自转验收口径 + 长跑预压测。
  - `docs/perf/m2-acceptance.md`（新）：604,800 tick 验收口径——崩溃判定 C1–C10（进程/tick/RSS/句柄/GC/缓存/实体/漂移/确定性/延迟）；降采样断言三级（CI 缩样 / nightly 30k / 里程碑完整 604,800）；
    nightly 接法提案 §4（方案 A nightly step vs 方案 B 独立 workflow，交 cline 裁决）。
  - `sim/tests/bench/soak.py`（新）：窗口化长跑 harness——跨平台进程探针（RSS/句柄/GC 对象）+ `run_soak` 分窗统计 + 确定性持续走动 mock 喂给。
  - `sim/tests/bench/test_bench_soak.py`（新）：CI 缩样冒烟（1,200 tick）+ 探针/量纲契约；`@bench` nightly 30k tick 漂移/p99/缓存/确定性；完整 604,800 环境门 `PI_M2_FULL_SOAK=1`（默认 skip）。
  - `thresholds.py`：加 `SOAK_STEADY_MEAN_LIMIT_MS=6.2` / `SOAK_MEAN_DRIFT_RATIO_LIMIT=1.5` / `SOAK_RSS_GROWTH_LIMIT_MB=128` / `SOAK_GC_OBJECT_GROWTH_LIMIT=20000` / `SOAK_HANDLE_GROWTH_LIMIT=64`。
  - `budget.md` §4 补 M2-P2 对账；`hotspots.md` 加 H-7 长跑隐性累积；`bench-plan.md` §1/§2/§3/§4 补长跑；bench README + docs/README.md 同步。
  - 实测（50 NPC + 感知 + 持续走动 mock，100k tick）：均值无漂移（1.86→1.86ms）、RSS/句柄/GC 有界、缓存封顶。未发现 O(n) 累积/泄漏。
  - CI：bench 36 passed/1 skipped；`-m "not bench"` 649 passed/55 skipped；ruff/format/pyright 绿。
- **M2-P1 交付（2026-09-20，已收编 e42b979）**：L1 效用 + 嗅觉传播预算与 bench 红线。
  - `docs/perf/budget.md`：§1 表新增「嗅觉传播（M2）0.05/0.15」+ 新增「合计（M2）7.05/12.50」；§1.2 M2 分解表；§2.4 补 L1 实测；新增 §2.9 嗅觉；§3/§4 对账补 M2。
  - `docs/perf/bench-plan.md`：§1 清单加 npc.utility / perception.smell；§3 阈值表加 L1 全量/单 NPC/断线兜底/嗅觉四行。
  - `docs/perf/hotspots.md`：H-1 补嗅觉延伸（Eulerian 网格 vs 逐对）。
  - `sim/tests/bench/thresholds.py`：新增 `L1_UTILITY_TICK_LIMIT_MS=6.0` / `L1_UTILITY_PER_NPC_LIMIT_MS=0.12` / `L1_OFFLINE_FALLBACK_LIMIT_MS=0.20` / `SMELL_TICK_LIMIT_MS=0.15` / `SMELL_NAIVE_SENTINEL_MS=3.0`。
  - 新 bench：`test_bench_l1_utility.py`（4 bench + 2 契约）、`test_bench_smell.py`（4 bench + 1 契约）。
  - 实测（暖态中位·本机）：L1 向量化 ~0.02ms / 单 NPC ~0.0004ms；断线兜底 ~0.001ms；嗅觉扩散 ~0.009ms + 采样 ~0.001ms。逐对哨兵：L1 scalar ~4.4ms、嗅觉 naive ~4.6ms。
  - bench 全量 29 passed；`-m "not bench"` 581 passed / 55 skipped；ruff/format/pyright 全绿。
- 感知 bench 红线复核（F06 暖态中位口径采纳）+budget 4x 对账+bench 方法论沉淀（warmup/中位/冷启动诊断）。
  红线口径定案：暖态中位（`assert_median_threshold` + `warmup_rounds=1` 剔 LOS 冷启动 7.6-8.2ms），
  `PERCEPTION_TICK_LIMIT_MS=3.6`（预算目标 3.00ms 另一口径）；RNG 1M 警戒线 300ms、真预算每 tick 200 draws ≤0.10ms。
- 更早累计：TASK-001~003 全链路参与（budget.md/hotspots.md/bench-plan.md + bench 脚手架；详见 git log 与 docs/perf/）。

- **M2-P4 交付（2026-09-22，分支 ZX466/pi，commit `82efcc2`，等 Claude 裁决后收编）**：第三批预算预案。
  - `docs/perf/m2-p4-budget-preplan.md`（新）：三项任务逐一回答 + 预算拆表 + 断言方案 + 上界建议。
  - 拆分口径：smell 场推进（源=全体实体）与旧「纯网格 K=20」口径分离；新红线提案
    `SMELL_WIRED_TICK_LIMIT_MS=1.0`（实测 50 源 0.451ms / 100 源 0.976ms），旧 `SMELL_TICK_LIMIT_MS=0.15`
    保留改注释（不再上浮而是补行）。
  - 最大热点 = `SmellField.inject` 逐源 `np.clip` Python 循环（50 源 0.330ms；`np.add.at` 0.0024ms
    ≈140x 且同格累加语义等价）→ 交架构域改（性能域不越界）；次热点 = `others_max` 逐 observer
    O(N²) 扫描（50×50 = 0.107ms）→ 全局 max + 次大值 O(1) 提案（待语义等价裁决）。
  - flush 断言三件套（探针零触发 / 计时器注入 / flush 与 tick 分开累计）+ 帧级警戒 20ms +
    structlog `perf.flush_ms` 字段；实测 flush_tick 50 条：内存库 2.6ms / 文件库 7.8ms
    （说明一旦误进 tick = 半帧预算，动机成立）。
  - cognition 上界：检索缝 0.15ms/次（实测两钩子净增 0.054）、效用缝 0.01ms/NPC（实测 0.0004）、
    HiddenState.evaluate 0.30ms/tick（实测 0.10）；合计增量 ≤0.20ms/tick 进 L1 行不新增行。
  - 防呆提醒：检索缝必须维持「决策/装 prompt 驱动」频次；若退化成每 tick 每 NPC 全量检索
    ≈27ms/tick 直接破 16.6ms 总预算。
  - 验证：`-m "not bench"` 855 passed/55 skipped；`-m bench` 29 passed/1 skipped（首轮 2 例抖红，
    单跑复绿=机器调度噪声，非回归；已按 bench-plan §0「bench 不进每提交红线」口径记录）。

- **M2-P5 交付①（2026-09-22，分支 ZX466/pi，commit `00bea5c`，等收编）**：SMELL_WIRED 红线 + 嗅觉接线版 bench 用例。
  - `thresholds.py` 新增 `SMELL_WIRED_TICK_LIMIT_MS=1.0`；旧 `SMELL_TICK_LIMIT_MS=0.15`
    保留、注释改「纯网格参考口径（K=20 活性物质源）」；文件头注明两口径**勿混用**。
  - `test_bench_smell.py`：`test_smell_world_step_50_entities`（50 实体硬红线）+ 
    `test_smell_world_step_100_sources_headroom`（100 源上界哨兵）+ 
    `test_smell_world_step_tick_amortized`（非 bench：每 tick 摊销 ≤ 红线/2，
    盯 `tick.py::_PERCEPTION_EVERY_N_TICKS=2` 失效）。
  - 复测（inject 向量化 `653d395` 后，np.add.at）：50 源 **0.116ms** / 100 源 0.135 /
    200 源 0.151 / 500 源 0.335 —— P4 的 50 源 0.451ms 已被向量化淘汰；红线按裁决原值
    1.0 不缩（覆盖 ~10x L1 上界，50 源余量 ~8.6x）。
  - 验证：smell 文件 `-m bench` 6 passed；`-m "not bench"` 904 passed/55 skipped；
    ruff check+format、pyright（sim/tests/bench）全绿。
  - 附带告警（非回归）：全量 bench 首跑 `test_rng_1m_draws_per_call` 中位 300.084ms >
    300.000ms 警戒线（差 0.084ms，单跑复绿 = 贴边抖动）。已提案 300→330 待 Claude 裁决。

- **M2-P6 交付（2026-09-23，分支 ZX466/pi，commit `8fd9a17`，等收编）**：advisory 门（裁 1）+ RNG 330（裁 2）+ CI 定标提案。
  - `harness.py`：`ADVISORY_ENV="PI_BENCH_ADVISORY"` + `advisory_mode()`（调用时读 env）；
    `assert_threshold`/`assert_median_threshold` 改 advisory 语义——置 "1" 越线只
    structlog warning（`bench.advisory.threshold_exceeded`/`median_exceeded`）并返回 True；
    未越线 False；缺省仍 AssertionError（`raise AssertionError(...)`，非 `assert False`
    以过 B011 lint）。采集逻辑零改动。
  - `test_bench_advisory_gate.py`（新，9 例，TDD 先 RED）：env 语义（仅 "1" 为开）×
    越线/未越线 × advisory 开关；冒牌 `_FakeStats` 只提供 `.stats.median/.mean`（秒）。
  - `nightly-bench.yml`：「跑基准」step 传 `PI_BENCH_ADVISORY: "1"`；「基线对比」step
    注释补契约（真相源唯一 thresholds.py；advisory 下回归判定 = 相对基线漂移）。
  - `RNG_1M_DRAWS_LIMIT_MS` 300→330（本机全量中位 300.084ms 贴边，+10% 余量；聚合
    警戒线非 tick 硬预算）。
  - **P6② 定标提案**（`docs/perf/ci-calibration-m2p6.md`，**未动 thresholds**）：已从
    run 35816437844 下载 artifact（EPYC 9V74 / nproc4 / py3.12.3）与本机同 commit 对照
    → CI/本机稳定档 **median 1.14**（区间 0.86–1.35）；Python 侧项 CI 慢 1.13–1.35x、
    numpy 侧项 CI 快 0.86–0.92x。唯一红项感知听觉 CI 3.93 vs 3.6（+9% 在档位区间内），
    同 run mean 11.5ms = median 2.9x（被抢断）→ 负载噪声非回归。提案 P-A：建
    `docs/perf/baseline.json` + nightly `--benchmark-compare-fail=median:25%`（等 advisory
    合入后首个全绿 run）；P-B 备选 = nightly 只归档。共同前提 = thresholds 不放宽。
  - 验证：门单测 9 passed；`-m bench` 31 passed/1 skipped（advisory 关）；
    `PI_BENCH_ADVISORY=1 -m bench` 31 passed/1 skipped + 构造越线用例验证 advisory 生效；
    `-m "not bench"` 913 passed/55 skipped；ruff check+format、pyright 全绿。

- **M3-P1 交付（2026-09-23，分支 ZX466/pi，commit `1d09581`，等收编）**：检索缝预算案 + embed 监控 + baseline 流程（零代码）。
  - `docs/perf/m3-retrieval-budget.md`（新）：实测本机多轮中位——候选生成 numpy 余弦 **0.019ms/NPC**（600 可见）；
    打分链 600 候选×2 钩子 **0.862ms** / 3000 候选 4.91ms / 30000 候选 57.8ms；M3 正常形态（k=20 候选
    + 只打 20 条）≈ **0.05ms/NPC**。红线提案（待裁，随 A4 进 thresholds.py）：`VEC_CANDIDATE_PER_NPC_LIMIT_MS=0.30` /
    `RETRIEVAL_SCORE_PER_NPC_LIMIT_MS=0.30` / `RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS=2.00`（600 全量退化哨兵）/
    `RETRIEVAL_TICK_LIMIT_MS=12.0`。
  - **防呆红线延续反证数据**：每 tick 全量检索 50 NPC = 43.1ms/tick（600 候选）/ 245.5ms/tick（3000）= 破
    16.6ms **2.6x / 14.8x**；每 tick 广播只候选也 1–9.3ms/tick。V5 建议 = 按需为主 + 批量窗口可选
    （窗口一次 2.65ms/50NPC，摊销 2.65/N）。反直觉：50 NPC 批量矩阵比 50 次串行 matvec **慢**（2.65 vs 0.91ms，
    小 n BLAS 开销）——批量优化须先 bench 证伪。
  - `llm-monitoring.md` §7（A6）：`llm.embed_request/response/error/cache_hit` 族 + 字段（batch_size/dim/
    total_tokens/latency_ms/degraded/cache_hit；禁记向量本体与明文）+ 独立阈值（单条 P95<300ms / 批量≤32
    P95<2s / cache_hit>60% / 降级>10%）。chat 族口径零改动。
  - `bench-plan.md` §4.1（裁 4 执行件）：baseline.json 建8 步 + 触发前提 3 条 + 禁令 3 条。
  - `budget.md`：§1.2 指针 + §2.10 新节。
  - 验证：`-m "not bench"` 917 passed + 30 RED（M3-S1 钉子，同 main `db46b9e`）/ 55 skipped；ruff docs 通过。

- **M3-P2（2026-09-23，分支 ZX466/pi，commit `48db6cf`，等收编）**：检索缝四红线 bench 配套。
  - `sim/tests/bench/test_bench_retrieval.py`（新，8 用例）：4 红线 + 3 契约守卫（候选形状 / 治理 JOIN 最小自证 /
    哨兵区分度）+ 1 反模式探针。参考实现 = A4 同语义治理 JOIN（minimal 直建表 + 80 参 IN-JOIN + 4x 过取）。
  - 实测对账（暖态中位）：候选 **0.233ms**/0.30（1.29x，偏紧）；打分 20 候选 **0.057ms**/0.30（5.3x）；
    退化哨兵 600 全量 **0.970ms**/2.00（2.06x）；常态 tick 总量（决策驱动 10 次）**2.9ms**/12.0（4.1x）。
  - **④ 拆两口径**：反模式（50 NPC 广播）= 探测量不设硬断言——实测 **16.8ms = tick 预算 101%**
    （无-JOIN 38.9ms=234% / 全表掩码 131.2ms=790% → 三种实现全破线=防呆论据）。
  - **M3-P1 模型修正**：按纯 numpy 估 50NPC=2.5ms，实测 A4 语义参考 0.29ms/NPC = **低估 6~52x**
    （要回填 m3-retrieval-budget.md §2；结论不变=触发必须决策驱动）。
  - thresholds.py 同步四常量（opencode `caddcdd` 已落同值）。
  - 验证：retrieval 8 passed；`-m bench` 36 passed/1 skipped（2 例首跑抖动、单跑复绿=调度噪声）；
    `-m "not bench"` 948 passed + 3 RED（R2 钉子=A4 未收编 main）/ 55 skipped；ruff+pyright 全绿。
  - baseline.json（M3-P2 ②）**未执行**：nightly 迄今 7 跑全 failure（最新 35816437844 = advisory 门前旧跑）
    → 首个 advisory=1 全绿 run 未出现；等跑出现按 bench-plan §4.1 八步执行。

- **M3-P2② 交付（2026-09-24，分支 ZX466/pi，commit `ee05ab0`，等收编）**：baseline.json 八步执行 + AGENTS.md 清账。
  - runner 5 字段（run 35918283944 artifact 原样）：ubuntu-latest / nproc 4 / **AMD EPYC 7763 64-Core** / py3.12.3 / uv 0.12.18；
    head=main `372153a`，conclusion success。
  - `docs/perf/baseline.json` 入库：21 benchmarks + `machine_info.baseline_meta`（source_run/branch/commit/判据说明）；
    严格可解析 JSON（说明走 meta 字段，不破坏 json.load）。
  - nightly-bench.yml「基线对比」step：echo 提示 → `uv run pytest -q -m bench
    --benchmark-compare=docs/perf/baseline.json --benchmark-compare-fail=median:25%`；yml 仍不复制阈值。
  - **档位观察**：本 run 是 EPYC 7763（上轮 M2-P6② 是 9V74，微软换了机型）→ CI/本机中位比 median **1.71**
    （1.08–1.93，21 项）vs 上轮 1.14。25% 相对参数适用边界 = **跨 run 同档位**比较；档位切换需重新对账
    （已写进 yml 注释 + bench-plan §4.1 step 6 注记）。
  - AGENTS.md 13 行残账随本批提交，工作区干净。
  - 验证：`-m "not bench"` 981 passed/55 skipped；`-m bench` 36 passed/1 skipped；bench ruff+pyright 全绿；
    nightly-bench.yml YAML 解析通过。

## 当前任务

（空——M3-P2 ①② 均已交付，等 Claude 收编；下一步等 M3 批次 A4/embedding 相关派单（A1 定 V3 后 embed 监控事件族由 opencode 客户端照抄 llm-monitoring §7））

## 进行中

（无）

## 留言板

（收编回执见 .orca/talking.txt 留言板）

## ⑥ kilo（接口 / 兼容性域）
- 【2026-09-26 第十三轮快照｜M5-K8 意愿独白 S2C（未提交，待收编）】**产码采案 A（事件进流）**：新增 `EventKind.NPC_MONOLOGUE="npc.monologue"` + `NpcMonologuePayload`（**只 npc_id/form/content，extra=forbid** 挡数值/档位号）+ `npc_monologue_event()`（actor_id=npc_id，无 target/witnesses）。否决案 B（直接帧）：不可重放（§14 铁律）+ 绕过事件白名单可夹带数值，流量收益不足抵。**两案对比已写入 `sim/api/ws.py` 模块 docstring**。**投递面契约**（ws-protocol §4.2 W7 字段最小化：帧只含 form+content，**无 rtoken/actor** → 路由只能服务端按 form 定）：`ws.py` 新增 `MONOLOGUE_DELIVERY_ALL={bubble,plan}`（旁观者可见，广播）/`MONOLOGUE_DELIVERY_SELF={thought}`（思维面板私密，`send_to_subscriber` 定向）/未知 form **fail-closed 不投**。`ConnectionManager` 加 `subscriber_id`（`register(ws, subscriber_id=None)`；`subscriber_of`/`send_to_subscriber`；unregister 清身份；向后兼容——不传=旁观者）；`main.py::ws_endpoint` 用 **`subscriber_for_protagonist(loop)`=实体表首 id**（服务端定身份，**不采客户端自报**防空越权读他人面板）。`run_world_driver` 在 on_flush（落库）后投影 `monologue_events_to_frames` 逐帧按 form 路由。**defers→plan 联动**（K8 §3）：`plan_view.py` 新增 `DEFER_PLAN_PREFIX="（缓一缓）"`（**全角括号在 ruff allowed-confusables 白名单内**，U+FF08/FF09；替换初版 `〔〕` 因 RUF001/002/003 报 ambiguous）+ `defer_plan_text`（幂等）+ `set_plan_from_expression(entity,base,band=,defers=)`（band=3→带前缀；空 base→清项不吃前缀）。**测试**：`sim/tests/test_m5_monologue_s2c.py` 42 钉子（事件白名单/帧逐位投影/三 form 投递面/未知 form fail-closed/defers plan/端到端 + `willingness_expression` band=3↔defers 语义对齐）。**验证**：`ruff check+format` 清、`pyright` 0 err、`gen-protocol --check` **通过（schema 未改，未重生成）**、`pytest -m "not bench" --ignore=sim/tests/bench` **1315 passed 55 skipped**。**坑**：①`test_bench_soak.py::test_soak_ci_smoke_stability`（未标 bench，走每提交 CI）在本机 **墙钟 11.6ms>6.2ms 预算**——git stash 清树对照**同样 FAILED**，纯本机负载抖动域，与本次无关（勿据此改代码）。②假 WS 喂 `ConnectionManager` 须 `cast("WebSocket", fake)` 过 pyright（duck type 只实现 send_json）。③`PAYLOAD_MODELS`（`sim/core/persistence/event_validation.py`）与 `EventKind` 必须等集（`test_t1_m4_structure_payloads` 钉），新 kind 必登记否则该 T1 红。
- 【2026-09-26 第十二轮快照｜M5-K7 三项落地（未提交，待收编）】①**state_delta 顶层可选 `plan` 字段**（裁 14-3）：`ws.py::delta_payload` 追加 `plan=[{rtoken,text}]`；账本空则**不发该键**（可选字段不制造噪声——已有测试钉 absent），已清实体发 `text:""`（前端收起看板，非删键）。rtoken 出网关，按 `loop.state.entities` 过滤已注销实体。②**`_impulse_cue()` 钩子缝**：保留既有 accepted/hesitation/complaint 三值（启发式不回退），docstring 标明 band→cue 映射表真源=新增 `sim/npc/plan_view.py::band_to_cue`（`will.py::WillingnessVerdict.band` 四档 pure function 为输入真源）。③**anchors 部署债 #1 闭环**：新增 `sim/api/anchors.py`（`GET /api/anchors` 列表 + `GET /api/anchors/{anchor_id}`），两路由都调 `register_anchor_id()` 把 id 注进 `ws.py::_ANCHOR_IDS` 同步查表集——`load_anchor` 的存在性判定转由落库供数。新增 `sim/npc/plan_view.py`（`PlanDeltaStore` 进程内账本 + `band_to_cue`）。**范围外（Claude 域，文件中已显式标注）**：POST/PATCH/DELETE 三路由、`sim/api/errors.py` ProblemDetail handler（§3.2 三层接法）、`player_anchors.protected` 新列迁移。因此 anchors 404 目前仍是 `{"detail"}` 形，非 ProblemDetail 四键形。**坑（本机实测）**：①全仓 `pytest sim/tests` 有既有失败前缀 `.........F...FFFFFF.....FF.F..FFFF..F.F..FFFFF...FF...FFF..FFFF...FF.s`——与本次改动无关（git stash 对照基线逐字一致，很可能是 bench 文件交叉污染）；验证只跑相关文件子集。②`pydantic` 对齐快照须两处 K3 同款开关：`model_config.json_schema_extra={"description": ""}` 抑 docstring 进 schema + `created_at` 加 `Field(json_schema_extra={"format": "date-time"})`，否则实发 `AnchorListItem` 与 `shared/openapi.json` 逐字节 diff。③pytest `yield` fixture 必须标 `-> Iterator[None]`（pyright 报 reportReturnType）；`_rtoken` 由 `sim.api.ws` 导入共享，勿在测试里 `__import__("hashlib")`。
- 【2026-09-25 第十一轮快照｜M5-K6 分发块全落地 `13cb5b5`】K4 提案 8.1-8.6/8.8 全施工，六类 C→S 各有 `_handle_*` 纯函数（`ws.py:210` 起）。**已闭环**：set_control 回 `control_ack{action,applied:true,speed?}`（applied 恒 true=8.1 占位；pause/resume 走 `_PRE_PAUSE_SPEED` 栈恢复暂停前倍率，§1.2 不进 GameClock；携带 speed 容忍忽略=8.2）；player_impulse 注册+校验+**乐观** impulse_feedback（同步不 await、不改世界态）；load_anchor 注册+失败不断线+成功短期同步 full_snapshot；move_request 非法类型 → bad_target（不可达/主角不存在保留静默，§4 权衡）；10 项 code 收敛为 `_ERROR_*` 常量 + `_error_frame()`。**§7 对表 20/20 过**，钉子 56 例。**两条部署债（已记提案 §8.9）**：① `_impulse_cue()`/monologue 模板是**占位**——冲突度规则表（8.3）归 LLM 域 M4 定稿，协议面无需再动；② `_ANCHOR_IDS`+`_ANCHOR_LOAD_HOOK` 是进程内同步查表替身（handler 同步而 `player_anchors` 表在 async `SqlEventStore`）——`GET /api/anchors` 路由落地后由落库路径调 `register_anchor_id()`，「定位→快照→重放」driver 化时接 hook；M2 多连接前改为 `ConnectionManager` 每连接字段。**坑：模块级会话态必须 autouse fixture 隔离**（`reset_pre_pause_speed`/`reset_anchor_registry`），否则跨用例污染。**签名铁律**：`handle_client_message(raw, loop, pf)` 三参不变（§8.5 备选案 `pf.tile_map`），`main.py` 调用点零改动。
- 【历史】M5-K5 sync_request 回错型首修（`e763b04`，K4 §5/§8.7）；M5-K4 提案 264 行 + 裁 12 全采 8.1-8.8；M5-K3 ext↔快照 diff 17 schema 差异表=ext 返工验收清单，已返工+复验放行；M2-K2 复核 6 类全采信（切源暂缓，mock 源唯一真相源）；M5-K1 anchors 契约稿 306 行（`b849025`）。**active 约定**：K3 关键修正=subject 整删 + ext 侧 nullable=0 红线；切源解禁两条件（codegen.md §4.1）=M5 锚点路由落地 + sim 全局 404 声明；`openapi_ext.py:17`「anchors 不施工」+ test ADDED_SCHEMAS 白名单两处 M2-K3 遗留注释留待 M5 路由落地时改（Claude 域文件）。**本机 bench 阈值不稳**：`test_bench_soak.py` tick 延迟失败＝ CPU 抖动/机型问题（pi 域口径），勿误判为代码回归。

> ——kilo 树 memory.md（更新于 5f5f525：K04 完成回执 + 跨域发现）——
> 用户规则 #7：本文件保存 **kilo 自己的记忆**，供新对话继续任务。**已入库**（main `3e320b9` 裁决），改动走提交；跨树融合由主导方（Claude）收编时合并（本树本地版 = 权威来源）。
> 新对话开场先读：`.orca/talking.txt`（Claude 派活/回执）→ 本文件 → `.orca/workflow.txt` + `.orca/agent-registry.md`。

## 0. 我是谁 / 在哪

- 能力域：**接口 / 兼容性**（评审 Agent = Claude）。
- 工作树：`E:/zxdevelop/.orca/worktrees/project7/kilo`，分支 `ZX466/kilo`。
- 收编由 Claude 执行；我 **只提交本分支，不自行 push/merge 到 main**；用 `git merge origin/main` 同步。
- 上下文达 50% 时提醒用户切换新对话。

## 1. 项目一句话

临河镇：2D 像素 LLM 模拟世界。设计基线 `DESIGN.md`（v2.1 冻结）。多 agent：Claude 主导/组织（架构·质量·逻辑·测试·前端），cline=依赖/配置/文档，codex=安全/合规/风险，pi=性能，opencode=数据/库，kilo=接口/兼容性。沟通靠各树 `.orca/talking.txt`（本地保存不入库）。

## 2. 我的交付物与命令（接口域）

交付物：`docs/api/{ws-protocol,openapi,codegen,versioning}.md`｜`shared/openapi.json`（协议快照：HTTP+WS+响应 schema）｜`shared/protocol.ts`（openapi-typescript 生成物，**永不手写**）｜`tools/gen-protocol.ts`（生成脚本）｜`client/src/net/protocol.ts`（前端唯一类型入口，re-export+判别联合）｜`client/src/net/__tests__/protocol-types.test.ts`（出戏边界类型断言）｜`client/src/net/settingsApi.ts` + `client/src/ui/SettingsPage.tsx`（K03 设置页）。

命令（在 `client/` 下）：
- 生成：`node ../tools/gen-protocol.ts`（npm 别名 `gen:protocol`，由 cline 配置）
- 漂移校验：`node ../tools/gen-protocol.ts --check`
- 切真实源：`node ../tools/gen-protocol.ts --src http://127.0.0.1:8000/openapi.json`
- 验收组合：`gen-protocol --check` + `npm run typecheck` + `npm run lint` + `npm run test`(vitest) + `npm run build` 全绿才算过。

## 3. 关键约束与坑（裁决已批）

1. **rtoken** 是不透明渲染替身（`rtoken↔内部 id` 映射表留 sim）；前端**只接触 rtoken，绝不接触真实 id**。`entity_id/source_id/tick/seed/seq/branch_id` 绝不进任何对外字段。
2. 信封 `ws_seq` = 传输序号（丢帧/乱序检测），**不是世界 tick**。
3. **出戏边界**：narrative 通道 `content` 必须第一人称、无数值无系统词；`rtoken` 仅 render 通道出现，不进 narrative。
4. sim OpenAPI 地址是 **`/openapi.json`**（FastAPI 默认，**非** `/api/openapi.json`）。
5. **K5 白名单**：profile 响应 = `{id,name,base_url,model,temperature,max_tokens,active,api_key_hint}`，绝不含 `api_key` 明文/`api_key_enc`/`provider`/`params`。
6. **W7 字段最小化**：`monologue` 删 `anchor_ref`，`impulse_feedback` 删 `delay_ms`。
7. sim 启动需环境变量 `LZ_MASTER_KEY`（Fernet key，codex K2；缺失拒绝启动）。开发用临时 key，勿提交。启动：`uv run uvicorn sim.api.main:app --port 8000`。
8. `gen-protocol.ts` 依赖 **Node ≥ 24**（无旗标类型擦除跑 .ts）；调用 `client/node_modules` 内 openapi-typescript/prettier 真实入口。
9. 前端 HTTP 走 vite dev 代理 `/api`→sim:8000（免 CORS）；WS 直连 `ws://127.0.0.1:8000/ws`。vite 在 Windows 上用 `localhost:5173` 访问（`127.0.0.1` 可能连不上）。
10. **⚠ CRLF 假报漂移**：本机 `core.autocrlf=true` 且无 `.gitattributes`，工作副本 CRLF 而生成器写 LF → `--check` 逐字节比对**假报漂移**。代码无问题；用 LF 索引内容复测即在。cline 已建议 Claude 加 `.gitattributes`（`* text=auto eol=lf`）。
11. **⚠ `.orca/memory.md` 被 main 误追踪**（本地文件却进了 git，`344ae3d` 含它）→ 各树同名文件合并必冲突。应对：本地维护我自己的 memory.md、**不提交**；已请 cline `git rm --cached .orca/memory.md` + `.gitignore` 加 `.orca/memory.md`（配置域）。

## 4. 进度（2026-09-20 同步 main `3e320b9`）

- M0 ✅、M1 主体 ✅（C06 全部进 main，~310 passed）。
- 我已完成并收编：TASK-001（协议四文档）→ TASK-002/K01（gen 工具+WS 类型+断言；补 MoveRequestMessage）→ TASK-003/K02（`/api/world/map` chunk + M1 三消息定稿 + settings 契约）→ **TASK-004/K03（设置页前端 + protocol 切真实源；收编 `0f06684` 入 main `344ae3d`）**。
- Claude 已按我回写补齐 sim 缺口（`344ae3d`）：settings 四路由挂 `response_model=ProfileListItem`；`sim/api/openapi_ext.py` 注入 `components.wsMessages`（serverToClient: WsFullSnapshot/WsStateDelta；clientToServer: 白名单 4 消息）。**→ `--src .../openapi.json` 现可全量生成。**

## 5. 当前任务 / 进行中

- **K04（2026-09-21 已派发+接受+交付，已收编 main `8dd8355`）**：
  WS 消息类型全量生成进 `shared/protocol.ts`。核验结论：`shared/protocol.ts` 的 `WsMessage`
  判别联合（14 成员：C→S 5 = player_impulse/set_control/move_request/load_anchor/sync_request；
  S→C 9 = full_snapshot/state_delta/perception/monologue/impulse_feedback/combat_event/
  timescale/control_ack/error）早已生成；`client/src/net/protocol.ts` re-export 齐全；
  `ws.ts` 已用生成类型（仅 `WsStatus`/`WsCallbacks` 手写 = 传输层，非协议）。
  交付：`protocol-types.test.ts` 补 K04 #1/#2（WsMessage['type'] 14 枚举 + 每成员必填
  字段形状 + 五通道判别字面量 + 出戏边界），`docs/api/ws-protocol.md` §3.1 补 `move_request`
  行（快照 `c48358f` 早加但文档漏更的偏差）。
- **⚠ 跨域发现（K04 回执已写 talking.txt；Claude 已收进架构稿 §6，M2-A2 待办）**：
  1. `sim/api/openapi_ext.py` 的 `components.wsMessages` **openapi-typescript 完全不读**（只读
     `components.schemas`）→ 实测 `--src` 指 sim `/openapi.json` 生成 0 个 WS 类型。该注入对
     前端类型源无效。
  2. 且草图本身不完整/不准：只 6 条（缺 §3 清单 9 条：player_impulse/load_anchor/perception/
     monologue/impulse_feedback/combat_event/timescale/control_ack/error）；形状也不对
     （WsStateDelta 缺 `channel`；WsSetControl 用 `controlled` 而非 `action/speed`）。
  3. `hello`/`hello_ack`（W6 鉴权握手，`sim/api/ws.py` 实发）**故意不进协议清单**（安全域），
     快照联合无它们是正确裁决，勿"补齐"。
  4. 结论：`shared/openapi.json` 的 oneOf+discriminator 联合方式是唯一可行前端类型源；要真正
     消除 sim↔前端漂移，需 sim 侧把 §3 清单写进 `components.schemas.WsMessage`（sim 域改动）。
  5. `sim/api/ws.py` 与快照的另一处差：`error` 消息 sim 不发 `ref`（快照 required 含 ref）。
- **M2-K1（2026-09-21 派发+接受，两项）**：
  1. openapi_ext 复核——**等 Claude 改写 `components.schemas.WsMessage` 的通知**再动手；届时
     验 `--src` 全量生成 14 成员 + `--check`。
  2. language.py 叙事边界复核——**已交付**（意见写 talking.txt 留言板 2026-09-21）。要点：
     - 架构稿 §5.2「LanguageProfile 挂 species/阶层 profile」**会误导成物种级**；数据层既定
       `npc_profiles.knowledge_boundary`（0004 迁移 + `models.py:293` + `sim/tests/test_persistence_m2.py:69`
       夹具）= 每角色 JSON `{"literacy","jargon","class_register"}`。DESIGN §229「人类共用一套」
       指感知参数（`PerceptionProfile`）非语言能力。→ 须按角色构造；`species_language` 才是物种级枚举位。
     - 命名待 sim 域定：`register`（架构）vs `class_register`（夹具，倾向后者）；`jargon: set[str]`
       （架构）vs JSON list（夹具，建议 `Sequence[str]`）。
     - 出戏边界 4 红线：降质文案零数值零系统词（架构三条候选已实测过 `banned_words.scan()` 0 命中）；
       `literacy` 只做阈值绝不进文本；降质只动叙事层文本、`Observation`/`PerceptionFrame` 原始数据
       保持完整（M3 知识传播前提）；挂载点应为 `PerceptionFrame.narrated()` 内而非 `Observation` 构造处。
     - 接口域增量：语言降质文本走现有 `perception` 消息 `content`（string），**schema 不变**；
       `species_language`/`class_register` 等判据不出 WS。K04 的 14 成员联合无需改。
- **M2-K2（2026-09-22 派发，复核 59ffd86 openapi_ext 改写 + 接口三查——已交付）**：
  - 结论：**结构骨架对、成员内容简化过度**。14 成员 + oneOf/discriminator 进 components.schemas ✅、wsMessages 废除 ✅、channel 下沉 ✅、error 无 ref ✅、hello/hello_ack 不进联合 ✅（W6 保持）。sim 侧 test_openapi_ext.py 8 用例本机全过，ruff/pyright 干净。
  - **P0**：`--src <sim>/openapi.json` 全量生成 631 行 vs 提交 830 行——缺 21 个快照独有 schema（Actor/MapInfo/MapChunk/WorldMapResponse/Light/LightDelta/Structure/StructureDelta/Weather/CombatInfo/Projectile/Hit/MonologueReaction/AnchorCreate/AnchorListItem/HealthStatus/ProblemDetail 等）。原因：HTTP 路由（/api/world/map、/api/anchors）仍是裸 dict，sim 只给 settings 四路由挂了 response_model。→ **mock 源 shared/openapi.json 仍是唯一可用真相源**，切源前 sim 须补 HTTP response_model。
  - **P1**：ext 的 12 个成员与 ws-protocol.md §3/§4 + 快照形状不一致（逐条见 talking.txt 留言板 2026-09-22）：perception 缺 form、monologue 用 reaction 对象（W7 曾删）、impulse_feedback 缺 injected/cue/reaction_monologue、combat_event 缺 §4.1 六项、timescale 缺 mode/active 且 channel 错写 render、control_ack 缺 action/speed/applied（ws.py 实发就带）、sync_request 缺 reason。
  - **P1**：OpenAPI 3.1 `{"nullable": true}` 是 no-op（openapi-typescript 不产 `| null`）；快照的 `oneOf:[...,{"type":"null"}]` 才是正确写法。preset/subject/attacker/defender/reaction/note 全中招。
  - **接口三查全过**：①WindVector/weather 不进 WS（openapi_ext 无 wind 字段）；②hidden/triggered 不进 WS（只被 gate/memory_scan 消费）；③perception content 仍 string（frame.py Observation.description: str + narrate.py 纯模板函数）。
  - 本机环境坑：PowerShell 捕获 python/node 的 stdout 会丢中文/整段输出——比对 JSON 用 node 写 .cjs 脚本落文件再 Read。起 sim 用 `LZ_MASTER_KEY` 临时值 + uvicorn :8000。
- 其他：等 Claude 派 M2 后续 / TASK-005。

## 6. 留言板 / 待回执

- cline P05：`*.tsbuildinfo` 已加 .gitignore ✅；`_PROTOCOL_VERSION` 与前端 `v` 统一 1.0（并代改了我前端域 `client/src/net/ws.ts` 的硬编码，见 §3.10）；K04 前置就绪。
- 待我：若有 K04 之外的 M2 派发，以 talking.txt 为准。
