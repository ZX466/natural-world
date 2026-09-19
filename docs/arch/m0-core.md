# M0 内核设计 — 确定性 tick 核心（TASK-C01）

> 依据 DESIGN.md（v2.1 冻结基线）§2 约束、§3 架构、§5 目录、§6 契约、§9 战斗时间尺、§10 时间锁定、§11 混合熵、§19 禁止事项。
> 范围：M0 的 `sim/core/`（clock / rng / entropy / events / persistence）+ `sim/world/`（map / pathfinding）数据模型与接口契约。
> 不涉及：LLM（M1）、感知传播（M1）、数据库 schema 细节（opencode TASK-001）、WS 协议细节（kilo TASK-001）——本文只定内核接口与边界。

---

## 0. M0 的架构目标（为什么这样切）

M0 要交付的不是"能走动的地图"，而是**整个项目的确定性骨架**：时钟、RNG、事件溯源、唯一写路径。后面 M1-M6 所有能力（感知、LLM、战斗、存档分叉）都长在这副骨架上。因此 M0 的设计标准只有一条：**骨架定型后永不返工**。

三条不可变约束直接决定内核形态：

| 约束 | 对内核的要求 |
|---|---|
| C4 事件溯源 | 一切状态变化是 append-only 事件流，`apply(event)` 是唯一写路径 |
| C5 RNG 注入点全记录 | 所有随机性来自两个源：确定性 RNG（可重放）+ 熵注入（记录后可重放） |
| C6 双轨存档（M5 落地，M0 预留） | 事件流从第一天就是树形（branch_id），快照机制预留 |

---

## 1. core/clock — 游戏时钟

### 1.1 职责

游戏时间的唯一权威。tick 计数、倍速、战斗时间尺切换、昼夜/集市日派生。**clock 不推进世界，只回答"现在是什么时间、该走几个 tick"。**

### 1.2 接口契约

```python
class TimeScale(Enum):
    NORMAL = auto()    # 1x = 60 tick/s 实机（DESIGN §10）
    COMBAT = auto()    # 战斗时间尺：1 tick = 1 真实秒（§9 v2.1）

class GameClock:
    @property
    def tick(self) -> int: ...            # 单调递增，世界内唯一时间轴
    @property
    def speed(self) -> float: ...         # 0(暂停) / 1 / 4 / 16
    @property
    def timescale(self) -> TimeScale: ...

    def ticks_per_real_second(self) -> float:
        # NORMAL: 60 * speed ; COMBAT: 1 * speed

    def advance(self, real_dt: float) -> int:
        """喂入真实流逝秒数，返回本帧应推进的 tick 数（累加器模式，见 §5）。"""

    def enter_combat(self) -> None: ...   # 切换时间尺；累加器清零防突跳
    def exit_combat(self) -> None: ...

    # 派生时间（纯函数，不落状态）
    def game_time(self) -> GameTime: ...  # (day, hour, minute, second) ← tick 换算
    def phase_of_day(self) -> DayPhase: ...  # 黎明/白天/黄昏/夜晚
    def is_market_day(self) -> bool: ...
```

**要点**：
- `tick` 是**世界内**时间，前端永不直接显示原始 tick（界面双层铁律 C3）；`game_time()` 是唯一的戏内时间表达。
- 时间尺切换只改"真实秒→tick"的换算率，**不改事件流结构**——回放逻辑对时间尺无感。
- 昼夜/集市日全部由 tick 纯函数派生，**不存进世界状态**（减少快照体积，且重放自然一致）。

---

## 2. core/rng — 确定性随机源

### 2.1 职责

为世界模拟提供**可逐位重放**的随机数。这是 C4/C5 的地基。

### 2.2 设计：分流 RNG（streamed RNG）

不分流的单一全局 RNG 有个隐患：任何一处新增的随机调用都会改变后续所有抽签序列，回放即崩。因此按**子系统分流**：

```python
class RngRegistry:
    """每个子系统持有独立流；流之间互不影响。"""
    def __init__(self, world_seed: int): ...
    def stream(self, name: str) -> numpy.random.Generator:
        # 由 (world_seed, name) 派生种子，确定性
        # 例：stream("combat.critical") / stream("world.weather") / stream("map.gen")
```

- 算法：PCG64（numpy 默认），种子派生用 SHA-256(world_seed ‖ stream_name) 折成 128bit。
- **规则**：业务代码禁止 `import random` / `numpy.random` 全局实例；只能经 `RngRegistry.stream()`。T2 测试用静态扫描（ruff 自定义规则或简单 grep 断言）强制。
- 流名即文档：约定 `<子系统>.<用途>`，写进各模块常量。

