"""sim.npc.sim_exec — NPC 决策的实况执行面（批次 B）。

NpcRuntime.tick 产出的 NPC_ACT 批次 → 可观察后果（C4 唯一写路径）：
每个动作都有「去做事的地方」的位移面——eat 去食摊、rest 回家、work 去农田、
request_chat 走向交谈对象、wander/move 哈希散布闲逛。到站后再决策原地停留
（goal == pos → 退化为闲逛，镇子不停摆）。

确定性账（C5）：目标解析是 (action, npc_id, tick, state) 的纯函数、无 RNG
状态流——重放时执行面不参与（WorldState 只由事件 fold），同事件序列逐位
一致不受执行面影响；执行面只在实况侧把决策翻译成事件。
效用矩阵不动（M2 定标内容常量、有测试钉）：实测分布 rest/chat/eat 占优、
wander 零票——本执行面让**全部动作族**都产生走动，镇子活性不依赖 wander 胜出。
"""

from __future__ import annotations

import hashlib

from sim.core.events import WorldEvent, move_event
from sim.core.world import WorldState
from sim.world.pathfinding import Pathfinder

# ---------------------------------------------------------------------------
# 意愿独白（批次 D2：NPC 开口）——节流常数
# ---------------------------------------------------------------------------

#: 同 NPC 两次 bubble 独白的最小间隔（tick；300 = 5 游戏分）。batch B 实测
#: 每 10 tick 一决策，50 人不节流每分钟可产 3000 条独白帧（刷屏+烧 WS）。
_MONOLOGUE_COOLDOWN_TICKS = 300

# ---------------------------------------------------------------------------
# 动作目的地（批次 B 内容面；坐标须在 linhe-town.json 可走格上）
# ---------------------------------------------------------------------------

#: eat → 药铺门前空地（镇上唯一的吃食处）
EAT_SITE: tuple[int, int] = (10, 15)
#: rest → 两宅门前（按 npc_id 哈希选一家；「家」概念随 M4 日程域细化）
REST_SITES: tuple[tuple[int, int], ...] = ((34, 13), (34, 39))
#: work → 农田中心
WORK_SITE: tuple[int, int] = (13, 35)


def _hash_u32(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[0:4], "big")


def wander_goal(seed: int, tick: int, npc_id: str, w: int, h: int) -> tuple[int, int]:
    """确定性闲逛目标：(seed, tick, npc_id) 哈希散布进 [0,w)×[0,h)。

    同输入恒同输出（无随机流）；不同 npc_id 散布开（sha256 雪崩）。
    """
    digest = _hash_u32(seed, tick, npc_id)
    return (digest % w, (digest // w) % h)


def _resolve_goal(
    state: WorldState, npc_id: str, action: str, *, seed: int, tick: int, w: int, h: int
) -> tuple[int, int] | None:
    """动作 → 目的地（纯函数）；None = 该动作无位移面。"""
    if action in ("wander", "move"):
        return wander_goal(seed, tick, npc_id, w, h)
    if action == "eat":
        return EAT_SITE
    if action == "rest":
        return REST_SITES[_hash_u32(npc_id) % len(REST_SITES)]
    if action == "work":
        return WORK_SITE
    if action == "request_chat":
        others = sorted(eid for eid in state.entities if eid != npc_id)
        if not others:
            return wander_goal(seed, tick, npc_id, w, h)
        target = others[_hash_u32(npc_id, tick) % len(others)]
        return state.entities[target].pos
    return None


def plan_npc_move(
    state: WorldState,
    npc_id: str,
    action: str,
    pathfinder: Pathfinder,
    *,
    seed: int,
    tick: int,
) -> WorldEvent | None:
    """单个动作 → move_event（去「做事的地方」）；不该动/动不了 → None。

    - 未知实体 / 在途（剩余 path 未耗尽）→ None（防抖）；
    - goal == 当前位（已到站）→ 退化为闲逛目标（站桩兜底，镇子不停摆）；
    - 不可达 → 退化为闲逛；再不可达 → None（fail-soft，不刷错误日志）。
    返回的 move_event **不入流**（无 enqueue）——调用方决定入流时机与 tick。
    """
    entity = state.entities.get(npc_id)
    if entity is None or entity.path:
        return None
    w, h = pathfinder.tile_map.width, pathfinder.tile_map.height
    goal = _resolve_goal(state, npc_id, action, seed=seed, tick=tick, w=w, h=h)
    if goal is None:
        return None
    start = entity.pos
    if goal == start:
        goal = wander_goal(seed, tick, npc_id, w, h)
        if goal == start:
            return None
    try:
        path = pathfinder.find(start, goal)
    except ValueError:
        # 目的地不可达 → 退化为闲逛（离散布点也可能落进围合区）
        fallback = wander_goal(seed, tick, npc_id, w, h)
        if fallback == start:
            return None
        try:
            path = pathfinder.find(start, fallback)
        except ValueError:
            return None
    return move_event(
        tick=0,  # tick 由调用方改写（issue 时点）；工厂校验 path 完整性
        actor_id=npc_id,
        start=start,
        goal=path[-1],
        path=path,
    )


def npc_events_for_tick(
    runtime: object,
    state: WorldState,
    tick: int,
    pathfinder: Pathfinder,
    *,
    seed: int,
    monologue_last: dict[str, int] | None = None,
) -> list[WorldEvent]:
    """一个决策节拍的事件批次：NpcRuntime.tick → NPC_ACT 批次 + MOVE 交错。

    每个活跃 NPC 恰一条 NPC_ACT（决策记录）；移动类决策紧跟同 NPC 的
    move_event（日志可读序：ACT → MOVE）。runtime.tick 返回的意愿独白
    （NPC_MONOLOGUE，M4-B3 通路）按 `monologue_last` 节流后原样并入批次
    （batch D2：NPC 开口——冷却 300 tick 内同 NPC 不再开口，防刷屏）。
    `monologue_last`：{npc_id: 上次发表 tick}，调用方持有（跨拍记忆态，
    确定性不受影响——节流只发生在实况侧，不进重放面）。

    runtime 参数是 NpcRuntime（object 注解避免内核↔npc 域反向依赖——
    实际调用点在 main.py 装配层）。
    """
    acts = runtime.tick(tick)  # type: ignore[attr-defined]
    events: list[WorldEvent] = []
    for event in acts:
        if event.event_type.value == "npc.monologue":
            npc_id = str(event.payload.get("npc_id", ""))
            if monologue_last is not None:
                last = monologue_last.get(npc_id, -_MONOLOGUE_COOLDOWN_TICKS)
                if tick - last < _MONOLOGUE_COOLDOWN_TICKS:
                    continue  # 冷却期内：静默丢弃（表现面节流，非世界真相）
                monologue_last[npc_id] = tick
            # 意愿独白的呈现面转换：runtime 产 thought（M4-B3 硬编码），但村民
            # 的意愿挣扎是**外在可观察面**（路人可见的嘟囔）——投影为 bubble
            # （广播面）。thought 私密面归 chenmo L2（driver 侧不经此路）。
            # 事件入流前替换 payload：内容逐位不变，仅 form 呈现档（见 M5-K8
            # 投递面契约：bubble=广播）。frozen 事件用 model_copy。
            if event.payload.get("form") == "thought":
                event = event.model_copy(
                    update={"payload": {**event.payload, "form": "bubble"}}
                )
            events.append(event)
            continue
        if event.event_type.value != "npc.act":
            continue
        events.append(event)
        mv = plan_npc_move(
            state,
            str(event.payload.get("npc_id", "")),
            str(event.payload.get("action", "")),
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
