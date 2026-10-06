"""确定性 tick loop — 固定执行序（m0-core.md §5.2）。

顺序即确定性：新增子系统只能追加到预留挂载点，不得插入中间。
外层 asyncio 驱动（喂时间/刷 I/O）与内层同步 tick 分离——引擎不做模拟内核。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from sim.core.clock import GameClock
from sim.core.entropy import EntropyMixer
from sim.core.events import WorldEvent, combat_scale_event, move_event
from sim.core.rng import RngRegistry
from sim.core.world import EventBus, TickContext, WorldState
from sim.world.pathfinding import Pathfinder

_MAX_TICKS_PER_FRAME = 240  # 16x = 960 tick/s 上限按 4s catch-up → 单帧封顶
_PERCEPTION_EVERY_N_TICKS = 2  # H-1 方案 3：视觉传播降采样（听觉随帧全速）
_NPC_DECISION_INTERVAL = 10  # 批次 B：L1 决策节拍（60tps 下每秒 5 轮，防事件洪泛）
_MOVE_TICKS_PER_TILE = 15  # 批次 D1：行走节拍（1x 下 60/15 = 4 格/秒，星露谷手感；
# 16x 下 64 格/秒——倍速快进语义，视觉瞬移属预期）
_MOVE_PHASE_SPAN = 15  # 相位散布跨度（0..14，与节拍同模——每 tick 都有人迈步）


def entity_move_phase(entity_id: str) -> int:
    """实体行走相位（确定性纯函数，无 RNG 流）：id 哈希散布进 [0, 节拍)。

    作用：不同实体在同一 tick 内交错迈步（无全员齐步脉冲）；同 id 恒同相位
    ⇒ 重放逐位一致（C5）。crc32 快且散布均匀，够用。
    """
    import zlib

    return zlib.crc32(entity_id.encode()) % _MOVE_TICKS_PER_TILE

# 感知装配钩子签名：(state, tick_events) -> dict[rtoken, frame]。
# 返回值 value 用 object 避免内核 import 感知域（内核零依赖感知，钩子由外层注入）；
# Mapping 保持值型协变，调用方 PerceptionFrame 可直接传入。
PerceptionHook = Callable[[WorldState, list[WorldEvent]], "Mapping[str, object]"]

# NPC 决策钩子签名（批次 B）：(state, tick) -> 本节拍事件批次（WorldEvent 列表）。
# 返回批次由 TickLoop 经 enqueue 逐条入流（C4 唯一写路径）；None/空 = 本拍无事。
# 与 PerceptionHook 同纪律：内核零依赖 npc 域，实现由装配层注入（main.py）。
NpcRuntimeHook = Callable[[WorldState, int], "list[WorldEvent] | None"]


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
    # M1 感知：tick 内装配的最新帧（rtoken → frame）；感知域消费，WS 不广播
    perception_frames: Mapping[str, object] = field(default_factory=dict)
    _perception_hook: PerceptionHook | None = field(default=None, repr=False, compare=False)
    # 批次 B：NPC 决策钩子（每 _NPC_DECISION_INTERVAL tick 一次）
    _npc_hook: NpcRuntimeHook | None = field(default=None, repr=False, compare=False)

    def advance_frame(self, real_dt: float) -> int:
        """喂入真实秒数，推进 0..N 个 tick（catch-up 封顶）。返回推进数。"""
        n = min(self.clock.advance(real_dt), _MAX_TICKS_PER_FRAME)
        for _ in range(n):
            self._tick_once()
        return n

    def _tick_once(self) -> None:
        """固定执行序：0 熵注入（M5 批次 A 接线）→ 1 实体移动 → 2 定时任务（M0 空）→ 3 感知。"""
        self._maybe_daily_reseed()
        self._step_entity_movement()
        self._run_npc_runtime()  # 批次 B：定时任务挂载点兑现（决策节拍）
        self._run_perception()
        # 预留挂载点（M1+：L1 效用 / Intent 执行时二次校验）
        self.state = self.state.model_copy(update={"tick": self.state.tick + 1})

    def _maybe_daily_reseed(self) -> None:
        """每日天气熵注入（DESIGN §11；M5 批次 A 的「inject 生产接线」兑现）。

        `daily_reseed_due(tick)` 为真时：用 `state.world_seed` 重建 `RngRegistry`
        （weather 既有口径——materials 仅含已注入流，纯函数可重建）→
        `EntropyMixer.mix(WEATHER_STREAM, tick)` → 事件经 `enqueue` 落日志
        （C4 唯一写路径；mix 返回的新 registry 的 materials 随事件材料重放可重建，
        状态层 no-op——见 `_apply_entropy_inject`）。tick 0 也注入（首日天气
        同走注入路径，weather.daily_reseed_due 口径）。

        registry 本体不入 `WorldState`（不碰 schema/state_hash）：mix 内部把新
        registry 的材料记录在熵事件的 payload 里，消费方（wind/chaotic 抽签）
        按事件流重放 `replay_mix` 即逐位一致（C5）；`TickContext.rng_cache` 保持
        抽签进度缓存（不入快照）。
        """
        from sim.world.weather import WEATHER_STREAM, daily_reseed_due

        if not daily_reseed_due(self.state.tick):
            return
        registry = RngRegistry(world_seed=self.state.world_seed)
        _, event = EntropyMixer(rng=registry).mix(WEATHER_STREAM, tick=self.state.tick)
        self.enqueue(event)

    def _run_perception(self) -> None:
        """感知挂载点（C06-③）：感知引擎挂入时每帧装配，替换为真实引擎。

        M0 内核不 import 感知域（内核零依赖感知）；装配入口由
        sim.perception.senses.run_perception_step 提供，经 attach_perception 注入，
        保持 tick loop 对感知实现解耦（引擎替换不回改内核）。
        """
        hook = self._perception_hook
        if hook is None:
            return
        # 视觉降采样节拍：奇数 tick 跳过（帧保持上一帧内容），H-1 方案 3
        if self.state.tick % _PERCEPTION_EVERY_N_TICKS == 1:
            return
        frames = hook(self.state, self.pending_events)
        if frames:
            self.perception_frames = frames

    def attach_perception(self, hook: PerceptionHook) -> None:
        """注入感知装配钩子：签名 (state, tick_events) -> dict[rtoken, frame]。"""
        self._perception_hook = hook

    def attach_npc_runtime(self, hook: NpcRuntimeHook) -> None:
        """注入 NPC 决策钩子（批次 B）：每 _NPC_DECISION_INTERVAL tick 一次。

        返回的事件批次立即 enqueue（本 tick 入流）——NPC_ACT 走 no-op handler
        （记录面），MOVE 走正式 handler（真驱动）。None/空返回 = 本拍无事。
        """
        self._npc_hook = hook

    def _run_npc_runtime(self) -> None:
        """定时任务挂载点（M0 预留 → 批次 B 兑现）：决策节拍驱动 NPC runtime。"""
        hook = self._npc_hook
        if hook is None or self.state.tick % _NPC_DECISION_INTERVAL != 0:
            return
        batch = hook(self.state, self.state.tick)
        if not batch:
            return
        for event in batch:
            self.enqueue(event)

    def _step_entity_movement(self) -> None:
        """沿路径走一格（批次 D1 行走节拍：非每 tick 一步）。

        节拍门：`(state.tick + entity_move_phase(entity_id)) % _MOVE_TICKS_PER_TILE == 0`
        时本实体才迈步——1x 下 4 格/秒（视觉可辨），16x 下 64 格/秒（快进语义）。
        相位偏移使不同实体在同 tick 内交错迈步（无齐步脉冲）；同 id 恒同相位，
        重放逐位一致（C5：节拍是 tick 与 id 的纯函数，无 RNG 状态流）。
        路径耗尽不发事件；每格一次 MOVE 不必要——移动是 tick 内插值（路径段
        事件已含全部信息），此步只更新位置。
        """
        moved: dict[str, object] = {}
        for entity_id, entity in self.state.entities.items():
            if not entity.path:
                continue
            if (self.state.tick + entity_move_phase(entity_id)) % _MOVE_TICKS_PER_TILE != 0:
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
        """便捷入口：外部请求移动（如 WS 的 move_intent）→ 路径段 MOVE 事件。

        payload 白名单与 start/goal 一致性校验在 move_event 工厂内强制。
        """
        if not path:
            msg = "空路径"
            raise ValueError(msg)
        event = move_event(
            tick=self.state.tick + 1,
            actor_id=entity_id,
            start=path[0],
            goal=path[-1],
            path=tuple(path),
        )
        self.enqueue(event)
        return event

    def issue_combat_scale(self, entering: bool) -> WorldEvent:
        """战斗时间尺切换：clock 即时切换 + 事件落日志（codex 意见 1：回放语义）。"""
        event = combat_scale_event(tick=self.state.tick + 1, entering=entering)
        if entering:
            self.enter_combat()
        else:
            self.exit_combat()
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
