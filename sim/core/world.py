"""世界状态与唯一写路径 — EventBus.apply（m0-core.md §4/§5，C4）。

设计：handler 是纯函数（旧状态+事件 → 新状态），frozen WorldState 走
model_copy 不可变更新（项目编码规范：永不原地修改）。唯一写路径 =
「状态只能从 apply 返回的新实例流出」。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from sim.core.events import EventKind, WorldEvent

logger = structlog.get_logger(__name__)

ApplyFn = Callable[["WorldState", WorldEvent, "TickContext"], "ApplyResult"]


class EntityState(BaseModel):
    """M0 实体：位置 + 剩余路径。M2 起由 npc 域扩展。"""

    model_config = ConfigDict(frozen=True)

    entity_id: str
    pos: tuple[int, int]
    path: tuple[tuple[int, int], ...] = ()  # 剩余路径（路径段事件粒度，m0-core §11.3）


class WorldState(BaseModel):
    """世界真相（不可变）。M0 只含种子与实体；地图是静态资产，M3 进状态。"""

    model_config = ConfigDict(frozen=True)

    world_seed: int = 0
    tick: int = Field(default=0, ge=0)
    entities: dict[str, EntityState] = Field(default_factory=dict)

    def state_hash(self) -> str:
        """状态指纹 — T2 回放逐位一致的断言对象。"""
        import hashlib
        import json

        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()


class TickContext(BaseModel):
    """tick 内共享上下文：时间尺开关 + RNG 抽签状态缓存（不入快照）。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    combat_active: bool = False
    rng_cache: dict[str, Any] = Field(default_factory=dict)

    def with_combat(self, active: bool) -> TickContext:
        return self.model_copy(update={"combat_active": active})


class ApplyResult(BaseModel):
    """apply 的输出：新状态（不可变流转）+ 派生事件（级联，调用方递归入队）。"""

    model_config = ConfigDict(frozen=True)

    state: WorldState
    derived: tuple[WorldEvent, ...] = ()


class EventBus:
    """kind → handler 注册表。apply 是唯一写路径。"""

    def __init__(self) -> None:
        self._handlers: dict[EventKind, ApplyFn] = {}

    def register(self, kind: EventKind, fn: ApplyFn) -> None:
        if kind in self._handlers:
            msg = f"事件种类重复注册: {kind}"
            raise ValueError(msg)
        self._handlers[kind] = fn

    def apply(self, state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
        """校验 → handler（纯函数）→ 返回新状态与派生事件。"""
        handler = self._handlers.get(event.event_type)
        if handler is None:
            msg = f"未注册的事件种类: {event.event_type}"
            raise ValueError(msg)
        if event.tick > state.tick + 1:
            msg = f"事件来自未来: event.tick={event.tick} > state.tick+1={state.tick + 1}"
            raise ValueError(msg)
        result = handler(state, event, ctx)
        logger.debug("event.applied", event_type=event.event_type.value, tick=event.tick)
        return result


# ---------------------------------------------------------------------------
# M0 内置 handler — 全部纯函数：入参 state 不改，返回新 state
# ---------------------------------------------------------------------------


def _apply_world_create(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """创世：payload {seed, entities: [{entity_id, pos}]}。只能作用于空白状态。"""
    if state.entities or state.tick != 0:
        msg = "创世事件只能作用于空白世界状态"
        raise ValueError(msg)
    entities = {
        str(e["entity_id"]): EntityState(
            entity_id=str(e["entity_id"]), pos=(int(e["pos"][0]), int(e["pos"][1]))
        )
        for e in event.payload.get("entities", [])
    }
    new_state = state.model_copy(
        update={"world_seed": int(event.payload["seed"]), "entities": entities}
    )
    return ApplyResult(state=new_state)


def _apply_move(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """路径段移动：payload {entity_id, path: [[x,y],...]}。终点=路径最后一格。"""
    entity_id = str(event.payload["entity_id"])
    entity = state.entities.get(entity_id)
    if entity is None:
        msg = f"未知实体: {entity_id}"
        raise ValueError(msg)
    path = tuple((int(x), int(y)) for x, y in event.payload.get("path", []))
    new_entity = entity.model_copy(update={"path": path})
    new_state = state.model_copy(update={"entities": {**state.entities, entity_id: new_entity}})
    return ApplyResult(state=new_state)


def _apply_entropy_inject(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """熵注入在状态层 no-op：材料在事件日志里，registry 重建由重放装配层做。"""
    return ApplyResult(state=state)


def _apply_tile_changed(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """M3 预留：M0 地图静态，收到即拒绝。"""
    msg = "tile_changed 在 M0 未启用（可变地图底座是 M3）"
    raise NotImplementedError(msg)


def build_default_bus() -> EventBus:
    """M0 默认事件总线。"""
    bus = EventBus()
    bus.register(EventKind.WORLD_CREATE, _apply_world_create)
    bus.register(EventKind.MOVE, _apply_move)
    bus.register(EventKind.ENTROPY_INJECT, _apply_entropy_inject)
    bus.register(EventKind.TILE_CHANGED, _apply_tile_changed)
    return bus
