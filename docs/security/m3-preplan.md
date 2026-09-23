# M3 安规预研（docs/security/m3-preplan.md）

> 维护：Codex（安全/合规/风险域）· 依据：DESIGN.md §16（信息边界不变量）/§14（建造）/§17（M3 里程碑）、
> memory-scan.md（S1-S6）、self-unknown.md、l1-whitelist.md、schema.md §5/§6/§8/§9/§14 · 日期：2026-09-23
> 状态：M2 第五轮预研交付稿。**零代码**——本文只定风险、缝与验收清单；实现归属各域（§5）。

## 0. 一句话

M3 开工前的三面安规盘点：①记忆/知识传播不得绕过 S5 治理列与自我未知边界（有 4 条真实缝）；
②建造系统的输入面沿用 M2 事件校验骨架扩清单（NaN/权限/note 是新暴露面）；③trauma_avoidance
进效用决策后，扫描面以「构造隔离 + 钉子测试」守住——breakdown/triggered 永不进戏内产物。

## 1. 记忆传播的信息边界（风险点 R1-R7）

现状锚点：读侧唯一入口 `sim/npc/memory.py::retrieve`（候选=持有者自己的 `iter_visible`，S5 过滤）；
写侧唯一入口 `MemoryWritePipeline.write`（banned + hidden 双扫）；治理列=`superseded_by`/`invalid_reason`。

| # | 风险/缝 | 证据 | 对策建议（实现归 §5 各域） |
|---|---|---|---|
| R1 | **knowledge 表无治理列**：记忆条目可被 supersede，但由它派生的 `knowledge.fact` 永久有效——M3 反思/转述把记忆转成知识后，污染条目借知识表复活，S5 被旁路 | 0002 迁移/schema §8：fact/confidence/source 无 superseded_by 类列 | knowledge 落库走写入门（banned+hidden 扫描同记忆）；记录派生源 `source_memory`（entry_id）；源被 supersede → 知识条目级联失效或 confidence 衰减 |
| R2 | **npc_memory_vec 无治理列**：supersede 只 UPDATE npc_memories，vec 行不删——M3 向量召回把已治理条目带回候选；若候选按 rowid 回查不复查治理列 = 直通绕过 | `vector.py`（vec0 只存向量，rowid=npc_memories.id）；memory_store.py supersede 无 vec 操作 | 向量候选生成必须 JOIN npc_memories 且过滤治理列；或 supersede 同事务删/标 vec 行。这是 self-unknown.md §4「检索端按 triggered 过滤」契约的落地点 |
| R3 | **invalid_reason 单置仍可见**：`iter_visible` 只过滤 `superseded_by IS NULL`；schema 允许只置 invalid_reason 的行继续进检索 | memory_store.py `WHERE npc_id=? AND superseded_by IS NULL` | 口径二选一并写死：双列任一非空即不可见；或强制成对写（supersede 已成对，禁止裸置 invalid_reason） |
| R4 | **跨分支记忆混入**：`iter_visible(npc_id)` 不过滤 branch_id——abandoned 分支的记忆会混进当前分支检索；knowledge/relationships 有 branch_id 列，记忆表也有但没用上 | memory_store.py SQL；0002 迁移 | M3 起所有读 API 带 branch_id（M5 双轨存档前的定时炸弹）；传播写入落当前分支 |
| R5 | **转述链跨人属性**：B 转述「C 有旧伤」——B 自身 profile 无该 descriptor，B 的写入门扫不到。社会面信息边界（他人隐藏属性不该被未目击者知晓）目前无工具可拦 | self-unknown.md 铁律 2（扫描面=自身属性）；knowledge.source=witnessed/told/inferred | 证据链规则：他人隐藏属性成为知识的前提=`witnessed` 且目击 tick 该属性处于 triggered 窗口；`told` 传播 confidence 衰减；`inferred` 不得产出他人隐藏属性 |
| R6 | **跨 NPC 记忆直读**：若 M3 实现「共享记忆池/借阅查询」类 API，绕开以持有者为键的 S5 过滤 | MemoryStoreLike 协议仅 `iter_visible(npc_id)`——契约靠约定维持 | 架构约定：检索 API 永远以持有者 npc_id 为键；传播只经「写入门」复制（A 告诉 B = B 侧走一次 write），不开放跨人读 |
| R7 | **反思产物绕行**：M3 反思批处理（DESIGN §15）生成的摘要条目若不走 write() 唯一入口，全部扫描失效 | memory-scan.md S1（CI 守卫断言仓内无绕过构造点） | S1 守卫测试扩到反思/传播新构造点；摘要=write(source="reason") 同款 |

