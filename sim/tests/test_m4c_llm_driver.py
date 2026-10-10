"""批次 C（LLM 接进决策循环——陈默 L2）钉子。

五个面：
1. sim/agent/driver.py ChenmoDriver：拼 prompt → LlmClient.complete →
   parse_intent → IntentGate.validate → pending 队列；执行 tick 二次校验 →
   issue_move + npc_monologue（reason 第一人称，thought 形态）。
2. 降级面（世界照常运转）：无 active profile / LlmError / 解析失败 / 闸门拒绝
   → 本轮零事件产出，不抛。
3. impulse 即时触发：player_impulse 到达 → request_decision() 置位 → 决策循环
   消费置位立即跑一轮（不等 60s 节拍）。
4. sim/content/protagonist.py：陈默档案播种（药铺学徒人设 + identity_anchor）
   + IdentityAnchor 构建（prompt 身份锚供数）。
5. 接线钉：main.py driver 任务随 lifespan 启动；ws.py impulse handler 调
   driver.request_decision()。

全部走 mock LlmClient（不花钱）；真调用只在实弹冒烟做一次。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytestmark = pytest.mark.t1


# ---------------------------------------------------------------------------
# 4. 主角档案（sim/content/protagonist.py）
# ---------------------------------------------------------------------------


class TestProtagonistProfile:
    def test_identity_anchor_shape(self) -> None:
        from sim.content.protagonist import build_anchor

        anchor = build_anchor()
        assert anchor.entity_id == "chenmo"
        assert anchor.self_narrative.startswith("我叫陈默")
        assert anchor.persona_summary and anchor.long_term_goal

    def test_seed_inserts_profile_and_idempotent(self) -> None:
        """chenmo profile 落库幂等（session 直插，同 villagers 口径）。"""
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import StaticPool

        from sim.content.protagonist import seed_protagonist
        from sim.core.persistence.database import create_session_factory, init_database

        async def _run() -> tuple[int, int]:
            engine = create_async_engine(
                "sqlite+aiosqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            await init_database(engine)
            sf = create_session_factory(engine)
            first = await seed_protagonist(sf)
            second = await seed_protagonist(sf)
            return first, second

        first, second = asyncio.run(_run())
        assert first == 1
        assert second == 0


# ---------------------------------------------------------------------------
# LlmClient 替身
# ---------------------------------------------------------------------------


class _FakeResult:
    """LlmCallResult 最小替身。"""

    content: str


class _FakeLlm:
    """可控 LlmClient 替身：记录调用；result 或 error 二选一。"""

    def __init__(self, result_content: str | None = None, error: Exception | None = None):
        self.calls = 0
        self.last_messages: list[dict[str, str]] | None = None
        self._content = result_content
        self._error = error

    async def complete(
        self,
        profile: Any,
        messages: list[dict[str, str]],
        decision: Any = None,
        *,
        max_tokens_override: int | None = None,
    ) -> _FakeResult:
        self.calls += 1
        self.last_messages = messages
        if self._error is not None:
            raise self._error
        result = _FakeResult()
        result.content = self._content or ""
        return result  # type: ignore[return-value]


class _FakeProfile:
    """ProfileSnapshot 替身（driver 只透传给 complete）。"""


# ---------------------------------------------------------------------------
# 1+2. ChenmoDriver 正常轮 + 降级面
# ---------------------------------------------------------------------------


class TestChenmoDriver:
    @staticmethod
    def _driver(llm: _FakeLlm, *, profile: Any | None = None) -> Any:
        from sim.agent.driver import ChenmoDriver
        from sim.content.protagonist import build_anchor

        return ChenmoDriver(
            anchor=build_anchor(),
            llm=llm,  # type: ignore[arg-type]
            profile_provider=lambda: profile,
        )

    @staticmethod
    def _loop_with_chenmo():
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
        )
        loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
        loop.drain_events()
        loop.issue_move("chenmo", [(0, 0), (8, 16)])
        loop.advance_frame(1.0)
        loop.drain_events()
        return loop

    def test_happy_path_move_to(self) -> None:
        """正常轮：LLM 返回 move_to → 闸门 → 执行 → MOVE + thought 独白。"""
        from sim.core.events import EventKind

        llm = _FakeLlm(
            '{"action": "move_to", "target_pos": [12, 24], '
            '"reason": "我想去集市路口看看", "confidence": 0.9}'
        )
        driver = self._driver(llm, profile=_FakeProfile())
        loop = self._loop_with_chenmo()
        ok = asyncio.run(driver.decide_once(loop.state, tick=100))
        assert ok is True
        assert llm.calls == 1
        # messages[0] 是身份锚（前缀缓存契约）
        assert "陈默" in llm.last_messages[0]["content"]
        from sim.api.main import _fallback_map
        from sim.world.pathfinding import Pathfinder

        executed = driver.execute_pending(loop, pathfinder=Pathfinder(_fallback_map()))
        assert executed == 1
        events = loop.drain_events()
        kinds = {e.event_type for e in events}
        assert EventKind.MOVE in kinds
        assert EventKind.NPC_MONOLOGUE in kinds
        mono = next(e for e in events if e.event_type is EventKind.NPC_MONOLOGUE)
        assert mono.payload["npc_id"] == "chenmo"
        assert mono.payload["form"] == "thought"
        assert mono.payload["content"] == "我想去集市路口看看"

    def test_gate_rejection_yields_no_events(self) -> None:
        """闸门拒绝（越界目标）→ 本轮零事件（幻觉隔离铁律 4）。"""
        from sim.core.events import EventKind

        llm = _FakeLlm(
            '{"action": "move_to", "target_pos": [99999, 99999], '
            '"reason": "我要出镇去看看", "confidence": 0.9}'
        )
        driver = self._driver(llm, profile=_FakeProfile())
        loop = self._loop_with_chenmo()
        ok = asyncio.run(driver.decide_once(loop.state, tick=100))
        assert ok is True  # 决策本身成立（LLM 正常返回、解析成功）
        executed = driver.execute_pending(loop, pathfinder=None)  # type: ignore[arg-type]
        assert executed == 0
        events = loop.drain_events()
        assert all(e.event_type is not EventKind.MOVE for e in events)
        assert all(e.event_type is not EventKind.NPC_MONOLOGUE for e in events)

    def test_parse_failure_degrades(self) -> None:
        """解析失败（非 JSON）→ 降级本轮，零事件，不抛。"""
        llm = _FakeLlm("我觉得还是走走看吧")
        driver = self._driver(llm, profile=_FakeProfile())
        loop = self._loop_with_chenmo()
        ok = asyncio.run(driver.decide_once(loop.state, tick=100))
        assert ok is False
        assert loop.drain_events() == []

    def test_llm_error_degrades(self) -> None:
        """LlmError → 降级本轮（ok=False），零事件，不抛。"""
        from sim.llm.client import LlmError

        llm = _FakeLlm(error=LlmError("timeout", "APITimeoutError"))
        driver = self._driver(llm, profile=_FakeProfile())
        loop = self._loop_with_chenmo()
        ok = asyncio.run(driver.decide_once(loop.state, tick=100))
        assert ok is False
        assert loop.drain_events() == []

    def test_no_profile_degrades_without_calling(self) -> None:
        """无 active profile → 不调 LLM 直接降级（闲时零成本）。"""
        llm = _FakeLlm('{"action": "wait", "reason": "歇会儿", "confidence": 0.9}')
        driver = self._driver(llm, profile=None)
        loop = self._loop_with_chenmo()
        ok = asyncio.run(driver.decide_once(loop.state, tick=100))
        assert ok is False
        assert llm.calls == 0
        assert loop.drain_events() == []

    def test_wait_intent_no_move(self) -> None:
        """wait 意图：无位移，仍产 thought 独白。"""
        from sim.core.events import EventKind

        llm = _FakeLlm('{"action": "wait", "reason": "我想站会儿", "confidence": 0.9}')
        driver = self._driver(llm, profile=_FakeProfile())
        loop = self._loop_with_chenmo()
        asyncio.run(driver.decide_once(loop.state, tick=100))
        executed = driver.execute_pending(loop, pathfinder=None)  # type: ignore[arg-type]
        assert executed == 1
        events = loop.drain_events()
        assert all(e.event_type is not EventKind.MOVE for e in events)
        mono = next(e for e in events if e.event_type is EventKind.NPC_MONOLOGUE)
        assert mono.payload["content"] == "我想站会儿"

    def test_execute_revalidate_uses_gate(self) -> None:
        """执行时二次校验接真 IntentGate：目标已消失 → 丢弃（零事件）。"""
        from sim.core.events import EventKind

        llm = _FakeLlm(
            '{"action": "talk_to", "target_id": "villager_01", '
            '"reason": "我想跟人搭句话", "confidence": 0.9}'
        )
        driver = self._driver(llm, profile=_FakeProfile())
        loop = self._loop_with_chenmo()
        asyncio.run(driver.decide_once(loop.state, tick=100))
        # 执行前 villager_01 从世界消失 → revalidate target_gone
        loop.state = loop.state.model_copy(update={"entities": {}})
        executed = driver.execute_pending(loop, pathfinder=None)  # type: ignore[arg-type]
        assert executed == 0
        events = loop.drain_events()
        assert all(e.event_type is not EventKind.MOVE for e in events)


# ---------------------------------------------------------------------------
# 3. impulse 即时触发
# ---------------------------------------------------------------------------


class TestImpulseTrigger:
    def test_request_decision_consumed_by_poll(self) -> None:
        """request_decision() 置位 → take_requested() 取走（一次）。"""
        from sim.agent.driver import ChenmoDriver
        from sim.content.protagonist import build_anchor

        driver = ChenmoDriver(anchor=build_anchor(), llm=_FakeLlm(), profile_provider=lambda: None)
        assert driver.take_requested() is False
        driver.request_decision()
        assert driver.take_requested() is True
        assert driver.take_requested() is False  # 消费即清

    def test_take_requested_thread_safe(self) -> None:
        """asyncio 任务置位、事件循环消费——用线程安全原语（Event 或 lock 内布尔）。"""
        from sim.agent.driver import ChenmoDriver
        from sim.content.protagonist import build_anchor

        driver = ChenmoDriver(anchor=build_anchor(), llm=_FakeLlm(), profile_provider=lambda: None)

        async def _set() -> None:
            driver.request_decision()

        asyncio.run(_set())
        assert driver.take_requested() is True


# ---------------------------------------------------------------------------
# 5. 接线钉（main.py lifespan 启动 driver；ws.py impulse handler 触发）
# ---------------------------------------------------------------------------


class TestWiring:
    def test_main_has_driver_start(self) -> None:
        """main.py lifespan 里必须启动 driver 任务（静态源码钉：接线不许丢）。"""
        from pathlib import Path

        source = (Path(__file__).parents[1] / "api" / "main.py").read_text(encoding="utf-8")
        assert "start_driver" in source or "ChenmoDriver" in source

    def test_ws_impulse_handler_triggers_driver(self) -> None:
        """ws.py impulse handler 必须经钩子触发 driver（装配缝 = set_impulse_trigger
        + handler 内 _IMPULSE_TRIGGER 调用；静态源码钉 + 行为钉双验）。"""
        from pathlib import Path

        ws_source = (Path(__file__).parents[1] / "api" / "ws.py").read_text(encoding="utf-8")
        assert "_IMPULSE_TRIGGER(" in ws_source
        main_source = (Path(__file__).parents[1] / "api" / "main.py").read_text(encoding="utf-8")
        assert "set_impulse_trigger" in main_source

        # 行为钉：装配钩子后，过闸 impulse 会触发置位（cleaned 文本透传）
        from sim.agent.driver import ChenmoDriver
        from sim.api import ws as ws_mod
        from sim.content.protagonist import build_anchor

        driver = ChenmoDriver(anchor=build_anchor(), llm=_FakeLlm(), profile_provider=lambda: None)
        received: list[str | None] = []
        ws_mod.set_impulse_trigger(lambda text: received.append(text))
        try:
            reply = ws_mod._handle_player_impulse({"text": "今天去河边转转"})
        finally:
            ws_mod.set_impulse_trigger(None)
        assert reply["injected"] is True
        assert received == ["今天去河边转转"]
        assert driver.take_requested() is False  # driver 本体未被直连（经钩子解耦）
