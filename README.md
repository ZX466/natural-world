# 临河镇（linhe-town）

> 一个 2D 像素模拟世界。主角是 LLM 驱动、坚信自己是人的 Agent——小镇药铺学徒陈默，有持久的人格、记忆与关系。
> 玩家不控制他，只是他的「直觉」：偶尔让某个念头在他脑中冒出来。
> 世界不可预测、不可控、不可预定。

[![tests](https://img.shields.io/badge/tests-2752%20passed-green)]() [![ruff](https://img.shields.io/badge/ruff-clean-green)]() [![pyright](https://img.shields.io/badge/pyright-0%20new%20errors-green)]() [![protocol](https://img.shields.io/badge/protocol-1.11-blue)]()

设计基线见 [DESIGN.md](DESIGN.md)（v2.1 冻结）；本 README 是**运行与开发入口**，设计细节以 DESIGN 与 `docs/` 为准。

---

## 快速开始

### 环境要求

| 工具 | 版本 | 用途 | 安装 |
|---|---|---|---|
| [Python](https://www.python.org/) | 3.12+ | sim 后端 | 官网安装包或 `winget install Python.Python.3.12` |
| [uv](https://docs.astral.sh/uv/) | 最新 | Python 包管理（**不用 pip**） | `winget install astral-sh.uv` 或官网脚本 |
| [Node.js](https://nodejs.org/) | ≥24 | 前端构建 | 官网 LTS 安装包或 `winget install OpenJS.NodeJS.LTS` |

SQLite 无需单独安装（Python 内置；开发库 `world.db` 首次启动自动创建）。

### 第 1 步：安装依赖（首次 / 拉取后）

```powershell
# 仓库根目录下执行（E:\zxdevelop\project7）
uv sync                # 后端：按 uv.lock 钉定版本装到 .venv/（约 1-2 分钟）
cd client
npm ci                 # 前端：按 package-lock.json 装到 node_modules/（约 1-3 分钟）
cd ..
```

### 第 2 步：启动后端（终端 1）

```powershell
# 仓库根目录
uv run uvicorn sim.api.main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即成功。此终端保持开启，`Ctrl+C` 停止。

- 启动即自动建世界（创世事件入库，开发库 `world.db` 自动创建）；
- `--reload`：改 Python 代码自动重启（生产/压测去掉）；
- 交互式 API 文档：浏览器开 `http://127.0.0.1:8000/docs`。

### 第 3 步：启动前端（终端 2，另开一个）

```powershell
cd client
npm run dev
```

看到 `Local: http://localhost:5173/` 后浏览器打开该地址即进入游戏界面。此终端保持开启。

### 验证跑通

- **顶栏**：显示「第 N 天 HH:MM」戏内时钟，绿色圆点 = 已连上后端；
  - 若约 2.5 秒后仍未变绿：后端没起来（回第 2 步看终端报错）；
  - 橙色点 = 连接中/重连中；红点 = 已断开；
- **世界画面**：地图铺装 + 主角可见。点击可通行格，主角走过去；
- **倍速**：顶栏 `1x / 4x / 16x` 切换时间流速；`暂停` 冻结世界；
- **直连验证**（可选）：`http://127.0.0.1:8000/api/health` 返回 JSON 即后端正常。

> 端口约定：后端 `8000`，前端 dev `5173`（Vite 已配置 `/api` 代理到后端，无需 CORS 处理；
> WS 由前端直连 `ws://127.0.0.1:8000/ws`）。两端口被占用时先释放或改
> `client/vite.config.ts` / uvicorn `--port`。

### 无后端演示模式

只跑了前端、没起后端时，前端约 2.5 秒后自动进入 **mock 模式**（绿点亮起但实际无连接）：
静态网格地图 + 占位主角来回走 + 时钟自走。用于纯前端开发/演示；要玩真实世界必须起后端。

**画面判别**：色块网格 + 矩形人 = mock（或后端未加载真实图）；瓦片小镇（草地/路/水塘/房屋）+ 像素小人 = 真实世界（96×96 临河镇图——D16 扩图五片区，创世 51 实体：陈默 + 50 名村民）。

### 常用命令（开发）

```powershell
uv run pytest -q            # 全量测试（not-bench，每提交 CI 同口径，秒级）
uv run pytest -q -m bench   # 性能基准（nightly 同口径）
uv run ruff check .         # Python lint
uv run pyright              # Python 类型检查
uv run alembic upgrade head # 数据库迁移（开发库自动建表，一般无需手动跑）

cd client
npm run test                # 前端单测（vitest）
npm run typecheck           # 前端类型检查
npm run lint                # 前端 lint
npm run gen:protocol:check  # 协议生成物漂移检查（改协议后必跑）
```

### 真模型探针（T4，可选）

让主角接入真实 LLM（当前锁定 `Deepseek-v4-flash` @ `https://chatapi.weixin.qq.com/openai/v1`）：

```powershell
$env:T4_RUN = "1"
$env:T4_MODEL_API_KEY = "<你的key>"   # 只走运行时环境变量，永不落盘
uv run pytest -m t4
```

### 常见问题

| 症状 | 原因与处理 |
|---|---|
| `uv: command not found` / 无法识别 | uv 没装或不在 PATH——回环境要求重装，重开终端 |
| `npm ci` 报 Node 版本不符 | Node < 24，升级 LTS 版本 |
| 前端一直橙点/红点，画面只有色块 | 后端未启动或端口被占——看终端 1 报错；`netstat -ano | findstr :8000` 查占用 |
| 时钟不走、画面是默认网格 | mock 模式（无后端）——起后端后刷新页面 |
| 端口 5173/8000 被占用 | 释放端口，或改 `client/vite.config.ts` 的 `server.port` / uvicorn 加 `--port 8001`（改后同步 `vite.config.ts` 代理目标） |

---

## 这是什么

**确定性 tick 内核**驱动的单机小镇模拟：50 个 NPC（1 个 LLM 驱动的 L2 主角 + 效用驱动的 L1 居民 + 统计档 L0），事件溯源（C4 唯一写路径）、快照+事件窗口重放（T2 逐位一致）、读档=分叉。

- **世界真相**只进事件日志——记忆、关系、物质、结构、火场、死亡全部是事件的投影；
- **确定性**：同 seed + 同事件序列 ⇒ 状态逐位一致（`state_hash` 钉死）；
- **玩家边界**：指令 UI + 念头注入；战斗是决策点制（自动慢镜），不是双摇杆；
- **出戏铁律**：内部数值（tick/seq/分支/权力/随机流状态）零出现在协议与叙事面。

## 架构一览

```
sim/
├── core/        # 内核：TickLoop（固定执行序）、EventBus（C4 唯一写路径）、
│   │            # WorldState（frozen）、RNG 注册表+熵注入、事件溯源持久化
│   └── persistence/  # SQLAlchemy async + Alembic（迁移链 0001→0014）
├── world/       # 世界派生：weather / ecology / fauna / fire / fog / matter / pathfinding / structure
├── npc/         # NPC：needs→utility（向量化 L1 决策）、记忆/知识/关系（证据链）、norms、power
├── agent/       # Agent 语义：language（识字/行话降质）、will（意愿）、impulse（念头闸门）
├── perception/  # 感知：视觉/听觉/嗅觉（Eulerian 平流）/内感受 → PerceptionFrame
├── api/         # FastAPI 网关：REST anchors/settings + WS 网关（出站咽喉闸：两层禁键剥除）
├── llm/         # LLM 客户端（OpenAI 协议）+ prompt 装配（messages[0] 前缀缓存契约）
└── tests/       # T1-T5 分级 + bench（pytest-benchmark）+ golden 场景
client/          # 前端（Phaser 画世界 + React 画 UI；outbound 协议类型由 gen-protocol 生成）
docs/            # 设计文档（arch/api/data/perf/security/config 六域）
tools/           # gen-protocol.ts（OpenAPI → protocol.ts 生成管线）
```

事件是唯一写路径：`world.create` / `move` / `npc.act` / `npc.monologue` / `matter.*` / `structure.*` / `fire.ignited|extinguished` / `npc.death`（对称删除）/ `entropy_inject` / `ecology.shift` / `fauna.tick` / `speech.shift` / `fog.reveal` 等——payload 全部 `extra="forbid"` 封闭、零归因键。

## 里程碑状态

M0–M6 六个里程碑**全部收官**（M6 于 2026-10-05 宣告，四道门 G1–G4 全 ✅）：

| 里程碑 | 内容 |
|---|---|
| M0 | 确定性内核 + 事件溯源 + 存档 |
| M1 | 感知通道（视/听/嗅/内感受）+ 战斗尺 |
| M2 | NPC 认知（需求/效用/意愿/嗅觉风场） |
| M3 | 证据链（记忆/知识/关系传播）+ 区块迷雾 + 生态底座 |
| M4 | 建造/坍塌 + 意愿系统 + T5 golden 场景 |
| M5 | 读档=分叉（anchors）+ 权力机制数据面 + 火灾数据面 + 性能治理 |
| M6 | 权力→决策传导 + 火灾机制面 + 死亡对称删除 + 内容面 + 定标（POWER 翻硬） |

**当前门禁**（2026-10-21 实测，`-m "not bench"`）：`exit 0` · ruff clean · pyright 0 · `gen-protocol --check` EXIT 0 · 协议版本 **1.11**。
计时类护栏已移入 `bench` 标记（`5b4ce50`），常规门禁不再受本机降频影响。
skip 全部为设计态（T4 真模型探针、T3 live-fire、T5 golden、降频自检门与环境门）。

## 实现程度速查（2026-10-20 复检）

> 口径：**逐项跑代码/查调用面亲测**，不采信文档自述。详细缺口与派单见 `.orca/memory.md`。

**已完成、可玩**：核心 tick 循环与事件溯源、50 村民 + 3 只动物 + 主角的同屏世界、LLM 驱动的心声/计划/对话、
感知→记忆→知识→关系传播、建造与坍塌、火灾、读档=分叉（anchors）、点击移动、暂停/1x/4x/16x、
96×96 瓦片地图与昼夜色罩、头顶气泡、存档面板、设置面板。

**已知未完成**（均已登记，按影响排序）：

| 缺口 | 影响 | 状态 |
|---|---|---|
| ~~`timescale` / `combat_event` 幽灵帧~~ | ~~战斗时间尺自动切换玩家不可见~~ | **已修**（`39d55b8`，`ws.py:1412/1424` 实发） |
| `tile_map` 读档不重建 | 旧分支完工建筑的碰撞残留到新分支；服务端寻路绕墙、前端 HTTP 图无墙 → **表现与逻辑不一致（看不见的墙）** | **已修**（`4a5dfa3`，启动+读档两处 `rebuild_tile_map`） |
| `build_runtime` 读档不清零 | 旧分支在建工地跨分支继续推进，发旧 `structure_id` 的事件 | **已修**（`reset()` + 从本分支事件流 `restore_from_events`） |
| `fire_runtime` 读档不清零 | 旧分支的火烧到新分支；`fire_seq` 跨分支污染 | **已修**（`reset()`，且更正了「fork 层已处理」的错误注释） |
| `derive_tile_events` 零生产调用 | 建筑坍塌/拆除后格子**永久为墙**——事件流里没有恢复可走的事件 | **已修**（`on_flush` 在 `maintenance.observe` 前补发逐格还原） |
| 心声提交**成功**无文字反馈 | 只有输入条边色一闪；玩家不确定「收到没有」，断线时更无声 | **未修**（O 单） |
| `perception` 帧不出站 | **非缺口**：设计明示只进 Agent 侧（`ws-protocol.md:65`） | 已裁定 |
| 计时类测试混在常规门禁 | 本机降频时 2 条假红，掩盖真实回归 | 已修（`5b4ce50`） |

**判据边界**：`docs/api/ws-protocol.md` 里的豁免登记必须逐条读——有 schema 不代表欠接线。

---

## M7 渲染面（2026-10-06 收口）

画面从占位色块升级为像素小镇：96×96 临河镇瓦片地图（D16 扩图：面积 ×4、五片区定籍领地）（CC0 素材，`sim/content/` 管线：`build_palette.py` 调色板 → `build_town.py` 确定性建图）、主角四向行走动画、3 名村民、戏内时钟权威帧（服务端供数+客户端平滑推进）、昼夜四相位色罩。设计见 `docs/arch/m7-render-art.md`。

## 玩法面接线（批次 A，2026-10-06）

玩家第一次有了「说话」的入口，NPC 第一次有了「心」。

- **念头注入条**（画面底部）：往陈默心里放一个念头（≤64 字），服务端经念头闸门回
  `impulse_feedback`——cue 四态（接受/迟疑/抱怨/抵触）驱动输入条边色一闪，反应独白进「心之声」面板；
- **心之声面板**（右侧）：陈默的独白流（心想/自语/打算三形态，环形缓冲最近 20 条）；
- **计划看板**（右侧）：NPC 计划文本（`state_delta.plan`），有则展开无则收起。
协议零新增（消费既有 monologue/impulse_feedback/error 帧）；纯前端施工。

## 镇子活了（批次 B，2026-10-06）

50 名村民进镇：M2 认知装配线（`NpcRuntime`）首次接入实况世界，镇上现在有
51 个实体（陈默 + 50 村民）各自走动。

- **决策节拍**：每 10 tick（1/6 游戏秒）一轮 L1 效用决策（M0 预留的定时任务
  挂载点兑现），决策记录走 NPC_ACT 事件（no-op handler，重放安全）；
- **全动作族位移面**：吃饭去食摊、休息回家、干活去农田、聊天走向对方、
  闲逛哈希散布——镇子活性不依赖 wander 胜出；
- **确定性播种**：50 村民名册（`sim/content/villagers.py`，中文名单+OCEAN
  确定性散布）幂等落库；出生位环形散布全可走；
- **世界真相不破**：WorldState 仍只由事件 fold（state_hash 逐位一致）；NPC
  需求/决策是 runtime 内存态，执行面只在实况侧把决策翻译成事件。

## 陈默活了（批次 C，2026-10-06）

LLM 接进决策循环：主角陈默从「被点击驱动的精灵」变成「有自己打算的人」。

- **决策循环**：`sim/agent/driver.py`——拼 prompt（身份锚前缀缓存）→ LLM →
  严格解析 Intent → 意图闸门两道校验 → 移动 + 第一人称独白事件。自主节拍
  默认 60s 一轮（`CHENMO_DECIDE_SECONDS` 可调，下限 5s），收到玩家念头时
  立即加跑一轮；
- **念头有了回应**：注入条发出的念头经念头闸门后直通陈默的决策上下文，
  他的反应（为什么想去、想做什么）几秒后出现在「心之声」面板；
- **降级面**：无 active profile / 超时 / 解析失败 / 闸门拒绝 → 本轮跳过，
  世界照常运转；LLM 永不直接改世界（C1：闸门纯读校验，事件唯一写路径）；
- **配置**：设置页配 LLM profile（Fernet 加密落库，key 永不回显）。
  主密钥三级引导（D13）：`LZ_MASTER_KEY` 环境变量 > `~/.linhe/master.key`
  文件 > 自动生成并持久化——**开箱即用无需预配置**；显式配 env 或删
  `~/.linhe/master.key` 可重新引导。设置页另有「拉取模型」（从 base_url
  拉模型清单变下拉）与「测试连接」（max_tokens=1 极小请求测连通）。

## 接入收官（批次 D，2026-10-06）

M1-M6 机制存货接进实况世界（D1-D7）：

- **D1 行走节拍**：60 格/秒的瞬移修复为 4 格/秒（15 tick/格 + 实体相位散布）；
- **D2 NPC 开口**：村民意愿独白（bubble 广播，300 tick 节流）进「心之声」；
- **D3 生理闭环**：eat 治饿 / rest 恢复精力——到站才回写（吃了才算吃）；
- **D4 存档/读档 UI**：面板存档、读档=分叉（叙事化告知 + 快照重同步）；
- **D5 火灾+死亡**：凌晨确定性起火（约 3 游戏日一场）→ 蔓延 → 火中人亡；
- **D6 感知进决策**：陈默的 prompt 带上他此刻看见/听见/闻到的（感知帧
  → 叙事投影），独白开始有处境质地；
- **D7 天气视觉**：晴/阴/雨日级天气（确定性抽签），雨层渲染 + 光照联动；
  音效留待素材工程。

全部接线遵守既有红线：状态变更走事件（no-op handler 记录面）、确定性
哈希代替 RNG（无熵流依赖）、执行面只在实况侧（重放逐位一致不破）。

## 玩法面接线（批次 E，2026-10-09）

世界第一次有了「动词」：陈默能说、能买、能盖、能动手。

- **E1 对话**：talk_to 走向目标开口（`npc.chat` 事件，模板台词池 + LLM 注入缝）；
  村民 request_chat 到站互聊（冷却散布防齐射）——对话第一次成为可观察行为
  （`npc.chat` 事件面；气泡渲染随下一批次）；
- **E2 记忆与关系**：聊天落 ChatLedger（进程内好感漂移 + 记忆环形缓冲，
  禁第二 SQL 驱动）；陈默 prompt [记忆] 段双源（检索 + 当日对话）；有旧闻的
  村民会学舌（retell bubble 转述**开口前**记忆 + trust 漂移）——流言成立；
- **E3 经济**：`coin.grant` 事件 + CoinLedger 余额（账单即真相）；三件货价目
  （±20% 确定性浮动）；陈默 buy/sell 执行面（买不起=结构化拒绝+叙事）；
  work 到站计酬（冷却防刷）——谋生闭环成立；
- **E4 建造**：build 扣工料（余额不足不开工）→ `structure.started` → 每日
  checkpoint → completed → TILE_CHANGED 占格 → 寻路缓存失效——§14 施工
  推进第一次进实况（含既有 STRUCTURE_*/TILE_CHANGED handler 注册收口）；
- **E5 非理性**：陈默检索挂回确认偏误/情绪一致性 scorers（§8 偏差表首次
  生效于实况决策）；
- **E6 战斗最小面**：attack 确定性结算（25% miss / 55% hit / 20% crit）→
  `npc.death`（既有 kind，零新增）→ 呼救 bubble；命中自动切战斗时间尺
  （§9 `combat.scale_change` 首次生产触发，60 tick 窗口过期自动退出）；
- **协议 1.7**：structures 增量投影（M 面预留 StructureDelta 首次启用；
  additive——旧客户端安全忽略）；前端完工建筑占格重绘。
- **协议 1.8 / 1.9**：M7 地面层与戏内时钟权威帧；生态/动物纯派生投影
  （动物复用 `actors[]`、零新增 canonical 实体）；build 七动作白名单与
  L1/L2 到站翻译；`structure.*` 快照全集。

## 文档地图

| 域 | 入口 |
|---|---|
| 设计基线 | `DESIGN.md`（§16 测试分级 / §17 里程碑 / §18 可砍序） |
| 架构 | `docs/arch/`（内核 / NPC 认知 / 证据链 / 各里程碑计划与裁决） |
| API / 数据 | `docs/api/`（anchors、ws-protocol、versioning）、`docs/data/`（schema、migration、事件溯源） |
| 性能 / 安规 | `docs/perf/`（预算红线与定标记录）、`docs/security/`（威胁模型与收官预审） |
| 协作 | `.orca/`（workflow.txt + agent-registry.md + memory.md，多 Agent 分域协作契约） |

## 开发约定

- **包管理一律 [uv](https://docs.astral.sh/uv/)**（不直接用 pip）；Windows 不装 uvloop；
- **事件是唯一写路径**（C4）：任何状态变更必须产事件经 `EventBus.apply`，投影与重放共用同一 fold；
- **新 kind 必须同 commit 登记 payload 模型**（`PAYLOAD_MODELS` 闭合集，红线 A）；
- **确定性红线（C5）**：同 seed+同事件序列 ⇒ 逐位一致；随机只经 `RngRegistry`+熵注入；
- **测试分级 T1-T5**（DESIGN §16）；性能走 `-m bench`；
- **key 纪律**：API key 只经运行时环境变量，永不写进文件或提交；
- **提交**：Conventional Commits（`feat|fix|docs|test|chore|perf|ci`）。

## License

未定（私有项目）。