## 2. 建造系统输入面校验清单（草案 C1-C13）

现状锚点：事件行校验 `event_validation.py`（PAYLOAD_MODELS 唯一 schema 真相 + append 默认 validate=True）；
`TileChangedPayload`（x/y/tile_id，extra=forbid）已登记、M0 拒收；`MatterPayload` 四 kind 已登记；
WS 模式=type 白名单 + channel 校验 + 逐字段显式校验 + 结构化 error（`ws.py::handle_client_message`）。

| # | 清单项 | 说明/证据 |
|---|---|---|
| C1 | 新事件 kind 必须登记 PAYLOAD_MODELS | 建造/拆除若新增 kind（或复用 TILE_CHANGED/MATTER_BUILD），未登记即拒落库（event_validation.py）；新模型 extra="forbid" |
| C2 | 数值域约束 | amount/durability/decay_rate/tile_id/x/y 加 Field(ge/le) + `allow_inf_nan=False`——python json.loads 接受 NaN/Infinity 字面量，ws.receive_json 不设防，pydantic float 默认放行 NaN，np.clip(NaN)=NaN 会污染 integrity（MatterPayload 现无任何域约束，M3 必须补） |
| C3 | bool 冒充 int | P3 #1 教训（move_request 已防）：所有坐标/数值入参用「isinstance(int) 且非 bool」或 strict 模式，建造指令同款 |
| C4 | 服务端裁决 | 界内 + 可通行 + 材料充足一律服务端校验；客户端预检不可信（单机 M0 的「客户端已预检」注释不适用于 M4 多输入面） |
| C5 | 标识符约束 | matter_id/structure_id 限格式（长度/字符集）；禁自由文本；禁 LLM 原始输出直接作 id（威胁 T6 二次注入） |
| C6 | 主体权限 | WS 建造指令只允许操作 protagonist（念头注入同款「唯一受体」）；actor_id 服务端生成，客户端不可指定；L1 NPC 建造走引擎侧 NPC_ACT 白名单（六动作扩建造时同步 ACTION_PAYLOAD_KEYS） |
| C7 | note 字面 | MatterPayload.note 保持服务端生成 only（M2-S3 O1：现仅「耐久归零坍塌」）；客户端/LLM 传入的 note 禁止，或强制过 banned+hidden 扫描后才能落 events |
| C8 | 频控 | per-connection 帧率与消息长度上限（威胁 T10/W4 同源）；16x 倍速下建造 tick 密度评估归 pi |
| C9 | 错误面结构化 | 拒绝必须回 error{ref,code,message}，禁静默丢弃（§19）。**顺手记档**：`set_control` 在 `_ALLOWED_CLIENT_TYPES` 白名单内但 handle_client_message 无处理分支 → 现在静默 None，M3 接 set_control 实装时一并补 |
| C10 | 解析健壮性 | ws.receive_json 的 JSONDecodeError 当前未捕获（只 except WebSocketDisconnect）——坏帧会打断接收循环；建造指令上量前须补 error 帧或安全关闭 |
| C11 | 重放一致性 | 建造变更全量走 events（快照+重放逐位重建，schema §14 matter_state 同构）；禁旁路 UPDATE structures/matter_state（§19 唯一写路径） |
| C12 | 材料守恒 | inventory 扣减与 structures 落成同事务/同事件批次（§16 T1 不变量 6 的 M4 落地面） |
| C13 | 通道纪律 | build/set_control 走 control 通道；render/narrative 通道永不收指令（channel 校验已在 handle_client_message，扩展类型时沿用 `_CHANNEL_FOR`） |

