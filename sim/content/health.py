"""名角健康内容与幂等创世播种；运行时变更仍只走健康事件。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sim.core.persistence.models import NpcHealth, NpcProfile
from sim.npc.hidden import HiddenCategory


@dataclass(frozen=True)
class HealthDefinition:
    npc_id: str
    code: str
    category: HiddenCategory
    label: str
    severity: float = 0.2
    hidden: bool = False
    descriptors: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()


HEALTH_SEEDS = (
    HealthDefinition("chenmo", "wrist_strain", "old_injury", "腕上旧伤", descriptors=("腕上旧伤",)),
    HealthDefinition(
        "chenmo",
        "night_unease",
        "trauma",
        "入夜心悸",
        hidden=True,
        descriptors=("入夜心悸", "一到夜里心便发慌"),
        triggers=("夜深了",),
    ),
    HealthDefinition(
        "villager_01",
        "shoulder_injury",
        "old_injury",
        "肩头旧伤",
        hidden=True,
        descriptors=("肩头旧伤", "旧伤牵着肩膀"),
        triggers=("伤处疼得厉害",),
    ),
    HealthDefinition(
        "villager_02",
        "night_fear",
        "trauma",
        "暗夜惊惧",
        hidden=True,
        descriptors=("暗夜惊惧", "夜里总觉得心慌"),
        triggers=("夜深了",),
    ),
    HealthDefinition(
        "villager_03", "wrist_strain", "old_injury", "手腕劳伤", descriptors=("手腕劳伤",)
    ),
    HealthDefinition(
        "villager_03",
        "dusk_unease",
        "trauma",
        "暮色不安",
        hidden=True,
        descriptors=("暮色不安", "天一黑心里就发紧"),
        triggers=("天色暗下来了",),
    ),
)

_LABELS: dict[HiddenCategory, str] = {
    "disease": "身体不适",
    "old_injury": "磕碰伤处",
    "addiction": "难戒的习惯",
    "disability": "行动不便",
    "trauma": "心中惊悸",
}


def health_definition(npc_id: str, code: str, category: HiddenCategory) -> HealthDefinition:
    for definition in HEALTH_SEEDS:
        if (definition.npc_id, definition.code) == (npc_id, code):
            if definition.category != category:
                raise ValueError("health category does not match content code")
            return definition
    label = _LABELS[category]
    return HealthDefinition(npc_id, code, category, label, descriptors=(label,))


async def seed_health(
    session_factory: async_sessionmaker[AsyncSession], *, branch_id: str = "main"
) -> int:
    """只补本分支现有角色的缺项，不覆盖事件投影，不复活人物。"""
    async with session_factory.begin() as session:
        profiles = set(
            await session.scalars(select(NpcProfile.id).where(NpcProfile.branch_id == branch_id))
        )
        existing = set(
            (
                await session.execute(
                    select(NpcHealth.npc_id, NpcHealth.code).where(NpcHealth.branch_id == branch_id)
                )
            ).all()
        )
        missing = [
            d for d in HEALTH_SEEDS if d.npc_id in profiles and (d.npc_id, d.code) not in existing
        ]
        for definition in missing:
            session.add(
                NpcHealth(
                    branch_id=branch_id,
                    npc_id=definition.npc_id,
                    code=definition.code,
                    category=definition.category,
                    label=definition.label,
                    severity=definition.severity,
                    hidden=definition.hidden,
                    descriptors=json.dumps(definition.descriptors, ensure_ascii=False),
                    trigger_conditions=json.dumps(definition.triggers, ensure_ascii=False),
                    created_at_tick=0,
                )
            )
        return len(missing)
