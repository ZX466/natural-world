"""生产差事：接单→走到指定地点→领取奖励，断线/分叉不重发。"""

from sim.core.events import EventKind
from sim.core.world import EntityState, WorldState
from sim.npc.errand_runtime import ErrandRuntime, errand_cases
from sim.world.economy import CoinLedger


def _state(pos=(5, 5), *, issuer=(5, 6), tick=0):
    return WorldState(
        world_seed=42,
        tick=tick,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=pos),
            "villager_01": EntityState(entity_id="villager_01", pos=issuer),
        },
    )


def test_twenty_real_jobs_are_distinct():
    cases = errand_cases()
    assert len(cases) == 20
    assert len({(case.issuer, case.target) for case in cases}) == 20


def test_accept_then_arrive_gets_single_reward():
    ledger = CoinLedger()
    runtime = ErrandRuntime(seed=42, coin_ledger=ledger)
    accepted = runtime.tick(_state(), 10)
    assert [e.event_type for e in accepted] == [EventKind.NPC_CHAT]
    assert ledger.balance_of("chenmo") == 0
    job = runtime.active
    assert job is not None and job.target != (5, 5)
    assert not runtime.tick(_state(pos=(5, 5)), 20)
    reached = runtime.tick(_state(pos=job.target), 30)
    assert [e.event_type for e in reached] == [EventKind.NPC_MONOLOGUE]
    assert ledger.balance_of("chenmo") == 0
    done = runtime.tick(_state(pos=(5, 5)), 40)
    assert [e.event_type for e in done] == [EventKind.NPC_CHAT, EventKind.COIN_GRANT]
    assert str(done[-1].payload["note"]).startswith("errand:")
    assert ledger.balance_of("chenmo") == 5
    assert not runtime.tick(_state(pos=job.target), 50)
    assert ledger.balance_of("chenmo") == 5


def test_no_job_if_issuer_absent_or_protagonist_dead():
    runtime = ErrandRuntime(seed=42, coin_ledger=CoinLedger())
    assert not runtime.tick(WorldState(world_seed=42), 10)
    only_chenmo = WorldState(
        world_seed=42, entities={"chenmo": EntityState(entity_id="chenmo", pos=(5, 5))}
    )
    assert not runtime.tick(only_chenmo, 10)


def test_twenty_production_errands_complete_on_real_map():
    from sim.api.main import _default_map

    town = _default_map()
    finished = 0
    for job in errand_cases():
        ledger = CoinLedger()
        runtime = ErrandRuntime(seed=42, coin_ledger=ledger)
        state = WorldState(
            world_seed=42,
            entities={
                "chenmo": EntityState(entity_id="chenmo", pos=(5, 5)),
                job.issuer: EntityState(entity_id=job.issuer, pos=(5, 6)),
            },
        )
        assert town.is_walkable(*job.target)
        runtime._next = job.number - 1  # 20 个预约位逐个独立验证
        assert runtime.tick(state, 10)[0].event_type is EventKind.NPC_CHAT
        state = state.model_copy(
            update={
                "entities": {
                    **state.entities,
                    "chenmo": EntityState(entity_id="chenmo", pos=job.target),
                }
            }
        )
        assert runtime.tick(state, 20)[0].event_type is EventKind.NPC_MONOLOGUE
        state = state.model_copy(
            update={
                "entities": {
                    **state.entities,
                    "chenmo": EntityState(entity_id="chenmo", pos=(5, 5)),
                }
            }
        )
        events = runtime.tick(state, 30)
        finished += int(len(events) == 2 and ledger.balance_of("chenmo") == 5)
    assert finished == 20


def test_reset_drops_unfinished_job_and_cooldown():
    runtime = ErrandRuntime(seed=42, coin_ledger=CoinLedger())
    assert runtime.tick(_state(), 10)
    runtime.reset()
    assert runtime.active is None
    assert runtime.tick(_state(), 10)
