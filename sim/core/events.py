"""事件契约 — WorldEvent（frozen）与事件种类注册表（m0-core.md §4）。

落库形状对齐 opencode 的 EventStore（event_type/actor_id/parent_seq/witnesses/entropy_ref）。
seq 由持久层分配（分支内自增），WorldEvent 不携带 seq。

payload schema 化（codex 评审意见 7，2026-09-19 采纳）：每个 kind 有对应
pydantic payload 模型（extra="forbid"），构造事件必须走工厂函数——事件日志
是戏外审计资产，LLM/玩家输入不可夹带任意键值。
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator


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
    # ---- M4（m4-plan 批次 D2 / 裁 14-2）----
    STRUCTURE_STARTED = "structure.started"
    STRUCTURE_CHECKPOINT = "structure.checkpoint"
    STRUCTURE_COMPLETED = "structure.completed"
    STRUCTURE_COLLAPSED = "structure.collapsed"
    STRUCTURE_REMOVED = "structure.removed"
    MATERIAL_MOVED = "material.moved"
    # ---- M5（m5-k8 意愿独白 S2C）----
    #: NPC 意愿独白（§8 三形态的产码来源）。**先落事件流=可重放**（§14 世界真相
    #: 进事件日志）→ WS 侧 `ws.monologue_events_to_frames` 投影成独立 monologue
    #: 帧，按 form 路由（bubble/plan 广播；thought 定向本人，见 ws.py 投递面契约）。
    NPC_MONOLOGUE = "npc.monologue"


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


class NpcMonologuePayload(BaseModel):
    """NPC 意愿独白（M5-K8，§8 独白三形态产码；§10 四档表现）。

    **字段白名单（X 系出戏边界，extra="forbid" 强制）**：只有 npc_id/form/content。
    - form ∈ bubble|thought|plan（§8 三形态；投递面路由见 ws.py 契约）；
    - content = 第一人称世界内语言（will.py 模板词面，**无数值无系统词**）；
    - 冲突度 score / band 档位号 / w₁-w₄ 权重**永不进本载荷**（元信息铁律：
      band 是装配层选模板的输入，落库只留表现文本）。band≥1 才有本事件。

    defers 语义不在此载荷（先做别的再绕回来 → 走 K7 的 plan 账本，见
    sim/npc/plan_view.py），故不在事件面重复表达。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    npc_id: str
    form: str = Field(pattern=r"^(bubble|thought|plan)$")
    content: str = Field(min_length=1, max_length=512)


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


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$"
_ID = Annotated[str, Field(min_length=1, max_length=64, pattern=_ID_PATTERN)]
_OPTIONAL_ID = Annotated[
    str,
    Field(max_length=64, pattern=r"^(?:|[A-Za-z0-9][A-Za-z0-9_.:-]{0,63})$"),
]
_SLUG = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
_REF = Annotated[
    str,
    Field(min_length=3, max_length=128, pattern=r"^[a-z]+:[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$"),
]
_TILE_COORD = Annotated[int, Field(strict=True, ge=0, lt=4096)]
_DURATION_TICKS = Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]


def _reject_bool(value: Any) -> Any:
    if isinstance(value, bool):
        msg = "bool 不可作数值"
        raise ValueError(msg)
    return value


_UNIT_FLOAT = Annotated[
    float,
    BeforeValidator(_reject_bool),
    Field(ge=0.0, le=1.0, allow_inf_nan=False),
]
_POSITIVE_FLOAT = Annotated[
    float,
    BeforeValidator(_reject_bool),
    Field(gt=0.0, allow_inf_nan=False),
]

StructureCollapseCause = Literal["decay", "damage", "support_lost"]
StructureRemoveReason = Literal["demolished", "cleanup"]
MaterialMoveReason = Literal[
    "build_reserved",
    "build_consumed",
    "build_refunded",
    "demolish_yield",
]


