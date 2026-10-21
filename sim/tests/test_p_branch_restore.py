"""P-2/P-4/P-6 红钉：读档跨分支的运行时账本与瓦片还原。

三组不变量：

- **P-2** `BuildRuntime._site` 是纯内存态 → 读档必须清零并从**本分支**事件流
  恢复在建工地；否则旧工地跨分支继续推进并发出旧 `structure_id`。
- **P-4** `FireRuntime.cells/fire_seq` 同理；旧火会烧进新分支。
- **P-6** 结构坍塌/拆除后必须补发逐格 `tile_changed(静态原值)`，
  否则格子永久为墙（`derive_tile_events` 此前零生产调用点）。

运行：`uv run pytest sim/tests/test_p_branch_restore.py -v`
"""

from __future__ import annotations

import pytest

from sim.agent.build_exec import BuildRuntime
from sim.api.main import _ground_tile_id, _with_structure_tile_restore
from sim.core.events import (
    WorldEvent,
    structure_collapsed_event,
    structure_removed_event,
    structure_started_event,
)
from sim.npc.fire_runtime import FireRuntime
from sim.tests.test_p_rebuild_tile_map_contract import make_open_map
from sim.world.structure import StructurePhase, StructureSnapshot

pytestmark = pytest.mark.t1


# ---------------------------------------------------------------------------
# P-4：火灾账本清零
# ---------------------------------------------------------------------------


def test_fire_runtime_reset_clears_cells_and_seq() -> None:
    """P-4：reset 后火格清空且 fire_seq 归零（否则 fire_id 跨分支污染）。"""
    rt = FireRuntime()
    rt.fire_seq = 7
    rt.reset()
    assert rt.cells == ()
    assert rt.fire_seq == 0


# ---------------------------------------------------------------------------
# P-2：工地账本清零 / 从事件恢复
# ---------------------------------------------------------------------------


def _started_event(tick: int = 100) -> WorldEvent:
    return structure_started_event(
        tick,
        structure_id="structure_42_100",
        tiles=((1, 1), (2, 1), (1, 2), (2, 2)),
        kind="hut",
        material="wood",
        planned_duration_ticks=2000,
        recipe_id="hut_v1",
        recipe_version="1",
        build_rule_version="1",
        owner_id="chenmo",
        built_by="chenmo",
    )


def test_build_runtime_reset_drops_site() -> None:
    """P-2：reset 后内存工地消失（旧分支不再推进）。"""
    rt = BuildRuntime(make_open_map(), seed=42)
    started = rt.start("chenmo", (1, 1), tick=100)
    assert started is not None and rt._site is not None
    rt.reset()
    assert rt._site is None


def test_build_runtime_restores_in_progress_site() -> None:
    """P-2：从事件流恢复在建工地，structure_id 与 started_tick 保持一致。"""
    rt = BuildRuntime(make_open_map(), seed=42)
    rt.restore_from_events(
        [
            {
                "event_type": "structure.started",
                "tick": 100,
                "payload": _started_event().payload,
            },
        ]
    )
    assert rt._site is not None
    assert rt._site.progress.structure_id == "structure_42_100"
    assert rt._site.progress.started_tick == 100
    # schema 会把 tiles 归一化为 sorted 元组序（行主序），故按集合断言。
    assert set(rt._site.tiles) == {(1, 1), (2, 1), (1, 2), (2, 2)}


def test_build_runtime_restore_ignores_completed_site() -> None:
    """P-2：已完工的工地不恢复（否则会重复推进、重复发 completed）。"""
    rt = BuildRuntime(make_open_map(), seed=42)
    rt.restore_from_events(
        [
            {"event_type": "structure.started", "tick": 100, "payload": _started_event().payload},
            {
                "event_type": "structure.completed",
                "tick": 2100,
                "payload": {"structure_id": "structure_42_100", "quality": 0.8, "integrity": 1.0},
            },
        ]
    )
    assert rt._site is None


