"""事件契约 — WorldEvent（frozen）与事件种类注册表（m0-core.md §4）。

落库形状对齐 opencode 的 EventStore（event_type/actor_id/parent_seq/witnesses/entropy_ref）。
seq 由持久层分配（分支内自增），WorldEvent 不携带 seq。

payload schema 化（codex 评审意见 7，2026-09-19 采纳）：每个 kind 有对应
pydantic payload 模型（extra="forbid"），构造事件必须走工厂函数——事件日志
是戏外审计资产，LLM/玩家输入不可夹带任意键值。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EventKind(StrEnum):
    """M0 事件种类。新增种类只能追加（事件流是冻结基线的一部分）。"""

    WORLD_CREATE = "world.create"
    MOVE = "move"  # 路径段事件（粒度裁决见 m0-core §11.3，字段白名单见 MovePayload）
    COMBAT_SCALE_CHANGE = "combat.scale_change"  # 战斗尺切换必须进事件流（codex 意见 1）
    ENTROPY_INJECT = "entropy_inject"
    TILE_CHANGED = "tile_changed"  # M3 可变底座预留
    # ---- M2（m2-npc-cognition §1.2/§2.1/§4.1）----
    NPC_LOD_CHANGE = "npc.lod_change"  # LOD 升降格（变更只走事件，不直改列）
    NPC_ACT = "npc.act"  # L1 效用/计划队列产出的动作（白名单见 sim/npc/actions.py）
    MATTER_DECAY = "matter.decay"  # 物质熵增：自然衰减（批量结算）
    MATTER_DAMAGE = "matter.damage"  # 物质熵增：交互损伤
    MATTER_BUILD = "matter.build"  # 物质熵增：建造（M4 承重前为简化版）
    MATTER_COLLAPSE = "matter.collapse"  # 物质熵增：耐久归零坍塌（简化版）
    # ---- M3（m3-plan 批次 B / m3-evidence-chain §3；裁 8）----
    NPC_HIDDEN_EMERGE = "npc.hidden_emerge"  # 隐藏属性新进触发窗口（E1：浮现即事件，R5 证据链根）


# ---------------------------------------------------------------------------
# payload 模型 — 按 kind 一一对应；新 kind 必须同步新增 payload 模型
# ---------------------------------------------------------------------------


class MovePayload(BaseModel):
    """路径段移动 — 字段白名单（codex 意见 3）：只有实体/起点/终点/路径。

    start/goal 冗余存一份：审计时无需重放即可核对该段意图边界。
    禁止 LLM 或玩家输入注入其他字段（extra="forbid"）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    start: tuple[int, int]
    goal: tuple[int, int]
    path: tuple[tuple[int, int], ...]


class WorldCreatePayload(BaseModel):
    """创世。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    entities: tuple[str, ...] = ()  # 实体 id 清单


class CombatScaleChangePayload(BaseModel):
    """战斗时间尺切换。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entering: bool  # True=进入战斗尺，False=退出


class EntropyInjectPayload(BaseModel):
    """熵注入（C5：材料必须随事件落日志）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stream: str
    material: str  # 熵材料 hex


class TileChangedPayload(BaseModel):
    """瓦片变更（M3）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: int
    y: int
    tile_id: int


class NpcLodChangePayload(BaseModel):
    """LOD 升降格（M2，m2-npc-cognition §1.2）。from_lod/to_lod ∈ {0,1,2}。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    npc_id: str
    from_lod: int = Field(ge=0, le=2)
    to_lod: int = Field(ge=0, le=2)
    reason: str  # 升降格原因（enter_range/leave_range/dialogue_end/...）


class NpcActPayload(BaseModel):
    """L1 效用动作（M2，§2.1）。action 白名单在 sim/npc/actions.py。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    npc_id: str
    action: str
    target: str = ""
    params: dict[str, str] = {}  # 白名单键见 actions.ACTION_PAYLOAD_KEYS


