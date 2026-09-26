"""事件写入前的行级校验（M2-D3，codex M2-S2/S3 MEDIUM ①）。

背景：`SqlEventStore.append()` 直接消费裸 dict，payload/actor/witnesses 不经
`extra="forbid"` 的 pydantic 模型校验 → 实测可写入夹带字段（smuggled params）
与伪造 witnesses（codex 评审 MEDIUM ①）。本模块把「事件行 = 已校验形状」这道
关补在**落库前**，与 `sim/core/events.py` 的 payload 模型同源（唯一 schema 真相）。

范围与语义：
- `event_type` 必须是已注册 `EventKind`（未知 → 拒绝；新增 kind 须同步登记模型）。
- `payload` 必须过对应 payload 模型（`extra="forbid"` 拒绝夹带键）。
- `NPC_ACT` 追加**动作白名单 + payload 键白名单**校验（`sim/npc/actions.py`）——
  堵住「白名单动作夹带非法 params」的缝。
- `witnesses` 必须是 ``list[str]``（非 str 元素 / 非 list → 拒绝）。
- `actor_id`/`target_id`/`entropy_ref` 类型校验。

不改变 `WorldEvent` 工厂（架构域）：工厂仍经模型构造；本模块只守 SQL 入口。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from sim.core.events import (
    CombatScaleChangePayload,
    EntropyInjectPayload,
    EventKind,
    HiddenEmergePayload,
    MaterialMovedPayload,
    MatterPayload,
    MovePayload,
    NpcActPayload,
    NpcLodChangePayload,
    StructureCheckpointPayload,
    StructureCollapsedPayload,
    StructureCompletedPayload,
    StructureRemovedPayload,
    StructureStartedPayload,
    TileChangedPayload,
    WorldCreatePayload,
)
from sim.npc.actions import is_action_allowed, payload_keys_allowed


class EventValidationError(ValueError):
    """事件行未过 schema/白名单校验（拒绝落库）。"""


#: kind → payload 模型（唯一 schema 真相源；新 kind 必须在此登记）。
PAYLOAD_MODELS: dict[EventKind, type[BaseModel]] = {
    EventKind.WORLD_CREATE: WorldCreatePayload,
    EventKind.MOVE: MovePayload,
    EventKind.COMBAT_SCALE_CHANGE: CombatScaleChangePayload,
    EventKind.ENTROPY_INJECT: EntropyInjectPayload,
    EventKind.TILE_CHANGED: TileChangedPayload,
    EventKind.NPC_LOD_CHANGE: NpcLodChangePayload,
    EventKind.NPC_ACT: NpcActPayload,
    EventKind.MATTER_DECAY: MatterPayload,
    EventKind.MATTER_DAMAGE: MatterPayload,
    EventKind.MATTER_BUILD: MatterPayload,
    EventKind.MATTER_COLLAPSE: MatterPayload,
    EventKind.NPC_HIDDEN_EMERGE: HiddenEmergePayload,
    EventKind.STRUCTURE_STARTED: StructureStartedPayload,
    EventKind.STRUCTURE_CHECKPOINT: StructureCheckpointPayload,
    EventKind.STRUCTURE_COMPLETED: StructureCompletedPayload,
    EventKind.STRUCTURE_COLLAPSED: StructureCollapsedPayload,
    EventKind.STRUCTURE_REMOVED: StructureRemovedPayload,
    EventKind.MATERIAL_MOVED: MaterialMovedPayload,
}


def validate_store_row(row: dict[str, Any]) -> None:
    """校验一条 store 行（`WorldEvent.to_store_dict()` 形状）；不合法即抛。

    抛 ``EventValidationError``（含 event_type 与原因），由 `append` 传播 →
    调用方（同事务）回滚，杜绝半写与夹带。
    """
    raw_kind = row.get("event_type")
    try:
        kind = EventKind(raw_kind)
    except ValueError as exc:
        raise EventValidationError(f"未知事件种类: {raw_kind!r}") from exc

    payload = row.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        msg = f"{kind.value}: payload 必须是对象，得到 {type(payload).__name__}"
        raise EventValidationError(msg)

    model = PAYLOAD_MODELS.get(kind)
    if model is None:
        raise EventValidationError(f"未登记 payload 模型的事件种类: {kind.value}")
    try:
        validated = model.model_validate(payload)
    except ValidationError as exc:
        raise EventValidationError(f"{kind.value}: payload 校验失败: {exc}") from exc

    if kind is EventKind.NPC_ACT:
        _validate_npc_act(validated)

    _validate_witnesses(row.get("witnesses"))
    for field_name in ("actor_id", "target_id", "entropy_ref"):
        _validate_optional_str(row.get(field_name), field_name)


def _validate_npc_act(payload: BaseModel) -> None:
    """NPC_ACT 白名单双检：动作在册且 params 键 ⊆ 该动作允许键。"""
    if not isinstance(payload, NpcActPayload):
        msg = f"NPC_ACT payload 模型异常: {type(payload).__name__}"
        raise EventValidationError(msg)
    if not is_action_allowed(payload.action):
        raise EventValidationError(f"npc.act: 非白名单动作: {payload.action!r}")
    if not payload_keys_allowed(payload.action, set(payload.params)):
        raise EventValidationError(
            f"npc.act: 动作 {payload.action!r} 的 params 键越界: {sorted(payload.params)}"
        )


def _validate_witnesses(witnesses: Any) -> None:
    # 缺省（None）视作空见证人；一旦给出则必须是 list[str]（拒绝伪造/夹带）。
    if witnesses is None:
        return
    if not isinstance(witnesses, list) or not all(isinstance(w, str) for w in witnesses):
        raise EventValidationError(f"witnesses 必须是 list[str]，得到 {witnesses!r}")


def _validate_optional_str(value: Any, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise EventValidationError(f"{field_name} 必须是 str 或 None，得到 {value!r}")
