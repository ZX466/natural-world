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

from sim.core.events import (
    CombatScaleChangePayload,
    EventKind,
    MovePayload,
    WorldCreatePayload,
    WorldEvent,
)

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
    """tick 内共享上下文：时间尺开关 + RNG 抽签状态缓存（不入快照）。

    fog_revealed（D17 视觉雾）：本帧主角新踏入的 chunk 账本（WS 投影 drain
    后清空）——迷雾是观察者投影不进世界态（裁 40-4：事件即真相），账本只
    服务「事件已入流后 delta/snapshot 投影何时带 fog 键」。
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    combat_active: bool = False
    rng_cache: dict[str, Any] = Field(default_factory=dict)
    fog_revealed: set = Field(default_factory=set)

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
    """创世：payload 白名单（WorldCreatePayload）。只能作用于空白状态。"""
    if state.entities or state.tick != 0:
        msg = "创世事件只能作用于空白世界状态"
        raise ValueError(msg)
    p = WorldCreatePayload.model_validate(event.payload)
    # M0：实体初始位形由创世方以 entity_id 为序默认置 (0,0)（简化；位形事件 M1 细化）
    entities = {eid: EntityState(entity_id=eid, pos=(0, 0)) for eid in p.entities}
    new_state = state.model_copy(update={"world_seed": p.seed, "entities": entities})
    return ApplyResult(state=new_state)


def _apply_move(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """路径段移动：payload 白名单（MovePayload）。终点=路径最后一格。"""
    p = MovePayload.model_validate(event.payload)
    entity = state.entities.get(p.entity_id)
    if entity is None:
        msg = f"未知实体: {p.entity_id}"
        raise ValueError(msg)
    new_entity = entity.model_copy(update={"path": p.path})
    new_state = state.model_copy(update={"entities": {**state.entities, p.entity_id: new_entity}})
    return ApplyResult(state=new_state)


def _apply_combat_scale(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """战斗尺切换的状态层语义：校验 payload；实际 rate 换算由 GameClock 执行。

    事件进日志保证回放时能重建时间尺序列（codex 意见 1）。状态层 no-op。
    """
    CombatScaleChangePayload.model_validate(event.payload)
    return ApplyResult(state=state)


def _apply_entropy_inject(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """熵注入在状态层 no-op：材料在事件日志里，registry 重建由重放装配层做。"""
    return ApplyResult(state=state)


def _apply_npc_death(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """NPC 死亡（M6 生命始终，落点 a）：从 `entities` 移除（**事件化**，非内存悄悄删）。

    - **未知实体 fail-closed**（同 `_apply_move` 的「未知实体」纪律——不静默忽略）；
    - **重复死亡 fail-closed**（不复活即可；幂等no-op 与 raise 皆合格，选 raise
      = fail-closed 口径一致）；
    - `npc_profiles` 行删除不在状态层——投影（schema §24 对称删除）在落库事务内做；
    - C5：同事件序列两遍 ⇒ `state_hash` 逐位相等（本 handler 纯函数、无随机）。
    """
    from sim.core.events import NpcDeathPayload

    p = NpcDeathPayload.model_validate(event.payload)
    if p.entity_id not in state.entities:
        msg = f"未知实体: {p.entity_id}（死亡只对在场实体成立）"
        raise ValueError(msg)
    entities = {k: v for k, v in state.entities.items() if k != p.entity_id}
    return ApplyResult(state=state.model_copy(update={"entities": entities}))


def _apply_npc_act(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """NPC_ACT（批次 B 实况接线）：决策记录进事件日志，状态层 no-op。

    L1 效用决策（sim/npc/runtime.py）每决策节拍产 NPC_ACT；其**可观察后果**
    由执行面拆成正式事件走各自 handler（移动 → MOVE；余者批次 C+）。
    本 handler 与 `_apply_entropy_inject` 同口径：no-op ⇒ 含 NPC_ACT 与不含
    NPC_ACT 的同构序列 fold 出逐位一致的 state_hash（回放安全，C5）。
    NPC 需求/决策是 runtime 内存态（不进 WorldState），不因重放重演。
    """
    from sim.core.events import NpcActPayload

    NpcActPayload.model_validate(event.payload)  # schema 校验；无状态效果
    return ApplyResult(state=state)


def _apply_npc_monologue(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """NPC_MONOLOGUE（批次 C 接线）：独白记录进事件日志，状态层 no-op。

    M2 起独白事件只走 WS 投影面（monologue_events_to_frames）；经 enqueue 入流
    需要本 handler 注册（同 _apply_npc_act / _apply_entropy_inject 口径——
    no-op ⇒ 重放安全）。独白是自言自语的叙述记录，不改世界状态。
    """
    from sim.core.events import NpcMonologuePayload

    NpcMonologuePayload.model_validate(event.payload)  # schema 校验；无状态效果
    return ApplyResult(state=state)


def _apply_npc_chat(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """NPC_CHAT（批次 E1）：聊天行为记录，状态层 no-op（关系/记忆效应归 runtime）。

    同 _apply_npc_monologue 口径：no-op ⇒ 含 NPC_CHAT 与不含 NPC_CHAT 的同构
    序列 fold 出逐位一致的 state_hash（回放安全，C5）。
    """
    from sim.core.events import NpcChatPayload

    NpcChatPayload.model_validate(event.payload)  # schema 校验；无状态效果
    return ApplyResult(state=state)


def _apply_coin_grant(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """COIN_GRANT（批次 E3）：账单记录，余额归 runtime CoinLedger（重放安全 no-op）。"""
    from sim.core.events import CoinGrantPayload

    CoinGrantPayload.model_validate(event.payload)  # schema 校验；无状态效果
    return ApplyResult(state=state)


def _apply_fog_reveal(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """迷雾揭示折叠：no-op 状态层（裁 40-4：迷雾是事件即真相的观察者投影，
    不进 state_hash；揭示集由投影侧 fold_fog_reveal 按事件流重建——同
    _apply_npc_act 口径：注册 handler 即可重放，状态零变更）。"""
    return ApplyResult(state=state)


def _apply_fire_event(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """FIRE_*（批次 D5 接线）：火灾记录进事件日志，状态层 no-op。

    火格账本是 FireRuntime 实况内存态（同 NPC 需求）；世界状态不含火场
    （A8「火场中间态不入库」口径——事件材料足以重放观察面）。
    """
    return ApplyResult(state=state)


def _apply_structure_event(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """STRUCTURE_*（批次 E4 实况接线）：施工记录进事件日志，状态层 no-op。

    结构投影（structures 表）与占格（tile_changed）由 NpcStore 投影缝 /
    BuildRuntime 实况侧承担；世界态不含结构（同火场口径——事件材料足以
    重放观察面）。no-op ⇒ 重放安全（C5）。schema 校验随 kind 分派（M1 修复：
    畸形 payload 拒绝而非静默折算——同 chat/coin 口径）。
    """
    from sim.core.events import (
        StructureCheckpointPayload,
        StructureCollapsedPayload,
        StructureCompletedPayload,
        StructureRemovedPayload,
        StructureStartedPayload,
    )

    _STRUCTURE_VALIDATORS = {
        EventKind.STRUCTURE_STARTED: StructureStartedPayload,
        EventKind.STRUCTURE_CHECKPOINT: StructureCheckpointPayload,
        EventKind.STRUCTURE_COMPLETED: StructureCompletedPayload,
        EventKind.STRUCTURE_COLLAPSED: StructureCollapsedPayload,
        EventKind.STRUCTURE_REMOVED: StructureRemovedPayload,
    }
    model = _STRUCTURE_VALIDATORS.get(event.event_type)
    if model is not None:
        model.model_validate(event.payload)
    return ApplyResult(state=state)


def _apply_material_event(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """MATERIAL_*（E4 前置一并注册——事件族同源；余额投影归 NpcStore）。

    schema 校验（M1 修复）：MaterialMovedPayload 显式验证（畸形拒绝）。
    """
    from sim.core.events import MaterialMovedPayload

    MaterialMovedPayload.model_validate(event.payload)
    return ApplyResult(state=state)


def _apply_tile_changed(state: WorldState, event: WorldEvent, ctx: TickContext) -> ApplyResult:
    """TILE_CHANGED（批次 E4 启用，替换 M0 的 NotImplementedError 占位）：
    瓦片变更是表现/寻路面（TileMap frozen 几何由 BuildRuntime 实况重建），
    状态层 no-op（实体位置不在 tile 上、WorldState 无瓦片字段）。"""
    from sim.core.events import TileChangedPayload

    TileChangedPayload.model_validate(event.payload)
    return ApplyResult(state=state)


def build_default_bus() -> EventBus:
    """M0 默认事件总线（批次 B 增 NPC_ACT no-op——决策记录面）。"""
    bus = EventBus()
    bus.register(EventKind.WORLD_CREATE, _apply_world_create)
    bus.register(EventKind.MOVE, _apply_move)
    bus.register(EventKind.COMBAT_SCALE_CHANGE, _apply_combat_scale)
    bus.register(EventKind.ENTROPY_INJECT, _apply_entropy_inject)
    bus.register(EventKind.TILE_CHANGED, _apply_tile_changed)
    bus.register(EventKind.NPC_DEATH, _apply_npc_death)
    bus.register(EventKind.NPC_ACT, _apply_npc_act)
    bus.register(EventKind.NPC_MONOLOGUE, _apply_npc_monologue)
    bus.register(EventKind.NPC_CHAT, _apply_npc_chat)
    bus.register(EventKind.COIN_GRANT, _apply_coin_grant)
    bus.register(EventKind.STRUCTURE_STARTED, _apply_structure_event)
    bus.register(EventKind.STRUCTURE_CHECKPOINT, _apply_structure_event)
    bus.register(EventKind.STRUCTURE_COMPLETED, _apply_structure_event)
    bus.register(EventKind.STRUCTURE_COLLAPSED, _apply_structure_event)
    bus.register(EventKind.STRUCTURE_REMOVED, _apply_structure_event)
    bus.register(EventKind.MATERIAL_MOVED, _apply_material_event)
    bus.register(EventKind.FIRE_IGNITED, _apply_fire_event)
    bus.register(EventKind.FOG_REVEAL, _apply_fog_reveal)
    bus.register(EventKind.FIRE_EXTINGUISHED, _apply_fire_event)
    return bus