class MatterPayload(BaseModel):
    """物质熵增（M2，§4.1）。matter_state 表 = 事件流持久化投影。

    decay_rate：对象静态衰减率（§17.2 方案 A，2026-09-22 裁决）。-1=不变更
    （damage/build 缺省）；settle_decay/build 事件携带账本静态率，投影写
    matter_state.decay_rate 恢复「事件重放逐位重建」（§14）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    matter_id: str
    #: 域约束（M3-S1 C2，m3-preplan §2）：防 NaN/±inf 与越界值固化进
    #: append-only 世界态（`np.clip(NaN)=NaN` / `min(1,inf)=1` 静默伪造）。
    #: x/y ∈ [-1,4096)：-1=未定位哨兵，上界=寻路界（gate.py out_of_bounds 同源）。
    x: int = Field(default=-1, ge=-1, lt=4096)
    y: int = Field(default=-1, ge=-1, lt=4096)
    #: 单 tick 变化量；[-1,1]（与账本 clip(0,1) 同语义）。-1..1 之外拒。
    amount: float = Field(default=0.0, ge=-1.0, le=1.0, allow_inf_nan=False)
    #: 耐久/积分；-1=不变更哨兵，≥0 为 0..1。
    durability: float = Field(default=-1.0, ge=-1.0, le=1.0, allow_inf_nan=False)
    #: 静态衰减率；-1=不变更哨兵，≥0 为静态率。
    decay_rate: float = Field(default=-1.0, ge=-1.0, le=1.0, allow_inf_nan=False)
    note: str = ""


class HiddenEmergePayload(BaseModel):
    """隐藏属性浮现（M3 E1，m3-evidence-chain §3；裁 8）。

    attr_ids 只装「新进触发窗口」的 delta（戏外主键 ``f"{npc_id}.health_{row.id}"``，
    非 descriptor/label 词面——X4 修订：词面永不入事件，extra=forbid 硬拒）。
    witnessed 装配在感知层（evidence.witnesses_of_emerge），不在 payload。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    npc_id: str
    attr_ids: tuple[str, ...]


class WorldEvent(BaseModel):
    """不可变事件 — 唯一写路径的载体（C4）。

    frozen：创建后不可改；append-only 由结构保证。
    """

    model_config = ConfigDict(frozen=True)

    branch_id: str = "main"
    tick: int = Field(ge=0)
    event_type: EventKind
    actor_id: str = ""  # 系统/世界事件为空串
    target_id: str | None = None
    parent_seq: int | None = None  # 派生事件指向触发事件（持久层分配后回填）
    payload: dict[str, object] = Field(default_factory=dict)
    witnesses: list[str] = Field(default_factory=list)  # 目击者 id（M1 感知用）
    entropy_ref: str | None = None  # 指向 entropy_log 的引用（C5）

    def to_store_dict(self) -> dict[str, object]:
        """EventStore.append 消费的字典形状（与 SqlEventStore 对齐）。"""
        return {
            "tick": self.tick,
            "event_type": self.event_type.value,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "parent_seq": self.parent_seq,
            "payload": self.payload,
            "witnesses": self.witnesses,
            "entropy_ref": self.entropy_ref,
        }


# ---------------------------------------------------------------------------
# 事件工厂 — 构造事件的唯一入口（payload schema 在此强制）
# ---------------------------------------------------------------------------


def world_create_event(
    tick: int, seed: int, entity_ids: tuple[str, ...], branch_id: str = "main"
) -> WorldEvent:
    p = WorldCreatePayload(seed=seed, entities=entity_ids)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.WORLD_CREATE,
        payload=p.model_dump(mode="json"),
    )


def move_event(
    tick: int,
    actor_id: str,
    start: tuple[int, int],
    goal: tuple[int, int],
    path: tuple[tuple[int, int], ...],
    branch_id: str = "main",
) -> WorldEvent:
    """路径段移动事件。path 白名单一致性校验：首=start、末=goal。"""
    if not path or path[0] != start or path[-1] != goal:
        first = path[0] if path else None
        last = path[-1] if path else None
        msg = f"路径与起终点不一致: start={start} goal={goal} path[0]={first} path[-1]={last}"
        raise ValueError(msg)
    p = MovePayload(entity_id=actor_id, start=start, goal=goal, path=path)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.MOVE,
        actor_id=actor_id,
        payload=p.model_dump(mode="json"),
    )


