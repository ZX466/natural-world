# 玩法与存档完整性深度复检（2026-10-21）

## 核查基准与结论

核查最新主树 **`3cbcd8d`**，通过 `git archive` 提取独立源码快照；未合并 main、未修改主树、未连接真实模型或真实游戏数据库。当前 codex 上已经交付的 O 单 `9447d1b` 不作为新增缺口。

**确认 8 组缺口：2 组 P0、6 组 P1。** 最优先的是世界状态恢复和事件日志完整性。现有协议接线、工地重建等局部修复成立，但它们不能代替完整的世界恢复。

- P0：持久化世界会丢失、污染日志，或正常历史读档不能完成。
- P1：核心交互、角色控制、资金/火场或世界呈现存在可复现错误。
- 不给完成百分比：本次没有足够证据把全部 DESIGN 承诺换算成一个数字。

## 证据与方法

源码快照与本机复现材料位于：

```text
.orca/audits/20261021-main-3cbcd8d/
  source/                       main@3cbcd8d 的源码
  deep_probes.py                 无真模型调用的独立行为探针
  deep-probes.json               实测结果
  probe-output.log
  existing-tests.log
  regressions.log
  source/sim/tests/test_deep_audit_regressions.py
```

复现命令，在 `source/` 目录执行（`--project` 指向本树已有 uv 环境）：

```powershell
uv run --project E:/zxdevelop/.orca/worktrees/project7/codex python ../deep_probes.py
uv run --project E:/zxdevelop/.orca/worktrees/project7/codex pytest sim/tests/test_build_restore.py sim/tests/test_deep_audit_regressions.py -q
```

本轮证据分两层：

| 验证 | 实测结果 | 证明范围 |
|---|---|---|
| 既有 P 分支恢复、瓦片契约、分叉编排、经济、战斗、WS 鉴权测试 | **62 passed** | 原有局部契约仍通过 |
| 既有启动/读档地图测试，作为相同夹具的对照 | **2 passed** | 地图修复本身有效，夹具可以正常完成分支切换 |
| 新增运行态恢复/呈现回归 | **5 failed** | 余额、火场、世界时钟、建筑快照、坍塌后的实时碰撞仍未闭环 |
| 独立探针 | 正常生成 JSON 结果 | 验证历史游标、真实启动流程、名字/货名、主角死亡与双控制者 |

新增回归保留在审计快照中，没有把已知失败用例加入项目常规 CI。分支切换回归复用了项目现有 `branch_world` 夹具：SQL 当前分支切换用替身，实际 `_drain_loads`、账本清理、地图重建和快照构造都执行真实代码。历史游标与重启探针使用真实 SQLite 和真实生产函数。

## P0：优先恢复世界真实性

### DA-01：重启重新创世，并把第二次创世写进旧时间线

**实测**：保存 tick=120、陈默位置 `(101,53)`、`villager_01` 已死亡，并写入世界快照；重新调用生产 `build_loop()` 后，tick=60、陈默回到 `(100,53)`、该村民重新出现。把新启动的待写事件正常 flush 后，同一分支包含 **2 条 `world.create`**；重放报「创世事件只能作用于空白世界状态」。

**代码**：`3cbcd8d:sim/api/main.py:181-206` 每次都构造空 `WorldState`、enqueue 创世和出生点移动；没有在已有世界时恢复最近快照与事件尾部。`sim/core/world.py` 的创世 handler 明确拒绝对已有世界再创世。

补充源证：在 `sim/api`、`sim/core`、`sim/npc`、`sim/agent`、`sim/world` 检索 `write_snapshot(`，只看到接口/实现定义，没有生产调度调用。设计中「每 1000 tick 自动快照」也没有接进实际循环。本次重启探针专门预先写入一个有效快照，仍然未被读取，因此结论不依赖这一项缺失。

**影响**：重启会回退角色状态、复活死者，继续运行还会污染原本应可重放的事件流。这比地图是否恢复更优先。

**修复验收**：空库只创世一次；已有库恢复当前会话分支的快照与事件尾部，恢复 tick/实体/时钟与必要上下文；重启前后可比世界状态一致；正常 flush 后创世条数仍为 1。已经被污染的旧日志须另定兼容/修复方案，不能静默删除 append-only 历史。

