"""起火抽中后必须真的落地：可走格占全图少数，不能在落点判定处静默丢弃。"""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.npc.fire_runtime import ignite_due
from sim.world.map import TileMap

TOWN = Path(__file__).resolve().parents[1] / "content/linhe-town.json"


@pytest.fixture(scope="module")
def town() -> TileMap:
    return TileMap.from_json_file(TOWN)


def _walkable_of(tile_map: TileMap) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y in range(tile_map.height)
        for x in range(tile_map.width)
        if tile_map.is_walkable(x, y)
    }


def test_ignition_lands_on_a_walkable_cell_instead_of_being_dropped(town: TileMap) -> None:
    """真实地图上可走格只占少数：落点不可走时必须改投，不能丢掉整场火。"""
    from sim.api.main import _ignition_spot

    walkable = _walkable_of(town)
    assert len(walkable) < town.width * town.height / 2, "前提：可走格是少数"

    spot = _ignition_spot(42, 86400 + 10800, town, avoid=set())
    assert spot is not None
    assert spot in walkable, "起火点必须落在可燃（可走）格上"


def test_ignition_spot_is_deterministic_and_in_bounds(town: TileMap) -> None:
    from sim.api.main import _ignition_spot

    first = _ignition_spot(42, 86400 + 10800, town, avoid=set())
    again = _ignition_spot(42, 86400 + 10800, town, avoid=set())
    assert first == again
    assert first is not None
    x, y = first
    assert 0 <= x < town.width and 0 <= y < town.height


def test_ignition_spot_respects_avoid_set(town: TileMap) -> None:
    from sim.api.main import _ignition_spot

    walkable = sorted(_walkable_of(town))
    avoid = set(walkable[:-1])
    spot = _ignition_spot(7, 86400 + 10800, town, avoid=avoid)
    assert spot is not None
    assert spot == walkable[-1]


def test_draw_rate_is_the_designed_thirty_four_percent() -> None:
    """抽签本身约 1/3 日；有效起火率不应再被落点判定砍掉四分之三。"""
    hits = sum(1 for day in range(1, 366) if ignite_due(42, day * 86400 + 3 * 3600))
    assert 0.28 <= hits / 365 <= 0.44
