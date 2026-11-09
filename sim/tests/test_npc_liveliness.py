"""Round 23: meaningful destinations, bounded travel and real construction."""

import json
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from sim.core.events import EventKind, npc_act_event
from sim.core.world import EntityState, WorldState
from sim.npc.sim_exec import _site_anchor_of, npc_events_for_tick, plan_npc_move
from sim.world.economy import CoinLedger
from sim.world.map import TileMap
from sim.world.pathfinding import Pathfinder

TOWN = Path("sim/content/linhe-town.json")


@pytest.mark.parametrize(
    ("npc_id", "action", "expected"),
    [
        ("villager_01", "work", (122, 19)),  # 农人 → 梯田
        ("villager_02", "work", (72, 52)),  # 商贩 → 染坊市集
        ("villager_03", "eat", (40, 18)),  # 匠人次地标 → 祖屋
        ("villager_04", "work", (66, 19)),
        ("villager_05", "work", (18, 52)),
        ("villager_06", "work", (44, 53)),
        ("villager_07", "work", (124, 52)),
        ("villager_07", "eat", (100, 52)),
        ("villager_08", "work", (100, 52)),
        ("villager_08", "eat", (15, 18)),
    ],
)
def test_occupation_actions_reach_primary_and_secondary_landmarks(npc_id, action, expected):
    assert _site_anchor_of(action, npc_id) == expected


def test_landmark_content_and_prompt_cover_the_complete_map():
    from sim.content.landmarks import LANDMARKS, landmarks_text

    coordinates = json.loads(TOWN.read_text(encoding="utf-8"))["_landmarks"]
    assert len(LANDMARKS) == len(coordinates) == 10
    assert {key: list(site.pos) for key, site in LANDMARKS.items()} == coordinates
    text = landmarks_text()
    for name in ("祖屋", "村塾", "钟山", "藏书房", "村广场"):
        assert name in text
    assert "药铺（100,53" in text


def test_wandering_uses_current_district_and_rest_still_returns_home():
    from sim.npc.sim_exec import home_base_of

    pf = Pathfinder(TileMap.from_json_file(TOWN))
    state = WorldState(
        entities={"villager_02": EntityState(entity_id="villager_02", pos=(124, 52))}
    )
    event = plan_npc_move(state, "villager_02", "wander", pf, seed=42, tick=7)
    assert event is not None
    x, y = cast("tuple[int, int]", event.payload["goal"])
    assert abs(x - 124) + abs(y - 52) <= 12
    assert _site_anchor_of("rest", "villager_02") == home_base_of("villager_02")


def test_larger_destination_radius_does_not_remedy_or_pay_a_distant_worker(monkeypatch):
    from sim.content.villagers import build_roster
    from sim.npc import sim_exec

    town = TileMap.from_json_file(TOWN)
    # Merchant's work site is (72,52); seven tiles away is not arrival.
    pos = next(
        (x, y)
        for y in range(42, 63)
        for x in range(62, 83)
        if abs(x - 72) + abs(y - 52) == 7 and town.is_walkable(x, y)
    )
    profile = build_roster()[1]

    class WorkRuntime:
        def __init__(self):
            self.profiles = {"villager_02": profile}

        def tick(self, tick, **kwargs):
            return [npc_act_event(tick, "villager_02", "work")]

    runtime = WorkRuntime()
    ledger = CoinLedger()
    monkeypatch.setattr(sim_exec, "_SITE_SCATTER_RADIUS", 12)
    events = npc_events_for_tick(
        runtime,
        WorldState(entities={"villager_02": EntityState(entity_id="villager_02", pos=pos)}),
        1000,
        Pathfinder(town),
        seed=42,
        wage_last={},
        coin_ledger=ledger,
    )
    assert not any(event.event_type is EventKind.COIN_GRANT for event in events)
    assert runtime.profiles["villager_02"].needs == profile.needs