### DA-02：生产读档仍走 head-only，且异步完成前就发出旧快照

**实测**：一个具有完整物化包、`materialization_ready=true` 的存档位于 seq=2；世界继续到 seq=3 后，调用与生产相同的 `orchestrate_load_anchor(..., hooks 未传)`，报 `ForkError: seq=2 < head=3`。请求尚未执行分叉，只让同步登记钩子返回 True，网关就已经返回 `session_state` 分叉告知和 `full_snapshot`。

**代码**：`sim/api/main.py:779` 没有把已经注册的物化 hooks 传入；`sim/core/persistence/fork_orchestration.py:279` 仅在显式传 hooks 时走历史物化；`fork.py:441` 拒绝非头部游标。`main.py:719` 的 `_expand_world` 仍返回 None；`_drain_loads` 没有替换 `loop.state`。回归里切到只继承 tick=0 创世事件的分支后，运行时仍是 **tick=172900**。

`sim/api/ws.py:1203-1223` 把「请求已登记」当作「已经读档」，先发当前旧世界的快照；`_drain_loads` 成功后只有日志和 outcome，没有补发真正恢复后的完成快照。

**影响**：正常旧档被拒；玩家可能先看到回档告知，随后才收到失败。即使 SQL 分叉通过，运行态、时间和响应完成顺序也没有完整恢复。

**修复验收**：用真实存档包覆盖「存档后继续推进再读档」；接通真实世界展开/重放，明确玩家会话分支与数据库 `is_current` 的交接规则；实际推进、保存都必须使用选中的子分支。完成确认和全量快照必须在恢复成功后发出。单纯补一个 `hooks=` 参数不足以闭环。

## P1：玩家能直接遇到的缺口

### DA-03：余额和火场被清掉，没有按锚点恢复

**实测**：记录 `coin.grant +100`，让目标分支继承到这条事件，再执行生产清零流程，余额为 **0 而非 100**。同样保留了 `fire.ignited` 的分支，读档后 `fire_runtime.cells` 为 **0 而非 1**。两条新增回归分别失败。

**代码**：`sim/api/main.py:797-799` 调用 `coin_ledger.reset()`、`fire_runtime.reset()`，后面仅重建 matter/structures/地图/工地；没有恢复 CoinLedger 或 FireRuntime。`CoinLedger` 的余额本可由 `coin.grant` 重建，却没有生产消费方。

**影响**：存档不保值，保存时的火也会凭空消失。清理旧分支状态和重建目标分支状态是两个必要步骤，只有前者不够。

**修复验收**：统一列出必须恢复的运行态投影；余额、活火及其序号由目标分支谱系事件恢复，并证明祖先分叉后的未来事件不会进入新分支。健康账本也需要纳入恢复设计；本轮没有把其未完整事件化的问题算成额外独立缺口。

### DA-04：模型说人名被拒，说中文货名则静默不成交

**实测**：受控 LLM 返回 `talk_to / 赵铁`，经过真实 `decide_once → parse_intent → gate` 后，队列长度 **0**，原因 `unknown_target`。返回 `buy / 草药` 时，执行数 **1**，但余额仍为 **100**、事件列表为空；同一输入仅改为内部标识 `herb`，余额变为 **87**，产生 `coin.grant` 和独白。

**代码**：`sim/llm/prompts/assembler.py:33` 要求「直接说名字或货名」；`driver.py` 解析后直接 gate；`gate.py:108` 按 `state.entities` 内部键查目标；`driver.py:418` 仅用 `_GOOD_INDEX` 内部键取货，查不到直接 return。地标段只有地点，没有明确的人名候选清单。

**影响**：人名部分是既有 N 单未在本次基准主树落地的缺口；本轮额外确认同一矛盾还阻断中文货名交易。模型严格遵守 prompt 也会失败。

**修复验收**：解析后、gate 前按动作规范化人名和货名；只对唯一、存在且符合交互范围的目标解析，未知/重名仍拒绝。候选人物按距离最多 12 名，只给戏内名，不把机器 ID 放入 LLM 面。姓名、中文货名、内部兼容标识和幻觉名都要覆盖。

### DA-05：新分支地图已还原，建筑表现缓存仍留在未来

