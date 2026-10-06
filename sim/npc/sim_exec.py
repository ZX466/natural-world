"""sim.npc.sim_exec — NPC 决策的实况执行面（批次 B）。

NpcRuntime.tick 产出的 NPC_ACT 批次 → 可观察后果（C4 唯一写路径）：
- wander/move → 确定性目标格 + Pathfinder 求路 → move_event（MOVE handler 真驱动）；
- eat/rest/work/request_chat → 批次 B 无执行面（事件本身已入流，记录面）。

确定性账（C5）：闲逛目标 = (world_seed, tick, npc_id) 的哈希散布，**无 RNG 状态
流**——重放时执行面不参与（WorldState 只由事件 fold），同事件序列逐位一致不受
执行面影响；执行面只在实况侧把决策翻译成事件。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from sim.core.events import WorldEvent, move_event, npc_act_event
from sim.core.world import WorldState
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder


def wander_goal(seed: int, tick: int, npc_id: str, w: int, h: int) -> tuple[int, int]:
    """确定性闲逛目标：(seed, tick, npc_id) 哈希散布进 [0,w)×[0,h)。

    同输入恒同输出（无随机流）；不同 npc_id 散布开（sha256 雪崩）。
    """
    digest = hashlib.sha256(f"{seed}:{tick}:{npc_id}".encode()).digest()
    gx = int.from_bytes(digest[0:4], "big") % w
    gy = int.from_bytes(digest[4:8], "big") % h
    return (gx, gy)


def plan_npc_move(
    state: WorldState,
    npc_id: str,
    action: str,
    pathfinder: Pathfinder,
    *,
    seed: int,
    tick: int,
) -> WorldEvent | None:
    """单个移动类动作 → move_event；不该动/动不了 → None（fail-soft）。

    - 仅 wander/move 两动作有位移面（eat/rest/work/request_chat 记录即可）；
    - 未知实体 / 在途（剩余 path 未耗尽）→ None（防抖）；
    - wander 目标 = wander_goal；不可达/不可走 → None（静默跳过，不刷错误日志）。
    返回的 move_event **不入流**（无 enqueue）——调用方决定入流时机与 tick。
    """
    if action not in ("wander", "move"):
        return None
    entity = state.entities.get(npc_id)
    if entity is None or entity.path:
        return None
    w, h = pathfinder.tile_map.width, pathfinder.tile_map.height
    goal = wander_goal(seed, tick, npc_id, w, h)
    if goal == entity.pos:
        return None
    start = entity.pos
    try:
        path = pathfinder.find(start, goal)
    except ValueError:
        return None
    return move_event(
        tick=0,  # tick 由调用方改写（issue 时点）；工厂校验 path 完整性
        actor_id=npc_id,
        start=start,
        goal=goal,
        path=path,
    )


def npc_events_for_tick(
    runtime: object,
    state: WorldState,
    tick: int,
    pathfinder: Pathfinder,
    *,
    seed: int,
) -> list[WorldEvent]:
    """一个决策节拍的事件批次：NpcRuntime.tick → NPC_ACT 批次 + MOVE 交错。

    每个活跃 NPC 恰一条 NPC_ACT（决策记录）；移动类决策紧跟同 NPC 的
    move_event（日志可读序：ACT → MOVE）。runtime 参数是 NpcRuntime
    （object 注解避免内核↔npc 域反向依赖——实际调用点在 main.py 装配层）。
    """
    acts = runtime.tick(tick)  # type: ignore[attr-defined]
    events: list[WorldEvent] = []
    for act in acts:
        if act.event_type.value != "npc.act":
            continue
        events.append(act)
        mv = plan_npc_move(
            state,
            str(act.payload.get("npc_id", "")),
            str(act.payload.get("action", "")),
            pathfinder,
            seed=seed,
            tick=tick,
        )
        if mv is not None:
            events.append(_retick(mv, tick))
    return events


def _retick(event: WorldEvent, tick: int) -> WorldEvent:
    """move_event 以 tick=0 占位构造后改写为本节拍 tick（frozen → model_copy）。"""
    return event.model_copy(update={"tick": tick})