def builder_fixture(*, count=1, money=40, urgent=False):
    from sim.agent.build_exec import BuildRuntime
    from sim.content.villagers import build_roster
    from sim.npc.runtime import NpcRuntime
    from sim.npc.utility import UtilityModel

    town = TileMap.from_json_file(TOWN)
    # The real map contains this open area; keep the fixture independent of site selection.
    pos = next(
        (x, y)
        for y in range(town.height - 2)
        for x in range(town.width - 2)
        if all(town.is_walkable(x + dx, y + dy) for dx in range(3) for dy in range(3))
    )
    profiles = {
        p.npc_id: replace(
            p, needs=tuple(replace(need, value=0.95 if urgent else 0.05) for need in p.needs)
        )
        for p in build_roster()[:count]
    }
    runtime = NpcRuntime(profiles=profiles, utility=UtilityModel(count, seed=42))
    state = WorldState(
        entities={nid: EntityState(entity_id=nid, pos=pos) for nid in profiles}, world_seed=42
    )
    ledger = CoinLedger()
    for nid in profiles:
        ledger.apply_grant(nid, money, tick=0)
    return runtime, state, Pathfinder(town), ledger, BuildRuntime(town, seed=42)


def test_real_l1_chooses_a_buildable_site_and_records_the_debit_once():
    runtime, state, pf, ledger, build = builder_fixture(count=2)
    events = npc_events_for_tick(
        runtime, state, 30_000, pf, seed=42, coin_ledger=ledger, build_runtime=build
    )
    starts = [event for event in events if event.event_type is EventKind.STRUCTURE_STARTED]
    assert len(starts) == 1
    acts = [
        event
        for event in events
        if event.event_type is EventKind.NPC_ACT and event.payload["action"] == "build"
    ]
    assert len(acts) == 1
    assert isinstance(acts[0].payload["params"], dict)
    assert set(acts[0].payload["params"]) == {"x", "y"}
    grants = [event for event in events if event.event_type is EventKind.COIN_GRANT]
    assert len(grants) == 1 and grants[0].payload["delta"] == -40
    assert sorted(ledger.balance_of(nid) for nid in runtime.profiles) == [0, 40]
    assert not any("另寻去处" in str(event.payload) for event in events)
    # A second tick while construction is active should not choose build or emit failures.
    after = npc_events_for_tick(
        runtime, state, 30_010, pf, seed=42, coin_ledger=ledger, build_runtime=build
    )
    assert not any(event.payload.get("action") == "build" for event in after)
    assert not any("另寻去处" in str(event.payload) for event in after)


@pytest.mark.parametrize("case", ["poor", "urgent", "travelling", "night", "occupied"])
def test_build_never_overrides_needs_or_missing_preconditions(case):
    runtime, state, pf, ledger, build = builder_fixture(
        money=39 if case == "poor" else 40, urgent=case == "urgent"
    )
    if case == "travelling":
        actor = state.entities["villager_01"]
        state = state.model_copy(
            update={"entities": {"villager_01": actor.model_copy(update={"path": (actor.pos,)})}}
        )
    elif case == "occupied":
        # All nearby land is blocked in the map, so there is no valid construction site.
        for y in range(pf.tile_map.height):
            for x in range(pf.tile_map.width):
                if (
                    abs(x - state.entities["villager_01"].pos[0])
                    + abs(y - state.entities["villager_01"].pos[1])
                    <= 6
                ):
                    build.tile_map = build.tile_map.with_collision(x, y, walkable=False)
        pf.observe_map(build.tile_map)
    events = npc_events_for_tick(
        runtime,
        state,
        0 if case == "night" else 30_000,
        pf,
        seed=42,
        coin_ledger=ledger,
        build_runtime=build,
    )
    assert not any(event.payload.get("action") == "build" for event in events)
    assert ledger.balance_of("villager_01") == (39 if case == "poor" else 40)


def test_failed_start_does_not_debit_then_refund(monkeypatch):
    from sim.npc.build_action import build_action_events

    _, state, _, ledger, build = builder_fixture()
    pos = state.entities["villager_01"].pos
    assert build.start("other", pos, tick=1) is not None
    original = ledger.apply_grant
    changes = []

    def record(owner, delta, *, tick):
        changes.append(delta)
        return original(owner, delta, tick=tick)

    monkeypatch.setattr(ledger, "apply_grant", record)
    events = build_action_events(state, "villager_01", pos, tick=2, runtime=build, ledger=ledger)
    assert changes == []
    assert not any(event.event_type is EventKind.COIN_GRANT for event in events)