**实测**：旧分支有建筑；切到建筑产生前的分支，服务端格子可走，但新构造的 `full_snapshot.structures` 仍包含旧建筑。

**代码**：`sim/api/ws.py:540-550` 的模块级建筑表现账本没有在读档后清理并重建；`main.py:813` 更新的是 `maintenance.structures`，不是 WS 账本。`on_flush` 对外投影只处理 completed。

**影响**：数据库、寻路图与玩家看到的建筑不一致。P-1 的碰撞修复本身通过，但表现层没有同步完成。

**修复验收**：从目标分支结构投影重建 WS 建筑账本；成功完成后推全量快照；覆盖旧分支未来建筑不出现、历史建筑保留、坍塌/移除相位更新。此项只核查 `structures`，没有重新报告已撤回的 L 单面板空态误报。

### DA-06：坍塌还原事件入库正确，实时碰撞图却没有应用

**实测**：触发真实 `structure.collapsed` 后 flush，日志已经有正 tile_id 的还原事件；调用 `rebuild_tile_map` 得到的图可走，但当前 `app.state.tile_map` 仍不可走，新增回归失败。

**代码**：`sim/api/main.py:295` 的 `_with_structure_tile_restore` 补发日志，但 flush 后没有把这些瓦片改动应用到当前地图、BuildRuntime 地图和 Pathfinder；重建函数只在启动/读档调用。

**影响**：建筑倒了仍撞墙，直至再次重建地图。主树 P-6 的「补日志」部分有效，实时消费部分仍缺。

**修复验收**：结构终态派生瓦片事件被当前世界立即消费，三个地图引用及寻路缓存同步；同一事件序列的在线图与重建图一致。不要每 tick 全图重建，也不要只改数据库。

### DA-07：主角受火灾伤害走普通 NPC 删除，没有失能续玩路径

**实测**：使用生产 `FireRuntime.collect_deaths`，把陈默置于燃烧格；返回 `npc.death`，正常 enqueue 后 `chenmo` 从实体表消失。

**代码**：`sim/npc/fire_runtime.py:87` 对所有实体同样产死亡事件；`sim/core/world.py:147-163` 无主角例外地删除。当前没有与此配套的主角失能、时间跳跃或恢复挂载点。

**设计差距**：`DESIGN.md:339` 明确主角只失能、不永久死亡。此处是尚未兑现的角色生命周期承诺，不是要求撤销普通村民死亡机制。

**修复验收**：明确主角与普通 NPC 的终态策略；以事件方式记录主角失能及后续恢复，覆盖火灾和战斗两条入口，并保证仍可接收念头和继续游戏。

### DA-08：重启后陈默又进入效用 AI，与独立 LLM 驱动并存

**实测**：真实 lifespan 第一轮启动，陈默不在 `npc_runtime.profiles`，效用层不为他产动作；第二轮启动后，两项都变为 True。测试禁用真实模型请求，但保留独立 ChenmoDriver 的装配。

**代码**：`sim/api/main.py:358` 先物化 NPC runtime，`:551` 才播种主角档案。第一次物化时主角行尚不存在，重启时已经存在；`sim/npc/runtime.py:141` 对全部 lod>0 的档案做效用决策。与此同时 ChenmoDriver 始终独立装配。

**影响**：角色控制权取决于是否重启过；运行时具备两个动作来源，可能出现自主改路、覆盖 LLM 意图。可观察的实测是「第二次启动产生主角效用动作」，具体交互表现尚未跑真模型验证。

**修复验收**：先建立稳定的角色装配规则，明确常驻 L2 的唯一控制者；如要实现 LLM 故障降级，必须显式切换控制权。首启/重启的动作来源与名单相同，禁止两个控制器同时给主角下动作。

## 已确认的简化与本轮边界

- 卖货代码明确把出售简化成手艺收入，不查库存；探针从 0 文卖一次 herb 得 6 文。购买路径目前只有扣款/独白，没有获得物品或药效闭环。这是需要产品确认的经济深度简化，不混入上述恢复错误。
- 其他 NPC 的 L2 升降格有标签与效用路径，但本轮没有追加真模型验证其 L2 规划，不标为完整实现。
- O 单在 codex 已交付 `9447d1b`，基准 main 尚未包含；不重复算成新问题。
- 本轮没有重跑全量后端、真实浏览器、付费模型或多日 soak；没有用缺失的外部地图源素材推导玩法完成度。

