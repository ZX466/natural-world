# 临河镇（linhe-town）

> 一个 2D 像素模拟世界。主角是一个 LLM 驱动、坚信自己是人的 Agent。
> 玩家不控制它，只能让某些念头在它脑中冒出来。
> 世界不可预测、不可控、不可预定。

[![tests](https://img.shields.io/badge/tests-2416%20passed-green)]() [![ruff](https://img.shields.io/badge/ruff-clean-green)]() [![pyright](https://img.shields.io/badge/pyright-0%20errors-green)]() [![protocol](https://img.shields.io/badge/protocol-1.2-blue)]()

**设计内核**：玩家从「控制一个角色」变成「旁观一个真实的人做选择，并偶尔在他耳边说一句话」。主角是陈默——小镇药铺的学徒，有完整持久的人格、记忆与关系；玩家是「直觉」，不是指挥官。

完整设计基线见 [DESIGN.md](DESIGN.md)（v2.1 冻结）；本 README 是**运行与开发入口**，设计细节以 DESIGN 与 `docs/` 为准。

---

## 快速开始

```bash
# 环境要求：Python 3.12+、uv、Node.js（前端）、SQLite
uv sync                      # 安装依赖（uv.lock 钉版本）

# 启动模拟世界（FastAPI + WS 网关，默认 32×32 地图）
uv run uvicorn sim.api.main:app --reload

# 跑测试（T1/T2 不变量与回放确定性；无 LLM，秒级）
uv run pytest -q             # 全量 not-bench（每提交 CI 同口径）
uv run pytest -q -m bench    # 性能基准（nightly 同口径）

# 静态检查
uv run ruff check .
uv run pyright

# 前端（client/）
cd client && npm ci && npm run test
```

真模型探针（T4，可选）：设 `T4_RUN=1` + `T4_MODEL_API_KEY`（运行时环境变量，**永不落盘**）后 `uv run pytest -m t4`。当前锁定 `Deepseek-v4-flash` @ `https://chatapi.weixin.qq.com/openai/v1`。

---

## 这是什么

一个**确定性 tick 内核**驱动的单机小镇模拟：50 个 NPC（1 个 LLM 驱动的 L2 主角 + 效用驱动的 L1 居民 + 统计档 L0），事件溯源（C4 唯一写路径）、快照+事件窗口重放（T2 逐位一致）、读档=分叉。

- **世界真相**只进事件日志——NPC 记忆、关系、物质、结构、火场、死亡全部是事件的投影；
- **确定性**：同 seed + 同事件序列 ⇒ 状态逐位一致（`state_hash` 钉死）；
- **玩家边界**：指令 UI + 念头注入；战斗是决策点制（自动慢镜），不是双摇杆；
- **出戏铁律**：内部数值（tick/seq/分支/权力/随机流状态）零出现在协议与叙事面。

## 架构一览

```
sim/
├── core/        # 内核：TickLoop（固定执行序）、EventBus（C4 唯一写路径）、
│   │            # WorldState（frozen）、RNG 注册表+熵注入、事件溯源持久化
│   └── persistence/  # SQLAlchemy async + Alembic（迁移链 0001→0014）
│                  # store/event_validation/npc_store/fire_store/power_store/
│                  # fork（读档=分叉）/anchor_package（物化包）
├── world/       # 世界派生：weather（风场）、ecology（生态相位）、fauna（动物节律）、
│                # fire（火灾蔓延，O(格数)）、fog（区块迷雾）、matter、pathfinding、structure
├── npc/         # NPC：needs→utility（向量化 L1 决策）、runtime（50 NPC 装配）、
│                # 记忆/知识/关系（证据链）、norms、power（权力→utility 偏置列）
├── agent/       # Agent 语义：language（识字/行话降质）、will（意愿）、impulse（念头闸门）
├── perception/  # 感知：视觉/听觉/嗅觉（Eulerian 平流）/内感受 → PerceptionFrame
├── api/         # FastAPI 网关：REST anchors/settings + WS 网关（出站咽喉闸：两层禁键剥除）
├── llm/         # LLM 客户端（OpenAI 协议）+ prompt 装配（messages[0] 前缀缓存契约）
└── tests/       # T1-T5 分级 + bench（pytest-benchmark）+ golden 场景
client/          # 前端（渲染 WS 快照/增量；outbound 协议类型由 gen-protocol 生成）
docs/            # 设计文档（arch/api/data/perf/security/config 六域）
tools/           # gen-protocol.ts（OpenAPI → protocol.ts 生成管线）
```

事件流（节选）：`world.create` / `move` / `npc.act` / `npc.monologue` / `matter.*` / `material.moved`（守恒账本）/ `structure.*`（施工/坍塌）/ `fire.ignited|extinguished` / `npc.death`（对称删除）/ `entropy_inject` / `ecology.shift` / `fauna.tick` / `speech.shift` / `fog.reveal` — 全部 payload `extra="forbid"` 封闭、零归因键。

## 里程碑状态

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 确定性内核 + 事件溯源 + 存档 | ✅ 收官 |
| M1 | 感知通道（视/听/嗅/内感受）+ 战斗尺 | ✅ 收官 |
| M2 | NPC 认知（需求/效用/意愿/嗅觉风场）| ✅ 收官 |
| M3 | 证据链（记忆/知识/关系传播）+ 区块迷雾 + 生态底座 | ✅ 收官 |
| M4 | 建造/坍塌 + 意愿系统 + T5 golden 场景 | ✅ 收官 |
| M5 | 读档=分叉（anchors）+ 权力机制数据面 + 火灾数据面 + 性能治理 | ✅ 收官 |
| M6 | 权力→决策传导 + 火灾机制面 + 死亡对称删除 + 内容面（生态/动物/语言阶层/迷雾事件化）+ 定标（POWER 翻硬） | ✅ 收官（2026-10-05 宣告） |

**当前门禁**：2416 passed / 122 skipped / 0 failed · ruff clean · pyright 0 · `gen-protocol --check` EXIT 0 · 协议版本 1.2。

122 个 skip 全部为设计态：T4 真模型探针 53（三把锁默认关，key 经运行时环境变量）、T3 live-fire 55、T5 golden 11、其余为降频自检门与环境门——无失败、无悬空。

## 文档地图

| 域 | 入口 |
|---|---|
| 设计基线 | `DESIGN.md`（§0 修订摘要 / §16 测试分级 / §17 里程碑 / §18 可砍序） |
| 架构 | `docs/arch/`（m0-core 内核 / m2-npc-cognition / m3-evidence-chain / m4-plan / m5-plan / m5-rulings 裁决 1–43） |
| API | `docs/api/`（anchors-api / ws-protocol / versioning / openapi 生成口径） |
| 数据 | `docs/data/`（schema（§21 事件投影 / §24 死亡对称删除）/ migration / 事件溯源） |
| 性能 | `docs/perf/`（budget 红线 / bench-plan / m5-m6 各预算案与定标记录） |
| 安规 | `docs/security/`（m1-checklist / m5/m6 各威胁模型与收官预审） |
| 协作 | `.orca/workflow.txt` + `.orca/agent-registry.md` + `.orca/memory.md`（多 Agent 分域协作契约） |

## 开发约定

- **包管理一律 [uv](https://docs.astral.sh/uv/)**（不直接用 pip）；Windows 不装 uvloop（硬约束）；
- **事件是唯一写路径**（C4）：任何状态变更必须产事件经 `EventBus.apply`，投影与重放共用同一 fold（禁第二套语义）；
- **新 kind 必须同 commit 登记 payload 模型**（`PAYLOAD_MODELS` 闭合集，红线 A）；
- **确定性红线（C5）**：同 seed+同事件序列 ⇒ 逐位一致；随机只经 `RngRegistry`+熵注入（材料随事件落日志）；
- **测试分级 T1-T5**（DESIGN §16）：T1 不变量 / T2 回放 / T3 闸门对抗 / T4 真模型探针（nightly）/ T5 golden；性能走 `-m bench`（nightly）；
- **key 纪律**：API key 只经运行时环境变量（Fernet 加密落库的 profile 除外），永不写进文件或提交；
- **提交**：Conventional Commits（`feat|fix|docs|test|chore|perf|ci`）。

## License

未定（私有项目；DESIGN.md 为冻结基线，新想法走「MVP 后清单」不回写基线）。