def test_build_runtime_restore_applies_last_checkpoint() -> None:
    """P-2：checkpoint 进度被恢复（不从头开始建）。"""
    rt = BuildRuntime(make_open_map(), seed=42)
    rt.restore_from_events(
        [
            {"event_type": "structure.started", "tick": 100, "payload": _started_event().payload},
            {
                "event_type": "structure.checkpoint",
                "tick": 1100,
                "payload": {
                    "structure_id": "structure_42_100",
                    "progress": 0.5,
                    "quality": 0.8,
                    "integrity": 1.0,
                    "build_rule_version": "1",
                },
            },
        ]
    )
    assert rt._site is not None
    assert rt._site.progress.progress == 0.5


# ---------------------------------------------------------------------------
# P-6：坍塌/拆除补发瓦片还原
# ---------------------------------------------------------------------------


def _snapshot(tiles: tuple[tuple[int, int], ...]) -> StructureSnapshot:
    return StructureSnapshot(
        structure_id="s1",
        tiles=tiles,
        kind="hut",
        material="wood",
        phase=StructurePhase.ACTIVE,
        load_bearing=False,
        supported_by=(),
    )


def test_ground_tile_id_reads_static_chunk() -> None:
    """P-6 前置：静态原值从 Chunk 的 ground 取（不是 TileMap 顶层）。"""
    tm = make_open_map()
    assert _ground_tile_id(tm, 3, 4) == 7


def test_collapsed_emits_tile_restore_events() -> None:
    """P-6：坍塌后逐格补发 tile_changed，且值为该格静态原值。"""
    tm = make_open_map()
    structures = {"s1": _snapshot(((2, 2), (3, 2)))}
    collapsed = structure_collapsed_event(500, structure_id="s1", cause="decay")
    out = _with_structure_tile_restore([collapsed], structures, tm)
    derived = [e for e in out if e.event_type.value == "tile_changed"]
    assert len(derived) == 2
    assert {(e.payload["x"], e.payload["y"]) for e in derived} == {(2, 2), (3, 2)}
    assert all(e.payload["tile_id"] == 7 for e in derived)


def test_removed_emits_tile_restore_events() -> None:
    """P-6：拆除同样补发（observe 会把 REMOVED pop 掉，派生必须在其之前）。"""
    tm = make_open_map()
    structures = {"s1": _snapshot(((5, 5),))}
    removed = structure_removed_event(600, structure_id="s1", reason="demolished")
    out = _with_structure_tile_restore([removed], structures, tm)
    derived = [e for e in out if e.event_type.value == "tile_changed"]
    assert len(derived) == 1
    assert derived[0].payload["tile_id"] == 7


def test_restore_uses_each_tiles_own_ground_value() -> None:
    """P-6：不同格子的还原值各自取（不能共用首格）——水面格仍不可走。"""
    tm = make_open_map()
    # 造一块异质地面：把 (3,2) 的 ground 改成 0（不可走水面）。
    from sim.world.map import CHUNK_SIZE

    key = tm.chunk_of(3, 2)
    chunk = tm.chunks[key]
    ground = list(chunk.ground)
    ground[(2 % CHUNK_SIZE) * CHUNK_SIZE + (3 % CHUNK_SIZE)] = 0
    tm = tm.model_copy(
        update={"chunks": {**tm.chunks, key: chunk.model_copy(update={"ground": tuple(ground)})}}
    )
    structures = {"s1": _snapshot(((2, 2), (3, 2)))}
    out = _with_structure_tile_restore(
        [structure_removed_event(700, structure_id="s1", reason="demolished")],
        structures,
        tm,
    )
    tiles = {
        e.payload["x"]: e.payload["tile_id"] for e in out if e.event_type.value == "tile_changed"
    }
    assert tiles[2] == 7
    assert tiles[3] == 0


def test_non_terminal_structures_pass_through_untouched() -> None:
    """P-6 回归：非坍塌/拆除事件原样透传（零派生、不改变行为）。"""
    started = _started_event()
    out = _with_structure_tile_restore([started], {"s1": _snapshot(((1, 1),))}, make_open_map())
    assert out == [started]


def test_restore_skips_unknown_structure() -> None:
    """P-6 防御：快照缺失时不派生（不崩、不猜格子）。"""
    out = _with_structure_tile_restore(
        [structure_removed_event(1, structure_id="ghost", reason="demolished")],
        {},
        make_open_map(),
    )
    assert len(out) == 1