## 建议补漏顺序与验收门

1. **DA-01 + DA-02**：先做冷启动和真实历史读档的世界状态闭环。以 tick、位置、死亡集合、世界可比哈希、单次创世、实际分支写入为验收门。
2. **DA-03 + DA-05 + DA-06**：重建运行态投影并立即同步 HTTP 地图、寻路和 WS 快照；验收在线状态与同事件重建状态一致。
3. **DA-04 + DA-08**：修通戏内名称到目标的解析，稳定主角控制权；覆盖首启/重启、人物/货品、未知目标拒绝。
4. **DA-07**：按设计落实主角失能续玩，并保留普通 NPC 死亡。

这些是有复现材料的补漏单，不是「全部玩法已实现」的声明。涉及主树架构与跨分支协议的修改应由主树分单收编；本轮未直接改动游戏逻辑。

## 后续修复：DA-01（codex 本树，2026-10-21）

用户直接授权继续修复后，先接通冷启动恢复。已有世界读取 `is_current` 指向的分支，沿分叉游标选择完整世界检查点并消费尾部事件；实体、路径、时钟、战斗时间尺、混沌链和 PCG64 进度使用内部格式保存。检查点与非空事件批次同事务写入，不经 WS 表现快照反推。无当前指针保留诊断面且停止推进；重复创世日志拒绝启动，未删改历史。

同时隔离真实 API 测试的开发数据库，旧人工数据夹具改为合法创世与完整快照；存档包测试按实际游标验证最新快照引用。回归覆盖原有完整快照、尾部事件、当前子线、祖先截止、子线 seq=0 基线、事务回滚及行走重放。

边界：本单恢复核心世界及上述上下文，DA-02 的历史读档完成顺序、DA-03 的运行态账本等仍待独立修复。旧日志没有完整检查点时只能接续已记录时间边界，无法推断未持久化的静默时间。新检查点目前按非空批次生成，尚未做长期库容量压测。

验证：新增重启红钉先 4 failed，子线 seq=0 边界另复现 1 failed；修复后定向 41 passed、API/鉴权相关 52 passed。常规门禁明确排除两条既有缺素材用例后 **2774 passed / 131 skipped / 74 deselected**；ruff、格式检查与 pyright 通过。原两条地图用例未修，原始门禁仍不能宣称全绿。

## 后续修复：DA-02（codex 本树，2026-10-21）

生产读档改用真实物化链，在独立世界对象中展开内部检查点、恢复随机进度并对齐存档 tick；不再用末条事件 tick 代替存档时刻。`make_current=True` 仅供生产读档显式选线，默认归档分叉语义保留。世界 tick/可用哈希验证后，当前世界线、子线 seq=0 检查点与玩家当前游标同事务交接；继续推进或重启都接续该子线。

登记请求不发成功帧。恢复成功后才发 `session_state`、既有 `timescale`、真实全量快照，并丢弃旧分支本帧增量和等待中的模型决策。物化/分叉失败保留原世界；提交后地图等投影重建失败则暂停、停止模型执行，并拒绝写命令及保存，返回既有载入失败帧。所有帧形状与版本保持现有协议。

真实临时 SQLite 回归覆盖旧档后已有未来事件、安静头部、当前位置/死亡集合/时钟、子线写入与再次冷启动、玩家游标、坏 RNG、提交后投影失败、事务回滚和旧决策跨档。原地图恢复夹具改为真实存档包与分叉，取消 SQL 切线替身。主路径先 2 failed，跨档决策、失败暂停、时间尺与当前游标分别复现后修绿；定向 **79 passed**，事务复验 **43 passed**，ruff/format/pyright 与 `gen:protocol:check` 通过。

本单闭合核心世界、选线与完成回执；余额/火场/健康等运行态账本、建筑表现缓存等仍属 DA-03/DA-05 后续范围，不能据此宣称完整游戏状态全部恢复。未启用真模型或 T5 长跑。

