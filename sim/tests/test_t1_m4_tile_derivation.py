"""M4-D2d T1 钉子 — 结构终态派生 TILE_CHANGED → C3 chunk 失效接线。

D2d 采用最小数据域交付：纯派生函数 + 测试接线；EventBus/Pathfinder 生产持有者
属架构域，不在本任务修改。rubble/removed 的 tile_id 由调用方从静态 TileMap 提供。
"""

from __future__ import annotations

import pytest

from sim.core.events import (
    EventKind,
    structure_checkpoint_event,
    structure_collapsed_event,
    structure_completed_event,
    structure_removed_event,
    structure_started_event,
)
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder
from sim.world.structure import StructurePhase, StructureSnapshot, derive_tile_events


def make_open_map(size: int = 32) -> TileMap:
    chunks = {}
    for cy in range(size // CHUNK_SIZE):
        for cx in range(size // CHUNK_SIZE):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=size, height=size, chunks=chunks)


def snapshot(structure_id: str = "hut-1") -> StructureSnapshot:
    return StructureSnapshot(
        structure_id=structure_id,
        tiles=((0, 0), (1, 0)),
        kind="wood_hut",
        material="wood",
        phase=StructurePhase.ACTIVE,
        load_bearing=False,
        supported_by=(),
    )


def started(tick: int = 1) -> object:
    return structure_started_event(
        tick,
        structure_id="hut-1",
        tiles=((1, 0), (0, 0)),
        kind="wood_hut",
        material="wood",
        planned_duration_ticks=86_400,
        recipe_id="hut.v1",
        recipe_version="1",
        build_rule_version="m4-v1",
    )


@pytest.mark.t1
class TestTileDerivation:
    @pytest.mark.parametrize(
        "event",
        [
            structure_completed_event(2, structure_id="hut-1", quality=0.5, integrity=1.0),
            structure_collapsed_event(3, structure_id="hut-1", cause="support_lost"),
            structure_removed_event(4, structure_id="hut-1", reason="demolished"),
        ],
    )
    def test_terminal_kinds_derive_sorted_tiles(self, event) -> None:
        derived = derive_tile_events(event, snapshot(), tile_id=7)
        assert [item.payload["x"] for item in derived] == [0, 1]
        assert [item.payload["y"] for item in derived] == [0, 0]
        assert all(item.event_type is EventKind.TILE_CHANGED for item in derived)
        assert all(item.branch_id == event.branch_id for item in derived)

    @pytest.mark.parametrize(
        "event",
        [
            started(),
            structure_checkpoint_event(
                2,
                structure_id="hut-1",
                progress=0.5,
                quality=0.5,
                integrity=1.0,
                build_rule_version="m4-v1",
            ),
        ],
    )
    def test_non_terminal_kinds_do_not_derive(self, event) -> None:
        assert derive_tile_events(event, snapshot(), tile_id=7) == ()

    def test_derivation_is_deterministic(self) -> None:
        event = structure_completed_event(2, structure_id="hut-1", quality=0.5, integrity=1.0)
        assert derive_tile_events(event, snapshot(), tile_id=7) == derive_tile_events(
            event, snapshot(), tile_id=7
        )


@pytest.mark.t1
class TestChunkInvalidationWiring:
    def test_completed_derived_events_invalidate_only_affected_chunk(self) -> None:
        tm = make_open_map()
        pathfinder = Pathfinder(tm)
        pathfinder.find((0, 0), (20, 0))
        pathfinder.find((0, 20), (20, 20))
        assert len(pathfinder.cache.entries) == 2

        event = structure_completed_event(2, structure_id="hut-1", quality=0.5, integrity=1.0)
        derived = derive_tile_events(event, snapshot(), tile_id=7)

        assert pathfinder.observe_events(derived) == 1
        assert len(pathfinder.cache.entries) == 1
        assert pathfinder.observe_events(derived) == 0

    def test_collapse_then_remove_remain_idempotent(self) -> None:
        tm = make_open_map()
        pathfinder = Pathfinder(tm)
        pathfinder.find((0, 0), (10, 0))

        collapse = structure_collapsed_event(3, structure_id="hut-1", cause="support_lost")
        removed = structure_removed_event(4, structure_id="hut-1", reason="cleanup")
        first = derive_tile_events(collapse, snapshot(), tile_id=1)
        second = derive_tile_events(removed, snapshot(), tile_id=1)

        assert pathfinder.observe_events(first) == 1
        assert pathfinder.observe_events(second) == 0
        assert pathfinder.cache.entries == {}
