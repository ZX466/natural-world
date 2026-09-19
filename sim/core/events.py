"""事件契约 — WorldEvent（frozen）与事件种类注册表（m0-core.md §4）。

落库形状对齐 opencode 的 EventStore（event_type/actor_id/parent_seq/witnesses/entropy_ref）。
seq 由持久层分配（分支内自增），WorldEvent 不携带 seq。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventKind(StrEnum):
    """M0 事件种类。新增种类只能追加（事件流是冻结基线的一部分）。"""

    WORLD_CREATE = "world.create"
    MOVE = "move"  # 路径段事件（粒度裁决见 m0-core §11.3）
    ENTROPY_INJECT = "entropy_inject"
    TILE_CHANGED = "tile_changed"  # M3 可变底座预留


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
    payload: dict[str, Any] = Field(default_factory=dict)
    witnesses: list[str] = Field(default_factory=list)  # 目击者 id（M1 感知用）
    entropy_ref: str | None = None  # 指向 entropy_log 的引用（C5）

    def to_store_dict(self) -> dict[str, Any]:
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


def entropy_event(tick: int, stream: str, payload_hex: str, branch_id: str = "main") -> WorldEvent:
    """熵注入事件工厂（C5：注入必须成为事件流的一部分）。

    payload 携带目标流名与熵材料 hex；重放时在同一 tick 重放同一注入。
    """
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.ENTROPY_INJECT,
        payload={"stream": stream, "material": payload_hex},
    )
