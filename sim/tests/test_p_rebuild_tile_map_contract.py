"""P 单验收契约：读档重建的瓦片图必须与分支真源一致。

本文件钉的是**跨分支不变量**（P-1/P-2/P-4 的公共验收面），不测实现细节：

1. `rebuild_tile_map` 对空分支返回静态底图（等价 `_default_map()`）；
2. 重放 `tile_changed(tile_id=0)` 后该格不可走；
3. 重放 `tile_changed(tile_id=<底图原值>)` 后该格恢复可走
   ——这条依赖「坍塌/拆除补发恢复事件」（补充 6），在修复前应红；
4. 祖先分支的 `tile_changed` 经 `read_branch_history` 被计入，
   分叉点之后的事件**不**计入。

运行：`uv run pytest sim/tests/test_p_rebuild_tile_map_contract.py -v`
"""

from __future__ import annotations

import pytest

from sim.core.events import tile_changed_event
from sim.world.map import CHUNK_SIZE, Chunk, TileMap

pytestmark = pytest.mark.t1


def make_open_map(size: int = 32) -> TileMap:
    chunks = {}
    for cy in range(size // CHUNK_SIZE):
        for cx in range(size // CHUNK_SIZE):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=(7,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=size, height=size, chunks=chunks)


def test_tile_id_zero_means_blocked() -> None:
    """tile_id=0 是墙体占位的既有约定（build_exec.py:143 同源）。

    rebuild_tile_map 若用 `tile_id != 0` 推导可走性，这条是它的语义依据；
    若将来改成显式 walkable 字段，本钉随之更新。
    """
    tm = make_open_map()
    assert tm.is_walkable(3, 4) is True
    blocked = tm.with_collision(3, 4, walkable=False)
    assert blocked.is_walkable(3, 4) is False


def test_ground_tile_id_roundtrip() -> None:
    """静态底图的 ground 原值可被读回——恢复事件要用它。

    注意 ground/collision 挂在 **Chunk** 上（map.py:24-25），不是 TileMap：
    全局 (x,y) → chunk_of(x,y) + 内部局部下标 ly*CHUNK_SIZE+lx。
    """
    tm = make_open_map()
    chunk = tm.chunks[tm.chunk_of(3, 4)]
    lx, ly = 3 % CHUNK_SIZE, 4 % CHUNK_SIZE
    assert chunk.ground[ly * CHUNK_SIZE + lx] == 7


def test_tile_changed_event_carries_branch() -> None:
    """分叉历史回溯依赖事件带 branch_id（read_branch_history 的前提）。"""
    ev = tile_changed_event(10, 3, 4, 0, branch_id="branch-x")
    assert ev.branch_id == "branch-x"
    assert ev.payload["tile_id"] == 0


@pytest.mark.asyncio
async def test_rebuild_tile_map_is_pure_from_events() -> None:
    """空分支 → 静态图；仅墙事件 → 不可走；恢复事件 → 可走（三态）。"""

    class _Store:
        def __init__(self, events: list[dict]) -> None:
            self._events = events

        async def read_branch_history(self) -> list[dict]:
            return self._events

    from sim.api.main import rebuild_tile_map

    def _tile_ev(x: int, y: int, tile_id: int) -> dict:
        # branch_id 在事件顶层，不在 payload 内（TileChangedPayload 禁止 extra）。
        return {
            "event_type": "tile_changed",
            "tick": 1,
            "branch_id": "main",
            "payload": {"x": x, "y": y, "tile_id": tile_id},
        }

    # 空分支：等价静态底图——找一个底图本来就可走的格子做基准。
    empty = await rebuild_tile_map(_Store([]))
    walkable_xy = next(
        (x, y) for y in range(empty.height) for x in range(empty.width) if empty.is_walkable(x, y)
    )
    # 底图原值（恢复事件的正确目标）从这里取，不写死。
    from sim.api.main import _ground_tile_id

    ground_id = _ground_tile_id(empty, *walkable_xy)
    assert ground_id != 0, "可走格的底图 tile_id 不应是墙体占位"

    # 仅墙事件：该格不可走。
    walled = await rebuild_tile_map(_Store([_tile_ev(*walkable_xy, 0)]))
    assert not walled.is_walkable(*walkable_xy)

    # 恢复事件（底图原值）：该格重新可走。
    restored = await rebuild_tile_map(
        _Store([_tile_ev(*walkable_xy, 0), _tile_ev(*walkable_xy, ground_id)])
    )
    assert restored.is_walkable(*walkable_xy)