class StructureStartedPayload(BaseModel):
    """施工开始：结构拓扑与计划输入（裁 14-2 ①/②/④）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    structure_id: _ID
    tiles: tuple[tuple[_TILE_COORD, _TILE_COORD], ...]
    kind: _SLUG
    material: _SLUG
    owner_id: _OPTIONAL_ID = ""
    built_by: _OPTIONAL_ID = ""
    load_bearing: bool = False
    supported_by: tuple[_ID, ...] = ()
    planned_duration_ticks: _DURATION_TICKS
    recipe_id: _ID
    recipe_version: _ID
    build_rule_version: _ID

    @field_validator("tiles")
    @classmethod
    def _canonical_tiles(cls, value: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
        if not value:
            msg = "tiles 不得为空"
            raise ValueError(msg)
        canonical = tuple(sorted(value))
        if len(set(canonical)) != len(canonical):
            msg = "tiles 不得重复"
            raise ValueError(msg)
        return canonical

    @field_validator("supported_by")
    @classmethod
    def _canonical_supports(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        canonical = tuple(sorted(value))
        if len(set(canonical)) != len(canonical):
            msg = "supported_by 不得重复"
            raise ValueError(msg)
        return canonical

    @model_validator(mode="after")
    def _reject_self_support(self) -> StructureStartedPayload:
        if self.structure_id in self.supported_by:
            msg = "结构不得支撑自身"
            raise ValueError(msg)
        return self


class StructureCheckpointPayload(BaseModel):
    """施工检查点：累计进度/质量/完整度（每游戏日一次，裁 14-2 ②）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    structure_id: _ID
    progress: _UNIT_FLOAT
    quality: _UNIT_FLOAT
    integrity: _UNIT_FLOAT
    build_rule_version: _ID


class StructureCompletedPayload(BaseModel):
    """施工完成：终态质量与完整度。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    structure_id: _ID
    quality: _UNIT_FLOAT
    integrity: _UNIT_FLOAT


class StructureCollapsedPayload(BaseModel):
    """结构坍塌：领域因果；matter 熵态仍由 MATTER_COLLAPSE 折叠。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    structure_id: _ID
    cause: StructureCollapseCause
    support_path: tuple[_ID, ...] = ()
    integrity: _UNIT_FLOAT = 0.0

    @field_validator("support_path")
    @classmethod
    def _unique_support_path(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            msg = "support_path 不得重复"
            raise ValueError(msg)
        return value


class StructureRemovedPayload(BaseModel):
    """结构移除：主动拆除或清理；坍塌不走本事件。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    structure_id: _ID
    reason: StructureRemoveReason


class MaterialMovedPayload(BaseModel):
    """材料转移：来源→去向，守恒账本的唯一事件形态（裁 14-2 ⑦）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transfer_id: _ID
    material_id: _ID
    quantity: _POSITIVE_FLOAT
    from_ref: _REF
    to_ref: _REF
    reason: MaterialMoveReason
    structure_id: _OPTIONAL_ID = ""
    recipe_id: _OPTIONAL_ID = ""

    @model_validator(mode="after")
    def _reject_self_transfer(self) -> MaterialMovedPayload:
        if self.from_ref == self.to_ref:
            msg = "材料转移来源与去向不得相同"
            raise ValueError(msg)
        return self


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


def npc_monologue_event(
    tick: int,
    npc_id: str,
    form: str,
    content: str,
    branch_id: str = "main",
) -> WorldEvent:
    """意愿独白事件（M5-K8）。form ∈ bubble|thought|plan；content 第一人称叙事。

    唯一构造入口：payload schema（NpcMonologuePayload）在此强制——数值/档位号
    无法夹带（extra="forbid"）。band≥1 才有本事件（调用方 will 域保证）。
    actor_id 填 npc_id（本文事件的主体就是该 NPC）；不设 target/witnesses
    （独白是自言自语，供渲染与重放，非社会传播）。
    """
    p = NpcMonologuePayload(npc_id=npc_id, form=form, content=content)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.NPC_MONOLOGUE,
        actor_id=npc_id,
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
    witnesses: Sequence[str] | None = None,
    branch_id: str = "main",
) -> WorldEvent:
    """隐藏属性浮现事件（E1）：attr_ids = 新进触发窗口的 delta（X4 修订：仅戏外主键，
    descriptors/label/triggered 词面永不入事件——extra=forbid 硬拒）。

    witnesses 收窄（codex F1 advisory + S5 复核）：只接受 Sequence[str]——
    str/bytes 是 Sequence 但元素是字符，dict 可迭代出键，都会洗白成见证人
    （store 行级校验是纵深第二道，工厂层 fail-closed 同纪律）。
    """
    if witnesses is not None:
        if isinstance(witnesses, (str, bytes)) or not isinstance(witnesses, Sequence):
            msg = f"witnesses 必须是 Sequence[str]（禁 str/bytes/dict 洗白）: {witnesses!r}"
            raise TypeError(msg)
        if not all(isinstance(w, str) for w in witnesses):
            msg = f"witnesses 元素必须全是 str: {witnesses!r}"
            raise TypeError(msg)
    p = HiddenEmergePayload(npc_id=npc_id, attr_ids=attr_ids)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.NPC_HIDDEN_EMERGE,
        payload=p.model_dump(mode="json"),
        witnesses=list(witnesses or []),
    )


