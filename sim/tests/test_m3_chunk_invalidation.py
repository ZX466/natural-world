"""C3 chunk 失效正确性 — 量化验收「chunk 失效正确」（m3-plan 批次 C3）。

通路契约（map.py / pathfinding.py M3 可变底座）：
1. **标脏**：``TileMap.mark_tile_dirty`` / ``mark_chunk_dirty``；``dirty_chunks()``
   排序返回；``drain_dirty()`` 消费即清（幂等）。
2. **事件桥**：``event_tile_position`` — TILE_CHANGED 全量；MATTER_* 仅 x/y≥0
   （-1 未定位哨兵不标，C4 域约束）；无关事件 → None。
3. **失效**：``Pathfinder.observe_events`` 标脏 + 逐 chunk ``PathCache.invalidate``
   — 途经脏 chunk 的条目剔除，不途经的保留（精确失效，非全清）。
4. **不可变换图**：``TileMap.with_collision`` 返回新图并只标该 chunk 脏
   （新旧图 PrivateAttr 不串扰）；``Pathfinder.observe_map`` 换图消费脏集。
"""

from __future__ import annotations

import pytest

from sim.core.events import (
    EventKind,
    matter_event,
    npc_act_event,
    tile_changed_event,
)
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder, event_tile_position


def make_open_map(w: int = 48, h: int = 48) -> TileMap:
    """无障碍开阔图（≥3×3 chunk，够跨 chunk 路径）。"""
    chunks = {}
    for cy in range((h + CHUNK_SIZE - 1) // CHUNK_SIZE):
        for cx in range((w + CHUNK_SIZE - 1) // CHUNK_SIZE):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=w, height=h, chunks=chunks)


class TestDirtyTracking:
    """TileMap 脏标记原语。"""

    @pytest.mark.t1
    def test_dirty_chunks_initial_empty(self) -> None:
        assert make_open_map().dirty_chunks() == []

    @pytest.mark.t1
    def test_mark_tile_dirty_maps_to_chunk(self) -> None:
        tm = make_open_map()
        # (17, 20) → chunk (1, 1)
        assert tm.mark_tile_dirty(17, 20) == (1, 1)
        assert tm.dirty_chunks() == [(1, 1)]

    @pytest.mark.t1
    def test_mark_out_of_bounds_is_noop_sentinel(self) -> None:
        tm = make_open_map(16, 16)
        assert tm.mark_tile_dirty(99, 99) == (-1, -1)
        assert tm.dirty_chunks() == []

    @pytest.mark.t1
    def test_dirty_chunks_sorted_deterministic(self) -> None:
        tm = make_open_map()
        tm.mark_chunk_dirty((2, 0))
        tm.mark_chunk_dirty((0, 1))
        tm.mark_chunk_dirty((1, 1))
        assert tm.dirty_chunks() == [(0, 1), (1, 1), (2, 0)]

    @pytest.mark.t1
    def test_drain_dirty_clears_idempotent(self) -> None:
        tm = make_open_map()
        tm.mark_tile_dirty(0, 0)  # chunk (0,0)
        tm.mark_tile_dirty(20, 1)  # chunk (1,0)
        assert tm.drain_dirty() == [(0, 0), (1, 0)]
        assert tm.drain_dirty() == []
        assert tm.dirty_chunks() == []


class TestEventPositionBridge:
    """事件 → tile 坐标桥（MATTER 未定位哨兵）。"""

    @pytest.mark.t1
    def test_tile_changed_carries_position(self) -> None:
        ev = tile_changed_event(tick=1, x=5, y=7, tile_id=2)
        assert event_tile_position(ev) == (5, 7)

    @pytest.mark.t1
    @pytest.mark.parametrize(
        "kind",
        [
            EventKind.MATTER_DECAY,
            EventKind.MATTER_DAMAGE,
            EventKind.MATTER_BUILD,
            EventKind.MATTER_COLLAPSE,
        ],
    )
    def test_matter_located_carries_position(self, kind: EventKind) -> None:
        ev = matter_event(tick=1, kind=kind, matter_id="wall-1", x=10, y=12, durability=0.5)
        assert event_tile_position(ev) == (10, 12)

    @pytest.mark.t1
    @pytest.mark.parametrize(
        "kind",
        [
            EventKind.MATTER_DECAY,
            EventKind.MATTER_DAMAGE,
            EventKind.MATTER_BUILD,
            EventKind.MATTER_COLLAPSE,
        ],
    )
    def test_matter_unlocated_sentinel_none(self, kind: EventKind) -> None:
        # x/y=-1 哨兵（未定位）：不得标脏
        ev = matter_event(tick=1, kind=kind, matter_id="food-1", durability=0.5)
        assert event_tile_position(ev) is None

    @pytest.mark.t1
    def test_unrelated_event_none(self) -> None:
        ev = npc_act_event(tick=1, npc_id="chenmo", action="idle")
        assert event_tile_position(ev) is None


class TestObserveEventsInvalidation:
    """事件批 → 精确失效（量化：剔除数 + 保留集）。"""

    @pytest.mark.t1
    def test_tile_changed_invalidates_only_path_chunk(self) -> None:
        """跨 chunk 两条路径；只标其中一条途经的 chunk → 恰剔 1 留 1。"""
        tm = make_open_map(48, 48)
        pf = Pathfinder(tm)
        # 路径 A：横向穿 chunk (0,0)→(1,0)→(2,0)
        pf.find((0, 0), (40, 0))
        # 路径 B：底部，仅 chunk (0,1)/(1,1)/(2,1)
        pf.find((0, 40), (40, 40))
        assert len(pf.cache.entries) == 2

        # 标脏路径 A 中段 chunk (1,0)（坐标 (20, 0)）
        removed = pf.observe_events([tile_changed_event(tick=2, x=20, y=0, tile_id=1)])
        assert removed == 1
        assert len(pf.cache.entries) == 1
        # 保留的是底部路径 B
        assert ((0, 40), (40, 40)) in pf.cache.entries

    @pytest.mark.t1
    def test_located_matter_invalidates(self) -> None:
        tm = make_open_map(32, 32)
        pf = Pathfinder(tm)
        pf.find((0, 0), (30, 0))
        assert len(pf.cache.entries) == 1

        ev = matter_event(
            tick=2, kind=EventKind.MATTER_COLLAPSE, matter_id="wall-1", x=8, y=0, durability=0.0
        )
        assert pf.observe_events([ev]) == 1
        assert pf.cache.entries == {}

    @pytest.mark.t1
    def test_unlocated_matter_and_unrelated_events_noop(self) -> None:
        tm = make_open_map(32, 32)
        pf = Pathfinder(tm)
        pf.find((0, 0), (30, 0))

        evs = [
            matter_event(tick=2, kind=EventKind.MATTER_DECAY, matter_id="food-1", durability=0.9),
            npc_act_event(tick=2, npc_id="chenmo", action="idle"),
        ]
        assert pf.observe_events(evs) == 0
        assert len(pf.cache.entries) == 1

    @pytest.mark.t1
    def test_observe_empty_batch_idempotent(self) -> None:
        tm = make_open_map()
        pf = Pathfinder(tm)
        pf.find((0, 0), (5, 5))
        assert pf.observe_events([]) == 0
        assert pf.observe_events([]) == 0
        assert len(pf.cache.entries) == 1

    @pytest.mark.t1
    def test_unrelated_chunk_invalidate_not_cleared(self) -> None:
        """标脏远端空 chunk → 剔 0，路径缓存完整保留。"""
        tm = make_open_map(48, 48)
        pf = Pathfinder(tm)
        pf.find((0, 0), (10, 0))
        # (40, 40) 不在路径途经 chunk
        assert pf.observe_events([tile_changed_event(tick=2, x=40, y=40, tile_id=1)]) == 0
        assert len(pf.cache.entries) == 1


class TestImmutableMapSwap:
    """with_collision 不可变换图 + observe_map 消费脏集。"""

    @pytest.mark.t1
    def test_with_collision_marks_only_new_chunk(self) -> None:
        tm = make_open_map(32, 32)
        tm2 = tm.with_collision(5, 5, False)
        assert tm2 is not tm
        # 原图几何不变、不串脏
        assert tm.is_walkable(5, 5) is True
        assert tm.dirty_chunks() == []
        assert tm2.dirty_chunks() == [(0, 0)]
        assert tm2.is_walkable(5, 5) is False

    @pytest.mark.t1
    def test_with_collision_out_of_bounds_raises(self) -> None:
        tm = make_open_map(16, 16)
        with pytest.raises(ValueError, match="坐标越界"):
            tm.with_collision(20, 0, False)

    @pytest.mark.t1
    def test_observe_map_invalidates_after_block(self) -> None:
        """封死直线路 → 换图失效 → 重寻绕行（端到端路径正确性）。"""
        tm = make_open_map(32, 32)
        pf = Pathfinder(tm)
        # 直线：沿 y=0 从 (0,0) 到 (15,0)
        path1 = pf.find((0, 0), (15, 0))
        assert path1[1] == (1, 0)
        assert len(pf.cache.entries) == 1

        # 封死 (1,0)：直连第一格
        tm2 = tm.with_collision(1, 0, False)
        removed = pf.observe_map(tm2)
        assert removed == 1
        assert pf.cache.entries == {}

        path2 = pf.find((0, 0), (15, 0))
        assert (1, 0) not in path2
        # 绕行：下一步只能向下/斜下（对角禁穿角 → 先 (1,1) 或 (0,1)）
        assert path2[1] in {(0, 1), (1, 1)}

    @pytest.mark.t1
    def test_with_collision_full_block_unreachable(self) -> None:
        """窄图单列全封 → 失效后重寻抛不可达（缓存不返回陈旧路径）。"""
        # 4 宽图，中间 x=1 与 x=2 全列封死 → 左右隔离
        chunks = {
            (0, 0): Chunk(
                cx=0,
                cy=0,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
        }
        tm = TileMap(width=4, height=4, chunks=chunks)
        pf = Pathfinder(tm)
        pf.find((0, 0), (3, 0))
        assert len(pf.cache.entries) == 1

        tm2 = tm.with_collision(1, 0, False).with_collision(1, 1, False)
        tm2 = tm2.with_collision(1, 2, False).with_collision(1, 3, False)
        tm2 = tm2.with_collision(2, 0, False).with_collision(2, 1, False)
        tm2 = tm2.with_collision(2, 2, False).with_collision(2, 3, False)
        assert pf.observe_map(tm2) >= 1

        with pytest.raises(ValueError, match="不可达"):
            pf.find((0, 0), (3, 0))