### 2.3 与回放的关系

确定性 RNG 不需要把每次抽签写进事件日志——只要种子固定、调用顺序确定，重放自然逐位一致。**调用顺序的确定性由 tick loop 的固定执行序保证（§5）**。

---

## 3. core/entropy — 混合熵注入（C5）

### 3.1 为什么需要

纯确定性 RNG 意味着"同一个 seed 永远同一个世界"——这对**开发者重放**是特性，对**玩家不可预测**是缺陷（背板）。DESIGN §11 的裁决：开发者可重放 + 玩家不可预测并存 → 熵在**注入点**进入，注入本身作为事件被记录。

### 3.2 熵源与注入点

| 熵源 | 用途 | 时机 |
|---|---|---|
| `os.urandom` | 世界初始 seed、每日天气、致命一击 | 创世 / 每日 00:00 / 战斗结算 |
| 玩家输入时序（念头注入的真实时间戳） | 扰动当日熵池 | 念头注入时 |
| 系统时间（启动时） | 世界初始 seed 组分 | 创世 |

### 3.3 接口契约

```python
class EntropyEvent(BaseModel):       # 一种特殊的 WorldEvent
    kind: Literal["entropy_inject"]
    tick: int
    stream: str                      # 目标 RNG 流名
    payload: bytes                   # 注入的熵（hex 存储）

class EntropyMixer:
    def inject(self, stream: str, source: EntropySource) -> EntropyEvent:
        """采集外部熵 → 混入目标流（reseed）→ 返回事件（由调用方走 apply 落日志）。"""
```

**关键约束**：
- 熵注入**必须走 `apply(EntropyEvent)`**，成为事件流的一部分——回放时在同一 tick 重放同一注入，结果逐位一致。C5 的"注入点全记录"由此落地。
- 熵源采集函数（`os.urandom` 等）只允许出现在 `EntropyMixer` 内部，业务代码不直接碰。T2 静态扫描强制（同 RNG 规则）。
- 每日天气/NPC 初始倾向等"系统性随机"也走注入，而非启动时定死——否则长程回放会放大早期差异。

---

## 4. core/events — 事件与唯一写路径（C4）

### 4.1 事件契约

```python
class WorldEvent(BaseModel):
    model_config = ConfigDict(frozen=True)      # 事件不可变

    seq: int                  # 分支内单调序号（持久层分配，见 §4.3）
    branch_id: int            # 世界线分支；M0 恒为 0，C6/M5 启用分叉
    tick: int
    kind: str                 # "move" / "tile_changed" / "entropy_inject" / ...
    actor_id: str | None      # 触发者（NPC/Agent/系统 None）
    payload: dict             # 事件专属数据
```

- `frozen=True`：事件创建后不可改，天然 append-only。
- `kind` 用注册表管理（§4.2），禁止散落的魔法字符串。
- M0 只需要少量 kind：`world.create` / `tick.advance`（可选）/ `move` / `map.load` / `entropy_inject`。

### 4.2 apply(event) — 唯一写路径

DESIGN §19：不为世界状态直接赋值，必须走 `apply(event)`。机制设计：

```python
ApplyFn = Callable[[WorldState, WorldEvent, TickContext], list[WorldEvent]]

class EventBus:
    _handlers: dict[str, ApplyFn]          # kind → handler 注册表

    def register(self, kind: str, fn: ApplyFn) -> None: ...
    def apply(self, state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
        """
        1. 校验事件（kind 已注册、tick 合法、actor 存在）
        2. 调用 handler：handler 是唯一能写 state 的地方
        3. handler 返回派生事件（级联，如坍塌→伤人），递归入队
        4. 返回 ApplyResult：状态增量 delta + 派生事件队列
        """
```

**三层防线保证"唯一写路径"不是口号**：
1. **结构**：`WorldState` 的所有可变字段只被 handler 触碰；handler 签名是唯一的写入入口。
2. **测试**：T2 回放测试（同一事件流重放 → 状态哈希逐位一致）。任何绕过 apply 的写入都会破坏回放，测试立刻红。
3. **静态扫描**：ruff 自定义规则禁止 handler 之外的代码对 `WorldState` 赋值（规则随 cline 的配置任务落地）。

### 4.3 seq 的分配与持久化边界