def test_autonomous_build_does_not_isolate_a_real_map_dead_end():
    runtime, state, pf, ledger, build = builder_fixture()
    # This cell has exactly one walkable neighbor, (13,69). The former chosen
    # footprint (13,68)..(14,69) sealed it permanently at completion.
    pos = (12, 69)
    state = state.model_copy(
        update={"entities": {"villager_01": EntityState(entity_id="villager_01", pos=pos)}}
    )
    events = npc_events_for_tick(
        runtime, state, 30_000, pf, seed=42, coin_ledger=ledger, build_runtime=build
    )
    started = any(event.event_type is EventKind.STRUCTURE_STARTED for event in events)
    build.on_tick(30_000 + build.active_duration())
    reached: set[tuple[int, int]] = {pos}
    todo: deque[tuple[int, int]] = deque([pos])
    while todo:
        x, y = todo.popleft()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor not in reached and build.tile_map.is_walkable(*neighbor):
                reached.add(neighbor)
                todo.append(neighbor)
    assert len(reached) == 3947 - (4 if started else 0)


def test_explicit_build_rejects_a_footprint_that_cuts_existing_access():
    from sim.npc.build_action import build_action_events

    _, state, _, ledger, build = builder_fixture()
    state = state.model_copy(
        update={"entities": {"villager_01": EntityState(entity_id="villager_01", pos=(12, 69))}}
    )
    events = build_action_events(
        state, "villager_01", (13, 68), tick=30_000, runtime=build, ledger=ledger
    )
    assert not any(event.event_type is EventKind.STRUCTURE_STARTED for event in events)
    assert not any(event.event_type is EventKind.COIN_GRANT for event in events)
    assert ledger.balance_of("villager_01") == 40
    assert not build.busy


def test_completion_waits_until_people_have_left_the_footprint():
    _, state, _, _, build = builder_fixture()
    x, y = state.entities["villager_01"].pos
    assert build.start("villager_01", (x, y), tick=10) is not None
    due = 10 + build.active_duration()
    events = build.on_tick(due, occupied={(x, y)})
    assert not any(event.event_type is EventKind.STRUCTURE_COMPLETED for event in events)
    assert build.tile_map.is_walkable(x, y)
    assert build.busy
    completed = build.on_tick(due + 10)
    assert any(event.event_type is EventKind.STRUCTURE_COMPLETED for event in completed)
    assert not build.tile_map.is_walkable(x, y)


@pytest.mark.asyncio
async def test_production_completion_stops_an_existing_path_through_the_new_wall(monkeypatch):
    import asyncio

    from sim.api import main

    async def idle(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "run_world_driver", idle)
    async with main.lifespan(main.app):
        app = main.app
        _, state, _, _, _ = builder_fixture()
        x, y = state.entities["villager_01"].pos
        build = app.state.build_runtime
        assert build.start("villager_01", (x, y), tick=100) is not None
        actor = EntityState(entity_id="villager_01", pos=(x + 2, y), path=((x + 1, y), (x, y)))
        crossing = WorldState(entities={"villager_01": actor})
        hook = next(
            hook for hook in app.state.loop._npc_hooks if hook.__name__ == "_build_tick_hook"
        )
        events = hook(crossing, 100 + build.active_duration())
        assert any(event.event_type is EventKind.STRUCTURE_COMPLETED for event in events)
        stopped = [event for event in events if event.event_type is EventKind.MOVE]
        assert len(stopped) == 1
        assert stopped[0].payload["entity_id"] == "villager_01"
        assert stopped[0].payload["goal"] == [x + 2, y]
        assert stopped[0].payload["path"] == [[x + 2, y]]


@pytest.mark.asyncio
async def test_genesis_funds_are_event_sourced_and_not_regranted_on_restart(tmp_path, monkeypatch):
    from sim.api import main
    from sim.core.persistence.npc_store import NpcStore

    monkeypatch.setattr(main, "WORLD_DB_PATH", tmp_path / "world.db")
    loop, store, _ = await main.build_loop()
    try:
        events = loop.drain_events()
        grants = [event for event in events if event.event_type is EventKind.COIN_GRANT]
        assert len(grants) == 50
        assert {event.payload["delta"] for event in grants} == {15}
        await NpcStore(store).flush_tick(events)
    finally:
        await store.session_factory.kw["bind"].dispose()
    restored, reopened, _ = await main.build_loop()
    try:
        assert not any(
            event.event_type is EventKind.COIN_GRANT for event in restored.pending_events
        )
        rows = await reopened.read_branch_history("main")
        ledger = CoinLedger()
        ledger.restore_from_events(rows)
        assert ledger.balance_of("villager_01") == ledger.balance_of("villager_50") == 15
    finally:
        await reopened.session_factory.kw["bind"].dispose()
