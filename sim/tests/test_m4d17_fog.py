"""批次 D17（迷雾 B 案——视觉雾）钉子。

产品裁决落地（M6 移交清单①「迷雾 B 案」；`m6-content-outbound-prestudy.md`
§3.3 帧形状草案照抄；裁 40-4 事件化口径）：

1. **事件工厂**：`fog_reveal_event(tick, chunks)`——chunks 封闭校验
   （非空、int 对）；payload 与 `FogRevealPayload` 同形（只载已踏入事实，
   禁未探索先验——S4 FG-1）；
2. **bus 折叠**：`FOG_REVEAL` handler = no-op 状态折叠（迷雾是观察者投影、
   不进 state_hash——裁 40-4 事件即真相，`fold_fog_reveal` 在投影侧重建；
   同 `_apply_npc_act` 口径：注册 handler 即可重放，状态层零变更）；
3. **内核揭示**：主角踏入新 chunk（移动步）→ `fog.reveal` 事件入流
   （C4 唯一写路径；村民踏入**不**揭示——迷雾是陈默的观察面）；
   TickContext.fog_revealed（帧内新揭示账本）供 WS 投影 drain；
4. **WS 投影**：delta 帧**只在本帧有新揭示**时带可选 `fog={revealed:[…]}`；
   全量快照带全集（重连/读档重同步）——预研稿 §3.3 原案。

出戏边界：帧只载 chunk 坐标（整数对，零枚举零内部数值）——预研稿已核 D-10。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1


# ---------------------------------------------------------------------------
# ① 事件工厂 + bus 折叠
# ---------------------------------------------------------------------------


class TestFogRevealEvent:
    def test_factory_roundtrip(self) -> None:
        from sim.core.events import EventKind, fog_reveal_event

        ev = fog_reveal_event(tick=10, chunks=((2, 3), (0, 0)))
        assert ev.event_type is EventKind.FOG_REVEAL
        assert ev.payload["chunks"] == [[2, 3], [0, 0]]

    def test_factory_rejects_empty(self) -> None:
        from sim.core.events import fog_reveal_event

        with pytest.raises(ValueError, match="空"):
            fog_reveal_event(tick=10, chunks=())

    def test_bus_applies_noop(self) -> None:
        """handler 注册 → apply 不炸且状态逐位不变（no-op 折叠，重放安全）。"""
        from sim.core.events import fog_reveal_event, world_create_event
        from sim.core.tick import TickContext
        from sim.core.world import WorldState, build_default_bus

        state = WorldState(world_seed=42)
        bus = build_default_bus()
        ctx = TickContext()
        state = bus.apply(
            state, world_create_event(tick=0, seed=42, entity_ids=("chenmo",)), ctx
        ).state
        result = bus.apply(state, fog_reveal_event(tick=1, chunks=((3, 2),)), ctx)
        assert result.state == state, "迷雾不进世界态（裁 40-4：事件即真相）"


# ---------------------------------------------------------------------------
# ② 内核揭示：主角踏入新 chunk → fog.reveal 入流
# ---------------------------------------------------------------------------


def _loop_with_chenmo_at(x: int, y: int):
    """主角起于 (x,y)：造世 → 逐格 path 的 MOVE 走到位（move.path 是逐格
    路径；2 点「远距跳跃」与节拍门冲突，实体走不到——夹具必须真走）。"""
    from sim.core.clock import GameClock
    from sim.core.events import move_event, world_create_event
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus

    loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo", "villager_01")))
    steps = [(i, 0) for i in range(x + 1)] if y == 0 else [(x, j) for j in range(y + 1)]
    loop.enqueue(
        move_event(tick=1, actor_id="chenmo", start=(0, 0), goal=(x, y), path=tuple(steps))
    )
    loop.pending_events.clear()  # 初始安顿路径的 fog/移动事件不算
    loop.fog_seen.clear()
    loop.context.fog_revealed.clear()
    loop.advance_frame(2.0)
    assert loop.state.entities["chenmo"].pos == (x, y), "夹具安置失败"
    loop.pending_events.clear()
    return loop


class TestKernelReveal:
    def test_protagonist_entering_new_chunk_reveals(self) -> None:
        """主角移动跨 chunk → fog.reveal 事件在 pending_events；同 chunk 内移动不重复。"""
        from sim.core.events import EventKind

        loop = _loop_with_chenmo_at(4, 0)  # chunk (0,0)
        loop.pending_events.clear()
        loop.issue_move("chenmo", [(x, 0) for x in range(4, 21)])  # 跨入 chunk (1,0)
        loop.advance_frame(5.0)  # 17 格 × 15 tick/格 = 255 tick > 120（2s 不够走完）
        fog_events = [e for e in loop.pending_events if e.event_type is EventKind.FOG_REVEAL]
        assert fog_events, "跨 chunk 移动必须产 fog.reveal"
        chunks = fog_events[0].payload["chunks"]
        assert chunks == [[1, 0]], f"只载新踏入块：{chunks}"

    def test_villager_movement_does_not_reveal(self) -> None:
        """村民踏入不揭示（迷雾=陈默观察面）。"""
        from sim.core.events import EventKind

        loop = _loop_with_chenmo_at(4, 0)
        steps = [(x, 40) for x in range(40, 61)]
        loop.enqueue(
            __import__("sim.core.events", fromlist=["move_event"]).move_event(
                tick=loop.state.tick + 1,
                actor_id="villager_01",
                start=(40, 40),
                goal=(60, 40),
                path=tuple(steps),
            ),
        )
        loop.pending_events.clear()
        loop.advance_frame(6.0)  # 20 格 × 15 tick/格
        assert not [e for e in loop.pending_events if e.event_type is EventKind.FOG_REVEAL]

    def test_reveal_is_idempotent(self) -> None:
        """已揭示 chunk 不再产事件（踏入即永久，幂等）。"""
        from sim.core.events import EventKind, fog_reveal_event

        loop = _loop_with_chenmo_at(4, 0)
        loop.enqueue(fog_reveal_event(tick=loop.state.tick + 1, chunks=((0, 0),)))
        loop.pending_events.clear()
        loop.issue_move("chenmo", [(x, 0) for x in range(4, 7)])  # 同 chunk (0,0) 内移动
        loop.advance_frame(1.0)
        assert not [e for e in loop.pending_events if e.event_type is EventKind.FOG_REVEAL]


# ---------------------------------------------------------------------------
# ③ WS 投影：delta 增量 / 快照全集
# ---------------------------------------------------------------------------


class TestWsProjection:
    def test_delta_carries_fog_only_when_new(self) -> None:
        from sim.api.ws import delta_payload
        from sim.core.clock import GameClock
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=WorldState(world_seed=42))
        # 无新揭示 → 无 fog 键
        p1 = delta_payload(loop, {"chenmo"})
        assert "fog" not in p1
        # 帧内 drain 出新揭示 → fog 键出现（形状=预研稿 §3.3）
        # frozen ctx：set 原地变更（字段不可重绑，容器可变）
        loop.context.fog_revealed.update({(2, 3), (0, 1)})
        p2 = delta_payload(loop, {"chenmo"})
        assert p2["fog"] == {"revealed": [{"cx": 0, "cy": 1}, {"cx": 2, "cy": 3}]}
        loop.context.fog_revealed.clear()

    def test_snapshot_carries_full_revealed_set(self) -> None:
        from sim.api.main import _fallback_map
        from sim.api.ws import snapshot_payload
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=WorldState(world_seed=42))
        loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
        loop.fog_seen.update({(0, 0), (1, 0)})  # 快照真源=已揭示全集（fog_seen）
        snap = snapshot_payload(loop, _fallback_map())
        assert snap["fog"] == {"revealed": [{"cx": 0, "cy": 0}, {"cx": 1, "cy": 0}]}, (
            "快照带全集（重连/读档重同步）"
        )

    def test_delta_fog_sorted_deterministic(self) -> None:
        """revealed 排序确定（(cx,cy) 字典序——C5，不依赖 set 迭代序）。"""
        from sim.api.ws import delta_payload
        from sim.core.clock import GameClock
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(clock=GameClock(), bus=build_default_bus(), state=WorldState(world_seed=42))
        loop.context.fog_revealed.update({(3, 1), (0, 2), (1, 0)})
        a = delta_payload(loop, set())["fog"]["revealed"]
        loop.context.fog_revealed.update({(1, 0), (3, 1), (0, 2)})
        b = delta_payload(loop, set())["fog"]["revealed"]
        assert a == b
