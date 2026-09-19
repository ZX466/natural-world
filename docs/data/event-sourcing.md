# 事件溯源方案

> 对齐 DESIGN.md §4 C4（事件溯源是唯一写路径）、§6 WorldEvent、§11 混合熵、§12 双轨存档、§19 禁止事项。

---

## 1. 核心原则

- **唯一写路径**：所有世界状态变更必须通过 `apply(event)` → INSERT INTO events。
- **append-only**：events 表永不 UPDATE/DELETE（§19 禁止事项）。
- **确定性回放**：给定 seed + events 序列，世界状态必须逐位一致（§5 C5）。
- **分支即分叉**：读档不回退历史，而是创建新分支（§12 C6）。

---

## 2. `apply(event)` — 唯一写路径

### 2.1 函数签名

```python
async def apply(
    session: AsyncSession,
    event: WorldEvent,
    *,
    entropy_draw: EntropyDraw | None = None,
) -> None:
    """
    唯一的世界状态写入路径。

    1. 校验 event 合法性
    2. 写入 events 表（append-only）
    3. 若有 entropy_draw，写入 entropy_log
    4. 更新 entity 在物化视图中的状态（可选，见 §3）
    """
```

### 2.2 执行流程

```
Intent 通过闸门校验
        │
        ▼
   apply(event)
        │
        ├── 1. 校验 event_type 在白名单内
        ├── 2. 校验 branch_id 存在且 status = 'active'
        ├── 3. 生成 seq = MAX(seq) + 1（分支内单调递增）
        ├── 4. INSERT INTO events (branch_id, seq, tick, ...)
        ├── 5. 若有 entropy_ref → INSERT INTO entropy_log
        ├── 6. 调用 _apply_effects(event) 更新物化状态
        └── 7. 返回（成功/失败原因）
```

### 2.3 闸门与 apply 的关系

§6 闸门顺序：白名单 → 目标存在可达 → 距离/视野/资源 → 世界规则。

```
LLM 输出 Intent
        │
        ▼
  ┌─ 规划时闸门（预检）─┐
  │  白名单             │
  │  目标存在可达       │
  │  距离/视野/资源     │
  │  世界规则           │
  └─────────────────────┘
        │ 通过
        ▼
  Intent 入队（等待执行 tick）
        │
        ▼
  ┌─ 执行时闸门（二次校验）─┐
  │  世界已变化？→ 过期丢弃  │
  │  → 触发重规划（最多 2 次）│
  └──────────────────────────┘
        │ 通过
        ▼
     apply(event)
```

**关键**：执行时二次校验是必须的。LLM 异步延迟期间世界已变化，过期 Intent 必须丢弃（§19：不静默丢弃，返回结构化失败原因）。

---

## 3. 物化状态（可选优化层）

### 3.1 问题

纯事件溯源的读取路径很慢：每次读当前状态都要从头重放所有事件。

### 3.2 方案：快照 + 增量重放

§12 已定义：每 1000 tick 一份全量快照。读取流程：

```
定位 anchor → (branch_id, seq)
        │
        ▼
  找最近快照（tick ≤ anchor.tick）
        │
        ▼
  从快照恢复全量状态
        │
        ▼
  重放快照后到 anchor.tick 的事件
        │
        ▼
  应用 agent_override
        │
        ▼
  创建新分支
```

### 3.3 物化视图（M0+）

在 fast-path 场景（每 tick 推进），不每次从快照重放。维护一个可选的物化状态：

```python
class MaterializedWorld:
    """
    当前活跃分支的物化状态。
    每次 apply(event) 后增量更新。
    快照时序列化为 snapshot_data。
    """
    entities: dict[str, EntityState]
    relationships: dict[tuple[str, str], Relationship]
    structures: dict[str, Structure]
    tick: int
    seq: int
```

**更新时机**：
- 每次 `apply(event)` → `_apply_effects(event)` → 更新 MaterializedWorld
- 每 1000 tick → 快照 = MaterializedWorld 序列化 + gzip
- 崩溃恢复 → 从最近快照 + 重放事件重建 MaterializedWorld

---

## 4. 读档重放流程

### 4.1 完整流程（伪代码）