- `seq` 由**持久层**在落库时分配（分支内自增），保证 append-only 顺序与落库顺序一致。
- `apply` 分两段：**先纯计算（内存）→ 再落库（I/O）**。tick loop 中计算段是同步确定性的，落库段异步批量刷盘（见 §5、§8），避免 I/O 抖动污染 tick 时序。
- 具体 schema（events/branches/snapshots 表）归 opencode TASK-001；本文只定接口：`EventStore.append(events) / read_range(branch, seq_from, seq_to) / snapshot(state, tick)`。

---

## 5. tick loop — 确定性主循环

### 5.1 结构：外层 asyncio 驱动 + 内层同步确定性 tick

游戏引擎不做模拟内核（§4 硬约束），asyncio 只负责**喂时间**和**刷 I/O**，世界推进本身是同步纯计算：

```python
# 外层（asyncio，非确定性区）
async def run(world, clock, store, bus, broadcaster):
    last = monotonic()
    while running:
        now = monotonic()
        n_ticks = clock.advance(now - last)     # 累加器：返回本帧应走 tick 数
        last = now
        for _ in range(n_ticks):
            tick(world, clock, bus, ctx)         # 内层：同步、确定性
            deltas = drain_deltas()              # 收集本 tick 状态增量
            await broadcaster.send(deltas)       # WS 广播（kilo 协议）
        await store.flush()                      # 批量刷事件日志（opencode）
        await asyncio.sleep(0)                   # 让出事件循环
```

### 5.2 内层 tick — 固定执行序（回放一致性的关键）

```python
def tick(world, clock, bus, ctx):
    ctx.tick = clock.tick
    # 固定顺序，任何模块不得改变——顺序即确定性
    world.advance_needs(ctx)          # 1. 需求/身体推进（M2 起有内容，M0 空转）
    world.process_scheduled(ctx)      # 2. 定时事件（天气注入等）
    world.move_entities(ctx)          # 3. 实体沿路径移动（M0 核心）
    # M1+: 感知传播 / L1 效用 / LLM Intent 执行时二次校验——预留挂载点
    clock.tick += 1
```

**为什么固定顺序**：确定性 RNG 的抽签序列依赖调用顺序。执行序一旦固定，重放同事件流必得同结果——T2 的本质就是验证这一点。新增子系统（M1 感知、M2 效用）只能**追加到固定序列末尾的预留挂载点**，不得插入中间。

### 5.3 倍速与战斗时间尺

- `clock.advance(real_dt)` 用累加器：NORMAL 1x 每秒 60 tick，4x 每秒 240 tick，暂停返回 0。低帧率时一帧补多个 tick（catch-up），设上限防"死亡螺旋"（单帧最多补 4 秒等价的 tick，超出丢弃并记日志）。
- 战斗时间尺只是换算率变为 1 tick/s（§9 v2.1），loop 结构不变——`enter_combat/exit_combat` 切的是 `GameClock` 的 rate，不是另一条循环。

---

## 6. world/map — 瓦片地图数据模型

### 6.1 分层

| 层 | 内容 | 可变性 |
|---|---|---|
| 底图 ground | 地形瓦片（Tiled 编辑） | M0 只读；M3 可变地图底座后可写（tile_changed 事件） |
| 碰撞 collision | 可通行位（墙/水/家具） | 随底图/建造变化，chunk 增量失效 |
| 实体 entities | NPC/Agent/物品 | 每 tick 变，走 apply(event) |
| 光照 light | 元气骑士调性的光照层（M0 简单昼夜调光，弹幕级光照后置） | 派生自 clock，不存 |

### 6.2 数据契约

```python
class TileMap(BaseModel):
    width: int; height: int
    tile_size: int = 16
    chunks: dict[tuple[int,int], Chunk]   # chunk = 16×16 瓦片，按需加载/失效

class Chunk(BaseModel):
    cx: int; cy: int
    ground: list[int]                     # 瓦片 id 扁平数组
    collision: list[bool]                 # 可通行位
    dirty: bool = False                   # tile_changed 后置位，触发寻路缓存失效
```

- Tiled 导出的 JSON → 构建期脚本转成内部 `TileMap`（不进运行时编辑器）。M0 一张图，不做流式加载，但 chunk 结构为 M3 可变底座/M14 建造预留。
- 碰撞从底图派生（Tiled 的 collision layer），不手写。

### 6.3 地标与命名

