"""Wave A: real intent execution conserves the existing material stock."""

from typing import cast

import pytest

from sim.agent.driver import ChenmoDriver
from sim.agent.intent import Intent
from sim.content.protagonist import build_anchor
from sim.core.clock import GameClock
from sim.core.events import EventKind, material_moved_event
from sim.core.persistence.event_validation import validate_store_row
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.llm.client import LlmClient
from sim.world import economy


def transfer_context(*, owner="villager_01", material="wood", quantity=3):
    ledger_type = getattr(economy, "MaterialLedger", None)
    assert ledger_type is not None, "take/give need the existing material event ledger projection"
    ledger = ledger_type()
    loop = TickLoop(
        GameClock(speed=1),
        build_default_bus(),
        WorldState(
            world_seed=42,
            entities={
                "chenmo": EntityState(entity_id="chenmo", pos=(1, 1)),
                "villager_01": EntityState(entity_id="villager_01", pos=(2, 1)),
            },
        ),
    )
    loop.attach_event_observer(ledger.observe)
    loop.enqueue(
        material_moved_event(
            0,
            transfer_id="seed",
            material_id=material,
            quantity=quantity,
            from_ref="world:seed",
            to_ref=f"npc:{owner}",
            reason="dig_yield",
        )
    )
    seed_events = loop.drain_events()
    driver = ChenmoDriver(
        build_anchor(),
        cast("LlmClient", object()),
        lambda: None,
        display_name_of=lambda entity_id: {"chenmo": "陈默", "villager_01": "李阿婆"}.get(
            entity_id
        ),
        inventory_provider=lambda: ledger,
    )
    return loop, ledger, driver, seed_events


@pytest.mark.parametrize(
    "action,owner,source,destination",
    [
        ("take", "villager_01", "npc:villager_01", "npc:chenmo"),
        ("give", "chenmo", "npc:chenmo", "npc:villager_01"),
    ],
)
def test_take_and_give_move_real_stock_with_one_result(action, owner, source, destination):
    loop, ledger, driver, _ = transfer_context(owner=owner)
    driver._pending.append(
        Intent(
            action=action,
            target_id="villager_01",
            params={"item": "木料", "quantity": "2"},
            reason="想把手边的东西交接清楚。",
        )
    )
    assert driver.execute_pending(loop, pathfinder=None) == 1
    events = loop.drain_events()
    moves = [event for event in events if event.event_type is EventKind.MATERIAL_MOVED]
    assert len(moves) == 1
    assert {
        key: moves[0].payload[key]
        for key in ("material_id", "quantity", "from_ref", "to_ref", "reason")
    } == {
        "material_id": "wood",
        "quantity": 2,
        "from_ref": source,
        "to_ref": destination,
        "reason": action,
    }
    validate_store_row(moves[0].to_store_dict())
    assert ledger.balance_of(source.removeprefix("npc:"), "wood") == 1
    assert ledger.balance_of(destination.removeprefix("npc:"), "wood") == 2
    thoughts = [event for event in events if event.event_type is EventKind.NPC_MONOLOGUE]
    assert len(thoughts) == 1
    content = thoughts[0].payload["content"]
    assert isinstance(content, str)
    assert "木料" in content
    assert "villager_01" not in content
    assert "想把手边" not in content


@pytest.mark.parametrize(
    "item,material",
    [
        ("土", "earth"),
        ("earth", "earth"),
        ("石料", "stone"),
        ("stone", "stone"),
        ("木料", "wood"),
        ("wood", "wood"),
    ],
)
def test_existing_material_labels_and_ids_transfer_one_unit_by_default(item, material):
    loop, ledger, driver, _ = transfer_context(material=material)
    driver._pending.append(
        Intent(
            action="take",
            target_id="villager_01",
            params={"item": item},
            reason="拿一份需要的材料。",
        )
    )
    driver.execute_pending(loop, pathfinder=None)
    assert ledger.balance_of("chenmo", material) == 1
    assert ledger.balance_of("villager_01", material) == 2


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"item": "herb"},
        {"item": "草药"},
        {"item": "wood", "quantity": "0"},
        {"item": "wood", "quantity": "-1"},
        {"item": "wood", "quantity": "1.5"},
        {"item": "wood", "quantity": "NaN"},
        {"item": "wood", "quantity": "inf"},
        {"item": "wood", "quantity": "100000000000000000000000000000"},
        {"item": "wood", "from_ref": "world:free"},
    ],
)
def test_invalid_or_missing_transfer_params_never_mint_stock(params):
    loop, ledger, driver, _ = transfer_context()
    driver._pending.append(
        Intent(action="take", target_id="villager_01", params=params, reason="先把东西说清楚。")
    )
    driver.execute_pending(loop, pathfinder=None)
    events = loop.drain_events()
    assert not any(event.event_type is EventKind.MATERIAL_MOVED for event in events)
    assert ledger.balance_of("chenmo", "wood") == 0
    assert ledger.balance_of("villager_01", "wood") == 3
    assert len([event for event in events if event.event_type is EventKind.NPC_MONOLOGUE]) == 1


def test_same_tick_intents_cannot_spend_the_same_stock_twice():
    loop, ledger, driver, _ = transfer_context()
    for _ in range(2):
        driver._pending.append(
            Intent(
                action="take",
                target_id="villager_01",
                params={"item": "wood", "quantity": "2"},
                reason="接过木料。",
            )
        )
    driver.execute_pending(loop, pathfinder=None)
    events = loop.drain_events()
    assert len([event for event in events if event.event_type is EventKind.MATERIAL_MOVED]) == 1
    assert ledger.balance_of("chenmo", "wood") == 2
    assert ledger.balance_of("villager_01", "wood") == 1
    assert len([event for event in events if event.event_type is EventKind.NPC_MONOLOGUE]) == 2