门禁过程中补回了原有「无当前世界线」的细分错误说明，避免恢复门禁遮盖分支真源故障；分支真源、ProblemDetail、WS 鉴权与真实历史档联合复验 **55 passed**。

最终常规门禁与 DA-01 一样显式排除两条既有缺地图素材用例，得到 **2789 passed / 131 skipped / 74 deselected**（408.25s）。ruff、格式、pyright 与协议生成检查通过；两条素材失败仍未修复，不把原始全量标为全绿。

## DA-03：账本恢复清单与边界（2026-10-21，基准 b929406）

| 必须随锚点恢复的投影 | 真源与恢复方式 | 本单状态 |
|---|---|---|
| 世界核心、时钟、随机上下文 | 内部世界检查点与事件尾部，沿用 DA-01/DA-02 | 不改检查点形状 |
| 各人物余额 | 目标分支谱系的 `coin.grant` 按序重放；坏账拒绝，不造负余额 | 接入 `_drain_loads` |
| 活火格与 ID 序号 | 同一 `fold_fire` 生命周期规则；保留未熄灭格，以全部历史编号（含已熄灭火）恢复最大序号 | 接入 `_drain_loads` |
| 工地、物质/结构投影与碰撞图 | 沿用主树 P 系装配；工地与余额/活火共用目标谱系历史，地图仍按瓦片事件重建 | 保留既有接线；不代替 DA-05/06 验收 |
| 健康与战斗 HP | `npc_health` 存疾病/旧伤等属性，不能充当 `CombatLedger._hp`；存活者扣血尚无完整事件来源 | 纳入设计，保留现有清零；另单补可回放健康事实后再恢复 HP |

前置缺陷采用**每个火格一个生命周期 ID**，与 `FireRow` 的单坐标及既有逐格点火事件一致。`FireRuntime` 给新格签发 ID 时同时替换步进结果中的格，事件读取同一个格的 ID；原有重复起火/熄灭拒绝规则保留。真实 SQLite 红钉先复现三步蔓延后格/回放不符与燃尽重复熄灭整批写失败，再修复生产方，不吞掉 `FireWriteError`。

火回放包含祖先分叉点前缀，`upto_seq` 只限制本分支；不同分支的局部 seq 不能混排。读档后新火可接续最大历史编号，父线分叉后的金额、起火和序号均不进入子线。余额重建先在临时账本完成，坏账不替换已有有效账本。

恢复的是生命周期事实与活火格集合。燃料仍是纯运行态，恢复时使用现有点火预算 12，不承诺读档前剩余燃料逐位一致；没有新增持久化字段、事件种类或 WS 帧。本单只在派单指定的 `_drain_loads` 接余额/活火恢复，冷启动余额/活火装配仍未扩修；健康 HP 也未声称已恢复。

验证：前置真实落库红钉 **2 failed**（格/事件 ID 不符、重复熄灭拒写），账本读档红钉 **6 failed / 4 passed**（100→0、活火/序号清空、嵌套分叉无法付款）；修复后相关集 **101 passed / 1 deselected**。原始 `uv run pytest -m 'not bench' -q --tb=short` 实测 **2818 passed / 131 skipped / 72 deselected / 2 failed**（285.72s），两条失败仍为 `test_m4d16_territory.py::TestTownGodMap::test_deterministic_build` 与 `test_m7_town_map.py::TestTownMap::test_deterministic_build`，本树缺 `tiled-map.json`，未掩盖或扩修。ruff、格式检查与 pyright 通过；原始门禁不能标为全绿。日志 `.orca/da03-{fire-red,fire-green,ledger-red,ledger-green,focused,python-full,pyright}.log`。

## DA-04：戏内名规范化（2026-10-21，基准 a5377d8）

本轮基准已包含主树 `afdfeb9` 冷启动补修，素材也已同步；前节的「冷启动未接」和两条缺素材失败属于历史读数。

新增纯函数解析层 `sim/agent/targets.py`，使用既有 `display_name_of` 注入的名字映射，无 IO。在真实 `decide_once → parse_intent → gate.validate` 链中，唯一、存在、曼哈顿范围内的人名转换为实体 ID；成功解析才用 frozen Intent 的 `model_copy` 更新目标。未知/歧义名保留原文交给原 gate 拒绝，不把它们变成可执行目标。现有内部标识输入仍兼容，并由 gate 执行前复核。

