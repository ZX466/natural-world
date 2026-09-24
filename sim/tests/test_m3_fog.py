"""D2 空间迷雾 — 区块迷雾 v0（m3-plan 批次 D2，DESIGN §14 未知四轴「空间未知」）。

设计基线（DESIGN §14）：「区块迷雾——最廉价的未知（去一趟就消除），仅辅助」。
- 揭示单位 = chunk（16×16），不是 tile——「最廉价」指状态量级 O(chunks)；
- 揭示语义 = **踏入即永久揭示**（去一趟就消除），无重置、无衰减（M3 最小集）；
- 纯内存、**不进事件流也不进存档**——迷雾是观察者视角的投影而非世界真相
  （§14 铁律：世界真相进事件日志；「谁见过哪里」是记忆/视角面，M3 只做
  NPC 踏入揭示的最小通路，玩家面 M4 指令 UI 再接）；
- frozen：reveal 返回新实例（immutability 规约）。
"""
from __future__ import annotations

import pytest

from sim.world.fog import FogOfWar, chunk_neighbors
from sim.world.map import CHUNK_SIZE, Chunk, TileMap


class TestReveal:
    """踏入揭示语义。"""

    @pytest.mark.t1
    def test_reveal_single_chunk(self) -> None:
        fog = FogOfWar()
        assert not fog.is_revealed(0, 0)
        new = fog.reveal(0, 0)
        assert new.is_revealed(0, 0)
        # frozen：原实例不变
        assert not fog.is_revealed(0, 0)

    @pytest.mark.t1
    def test_reveal_idempotent(self) -> None:
        fog = FogOfWar().reveal(1, 1).reveal(1, 1)
        assert fog.revealed_count == 1

    @pytest.mark.t1
    def test_reveal_by_position_tiles_map_to_chunk(self) -> None:
        fog = FogOfWar()
        # 踏入 (15, 20) → chunk (0, 1) 整块揭示
        new = fog.reveal_position(15, 20)
        assert new.is_revealed(0, 1)
        assert new.is_revealed(0, 1)  # 16×16 整块

    @pytest.mark.t1
    def test_reveal_count_grows(self) -> None:
        fog = FogOfWar()
        fog = fog.reveal(0, 0).reveal(1, 0).reveal(0, 1)
        assert fog.revealed_count == 3


class TestChunkNeighbors:
    """邻接（M3 最小集：踏入揭示本块，不扩 8 邻——「去一趟」= 本块）。"""

    @pytest.mark.t1
    def test_four_neighbors(self) -> None:
        assert chunk_neighbors(2, 2) == {(1, 2), (3, 2), (2, 1), (2, 3)}


class TestFogIntegration:
    """与 TileMap 的缝：按实体位置揭示（调用方从 state.entities 取 pos）。"""

    @pytest.mark.t1
    def test_reveal_position_on_real_map(self) -> None:
        m = TileMap(
            width=CHUNK_SIZE * 2,
            height=CHUNK_SIZE * 2,
            chunks={
                (cx, cy): Chunk(
                    cx=cx,
                    cy=cy,
                    ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                    collision=(False,) * (CHUNK_SIZE * CHUNK_SIZE),
                )
                for cx in range(2)
                for cy in range(2)
            },
        )
        fog = FogOfWar()
        cx, cy = m.chunk_of(CHUNK_SIZE + 3, CHUNK_SIZE + 4)
        fog = fog.reveal(cx, cy)
        assert fog.is_revealed(1, 1)
