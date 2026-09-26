"""M5-K8 意愿独白 S2C 广播通路（kilo 域施工）。

任务卡（talking.txt 2026-09-26）：把 M4-B2 意愿管线（`sim/agent/will.py`：
WillingnessExpression{band, monologue, defers}）推到戏内三形态（DESIGN §8：
头顶气泡/思维面板/计划看板）的 S2C 广播。判据与边界：

- **产码走事件流（案 A）**：`npc.monologue` WorldEvent 进 `EventKind`/事件日志
  （§14「世界真相进事件日志」→ 可重放）；WS 侧只做「事件 → 帧」投影，
  **不改内容**（逐位一致）。案 B（直接帧）因不可重放被否决（见 receipt 对比）。
- **投递面契约（§8 三形态）**：帧只含 `form`+`content`（ws-protocol §4.2 W7
  字段最小化：**无 rtoken/actor**）→ 路由只能由服务端按 form 决定：
  `bubble`/`plan` 广播（旁观者可见）；`thought` 定向本人（思维面板=私密）。
  未知 form fail-closed 不投（不猜面）。
- **defers→plan 联动（§10 四档）**：band=3「先做别的再绕回来」在 K7 plan 账本
  体现（推迟前缀，戏内措辞非系统词）。

出戏边界（X 系）：冲突度 score/band 档位号/w₁-w₄ 永不进任何载荷或文本；
`NpcMonologuePayload.extra="forbid"` 是构造层护栏。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi import WebSocket

from sim.agent.will import WillingnessExpression, WillingnessVerdict, willingness_expression
from sim.api.ws import (
    MONOLOGUE_DELIVERY_ALL,
    MONOLOGUE_DELIVERY_SELF,
    ConnectionManager,
    monologue_events_to_frames,
    monologue_payload,
    route_monologue,
)
from sim.core.events import (
    EventKind,
    NpcMonologuePayload,
    npc_monologue_event,
)
from sim.npc.plan_view import (
    DEFER_PLAN_PREFIX,
    PlanDeltaStore,
    defer_plan_text,
    reset_plan_registry,
    set_plan_from_expression,
)


@pytest.fixture(autouse=True)
def _clean_plan_registry() -> Iterator[None]:
    reset_plan_registry()
    yield
    reset_plan_registry()


# ---------------------------------------------------------------------------
# 假 WebSocket：记录收帧（测投递面路由，不碰真网络）
# ---------------------------------------------------------------------------


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


def _register(mgr: ConnectionManager, ws: Any, subscriber_id: str | None = None) -> None:
    """登记假 WS：测试 duck type 只实现 send_json，cast 满足 FastAPI WebSocket 标注。"""
    mgr.register(cast("WebSocket", ws), subscriber_id)


def _subscriber_of(mgr: ConnectionManager, ws: Any) -> str | None:
    return mgr.subscriber_of(cast("WebSocket", ws))


def _unregister(mgr: ConnectionManager, ws: Any) -> None:
    mgr.unregister(cast("WebSocket", ws))


# ---------------------------------------------------------------------------
# K8-① 事件产码：npc.monologue 进事件流（案 A），payload 白名单护栏
# ---------------------------------------------------------------------------


class TestMonologueEvent:
    """K8-① 事件面：构造入口 + 白名单（数值/档位号进不来）。"""

    def test_event_kind_registered(self) -> None:
        assert EventKind.NPC_MONOLOGUE == "npc.monologue"

    def test_event_actor_is_npc(self) -> None:
        e = npc_monologue_event(tick=5, npc_id="chenmo", form="thought", content="我干嘛要干这个")
        assert e.event_type is EventKind.NPC_MONOLOGUE
        assert e.actor_id == "chenmo"
        assert e.tick == 5

    def test_payload_keys_whitelist(self) -> None:
        """载荷只有 npc_id/form/content——无 score/band/数值（出戏边界）。"""
        e = npc_monologue_event(tick=1, npc_id="n", form="bubble", content="唔")
        assert set(e.payload) == {"npc_id", "form", "content"}

    @pytest.mark.parametrize("form", ["bubble", "thought", "plan"])
    def test_form_three_values_accepted(self, form: str) -> None:
        e = npc_monologue_event(tick=1, npc_id="n", form=form, content="x")
        assert e.payload["form"] == form

    def test_form_out_of_enum_rejected(self) -> None:
        with pytest.raises(ValueError, match="form"):
            npc_monologue_event(tick=1, npc_id="n", form="shout", content="x")

    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValueError):
            npc_monologue_event(tick=1, npc_id="n", form="bubble", content="")

    def test_payload_extra_field_rejected(self) -> None:
        """出戏边界：夹带 score/band 必须被 extra=forbid 挡下。"""
        with pytest.raises(ValueError):
            NpcMonologuePayload.model_validate(
                {"npc_id": "n", "form": "bubble", "content": "x", "score": 0.9}
            )
        with pytest.raises(ValueError):
            NpcMonologuePayload.model_validate(
                {"npc_id": "n", "form": "bubble", "content": "x", "band": 3}
            )


# ---------------------------------------------------------------------------
# K8-② 帧投影逐位一致（事件 → 帧，内容零改写）
# ---------------------------------------------------------------------------


class TestFrameProjection:
    """K8-② 事件 → WS 帧：content 逐位一致；帧不含 actor/rtoken。"""

    def test_frame_shape_and_channel(self) -> None:
        frame = monologue_payload("thought", "我干嘛要干这个")
        assert frame["type"] == "monologue"
        assert frame["channel"] == "narrative"
        assert frame["form"] == "thought"
        assert frame["content"] == "我干嘛要干这个"
        assert "ws_seq" in frame and frame["ws_seq"] == 0

    def test_frame_has_no_actor_or_rtoken(self) -> None:
        """W7 字段最小化：独白帧只含 form+content，无 actor/rtoken（出戏边界）。"""
        frame = monologue_payload("bubble", "唔")
        assert "rtoken" not in frame
        assert "actor" not in frame and "npc_id" not in frame
        assert set(frame) == {"type", "channel", "v", "ws_seq", "form", "content"}

    def test_projection_bit_exact(self) -> None:
        """事件 payload content → 帧 content 逐位一致（零改写）。"""
        e = npc_monologue_event(tick=3, npc_id="chenmo", form="plan", content="先磨蹭一会儿吧")
        frames = monologue_events_to_frames([e])
        assert frames == [("chenmo", monologue_payload("plan", "先磨蹭一会儿吧"))]

    def test_projection_ignores_non_monologue_events(self) -> None:
        """非 monologue 事件（如 npc.act / move）不产独白帧。"""
        from sim.core.events import move_event, npc_act_event

        events = [
            move_event(tick=1, actor_id="a", start=(0, 0), goal=(1, 1), path=((0, 0), (1, 1))),
            npc_act_event(tick=1, npc_id="a", action="eat"),
            npc_monologue_event(tick=1, npc_id="a", form="bubble", content="饿"),
        ]
        frames = monologue_events_to_frames(events)
        assert len(frames) == 1
        assert frames[0][0] == "a"
        assert frames[0][1]["content"] == "饿"

    def test_projection_empty_for_no_events(self) -> None:
        assert monologue_events_to_frames([]) == []

    def test_projection_order_stable(self) -> None:
        """多事件 → 多帧，序 = 事件序（不进排序，保回放序）。"""
        events = [
            npc_monologue_event(tick=1, npc_id="b", form="bubble", content="1"),
            npc_monologue_event(tick=2, npc_id="a", form="thought", content="2"),
        ]
        frames = monologue_events_to_frames(events)
        assert [f[0] for f in frames] == ["b", "a"]

    def test_event_replay_bit_exact(self) -> None:
        """重放逐位（§14）：同一事件重复投影 → 同帧（纯函数、无时序依赖）。"""
        e = npc_monologue_event(tick=7, npc_id="n", form="thought", content="缓存内容")
        assert monologue_events_to_frames([e]) == monologue_events_to_frames([e])


# ---------------------------------------------------------------------------
# K8-③ 投递面路由（§8 三形态：bubble/plan 广播，thought 定向本人）
# ---------------------------------------------------------------------------


class TestDeliveryRouting:
    """K8-③ form → 投递面：三个 form 各自的可见范围。"""

    def test_delivery_sets_are_exhaustive(self) -> None:
        """两集合必须穷尽三形态且不相交（防漏配档位静默不投）。"""
        covered = MONOLOGUE_DELIVERY_ALL | MONOLOGUE_DELIVERY_SELF
        assert covered == {"bubble", "thought", "plan"}
        assert MONOLOGUE_DELIVERY_ALL.isdisjoint(MONOLOGUE_DELIVERY_SELF)

    async def test_bubble_broadcast_to_all(self) -> None:
        """bubble（头顶气泡）=旁观者可见 → 全部连接收到。"""
        mgr = ConnectionManager()
        self_ws, other_ws = _FakeWS(), _FakeWS()
        _register(mgr, self_ws, subscriber_id="chenmo")
        _register(mgr, other_ws)  # 旁观者
        await route_monologue(mgr, "chenmo", monologue_payload("bubble", "唔"))
        assert len(self_ws.sent) == 1 and len(other_ws.sent) == 1

    async def test_plan_broadcast_to_all(self) -> None:
        """plan（计划看板）=外在可观察面 → 全部连接收到。"""
        mgr = ConnectionManager()
        self_ws, other_ws = _FakeWS(), _FakeWS()
        _register(mgr, self_ws, subscriber_id="chenmo")
        _register(mgr, other_ws)
        await route_monologue(mgr, "chenmo", monologue_payload("plan", "先去别处"))
        assert len(self_ws.sent) == 1 and len(other_ws.sent) == 1

    async def test_thought_only_to_self(self) -> None:
        """thought（思维面板）=私密心里话 → 仅本人连接收到，旁观者收不到。"""
        mgr = ConnectionManager()
        self_ws, other_ws = _FakeWS(), _FakeWS()
        _register(mgr, self_ws, subscriber_id="chenmo")
        _register(mgr, other_ws)
        await route_monologue(mgr, "chenmo", monologue_payload("thought", "心里话"))
        assert len(self_ws.sent) == 1
        assert other_ws.sent == []  # 旁观者不可知

    async def test_thought_actor_without_connection_drops(self) -> None:
        """@X 边界：无人订阅该 actor 时 thought 不投给任何旁观者（不降级为广播）。"""
        mgr = ConnectionManager()
        other_ws = _FakeWS()
        _register(mgr, other_ws)
        await route_monologue(mgr, "chenmo", monologue_payload("thought", "心里话"))
        assert other_ws.sent == []

    async def test_unknown_form_fail_closed(self) -> None:
        """未知 form → 不投任何面（fail-closed，防未来档位误广播私密内容）。"""
        mgr = ConnectionManager()
        self_ws, other_ws = _FakeWS(), _FakeWS()
        _register(mgr, self_ws, subscriber_id="chenmo")
        _register(mgr, other_ws)
        await route_monologue(mgr, "chenmo", monologue_payload("secret", "x"))
        assert self_ws.sent == [] and other_ws.sent == []


class TestConnectionSubscriber:
    """K8-③ 连接订阅者身份（投递面路由的前提；M0-M5 向后兼容）。"""

    def test_no_subscriber_is_observer(self) -> None:
        mgr = ConnectionManager()
        ws = _FakeWS()
        _register(mgr, ws)
        assert _subscriber_of(mgr, ws) is None

    def test_subscriber_recorded(self) -> None:
        mgr = ConnectionManager()
        ws = _FakeWS()
        _register(mgr, ws, subscriber_id="chenmo")
        assert _subscriber_of(mgr, ws) == "chenmo"

    def test_unregister_clears_subscriber(self) -> None:
        mgr = ConnectionManager()
        ws = _FakeWS()
        _register(mgr, ws, subscriber_id="chenmo")
        _unregister(mgr, ws)
        assert _subscriber_of(mgr, ws) is None
        assert mgr.count == 0

    async def test_broadcast_still_reaches_all(self) -> None:
        """广播语义不变（K7 delta 等既有调用点零回归）。"""
        mgr = ConnectionManager()
        a, b = _FakeWS(), _FakeWS()
        _register(mgr, a, subscriber_id="x")
        _register(mgr, b)
        await mgr.broadcast_json({"type": "state_delta"})
        assert len(a.sent) == 1 and len(b.sent) == 1

    async def test_dead_connection_pruned(self) -> None:
        mgr = ConnectionManager()

        class _Boom:
            async def send_json(self, payload: dict[str, Any]) -> None:
                raise RuntimeError("closed")

        bad = _Boom()
        _register(mgr, bad, subscriber_id="chenmo")
        await mgr.send_to_subscriber("chenmo", {"type": "monologue"})
        assert mgr.count == 0  # 死连接被摘除


# ---------------------------------------------------------------------------
# K8-④ defers → plan 联动（§10 四档：band=3 推迟进计划看板）
# ---------------------------------------------------------------------------


class TestDefersPlanLinkage:
    """K8-④ band=3 的 defers 在 K7 plan 账本的结构化体现。"""

    def test_prefix_is_diegetic_not_system_word(self) -> None:
        """看板是戏内 UI（§19）：前缀必须是戏内措辞，不含 DEFERRED 等系统词。"""
        assert DEFER_PLAN_PREFIX
        assert "DEFER" not in DEFER_PLAN_PREFIX.upper()
        assert not any(ch.isascii() and ch.isalpha() for ch in DEFER_PLAN_PREFIX)

    def test_defer_prefix_added(self) -> None:
        assert defer_plan_text("去河边") == DEFER_PLAN_PREFIX + "去河边"

    def test_defer_prefix_idempotent(self) -> None:
        once = defer_plan_text("去河边")
        assert defer_plan_text(once) == once

    def test_defer_empty_plan_gets_no_marker(self) -> None:
        """无计划 → 空串（不制造孤标记）。"""
        assert defer_plan_text("") == ""

    def test_band3_defers_marks_plan(self) -> None:
        """band=3（defers=True）→ 计划带推迟标记。"""
        set_plan_from_expression("chenmo", "去河边", band=3, defers=True)
        from sim.npc.plan_view import plan_of

        assert plan_of("chenmo") == DEFER_PLAN_PREFIX + "去河边"

    @pytest.mark.parametrize("band,defers", [(1, False), (2, False)])
    def test_lower_bands_no_marker(self, band: int, defers: bool) -> None:
        """band 1/2（无 defers）→ 计划不带标记（原文）。"""
        set_plan_from_expression("chenmo", "去河边", band=band, defers=defers)
        from sim.npc.plan_view import plan_of

        assert plan_of("chenmo") == "去河边"

    def test_empty_base_clears_plan(self) -> None:
        from sim.npc.plan_view import clear_plan, plan_of

        set_plan_from_expression("chenmo", "去河边", band=3, defers=True)
        set_plan_from_expression("chenmo", "", band=3, defers=True)
        assert plan_of("chenmo") == ""
        clear_plan("chenmo")
        assert plan_of("chenmo") is None

    def test_will_expression_defers_flags_align(self) -> None:
        """联动真源对齐：will.py band=3 的 WillingnessExpression.defers=True。

        本测试把「will 域产出的 defers」与「plan_view 消费的 defers」钉在同一
        语义上——将来 will 模板扩展时若 defers 语义漂移，此处先红。
        """
        v3 = WillingnessVerdict(score=0.9, band=3)
        expr3 = willingness_expression(v3, npc_name="陈默")
        assert isinstance(expr3, WillingnessExpression)
        assert expr3.defers is True
        assert expr3.band == 3

        v1 = WillingnessVerdict(score=0.4, band=1)
        expr1 = willingness_expression(v1, npc_name="陈默")
        assert expr1 is not None and expr1.defers is False

    def test_plan_entry_visible_in_delta_after_defer(self) -> None:
        """端到端：band=3 写入 → K7 state_delta 的 plan 项带推迟文本。"""
        from sim.api.ws import delta_payload
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=WorldState(world_seed=1),
        )
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=("chenmo",)))
        set_plan_from_expression("chenmo", "去河边", band=3, defers=True)
        payload = delta_payload(loop, set())
        assert payload["plan"][0]["text"] == DEFER_PLAN_PREFIX + "去河边"


class TestPlanDeltaStoreDefersIntegration:
    """K8-④ 与 K7 PlanDeltaStore 的联动不破坏其值语义。"""

    def test_store_overwrite_with_marker(self) -> None:
        store = PlanDeltaStore()
        store.set_plan("n", "A")
        store.set_plan("n", defer_plan_text("A"))
        assert store.plan_of("n") == DEFER_PLAN_PREFIX + "A"


# ---------------------------------------------------------------------------
# K8-⑤ 端到端链路（loop 事件 → drain → 投影 → 投递面）
# ---------------------------------------------------------------------------


class TestEndToEndChain:
    """K8-⑤ 全链：NPC 独白事件入 loop 队列 → drain → 帧投影 → 按面投递。"""

    def _loop(self) -> Any:
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=WorldState(world_seed=1),
        )
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=("chenmo", "lin")))
        return loop

    async def test_thought_event_routes_only_to_protagonist(self) -> None:
        loop = self._loop()
        # 直接 append 事件（模拟 npc 域产出；不经 bus.apply——monologue 是叙述非状态变更）
        loop.pending_events.append(
            npc_monologue_event(tick=1, npc_id="chenmo", form="thought", content="心里话")
        )
        events = loop.drain_events()
        mgr = ConnectionManager()
        protagonist, observer = _FakeWS(), _FakeWS()
        _register(mgr, protagonist, subscriber_id="chenmo")
        _register(mgr, observer)
        for actor_id, frame in monologue_events_to_frames(events):
            await route_monologue(mgr, actor_id, frame)
        assert [f["content"] for f in protagonist.sent] == ["心里话"]
        assert observer.sent == []

    async def test_bubble_event_routes_to_all(self) -> None:
        loop = self._loop()
        loop.pending_events.append(
            npc_monologue_event(tick=1, npc_id="lin", form="bubble", content="唔")
        )
        events = loop.drain_events()
        mgr = ConnectionManager()
        protagonist, observer = _FakeWS(), _FakeWS()
        _register(mgr, protagonist, subscriber_id="chenmo")
        _register(mgr, observer)
        for actor_id, frame in monologue_events_to_frames(events):
            await route_monologue(mgr, actor_id, frame)
        # bubble 是 lin 的，但广播：连主角连接也收（旁观者可见）
        assert len(protagonist.sent) == 1 and len(observer.sent) == 1

    async def test_observer_does_not_receive_others_thought(self) -> None:
        """@X：A 的 thought 不给 B（即便 B 也绑了别的 npc）。"""
        loop = self._loop()
        loop.pending_events.append(
            npc_monologue_event(tick=1, npc_id="chenmo", form="thought", content="秘密")
        )
        events = loop.drain_events()
        mgr = ConnectionManager()
        ws_lin = _FakeWS()
        _register(mgr, ws_lin, subscriber_id="lin")
        for actor_id, frame in monologue_events_to_frames(events):
            await route_monologue(mgr, actor_id, frame)
        assert ws_lin.sent == []


class TestProtagonistSubscriberResolution:
    """K8-⑤ 主角订阅者解析（服务端定身份，防客户端自授）。"""

    def test_subscriber_is_first_entity(self) -> None:
        from sim.api.ws import subscriber_for_protagonist
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=WorldState(world_seed=1),
        )
        assert subscriber_for_protagonist(loop) is None
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=("chenmo", "lin")))
        assert subscriber_for_protagonist(loop) == "chenmo"
