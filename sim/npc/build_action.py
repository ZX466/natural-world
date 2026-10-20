"""共享建造执行翻译：到站才开工，失败退还工料，结果必经事件流。"""

from sim.agent.build_exec import BuildRuntime
from sim.core.events import WorldEvent, coin_grant_event, npc_monologue_event
from sim.core.world import WorldState
from sim.world.economy import CoinLedger


def build_action_events(
    state: WorldState,
    npc_id: str,
    pos: tuple[int, int],
    *,
    tick: int,
    runtime: BuildRuntime,
    ledger: CoinLedger,
    form: str = "bubble",
) -> list[WorldEvent]:
    entity = state.entities.get(npc_id)
    if entity is None:
        return []

    def say(content: str) -> list[WorldEvent]:
        return [npc_monologue_event(tick + 1, npc_id, form=form, content=content)]

    if entity.path or abs(entity.pos[0] - pos[0]) + abs(entity.pos[1] - pos[1]) > 4:
        return say("得先走到跟前，才能搭棚子。")
    cost = runtime.build_cost
    if not ledger.apply_grant(npc_id, -cost, tick=tick):
        return say(f"手里凑不齐这{cost}文的工料钱，搭棚的事再缓缓。")
    started = runtime.start(npc_id, pos, tick=tick)
    if started is None:
        ledger.apply_grant(npc_id, cost, tick=tick)
        return say("这块地使不得了，另寻去处吧。")
    return [
        coin_grant_event(tick, npc_id, -cost, note="build:shed"),
        started,
        *say("地块我看好了，明天起木料，搭个棚子。"),
    ]
