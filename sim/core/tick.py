"""确定性 tick loop — 固定执行序（m0-core.md §5.2）。

顺序即确定性：新增子系统只能追加到预留挂载点，不得插入中间。
外层 asyncio 驱动（喂时间/刷 I/O）与内层同步 tick 分离——引擎不做模拟内核。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.core.clock import GameClock
from sim.core.events import EventKind, WorldEvent
from sim.core.world import EventBus, TickContext, WorldState
from sim.world.pathfinding import Pathfinder

_MAX_TICKS_PER_FRAME = 240  # 16x = 960 tick/s 上限按 4s catch-up → 单帧封顶


@dataclass
class TickLoop:
    """M0 同步内核。advance_frame 是唯一推进入口（由外层 asyncio 喂 real_dt）。"""

    clock: GameClock
    bus: EventBus
    state: WorldState
    pathfinder: Pathfinder | None = None
    context: TickContext = field(default_factory=TickContext)
    # 本帧待落库事件（外层每帧 flush 到 EventStore）
    pending_events: list[WorldEvent] = field(default_factory=list)
    # 本帧状态增量（外层广播给 WS；M0 = 移动过的实体 id）
    pending_delta_entity_ids: set[str] = field(default_factory=set)

    def advance_frame(self, real_dt: float) -> int:
        """喂入真实秒数，推进 0..N 个 tick（catch-up 封顶）。返回推进数。"""
        n = min(self.clock.advance(real_dt), _MAX_TICKS_PER_FRAME)
        for _ in range(n):
            self._tick_once()
        return n

    def _tick_once(self) -> None:
        """固定执行序：1 实体移动 → 2 定时任务（M0 空）→ 3 感知（M1 挂载点）。"""
        self._step_entity_movement()
        # 预留挂载点（M1+：感知传播 / L1 效用 / Intent 执行时二次校验）
        self.state = self.state.model_copy(update={"tick": self.state.tick + 1})

    def _step_entity_movement(self) -> None:
        """沿路径走一格。路径耗尽不发事件；每格一次 MOVE 不必要——
        移动是 tick 内插值（路径段事件已含全部信息），此步只更新位置。
        """
        moved: dict[str, object] = {}
        for entity_id, entity in self.state.entities.items():
            if not entity.path:
                continue
            nxt = entity.path[0]
            rest = entity.path[1:]
            moved[entity_id] = entity.model_copy(update={"pos": nxt, "path": rest})
            self.pending_delta_entity_ids.add(entity_id)
        if moved:
            self.state = self.state.model_copy(
                update={"entities": {**self.state.entities, **moved}}
            )

    # --- 事件入队（唯一写路径的入口） ---

    def enqueue(self, event: WorldEvent) -> None:
        """校验事件（tick 合法）→ apply 得新状态 → 累积待落库。"""
        if event.tick > self.state.tick + 1:
            msg = f"事件来自未来: {event.tick} > {self.state.tick + 1}"
            raise ValueError(msg)
        result = self.bus.apply(self.state, event, self.context)
        self.state = result.state
        self.pending_events.append(event)
        for d in result.derived:
            self.pending_events.append(d)

    def issue_move(self, entity_id: str, path: list[tuple[int, int]]) -> WorldEvent:
        """便捷入口：外部请求移动（如 WS 的 move_intent）→ 路径段 MOVE 事件。"""
        event = WorldEvent(
            tick=self.state.tick + 1,
            event_type=EventKind.MOVE,
            actor_id=entity_id,
            payload={"entity_id": entity_id, "path": [list(p) for p in path]},
        )
        self.enqueue(event)
        return event

    def drain_events(self) -> list[WorldEvent]:
        """外层每帧取走待落库事件。"""
        out = self.pending_events
        self.pending_events = []
        return out

    def drain_delta(self) -> set[str]:
        """外层每帧取走增量实体 id（WS 广播用）。"""
        out = self.pending_delta_entity_ids
        self.pending_delta_entity_ids = set()
        return out

    def enter_combat(self) -> None:
        self.clock.enter_combat()
        self.context = self.context.with_combat(True)

    def exit_combat(self) -> None:
        self.clock.exit_combat()
        self.context = self.context.with_combat(False)
