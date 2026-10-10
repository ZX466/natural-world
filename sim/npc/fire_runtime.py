"""sim.npc.fire_runtime — 火灾实况运行时（批次 D5：火灾+死亡接进实况世界）。

世界自转面：每游戏日凌晨确定性窗口判定起火 → step_fires 每帧蔓延 → 火到
NPC 脚下 → npc.death（对称删除，代价真实可见）。

确定性账（C5）：起火判定是 (seed, tick) 纯函数；step_fires 是纯函数
（rng_draw None = 确定性蔓延——最简口径）。本模块只产出事件，世界状态由
bus fold（C4 唯一写路径）；火格账本是实况侧内存态（同 NpcRuntime）。
"""

from __future__ import annotations

import structlog

from sim.core.events import (
    WorldEvent,
    fire_extinguished_event,
    fire_ignited_event,
    npc_death_event,
)
from sim.core.world import WorldState
from sim.world.fire import FireCell, step_fires

logger = structlog.get_logger(__name__)

#: 起火判定窗口：每游戏日凌晨 3 点（tick ≡ 10800 mod 86400）
_IGNITE_PERIOD_TICKS = 86_400
_IGNITE_PHASE = 3 * 3600
#: 命中概率（约 3 游戏日一场火——镇子有代价但不毁灭；判定纯函数内联哈希）
_IGNITE_PROB_NUM = 34


def ignite_due(seed: int, tick: int) -> bool:
    """起火窗口判定（(seed, tick) 纯函数）：凌晨 3 点 + 确定性哈希抽签。

    每日判定一次；哈希抽签（无 RNG 流依赖——混沌流接线留待熵材料在
    _chenmo/世界驱动重放链稳定后统一换装，行为兼容）。
    """
    if (tick - _IGNITE_PHASE) % _IGNITE_PERIOD_TICKS != 0:
        return False
    import zlib

    draw = zlib.crc32(f"ignite:{seed}:{tick}".encode()) % 100
    return draw < _IGNITE_PROB_NUM


class FireRuntime:
    """活跃火格账本 + 蔓延/熄灭/死亡事件生产（实况侧；世界状态仍由事件 fold）。"""

    def __init__(self, *, cells: tuple[FireCell, ...] = (), fire_seq: int = 0) -> None:
        self.cells = cells
        self.fire_seq = fire_seq

    def step(
        self,
        *,
        tick: int,
        walkable: set[tuple[int, int]] | None = None,
    ) -> list[WorldEvent]:
        """一帧步进（确定性蔓延，无 rng_draw）：新格 ignited / 燃尽 extinguished。"""
        old_cells = self.cells
        result = step_fires(self.cells, tick=tick, walkable=walkable)
        events: list[WorldEvent] = []
        for cell in result.spread_to:
            self.fire_seq += 1
            events.append(
                fire_ignited_event(tick=tick, fire_id=f"fire-{self.fire_seq}", x=cell.x, y=cell.y)
            )
        for fire_id in result.burned_out:
            burned_cell = next((c for c in old_cells if c.fire_id == fire_id), None)
            x, y = (burned_cell.x, burned_cell.y) if burned_cell is not None else (-1, -1)
            events.append(
                fire_extinguished_event(tick=tick, fire_id=fire_id, x=x, y=y, end="fuel_out")
            )
        self.cells = result.cells
        return events

    def collect_deaths(
        self, state: WorldState, *, burning: set[tuple[int, int]]
    ) -> list[WorldEvent]:
        """火格上的活体 → npc.death 事件（对称删除投影由落库事务做）。"""
        deaths: list[WorldEvent] = []
        for entity_id, entity in state.entities.items():
            if entity.pos in burning:
                deaths.append(npc_death_event(tick=state.tick, entity_id=entity_id))
                logger.info("fire.claimed", entity_id=entity_id, pos=str(entity.pos))
        return deaths

    def ignite_at(self, *, tick: int, x: int, y: int) -> list[WorldEvent]:
        """起火（ignite_due 命中后由世界驱动调用）：首格入账本 + ignited 事件。"""
        self.fire_seq += 1
        cell = FireCell(x=x, y=y, fire_id=f"fire-{self.fire_seq}", fuel_ticks=12, ignited_tick=tick)
        self.cells = (*self.cells, cell)
        return [fire_ignited_event(tick=tick, fire_id=f"fire-{self.fire_seq}", x=x, y=y)]