# ---- M4 工厂（建造域；裁 14-2）----


def _reject_washed_sequence(value: Any, field_name: str) -> None:
    if isinstance(value, (str, bytes, dict)) or not isinstance(value, Sequence):
        msg = f"{field_name} 必须是序列（禁 str/bytes/dict 洗白）: {value!r}"
        raise TypeError(msg)


def structure_started_event(
    tick: int,
    *,
    structure_id: str,
    tiles: Sequence[tuple[int, int]],
    kind: str,
    material: str,
    planned_duration_ticks: int,
    recipe_id: str,
    recipe_version: str,
    build_rule_version: str,
    owner_id: str = "",
    built_by: str = "",
    load_bearing: bool = False,
    supported_by: Sequence[str] = (),
    branch_id: str = "main",
) -> WorldEvent:
    """施工开始事件；tiles/支撑在工厂层先拒可迭代洗白。"""
    _reject_washed_sequence(tiles, "tiles")
    _reject_washed_sequence(supported_by, "supported_by")
    payload = StructureStartedPayload(
        structure_id=structure_id,
        tiles=tuple(tiles),
        kind=kind,
        material=material,
        owner_id=owner_id,
        built_by=built_by,
        load_bearing=load_bearing,
        supported_by=tuple(supported_by),
        planned_duration_ticks=planned_duration_ticks,
        recipe_id=recipe_id,
        recipe_version=recipe_version,
        build_rule_version=build_rule_version,
    )
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.STRUCTURE_STARTED,
        payload=payload.model_dump(mode="json"),
    )


def structure_checkpoint_event(
    tick: int,
    *,
    structure_id: str,
    progress: float,
    quality: float,
    integrity: float,
    build_rule_version: str,
    branch_id: str = "main",
) -> WorldEvent:
    payload = StructureCheckpointPayload(
        structure_id=structure_id,
        progress=progress,
        quality=quality,
        integrity=integrity,
        build_rule_version=build_rule_version,
    )
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.STRUCTURE_CHECKPOINT,
        payload=payload.model_dump(mode="json"),
    )


def structure_completed_event(
    tick: int,
    *,
    structure_id: str,
    quality: float,
    integrity: float,
    branch_id: str = "main",
) -> WorldEvent:
    payload = StructureCompletedPayload(
        structure_id=structure_id,
        quality=quality,
        integrity=integrity,
    )
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.STRUCTURE_COMPLETED,
        payload=payload.model_dump(mode="json"),
    )


def structure_collapsed_event(
    tick: int,
    *,
    structure_id: str,
    cause: StructureCollapseCause,
    support_path: Sequence[str] = (),
    integrity: float = 0.0,
    branch_id: str = "main",
) -> WorldEvent:
    _reject_washed_sequence(support_path, "support_path")
    payload = StructureCollapsedPayload(
        structure_id=structure_id,
        cause=cause,
        support_path=tuple(support_path),
        integrity=integrity,
    )
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.STRUCTURE_COLLAPSED,
        payload=payload.model_dump(mode="json"),
    )


def structure_removed_event(
    tick: int,
    *,
    structure_id: str,
    reason: StructureRemoveReason,
    branch_id: str = "main",
) -> WorldEvent:
    payload = StructureRemovedPayload(structure_id=structure_id, reason=reason)
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.STRUCTURE_REMOVED,
        payload=payload.model_dump(mode="json"),
    )


def material_moved_event(
    tick: int,
    *,
    transfer_id: str,
    material_id: str,
    quantity: float,
    from_ref: str,
    to_ref: str,
    reason: MaterialMoveReason,
    structure_id: str = "",
    recipe_id: str = "",
    branch_id: str = "main",
) -> WorldEvent:
    payload = MaterialMovedPayload(
        transfer_id=transfer_id,
        material_id=material_id,
        quantity=quantity,
        from_ref=from_ref,
        to_ref=to_ref,
        reason=reason,
        structure_id=structure_id,
        recipe_id=recipe_id,
    )
    return WorldEvent(
        branch_id=branch_id,
        tick=tick,
        event_type=EventKind.MATERIAL_MOVED,
        payload=payload.model_dump(mode="json"),
    )
