"""A* 寻路 — 网格 + octile 启发 + 确定性 tie-break（m0-core.md §7）。

确定性：open set 用 (f, 坐标字典序) 排序，禁 hash 序——回放路径不因
容器遍历顺序分叉。chunk 增量失效：缓存条目记录途经 chunk，失效精确剔除。
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from sim.world.map import TileMap

# 8 邻接：四正交代价 1，四对角代价 √2
_NEIGHBORS: tuple[tuple[int, int, float], ...] = (
    (1, 0, 1.0),
    (-1, 0, 1.0),
    (0, 1, 1.0),
    (0, -1, 1.0),
    (1, 1, 2**0.5),
    (1, -1, 2**0.5),
    (-1, 1, 2**0.5),
    (-1, -1, 2**0.5),
)
_SQRT2 = 2**0.5


def _octile(dx: int, dy: int) -> float:
    ax, ay = abs(dx), abs(dy)
    return (ax + ay) + (_SQRT2 - 2) * min(ax, ay)


@dataclass
class PathCache:
    """路径缓存：键 (start, goal) → (路径, 途经 chunk 集)。"""

    entries: dict[
        tuple[tuple[int, int], tuple[int, int]],
        tuple[tuple[tuple[int, int], ...], frozenset[tuple[int, int]]],
    ] = field(default_factory=dict)
    max_entries: int = 4096

    def invalidate(self, chunk: tuple[int, int]) -> int:
        """tile_changed 后调用：仅剔除途经该 chunk 的条目。返回剔除数。"""
        stale = [k for k, (_, chunks) in self.entries.items() if chunk in chunks]
        for k in stale:
            del self.entries[k]
        return len(stale)

    def _evict_if_needed(self) -> None:
        if len(self.entries) > self.max_entries:
            # FIFO 淘汰（dict 保序）；确定性不依赖缓存内容，淘汰策略无关正确性
            for k in list(self.entries)[: len(self.entries) - self.max_entries]:
                del self.entries[k]


class Pathfinder:
    """A* 寻路器。持有缓存；TileMap 变更（M3）时逐 chunk 调 invalidate。"""

    def __init__(self, tile_map: TileMap, cache: PathCache | None = None) -> None:
        self._tile_map = tile_map
        self.cache = cache if cache is not None else PathCache()

    def find(self, start: tuple[int, int], goal: tuple[int, int]) -> tuple[tuple[int, int], ...]:
        """返回 start→goal 的完整格路径（含两端）。不可达抛 ValueError。

        缓存命中直接返回（途经 chunk 未失效即有效）。
        """
        key = (start, goal)
        cached = self.cache.entries.get(key)
        if cached is not None:
            return cached[0]
        if not self._tile_map.is_walkable(goal[0], goal[1]):
            msg = f"目标不可通行: {goal}"
            raise ValueError(msg)
        if start == goal:
            return (start,)

        path = self._search(start, goal)
        chunks = frozenset(self._tile_map.chunk_of(x, y) for x, y in path)
        self.cache.entries[key] = (path, chunks)
        self.cache._evict_if_needed()
        return path

    def _search(self, start: tuple[int, int], goal: tuple[int, int]) -> tuple[tuple[int, int], ...]:
        tm = self._tile_map
        # open 堆条目：(f, x, y) — 坐标字典序 tie-break 保证确定性
        open_heap: list[tuple[float, int, int]] = [
            (_octile(goal[0] - start[0], goal[1] - start[1]), start[0], start[1])
        ]
        g_score: dict[tuple[int, int], float] = {start: 0.0}
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        closed: set[tuple[int, int]] = set()

        while open_heap:
            _f, x, y = heapq.heappop(open_heap)
            current = (x, y)
            if current in closed:
                continue
            closed.add(current)
            if current == goal:
                return self._reconstruct(came_from, current)
            cx, cy = current
            for dx, dy, cost in _NEIGHBORS:
                nxt = (cx + dx, cy + dy)
                if nxt in closed or not tm.is_walkable(*nxt):
                    continue
                # 对角移动禁穿角：两正交邻格必须都可通行
                if (
                    dx != 0
                    and dy != 0
                    and not (tm.is_walkable(cx + dx, cy) and tm.is_walkable(cx, cy + dy))
                ):
                    continue
                tentative = g_score[current] + cost
                if tentative < g_score.get(nxt, float("inf")):
                    g_score[nxt] = tentative
                    came_from[nxt] = current
                    f = tentative + _octile(goal[0] - nxt[0], goal[1] - nxt[1])
                    heapq.heappush(open_heap, (f, nxt[0], nxt[1]))
        msg = f"不可达: {start} → {goal}"
        raise ValueError(msg)

    @staticmethod
    def _reconstruct(
        came_from: dict[tuple[int, int], tuple[int, int]], end: tuple[int, int]
    ) -> tuple[tuple[int, int], ...]:
        path = [end]
        while end in came_from:
            end = came_from[end]
            path.append(end)
        path.reverse()
        return tuple(path)