DESIGN §1 要求小镇级单图。M0 内容管线：`sim/content/` 放地图源文件 + 地标命名规范（药铺/铁匠铺/酒馆等锚点，供 M1 感知帧叙事化引用，如「药铺在我左手边第三间」）。M0 只需占位地图 + 碰撞正确。

---

## 7. world/pathfinding — 寻路

### 7.1 选型

A*，网格 + 对角移动，octile 启发。不引入导航网格（navmesh）——小镇单图 50 NPC，网格 A* 足够且与瓦片/碰撞天然对齐。

### 7.2 关键约束：chunk 增量失效，禁全图重算（§14/§19）

```python
class Pathfinder:
    def find(self, start: Pos, goal: Pos) -> list[Pos]: ...
    def invalidate(self, chunk: tuple[int,int]) -> None:
        """tile_changed 后调用：仅失效经过该 chunk 的缓存路径。"""
```

- 路径缓存键：(start, goal) 归一化到 chunk 对；缓存条目记录途经 chunk 集合，失效时精确剔除。
- 移动中的实体遇到路径失效：就地重寻剩余段（不重走全程）。
- 确定性：A* 的 open set 用确定性 tie-break（f 值相同比坐标字典序），**不用 hash 序**——否则回放路径可能分叉。tie-break 不写死随机，必要时经 `rng.stream("path.tiebreak")`。

---

## 8. core/persistence — 持久化接口（边界声明）

具体表结构、迁移、事件溯源 SQL 归 opencode（TASK-001，数据/数据库域）。内核只依赖抽象：

```python
class EventStore(Protocol):
    async def append(self, events: list[WorldEvent]) -> None: ...      # 分配 seq，append-only
    async def read_range(self, branch_id: int, frm: int, to: int) -> list[WorldEvent]: ...
    async def write_snapshot(self, branch_id: int, tick: int, blob: bytes) -> None: ...
    async def latest_snapshot(self, branch_id: int, before_tick: int) -> Snapshot | None: ...
```

- 批量 `flush`：tick loop 每帧把累计事件一次性 append，而非每事件一次 I/O。
- 快照序列化用 pydantic `model_dump` + gzip（对齐 §12 v2.1 体积治理）。

---

## 9. M0 验收映射（T2 通过 = 本文档的试金石）

| 验收 | 由本文档哪部分保证 |
|---|---|
| 可走动 | §6 地图 + §7 寻路 + §5 tick loop 移动实体 |
| T2 回放逐位一致 | §4 唯一写路径 + §5.2 固定执行序 + §2 分流 RNG + §3 熵走事件 |
| C4 事件溯源 | §4 EventBus + §8 EventStore |
| C5 熵注入全记录 | §3 EntropyMixer 经 apply 落日志 |
| 战斗时间尺预留 | §1 TimeScale + §5.3 |

**M0 的 T2 测试骨架**（`sim/tests/replay/`）：
1. 创世（固定 seed）→ 跑 N tick（含若干熵注入与移动）→ 记录状态哈希。
2. 从事件日志重放同 N tick → 状态哈希逐位相等。
3. 扫描断言：无 `import random`、无 handler 外的 WorldState 写入、RNG 调用顺序确定。

---

## 10. 与其他 agent 的接口（依赖声明）

| 依赖 | 提供方 | 我需要什么 |
|---|---|---|
| 骨架/pyproject/uv | cline TASK-001 | `sim/core`、`sim/world` 目录 + pytest/ruff/pyright 配置 |
| 事件表/快照表 schema | opencode TASK-001 | 实现 §8 EventStore Protocol |
| WS 广播协议 | kilo TASK-001 | `state_delta` 消息格式（§5.1 broadcaster 的消费方） |
| 每 tick 预算 | pi TASK-001 | 16.6ms 分解表，校核 §5.2 各阶段上限 |

**边界**：本文不定 DB schema、不定 WS 消息字段、不定前端渲染——那些归对应 agent，本文只声明内核要消费它们的接口形状。

---

## 11. 开放问题（提交评审）

1. `tick.advance` 是否进事件流？进则回放更严格但事件量 +86k/游戏日；倾向**不进**（tick 由 clock 单调驱动，重放天然对齐），标为待定，评审裁决。
2. 快照序列化格式：pydantic JSON vs MessagePack。体积/速度取舍留给 pi 的基准数据裁决，M0 先用 JSON 保正确性。
3. 移动事件的粒度：每 tick 一格一事件（事件量大）vs 路径段一个事件 + tick 内插值（事件少但重放逻辑复杂）。倾向**路径段事件**，M0 评审定。