def combat_scale_event(tick: int, entering: bool, branch_id: str = "main") -> WorldEvent:
    """战斗时间尺切换事件——影响后续所有结算语义，回放必须重放（codex 意见 1）。"""
    p = CombatScaleChangePayload(entering=entering)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.COMBAT_SCALE_CHANGE,
        payload=p.model_dump(mode="json"),
    )


def entropy_event(tick: int, stream: str, payload_hex: str, branch_id: str = "main") -> WorldEvent:
    """熵注入事件工厂（C5：注入必须成为事件流的一部分）。

    payload 携带目标流名与熵材料 hex；重放时在同一 tick 重放同一注入。
    """
    p = EntropyInjectPayload(stream=stream, material=payload_hex)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.ENTROPY_INJECT,
        payload=p.model_dump(mode="json"),
    )


def tile_changed_event(
    tick: int, x: int, y: int, tile_id: int, branch_id: str = "main"
) -> WorldEvent:
    p = TileChangedPayload(x=x, y=y, tile_id=tile_id)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.TILE_CHANGED,
        payload=p.model_dump(mode="json"),
    )


# ---- M2 工厂（m2-npc-cognition §1.2/§2.1/§4.1）----


def npc_lod_change_event(
    tick: int, npc_id: str, from_lod: int, to_lod: int, reason: str, branch_id: str = "main"
) -> WorldEvent:
    p = NpcLodChangePayload(npc_id=npc_id, from_lod=from_lod, to_lod=to_lod, reason=reason)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.NPC_LOD_CHANGE,
        payload=p.model_dump(mode="json"),
    )


def npc_act_event(
    tick: int,
    npc_id: str,
    action: str,
    target: str = "",
    params: dict[str, str] | None = None,
    branch_id: str = "main",
) -> WorldEvent:
    p = NpcActPayload(npc_id=npc_id, action=action, target=target, params=params or {})
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.NPC_ACT,
        payload=p.model_dump(mode="json"),
    )


def matter_event(
    tick: int,
    kind: EventKind,
    matter_id: str,
    x: int = -1,
    y: int = -1,
    amount: float = 0.0,
    durability: float = -1.0,
    decay_rate: float = -1.0,
    note: str = "",
    branch_id: str = "main",
) -> WorldEvent:
    """物质熵增事件（kind ∈ MATTER_DECAY/DAMAGE/BUILD/COLLAPSE）。

    decay_rate：账本静态率（§17.2 方案 A）；settle_decay/build 携带，damage 缺省 -1。
    """
    if kind not in (
        EventKind.MATTER_DECAY,
        EventKind.MATTER_DAMAGE,
        EventKind.MATTER_BUILD,
        EventKind.MATTER_COLLAPSE,
    ):
        raise ValueError(f"kind 必须为 MATTER_*: {kind}")
    p = MatterPayload(
        matter_id=matter_id,
        x=x,
        y=y,
        amount=amount,
        durability=durability,
        decay_rate=decay_rate,
        note=note,
    )
    return WorldEvent(
        branch_id=branch_id, tick=tick, event_type=kind, payload=p.model_dump(mode="json")
    )


# ---- M3 工厂（m3-evidence-chain §3/§4；裁 8 E1）----


def hidden_emerge_event(
    tick: int,
    npc_id: str,
    attr_ids: tuple[str, ...],
    witnesses: list[str] | None = None,
    branch_id: str = "main",
) -> WorldEvent:
    """隐藏属性浮现事件（E1）：attr_ids = 新进触发窗口的 delta（X4 修订：仅戏外主键，
    descriptors/label/triggered 词面永不入事件——extra=forbid 硬拒）。"""
    p = HiddenEmergePayload(npc_id=npc_id, attr_ids=attr_ids)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.NPC_HIDDEN_EMERGE,
        payload=p.model_dump(mode="json"),
        witnesses=list(witnesses or []),
    )