```python
async def load_anchor(
    session: AsyncSession,
    anchor: PlayerAnchor,
) -> MaterializedWorld:
    """
    读档 = 分叉。不破坏原世界线。
    """
    # 1. 定位 anchor 的 (branch_id, seq)
    branch_id = anchor.branch_id
    target_seq = anchor.seq

    # 2. 找最近快照（tick ≤ anchor.tick）
    snapshot = await session.execute(
        select(Snapshot)
        .where(Snapshot.branch_id == branch_id)
        .where(Snapshot.tick <= anchor.tick)
        .order_by(Snapshot.tick.desc())
        .limit(1)
    )
    snapshot = snapshot.scalar_one_or_none()

    # 3. 从快照恢复全量状态
    if snapshot:
        world = MaterializedWorld.from_snapshot(snapshot.snapshot_data)
        start_tick = snapshot.tick
        start_seq = snapshot.seq
    else:
        world = MaterializedWorld.empty()
        start_tick = 0
        start_seq = 0

    # 4. 重放快照后到 anchor.tick 的事件
    events = await session.execute(
        select(Event)
        .where(Event.branch_id == branch_id)
        .where(Event.seq > start_seq)
        .where(Event.tick <= anchor.tick)
        .order_by(Event.seq)
    )
    for event in events.scalars():
        world = apply_event(world, event)  # 纯函数，不写 DB

    # 5. 应用 agent_override
    world.apply_override(anchor.agent_override)

    # 6. 创建新分支
    new_branch = Branch(
        id=uuid4().hex,
        forked_from_branch=branch_id,
        forked_from_seq=target_seq,
        status="active",
    )
    session.add(new_branch)

    # 7. 旧分支标记 abandoned（如果还不是）
    old_branch = await session.get(Branch, branch_id)
    if old_branch.status == "active":
        old_branch.status = "abandoned"
        old_branch.abandoned_at = time.time()

    await session.commit()
    return world
```

### 4.2 关键约束

- **读档不删除/回退**原世界线的 events（§19 禁止事项）
- **读档创建新分支**，旧分支标记 abandoned（§12）
- **新分支的 NPC 对旧分支一无所知**（§12 分叉可见性，M5 前不启用既视感）

---

## 5. 回放确定性

### 5.1 RNG 确定性（§5 C5 + §11）

```python
class DeterministicRNG:
    """
    确定性伪随机数生成器。
    每个 stream 有独立状态，可序列化/反序列化。
    """
    _streams: dict[str, StreamState]
    _log: list[EntropyDraw]

    def chaotic(self, stream: str) -> float:
        """日常演化：确定性流，可重放"""
        return self._streams[stream].next()

    def inject(self, stream: str, reason: str) -> float:
        """关键分叉：真随机，记录后重新播种"""
        value = int.from_bytes(os.urandom(8), "big") / 2**64
        self._log.append(EntropyDraw(stream, reason, self.tick, value))
        self._streams[stream].reseed(value)
        return value
```

### 5.2 熵日志随事件落库

每个 `inject()` 调用产生一条 `EntropyDraw`，随事件一起写入：

```
events 表: event 的 entropy_ref = entropy_log.id
entropy_log 表: 记录 stream, reason, tick, value
```

**回放时**：读取 entropy_log，用相同 value 重新播种 RNG stream → 确定性一致。

### 5.3 逐位一致保证

```python
def replay_deterministic(
    seed: int,
    events: list[WorldEvent],
    entropy_log: list[EntropyDraw],
) -> MaterializedWorld:
    """
    给定 seed + events + entropy_log，
    必须产生与原始执行完全一致的世界状态。
    """
    rng = DeterministicRNG.from_seed(seed)
    world = MaterializedWorld.empty()

    # 重建熵日志索引
    entropy_by_tick = {e.tick: e for e in entropy_log}

    for event in events:
        # 如果这个 tick 有熵注入，先播种
        if event.tick in entropy_by_tick:
            ed = entropy_by_tick[event.tick]
            rng.reseed_at(ed.stream, ed.value)

        # 确定性应用事件
        world = apply_event_deterministic(world, event, rng)

    return world
```

### 5.4 禁止事项对齐

| 禁止 | 实现 |
|------|------|
| 禁 `random.*` | 只用 `DeterministicRNG.chaotic()` |
| 禁 `datetime.now()` | 只用 event.tick |
| 禁遍历 `set` | 使用 `dict` 或排序后的 `list` |

---

## 6. 分支管理

### 6.1 分支状态机

```
        创建
         │
         ▼
     [active] ◄─── 读档分叉创建新分支
         │
         │ 读档 / 用户删除
         ▼
    [abandoned]
```

### 6.2 分支清理策略（§12 体积治理）

| 条件 | 操作 |
|------|------|
| active 分支 + 最近 8 份热快照 | 保留 |
| active 分支 + 更早的快照 | 标记 `is_cold=1` |
| abandoned 分支 + 所有快照 | 整体冷归档（gzip + 移出主库） |
| 事件日志超阈值 | 快照点以前的 events 整段转冷 |

**主库目标稳态 <2GB**。

---

## 7. 崩溃恢复

```
崩溃
  │
  ▼
重启 → 检查 MaterializedWorld 是否存在
  │
  ├── 存在 → 直接使用（上次快照 + 增量）
  │
  └── 不存在 → 从最近快照恢复 → 重放事件 → 重建
```

**快照频率**：每 1000 tick（约 16.7 游戏分钟 @ 60 tick/s）。最坏情况丢失 1000 tick 的增量。

---

## 8. 确认测试策略

| 测试 | 验证点 |
|------|--------|
| T1 因果溯源 | 每个 state_change 必须有 event_seq |
| T2 回放确定性 | seed + events + entropy_log → 逐位一致 |
| T1 历史不可销毁 | 读档后原分支 events 不变 |
| T5 golden 场景 | 10 种子 × 10 游戏日，宏观结果一致 |