## 3. 隐藏属性跨域泄漏面复查清单（X1-X8）

现状锚点：cognition 骨架 `sim/agent/cognition.py`——效用缝四偏差为纯函数，M3 接行为决策链；
`trauma_avoidance_penalty(triggered) = -0.5 × len(triggered)`（**只吃计数不吃 id**）；
`MemoryHit.breakdown` 携带 `(BIAS_NAMES, value)` 纯诊断分解（memory.py 明文「不参与下游计算」）。

| # | 检查点 | 结论/要求 |
|---|---|---|
| X1 | 效用缝形状 | 保持「只计数、不传 id」：M3 接线不得把 attr_id/descriptors/triggered 集合本身传入效用链或其产物（现签名 frozenset→float 是安全形状，CR 冻结） |
| X2 | breakdown 死路 | BIAS_NAMES（confirmation_bias/trauma_avoidance…）是元信息标签且**不在** banned_words 词表——防线只能靠构造隔离：breakdown 只进 dev 观测，永不进 assemble_prompt/NPC_ACT params/WS payload/戏内 UI。落 T1 钉子测试锁定 |
| X3 | UtilityDecision.scores 审计面 | 六动作全量分数只做审计；runtime.tick 已按 ACTION_PAYLOAD_KEYS 过滤 params——加钉子测试防回归（scores 永不落 events/memory/knowledge） |
| X4 | triggered 窗口不持久化 | attr ids/triggered 集合永不入 events/记忆/知识/玩家可见日志（dev 除外）；HiddenState 内存态传递口径（l1-whitelist §2.1）延续到效用缝 |
| X5 | 触发词面扩面 | M3 新叙事源进 context_text：smell 风向叙事（narrate_smell 注释明示 M3 起）、天气/地标文本——「河/酒」类触发词可能被环境文本意外命中 → 浮现窗口被动扩大=泄露面扩大。CR：新叙事文本与 trigger 词面交叉审查（本域） |
| X6 | O1/O2 复核 | matter note / lod reason 仍为戏外事件流字段（m2-d2-review 观察维持）；M4 建造叙事消费 MATTER 事件进见证者记忆时，叙事层必须过 banned+hidden 扫描（实现归 Claude 域，本域出验收断言） |
| X7 | knowledge.fact 扫描 | 知识表 fact 是自由文本：写入过 banned+hidden（与记忆同工具同入口原则）；prompt 装配消费 knowledge 走 assembler（出口终扫已有） |
| X8 | 社会面口径 | 他人隐藏属性进入「我的记忆/知识」的合法路径只有 R5 证据链（witnessed@triggered-tick）；自身属性扫描面不变（hidden_leak_scan 按持有者 profile 走） |

## 4. 验收口径建议（M3 安规怎么判）

1. R1-R4 的缝在实现落地时各配 1 条 T1 钉子（向量化检索治理过滤/知识级联/分支隔离/双列口径）；
2. C2/C3/C9/C10 属「实现即验收」项，随建造首个 PR 一起进（不单独立里程碑）；
3. X2/X3 钉子测试进 T1 全量；X5 走 CR 文档流程（词面变更纪律同 self-unknown.md §7）；
4. M3 安规通过标准：上述钉子全绿 + 10k 采样 harness（M2-S4）对新增扫描面零回归。

## 5. 责任分工

| 面 | 实现域 | 本域职责 |
|---|---|---|
| R1-R7 记忆/知识传播 | opencode（存储/治理列）+ Claude（行为链） | 验收测试口径 + R3 口径裁决建议 |
| C1-C13 建造输入面 | Claude（事件/WS）+ kilo（契约对齐） | 清单评审 + C2/C10 复测 |
| X1-X8 扫描面 | 本域（钉子测试 + CR） | 全部 |