货品通过独立 `name_index()` 精确解析，`_GOOD_INDEX` 保持 ID→Good 语义；草药/药膏/饭食/米酒均支持买卖，内部 ID 继续可用。未知或歧义货名在规划与执行两处拒绝，记录 `chenmo.trade_rejected`，不再计为已执行的静默空操作。

| gate 理由 | 本单处理 |
|---|---|
| `unknown_good` | **唯一新增的理由名**：未知/歧义货品，以及执行前货品已不在目录中 |
| `unknown_target` | 保留：幻觉名、任何活体重名（含观察者同名）和不可解析人名仍拒绝 |
| `missing_target` | 保留；买卖执行前也复核缺失目标 |
| `target_gone` / `target_out_of_range` | 保留既有执行校验；目标移动超出原执行范围或消失仍拒绝 |
| 其他既有拒绝理由 | 支持动作、空/禁词 reason、置信度、坐标边界和隐藏属性判定保留，未放宽 |

候选人物按曼哈顿距离取最近最多 12 个，仅给唯一戏内名，排除自身、已知动物及内部 ID 标签。复用 `SituationSlice.landmarks_text` 的可变面；`_REQUIREMENTS_TEXT`、`_CAUSAL_UNKNOWN_TEXT`、装配段序及身份锚不变。对白缺少展示名时用自然称呼，不把内部 ID 补进模型消息。没有增加独立 replan 机制，拒绝后沿既有决策节拍继续。

红钉：主链 **5 failed / 4 passed**，包含真实输出 `assert 0 == 1`（人名未入队）、`assert 100 < 100`（中文货名无扣款）、`assert 1 == 0`（未知货品空执行）；观察者同名另先复现 1 failed。新集 **26 passed**，驱动/gate/prompt/经济/社交/战斗相关集 **116 passed**。全量验证还发现日志代理缓存的测试隔离问题，以及扩大执行距离改动影响旧差事 E10：夹具改用真实新 logger 代理，执行 gate 的原距离策略保持兼容；曼哈顿 12 仅用于本单新增姓名解析/候选范围。日志 `.orca/da04-{red,ambiguity-red,green,focused,python-full,pyright}.log`。

服务日志装配、真实历史读档、规范化与旧差事联合复验 **63 passed**。最终原始 `uv run pytest -m 'not bench' -q --tb=short` 得到 **2857 passed / 121 skipped / 72 deselected / 0 failed**（320.57s），两条地图确定性用例未排除。ruff/格式检查（352 files）、pyright（0 errors）及 diff check 通过。最终日志 `.orca/da04-python-verified.log`；首轮全量失败输出保留在 `.orca/da04-python-full.log`。

## DA-05：建筑表现接线与历史真源前置缺陷（2026-10-21，基准 969e616）

本轮在派单指定文件中接入启动/读档账本重建，复用 `maintenance.structures` 的同一份快照；落库后的 completed/collapsed/removed 分别更新 built/rubble/删除，并由既有增量协议发送 remove。客户端 full_snapshot 清空后替换建筑全集，state_delta 保持增量；WorldScene 用包含 token、相位、格位的内容签名判断重绘。测试复用既有 Scene 加载适配，执行真实 `syncStructures` 并断言 clear、fillStyle、fillRect 调用，没有替换绘图方法。

相位映射：`active→built`，`collapsing→collapsing`，`rubble→rubble`；`planned/building` 不进入完工建筑层，施工仍由既有工地表现负责，避免改变 E7 契约。`structure.collapsed` 已是坍塌终态，必须映射 rubble。协议保持 1.11，未改 StructureDelta 或 WorldCheckpoint。

初始红钉：服务端 **9 failed / 2 passed**，客户端 **5 failed / 4 passed**。接线后相关服务端 **27 passed / 3 failed**；客户端定向 **13 passed**、全量 **149 passed**，TypeScript、ruff/格式检查与 pyright 通过。**DA-05 尚未完成，未提交**：三个剩余失败暴露了边界外的历史分叉真源污染，不能称为全绿或通过删除测试结案。

