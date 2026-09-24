"""sim.world.fog — 区块迷雾 v0（M3 批次 D2，DESIGN §14 未知四轴「空间未知」）。
设计基线（DESIGN §14）：「区块迷雾——最廉价的未知（去一趟就消除），仅辅助」。
- 揭示单位 = chunk（16×16），不是 tile——「最廉价」指状态量级 O(chunks)；
- 揭示语义 = **踏入即永久揭示**（去一趟就消除），无重置、无衰减（M3 最小集；
  「重雾/复暗」若 M5+ 需要再扩，不预造）；
- 纯内存、**不进事件流也不进存档**——迷雾是观察者视角的投影而非世界真相
  （世界真相进事件日志；「谁见过哪里」是视角面，M3 只做 NPC 踏入揭示的
  最小通路，玩家观察面 M4 指令 UI 再接）；
- frozen：reveal 返回新实例（immutability 规约）；revealed 集合保序无意义，
  消费方只问 is_revealed/count，不依赖迭代序（C5：同输入同输出）。
不做：视野遮挡计算（LOS 在感知域 propagation.py）、逐 tile 迷雾（量级不符）。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FogOfWar:
    """已揭示 chunk 集合（immutable；reveal 返回新实例）。"""

    revealed: frozenset[tuple[int, int]] = field(default=frozenset())

    @property
    def revealed_count(self) -> int:
        return len(self.revealed)

    def is_revealed(self, cx: int, cy: int) -> bool:
        return (cx, cy) in self.revealed

    def reveal(self, cx: int, cy: int) -> FogOfWar:
        """踏入 chunk (cx, cy) → 揭示（幂等；frozen 返回新实例）。"""
        return FogOfWar(revealed=self.revealed | {(cx, cy)})

    def reveal_position(self, x: int, y: int, *, chunk_size: int = 16) -> FogOfWar:
        """按 tile 坐标揭示所在 chunk（调用方传实体 pos；chunk_size=CHUNK_SIZE）。"""
        return self.reveal(x // chunk_size, y // chunk_size)


def chunk_neighbors(cx: int, cy: int) -> frozenset[tuple[int, int]]:
    """四邻 chunk 坐标（M3 未用，预留给「踏入半亮邻块」扩展——不接入揭示语义）。"""
    return frozenset({(cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)})
