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
