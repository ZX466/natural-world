"""sim.npc.model — NPC 聚合根（M2-A1 架构稿 §1，DESIGN §13）。

从持久层 ORM 行构造 frozen 数据类；一切变更走 `apply_*` 返回新实例
（immutability 规约）。不碰 SQL——持久化在 sim/core/persistence/。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from pydantic import BaseModel, ConfigDict


class NeedsError(ValueError):
    """需求权重/取值非法。"""


@dataclass(frozen=True)
class Need:
    """单项需求（DESIGN §13：带权重，效用输入之一）。"""

    name: str
    value: float  # 0..1，1=最紧迫
    weight: float  # 效用权重 >0

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise NeedsError(f"need {self.name!r} value 越界: {self.value}")
        if self.weight <= 0:
            raise NeedsError(f"need {self.name!r} weight 必须 >0: {self.weight}")

    def advanced(self, delta_per_tick: float, ticks: int = 1) -> Need:
        """tick 推进后的新需求（clip 到 [0,1]，frozen 返回新实例）。"""
        raw = self.value + delta_per_tick * ticks
        return replace(self, value=min(1.0, max(0.0, raw)))


@dataclass(frozen=True)
class NpcProfileData:
    """NPC 可见属性聚合（npc_profiles 行的内存态；隐藏档在 hidden）。"""

    npc_id: str
    name: str
    species: str = "human"
    occupation: str = ""
    ocean: tuple[float, float, float, float, float] = (50.0, 50.0, 50.0, 50.0, 50.0)  # OCEAN 0-100
    pad: tuple[float, float, float] = (0.0, 0.0, 0.0)  # PAD -1..1
    needs: tuple[Need, ...] = ()
    skills: dict[str, int] = field(default_factory=dict)
    lod: int = 1  # 0=统计 1=效用 2=LLM（变更走 NPC_LOD_CHANGE 事件，不直改）

    def utility_scores(self) -> dict[str, float]:
        """需求加权 urgency（L1 效用输入；utility.py 消费）。"""
        return {n.name: n.value * n.weight for n in self.needs}

    def with_needs(self, needs: tuple[Need, ...]) -> NpcProfileData:
        return replace(self, needs=needs)

    def with_lod(self, lod: int) -> NpcProfileData:
        if lod not in (0, 1, 2):
            raise NeedsError(f"lod 非法: {lod}")
        return replace(self, lod=lod)


def needs_from_json(raw: str) -> tuple[Need, ...]:
    """npc_profiles.needs JSON 文本 → 需求元组（边界校验）。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NeedsError(f"needs JSON 非法: {exc}") from exc
    if not isinstance(data, list):
        raise NeedsError("needs JSON 必须是数组")
    needs: list[Need] = []
    for item in data:
        if not isinstance(item, dict):
            raise NeedsError(f"needs 项必须为对象: {item!r}")
        needs.append(
            Need(
                name=str(item.get("name", "")),
                value=float(item.get("value", 0.0)),
                weight=float(item.get("weight", 1.0)),
            )
        )
    return tuple(needs)


class NpcAction(BaseModel):
    """NPC_ACT 事件 payload（白名单见 sim/npc/actions.py；codex M2-S2 审查对象）。"""

    model_config = ConfigDict(frozen=True)

    npc_id: str
    action: str  # 必须在 ACTION_WHITELIST 内
    target: str = ""
    tick: int
