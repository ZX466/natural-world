"""火灾蔓延机制面 — 批次 D（M5-A9 数据面的机制消费方；裁 33 + K12 订正后形态）。

**职责边界（最小面）**：
- 起火/熄灭**不经本模块**——`FireStore.upsert_fire/set_fire_end` 是唯一写入口（F2/W-D1）；
- 本模块只做**蔓延步进**：给定当前活跃火场集合（`FireRow`），产出**本 tick**的
  蔓延/烧毁/熄灭决策（事件清单，交调用方经既有 `matter.damage` 族落库）；
- **蔓延必须 O(格数)**（P11 红线：O(G²) 成对扫描 G=1024 时 39.1ms 一次蔓延步即破线
  2.4x，O(G) 四邻膨胀 174.5µs ⇒ 224x）——实现 = 火格四邻集合运算，**禁**双层 for
  成对判邻；
- **事件预算（W-D3 / pi 定标 N=2）**：一个 tick 的聚合跃迁事件 ≤ `N_PER_10TICK`
  语义——本模块**每 tick 至多 1 条**「蔓延跃迁」聚合事件（多格同时起火合并为
  一条 matter.damage，坐标取质心哨兵 -1/-1 或首格）；传播步进本身**零事件**
  （无状态变更即零事件，fire_store 模块注口径）；
- **烧毁走既有族**（F4 守恒）：材料消耗产 `material.moved{reason="burned",
  to_ref="world:burned"}`，**禁**自定义消耗路径（T1 材料守恒逐位相等）；
- **熄灭是纯数据面**：燃料尽 ⇒ 调用方经 `FireStore.set_fire_end(end="fuel_out")`
  落 `fire.extinguished`（本模块只返回建议，不直接写）。

**纯函数**：`step_fires(...)` 无状态无 IO（输入=活跃火格快照，输出=事件清单+新火格），
同输入必同输出（C5）；本模块**不持有** `FireStore`/session——那是调用方的装配。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from sim.core.events import EventKind, WorldEvent, material_moved_event, matter_event

#: 每游戏日同时活跃火场上限 F 的约束式（pi P11 反解：2F ≤ CASCADE_EVENT_BUDGET_PER_FRAME=100
#: ⇒ F ≤ 50；N=2 语义钉的配套常量——**机制面只消费这个上界做防御截断**，超出即拒绝新火格
#: 展开，绝不绝不调大 N）。
MAX_ACTIVE_FIRES: Final[int] = 50

#: 每个活跃火场每 tick 的蔓延格数上界（P11「蔓延必须 O(格数)」的步进预算；
#: 内容常量·占位值——定标轮按实测翻 advisory→正式）。
SPREAD_CELLS_PER_TICK: Final[int] = 2

#: 单格燃料（tick 数）——烧尽即 `fuel_out`（内容常量·占位值；定标轮收口）。
FUEL_TICKS_PER_CELL: Final[int] = 30

#: 烧毁材料的去向哨兵（F4 守恒：`to_ref="world:burned"`，A8/K12 定案）。
BURNED_TO_REF: Final[str] = "world:burned"


@dataclass(frozen=True)
class FireCell:
    """一个燃烧中的火格（机制面内存态——**刻意不入库**，A8「火场中间态不入库」）。

    `fuel_ticks`：剩余燃烧 tick；`ignited_tick`：本格起火 tick（聚合事件坐标用）。
    """

    x: int
    y: int
    fire_id: str
    fuel_ticks: int
    ignited_tick: int


@dataclass(frozen=True)
class FireStepResult:
    """一个 tick 的蔓延决策（纯输出；调用方落事件+更新内存格）。

    - `spread_to`：本 tick 新点燃的格（调用方为**新场**建 `fire.ignited`——每场一条，
      W-D3 按**场**聚合）；
    - `burn_damage`：烧毁物质事件（`matter.damage` + `material.moved{burned}`，
      一次 tick 至多各 **1 条**——「无状态变更零事件」的反面即「有变更至多一条聚合」）；
    - `burned_out`：燃料尽的 fire_id 清单（调用方走 `FireStore.set_fire_end("fuel_out")`）；
    - `cells`：步进后的全量火格（新 tick 的输入，纯内存，不入库）。
    """

    spread_to: tuple[FireCell, ...]
    burn_damage: tuple[WorldEvent, ...]
    burned_out: tuple[str, ...]
    cells: tuple[FireCell, ...]


def _neighbors(cell: FireCell) -> tuple[tuple[int, int], ...]:
    """四邻坐标（O(1)；**禁**双层 for 成对判邻——P11 O(G) 红线的微观实现）。"""
    return ((cell.x + 1, cell.y), (cell.x - 1, cell.y), (cell.x, cell.y + 1), (cell.x, cell.y - 1))


def step_fires(
    cells: tuple[FireCell, ...],
    *,
    tick: int,
    walkable: set[tuple[int, int]] | None = None,
    occupied: set[tuple[int, int]] | None = None,
    rng_draw: Callable[[], float] | None = None,
) -> FireStepResult:
    """一个 tick 的蔓延步进（**纯函数**；O(格数)，禁 O(G²)）。

    Args:
        cells: 当前活跃火格（上一 tick 的输出）。
        tick: 当前 tick。
        walkable: 可燃格集合（None = 全图可燃——最小面不做地形耦合）。
        occupied: 已被其它火格占据的格（防重复点燃；None = 用 cells 自身）。
        rng_draw: 蔓延概率抽签（None = 确定性蔓延——C5 最简口径；接混沌流时传
            `chaotic_at("chaos", tick)` 阈值比较）。

    Returns:
        :class:`FireStepResult`（事件清单 + 新格集；调用方落库并推进）。
    """
    live = tuple(c for c in cells if c.fuel_ticks > 0)
    occupied_set = set(occupied) if occupied is not None else {(c.x, c.y) for c in live}
    # O(G)：所有火格的四邻并集（格数 × 4），**非**成对扫描。
    frontier: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for cell in live:
        for nx, ny in _neighbors(cell):
            key = (nx, ny)
            if key in seen or key in occupied_set:
                continue
            seen.add(key)
            if walkable is not None and key not in walkable:
                continue
            frontier.append(key)

    # 蔓延预算：本 tick 新点燃 ≤ SPREAD_CELLS_PER_TICK × 场数，且全场总数 ≤ MAX_ACTIVE_FIRES
    # （pi 约束式 2F ≤ 100 的机制面防御；F 超上界时**不再新增**——绝不绝不调大 N）。
    budget = SPREAD_CELLS_PER_TICK * max(1, len(live))
    room = MAX_ACTIVE_FIRES - len(live)
    spread_budget = max(0, min(budget, room))
    spread: list[FireCell] = []
    for x, y in frontier:
        if len(spread) >= spread_budget:
            break
        if rng_draw is not None and rng_draw() > 0.5:
            continue
        parent = next(c for c in live if (x, y) in [(n[0], n[1]) for n in _neighbors(c)])
        spread.append(
            FireCell(
                x=x,
                y=y,
                fire_id=parent.fire_id,
                fuel_ticks=FUEL_TICKS_PER_CELL,
                ignited_tick=tick,
            )
        )

    # 烧毁：每格燃料 -1；本 tick 有任何格在烧 ⇒ **至多 1 条** matter.damage 聚合
    # （W-D3：一次 tick ≤1 条跃迁事件；坐标哨兵 -1/-1 = 场聚合无单点）。
    events: list[WorldEvent] = []
    stepped: list[FireCell] = []
    burned_out: list[str] = []
    if live:
        events.append(
            matter_event(
                tick,
                EventKind.MATTER_DAMAGE,
                matter_id=f"fire:{live[0].fire_id}",
                x=-1,
                y=-1,
                amount=-0.1,
                note="fire-spread",
            )
        )
        events.append(
            material_moved_event(
                tick,
                transfer_id=f"burn:{tick}:{live[0].fire_id}",
                material_id="fuel",
                quantity=0.1,
                from_ref="world:vegetation",
                to_ref=BURNED_TO_REF,
                reason="burned",
            )
        )
    for cell in live:
        remain = cell.fuel_ticks - 1
        if remain <= 0:
            burned_out.append(cell.fire_id)
            continue
        stepped.append(
            FireCell(
                x=cell.x, y=cell.y, fire_id=cell.fire_id, fuel_ticks=remain,
                ignited_tick=cell.ignited_tick,
            )
        )
    stepped.extend(spread)
    stepped.sort(key=lambda c: (c.x, c.y, c.fire_id))  # C5：输出序确定
    return FireStepResult(
        spread_to=tuple(spread),
        burn_damage=tuple(events),
        burned_out=tuple(sorted(set(burned_out))),
        cells=tuple(stepped),
    )