真实 SQLite 复现：先在 main 的 seq=59 保存，再建 future、保存后加载旧档。新子线的有界事件谱系中 **没有任何 structure 事件**，但 `NpcStore(child).materialize_structures()` 仍返回 future。原始失败为 `AssertionError: branch structure source=['future'], bounded structure events=[]`；命令 `uv run pytest sim/tests/test_structure_presentation_restore.py::test_load_clears_stale_structure_ledger -q --tb=short`，日志 `.orca/da05-source-blocker.log`。

根因在 `sim/core/persistence/fork.py`：历史 anchor 路径只对 fires/relationships 等特殊处理，structures 仍通过 `_clone_bounded` 克隆父分支 head 行。该路径不能套用「分叉点就是父线头部」的 P1 前提。须先独立修复历史 structures 投影按包游标生成子线，再验收 DA-05；本轮未越界修改 fork，也未用禁用的 replay 或过滤维护账本掩盖问题。

原始全量 `uv run pytest -m 'not bench' -q --tb=short`：**2865 passed / 121 skipped / 72 deselected / 3 failed**（300.50s），没有排除任何用例。失败仅为新集的旧档清理、旧档恢复、子线重启三条；原有基准用例未失败。日志 `.orca/da05-python-full.log`。门禁仍红，不提交；工作区保留实现和回归测试，等待前置修复或 talking 明确扩界。

## DA-05P：按历史游标生成子线建筑真源（2026-10-22）

主树复验确认前置缺陷，并在 talking 明确允许修改 `fork.py` 的 structures 克隆路径。新增历史 anchor 特判：在原分叉事务内，从包的 branch/seq 沿祖先分叉点读取有界结构事件，各层按本地 seq 排序、祖先在先；复用 `fold_structure_snapshot` 生成子线结构行。没有复制父 head 的结构投影，也没有将不同分支的 seq 混排。循环、缺分支或缺祖先截止点会拒绝并回滚；head 分叉沿用原克隆路径。

写入保留格位、材料、承重、支撑关系、归属、建造者和完工时间；坍塌保留 rubble，移除不留结构行。没有更改物化包、blob/schema、WorldCheckpoint 或 `materialize_structures_replay` 接口，main 仍从维护快照重建 WS 表现，DA-05 的相位映射与客户端实现保留。

先复跑指定三钉，得到 **3 failed**（`.orca/da05p-red.log`）；另补未来坍塌/拆除回退和嵌套分叉，先得到 **3 failed**（`.orca/da05p-boundaries-red.log`）。这些用例故意在同 tick 保存不同 seq，验证不能用时间或父 head 近似游标。修复后建筑/读档/物化编排相关集 **149 passed**（`.orca/da05p-focused.log`），客户端全量 **149 passed / 27 files**、TypeScript、ruff/格式检查与 pyright 通过。最终全量与提交见 talking 完成回执。

最终原始 `uv run pytest -m 'not bench' -q --tb=short`：**2871 passed / 121 skipped / 72 deselected / 0 failed**（330.00s），无额外排除。ruff check、ruff format（353 files）、pyright（0 errors）、客户端 tsc 及 vitest（149 passed）均通过；`.orca/da05p-python-full.log` 保留全量输出。本单与前置缺陷已闭合；DA-06/07/08 不在本轮范围，尚未修复。

## DA-06：结构终态立即更新在线碰撞（2026-10-22）

`on_flush` 在事件与检查点成功落库后，才增量应用含结构终态批次里的 `tile_changed`。新地图同时交给 app、BuildRuntime 和 Pathfinder，并清空路径缓存；普通 flush 不重建或替换地图。P-6 的瓦片事件派生仍在 maintenance.observe 之前，且只派生一次。

真实 lifespan 红钉先复现坍塌、拆除后在线格仍不可走：**2 failed / 1 passed**，原文 `AssertionError: persisted tile restoration must update live collision`。修复后建筑/历史加载/工地相关集 **37 passed**；测试同时验证三处引用、真实寻路、缓存清理、在线图与事件重建图的逐格一致，以及无结构终态时保持地图实例。日志 `.orca/da06-{red,focused,python-full,pyright,client}.log`；最终门禁见 talking 回执。

