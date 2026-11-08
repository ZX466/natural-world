"""Event-cursor terrain projection shared by ground collision and player support."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from sim.core.events import EventKind, TileChangedPayload, VoxelEditedPayload, WorldEvent
from sim.world.map import CHUNK_SIZE, TileMap


class SurfaceMap:
    def __init__(self, tile_map: TileMap, height_of: Callable[[int, int], int]) -> None:
        self.tile_map = tile_map
        self._base_map = tile_map
        self._base_height = height_of
        self._heights: dict[tuple[int, int], int] = {}
        self._voxel_tiles: dict[tuple[int, int], int] = {}
        # Strong references prevent id reuse while a drained batch is being committed.
        self._observed: list[WorldEvent] = []

    def height_at(self, x: int, y: int) -> int:
        if not self.tile_map.in_bounds(x, y):
            return 0
        if (x, y) in self._heights:
            return self._heights[(x, y)]
        if self._base_map.is_walkable(x, y):
            return 1
        height = self._base_height(x, y)
        if type(height) is not int or not 0 <= height <= 3:
            raise ValueError("invalid surface height")
        return height

    def _ground(self, x: int, y: int) -> int:
        chunk = self._base_map.chunks[self._base_map.chunk_of(x, y)]
        return chunk.ground[(y % CHUNK_SIZE) * CHUNK_SIZE + x % CHUNK_SIZE]

    def _change(self, x: int, y: int, height: int, walkable: bool) -> None:
        if not self.tile_map.in_bounds(x, y):
            raise ValueError("surface edit out of bounds")
        self._heights[(x, y)] = height
        self.tile_map = self.tile_map.with_collision(x, y, walkable and height == 1)

    def apply(self, event: WorldEvent) -> bool:
        """Fold a historical event once; no inventory or database side effects."""
        if event.event_type is EventKind.VOXEL_EDITED:
            p = VoxelEditedPayload.model_validate(event.payload)
            height = p.result_height(self.height_at(p.x, p.y))
            self._voxel_tiles[(p.x, p.y)] = height
            self._change(
                p.x, p.y, height, p.action == "dig" and height == 1 and self._ground(p.x, p.y) != 0
            )
            return True
        if event.event_type is EventKind.TILE_CHANGED:
            tile = TileChangedPayload.model_validate(event.payload)
            pending = self._voxel_tiles.pop((tile.x, tile.y), None)
            height = tile.height if tile.height is not None else pending
            if height is None:
                height = 1 if tile.tile_id != 0 else 2
            self._change(tile.x, tile.y, height, tile.tile_id != 0)
            return True
        return False

    def observe(self, event: WorldEvent) -> bool:
        changed = self.apply(event)
        if changed:
            self._observed.append(event)
        return changed

    def observe_unseen(self, events: Iterable[WorldEvent]) -> bool:
        changed = False
        for event in events:
            if not any(event is prior for prior in self._observed):
                changed = self.observe(event) or changed
        return changed

    def mark_flushed(self, events: Iterable[WorldEvent]) -> None:
        completed = list(events)
        self._observed = [
            event for event in self._observed if not any(event is flushed for flushed in completed)
        ]


def standable(
    tile_map: TileMap, height_of: Callable[[int, int], int], x: int, y: int, elevation: int
) -> bool:
    return (
        tile_map.in_bounds(x, y)
        and 1 <= elevation <= 3
        and height_of(x, y) == elevation
        and (elevation > 1 or tile_map.is_walkable(x, y))
    )