def test_round_trip_survives_replay_and_identical_tick_batch_boundaries():
    loop, ledger, driver, seed = transfer_context(owner="chenmo")
    history = list(seed)
    for action in ("give", "take", "give", "take"):
        driver._pending.append(
            Intent(
                action=action,
                target_id="villager_01",
                params={"item": "wood"},
                reason="把木料交接妥当。",
            )
        )
        driver.execute_pending(loop, pathfinder=None)
        history.extend(loop.drain_events())
    moves = [event for event in history if event.event_type is EventKind.MATERIAL_MOVED]
    assert len(moves) == 5
    assert len({event.payload["transfer_id"] for event in moves}) == 5
    rebuilt = type(ledger)()
    rebuilt.restore_from_events(event.to_store_dict() for event in history)
    assert rebuilt.balance_of("chenmo", "wood") == ledger.balance_of("chenmo", "wood") == 3
    assert rebuilt.balance_of("villager_01", "wood") == 0


@pytest.mark.parametrize("target", ["chenmo", "missing"])
def test_self_or_missing_target_cannot_transfer(target):
    loop, ledger, driver, _ = transfer_context(owner="chenmo")
    driver._pending.append(
        Intent(action="give", target_id=target, params={"item": "wood"}, reason="把木料放稳。")
    )
    driver.execute_pending(loop, pathfinder=None)
    assert not any(event.event_type is EventKind.MATERIAL_MOVED for event in loop.drain_events())
    assert ledger.balance_of("chenmo", "wood") == 3


def test_target_moving_away_before_execution_is_rejected():
    loop, ledger, driver, _ = transfer_context()
    driver._pending.append(
        Intent(action="take", target_id="villager_01", params={"item": "wood"}, reason="接过木料。")
    )
    target = loop.state.entities["villager_01"].model_copy(update={"pos": (30, 30)})
    loop.state = loop.state.model_copy(
        update={"entities": {**loop.state.entities, "villager_01": target}}
    )
    assert driver.execute_pending(loop, pathfinder=None) == 0
    assert loop.drain_events() == []
    assert ledger.balance_of("villager_01", "wood") == 3


def test_bad_replay_cannot_partially_replace_existing_stock():
    _loop, ledger, _driver, seed = transfer_context(owner="chenmo")
    bad = material_moved_event(
        0,
        transfer_id="overdraft",
        material_id="wood",
        quantity=99,
        from_ref="npc:chenmo",
        to_ref="npc:villager_01",
        reason="dig_yield",
    )
    with pytest.raises(ValueError):
        ledger.restore_from_events(event.to_store_dict() for event in [*seed, bad])
    assert ledger.balance_of("chenmo", "wood") == 3
    assert ledger.balance_of("villager_01", "wood") == 0


def voxel_for(loop, ledger, seed):
    from sim.agent.voxel_exec import VoxelRuntime
    from sim.tests.test_p_rebuild_tile_map_contract import make_open_map

    runtime = VoxelRuntime(
        tile_map=make_open_map,
        height_of=lambda x, y: 1,
        ground_gid=lambda x, y: 7,
        occupied=lambda x, y: False,
        stock_available=lambda material: ledger.balance_of("chenmo", material),
    )
    runtime.observe(seed)
    return runtime


def test_pending_gift_cannot_be_spent_again_by_voxel_placement():
    from sim.agent.voxel_exec import VoxelRejected

    loop, ledger, driver, seed = transfer_context(owner="chenmo", quantity=1)
    voxel = voxel_for(loop, ledger, seed)
    driver._pending.append(
        Intent(
            action="give",
            target_id="villager_01",
            params={"item": "wood"},
            reason="把木料交给对方。",
        )
    )
    driver.execute_pending(loop, pathfinder=None)
    assert voxel.snapshot()["inventory"]["wood"] == 1  # Commit has not happened.
    with pytest.raises(VoxelRejected):
        voxel.request("place", 3, 1, loop.state, material="wood")


def test_pending_voxel_placement_cannot_be_spent_again_by_gift():
    loop, ledger, driver, seed = transfer_context(owner="chenmo", quantity=1)
    voxel = voxel_for(loop, ledger, seed)
    for event in voxel.request("place", 3, 1, loop.state, material="wood"):
        loop.enqueue(event)
    loop.drain_events()
    driver._pending.append(
        Intent(
            action="give", target_id="villager_01", params={"item": "wood"}, reason="交出一份木料。"
        )
    )
    driver.execute_pending(loop, pathfinder=None)
    assert not any(event.event_type is EventKind.MATERIAL_MOVED for event in loop.drain_events())
    assert ledger.balance_of("chenmo", "wood") == 0
    assert ledger.balance_of("villager_01", "wood") == 0


def test_uncommitted_take_does_not_enable_voxel_placement_early():
    from sim.agent.voxel_exec import VoxelRejected

    loop, ledger, driver, seed = transfer_context(quantity=1)
    voxel = voxel_for(loop, ledger, seed)
    driver._pending.append(
        Intent(action="take", target_id="villager_01", params={"item": "wood"}, reason="接过木料。")
    )
    driver.execute_pending(loop, pathfinder=None)
    events = loop.drain_events()
    assert ledger.balance_of("chenmo", "wood") == 1
    with pytest.raises(VoxelRejected):
        voxel.request("place", 3, 1, loop.state, material="wood")
    voxel.observe(events)
    assert voxel.request("place", 3, 1, loop.state, material="wood")