最终原始全量 **2874 passed / 121 skipped / 72 deselected / 0 failed**（325.32s），ruff/格式检查（354 files）、pyright（0 errors）、客户端 tsc 与 vitest（149 passed）均通过；无额外排除。DA-06 已闭合，DA-07/08 继续按本波派单处理。

## DA-08：主角控制权由装配方显式声明（2026-10-22）

`assemble_runtime` 接受不可变的外控实体名单，在构造效用矩阵与隐藏档之前排除这些实体；生产装配声明陈默由 `ChenmoDriver` 拥有。规则与人物档案是否已存在无关，不再依赖首启时主角尚未写库的偶然顺序。通用 NPC 装配的默认行为不变，普通村民继续走效用层；没有增加自动 LLM 故障降级或第二控制者。

用同一隔离库连续启动两次真实 lifespan，覆盖首启与重启：红钉 **1 failed**，原文 `AssertionError: controller ownership must not depend on startup timing`、`Extra items in the right set: 'chenmo'`。修复后相关装配/重启/历史读取/主角驱动集 **47 passed**，测试同时检查两轮名册一致、主角无效用动作、普通 NPC 确实有动作、专用驱动存在及效用矩阵人数一致。日志 `.orca/da08-{red,focused,python-full,pyright,client}.log`；最终门禁见 talking 回执。

最终原始全量 **2875 passed / 121 skipped / 72 deselected / 0 failed**（325.52s），ruff/格式检查（355 files）、pyright（0 errors）、客户端 tsc 与 vitest（149 passed）均通过，无额外排除。DA-08 已闭合；DA-07 的新失能/恢复事件与接线范围已提策略申请，依派单要求等待主树核准，尚未实现。

## DA-07：主角失能、跳时与恢复（2026-10-23）

用户授权本树核准已提交的策略并完成收尾。生产火灾与战斗致命结算对主角产生 `agent.incapacitated`，保留实体并清空路径；普通 NPC 继续产生 `npc.death` 并删除，既有死亡事件的历史回放语义保留。失能与恢复各有独立 payload 模型，均 `extra=forbid`，并登记在 EventKind、默认总线与 PAYLOAD_MODELS 中。

失能事件记录绝对恢复时刻（一游戏小时后）；期限随内部世界状态保存，重启/历史读档不会重新计时。健康态序列化省略新期限字段，旧状态指纹保持一致。移动与陈默决策/执行在失能期间受抑制，最近收到的念头保留；失能前在途的 LLM 决策由世界修订号作废，醒来后重新决策。恢复选择最近的可走、未燃烧格，仅恢复主角 HP，不清除其他 NPC 的伤势。

真实世界驱动复用既有快进预算推进模拟，普通 NPC 与世界事件继续演进；暂停仍由现有时钟控制。醒来时发既有 full_snapshot 同步时钟与位置，并产生戏内心声。自动恢复与玩家快进共享预算，分段重新读取时间尺，避免退出战斗后超额推进。新内部 kind 不增加 WS 帧或出站字段，协议仍为 1.11；`gen:protocol:check` 通过。

初始红钉 **3 failed / 1 passed**：火灾产生主角死亡、战斗删除主角、真实运行入口没有可恢复实体。核心扩展集 **10 passed**，火灾/战斗/死亡/重启/读档相关集 **88 passed / 2 skipped**。额外预算红钉原文 `assert 241 <= 240`；修复后包含新集的 WS 相关集 **76 passed**。首轮全量 **2884 passed / 1 failed**，唯一失败是旧 EntityState 三字段封闭白名单：现显式登记失能期限，保留字段集封闭，并补失能实体仍计入人口的断言，相关 **14 passed**。没有通过改夹具、删除或跳过测试掩盖失败。最终全量数字与提交见 talking 回执；日志 `.orca/da07-*.log`。

最终原始 `uv run pytest -m 'not bench' -q --tb=short`：**2887 passed / 121 skipped / 72 deselected / 0 failed**（290.58s），无额外排除。ruff check、ruff format（356 files）、pyright（0 errors）、客户端 tsc、vitest（149 passed）与 `gen:protocol:check` 全部通过。最终日志 `.orca/da07-python-verified.log`；本波 DA-06/07/08 已分别完成并本地提交，等待主树收编。
