"""戏内名称与内部目标之间的纯解析；不读取档案或修改世界。"""

import re
from collections import Counter
from collections.abc import Mapping

from sim.agent.gate import _TARGET_MAX_DISTANCE
from sim.content.animals import ANIMALS
from sim.core.world import WorldState
from sim.world.economy import _GOOD_INDEX, name_index


def resolve_actor_target(
    raw: str | None,
    state: WorldState,
    *,
    display_names: Mapping[str, str],
    actor_id: str = "chenmo",
) -> str | None:
    """精确解析唯一活体名；已有内部键继续走原 gate 的执行校验。"""
    if raw is None:
        return None
    if raw in state.entities:
        return raw
    matches = [entity_id for entity_id in state.entities if display_names.get(entity_id) == raw]
    if len(matches) != 1 or matches[0] == actor_id:
        return None
    actor = state.entities.get(actor_id)
    if actor is None:
        return None
    target = state.entities[matches[0]]
    distance = abs(actor.pos[0] - target.pos[0]) + abs(actor.pos[1] - target.pos[1])
    if distance > _TARGET_MAX_DISTANCE:
        return None
    return matches[0]


def resolve_good_target(raw: str | None) -> str | None:
    """精确解析货名，同时保留现有内部 ID 输入。"""
    if raw in _GOOD_INDEX:
        return raw
    good = name_index().get(raw) if raw is not None else None
    return good.id if good is not None else None


def nearby_actor_names(
    state: WorldState, *, display_names: Mapping[str, str], actor_id: str = "chenmo"
) -> tuple[str, ...]:
    """返回曼哈顿范围内最近十二名可唯一指认的人；不输出内部键。"""
    actor = state.entities.get(actor_id)
    if actor is None:
        return ()
    names = {
        entity_id: name for entity_id in state.entities if (name := display_names.get(entity_id))
    }
    counts = Counter(names.values())
    candidates = []
    for entity_id, name in names.items():
        if entity_id == actor_id or entity_id in ANIMALS or counts[name] != 1:
            continue
        if name in state.entities or re.search(r"villager_\d+", name):
            continue
        position = state.entities[entity_id].pos
        distance = abs(position[0] - actor.pos[0]) + abs(position[1] - actor.pos[1])
        if distance <= _TARGET_MAX_DISTANCE:
            candidates.append((distance, entity_id, name))
    return tuple(name for _, _, name in sorted(candidates)[:12])
