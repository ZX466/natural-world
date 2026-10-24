"""E7：WS structures 增量投影（协议 1.7 additive；复用 M 面预留 StructureDelta 形）。"""

from sim.api import ws as ws_mod


def setup_function(_):
    ws_mod.reset_structures()


def teardown_function(_):
    ws_mod.reset_structures()


def test_protocol_version_bumped():
    assert ws_mod._PROTOCOL_VERSION == "1.12"


def test_set_and_delta_payload():
    """登记 → delta 出 StructureDelta 数组；再取为空（增量语义）。"""
    ws_mod.set_structure_phase("s1", [(3, 3), (3, 4)], "built")
    delta = ws_mod._structures_delta_payload()
    assert len(delta) == 2
    assert {"op": "add", "rtoken": delta[0]["rtoken"], "x": 3, "y": 3, "phase": "built"} in delta
    assert ws_mod._structures_delta_payload() == []  # 已广播基准：无变化不出


def test_phase_change_rebroadcasts():
    ws_mod.set_structure_phase("s1", [(3, 3)], "built")
    ws_mod._structures_delta_payload()
    ws_mod.set_structure_phase("s1", [(3, 3)], "collapsing")
    delta = ws_mod._structures_delta_payload()
    assert len(delta) == 1
    assert delta[0]["phase"] == "collapsing"
    assert delta[0]["op"] == "add"  # 同格重声明（upsert 语义，前端按键覆盖）


def test_snapshot_contains_all():
    ws_mod.set_structure_phase("s1", [(3, 3)], "built")
    ws_mod.set_structure_phase("s2", [(9, 9)], "rubble")
    snap = ws_mod._structures_snapshot_payload()
    assert len(snap) == 2
    phases = {s["phase"] for s in snap}
    assert phases == {"built", "rubble"}


def test_delta_wires_into_delta_payload():
    """delta_payload 装配层：登记后有 structures 键，drain 后无键。"""
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import EntityState, WorldState, build_default_bus

    state = WorldState(
        world_seed=42,
        entities={"chenmo": EntityState(entity_id="chenmo", pos=(5, 5))},
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    ws_mod.set_structure_phase("s1", [(3, 3)], "built")
    payload = ws_mod.delta_payload(loop, moved_entity_ids=set())
    assert "structures" in payload
    assert ws_mod.delta_payload(loop, moved_entity_ids=set()).get("structures") is None
