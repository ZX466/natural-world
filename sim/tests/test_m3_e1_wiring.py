"""A2 第八批（E1 生产接线 F2 收口 + F1 工厂收窄 + B-B2 日切挂载点）钉子。

契约：
1. **F2 生产发射方**（m3-evidence-chain §3「实现归属：emerge 事件发射=Claude 批次 B4/B5」）：
   NpcRuntime.tick 第 0 步重估触发窗口后，`delta = triggered_now - triggered_prev`
   非空 → 每 NPC 合并一条 `npc.hidden_emerge` 事件（X4：attr_ids 仅戏外主键 delta），
   emit 先于 NPC_ACT（固定执行序 0 步 = 事件根）；attr_ids 排序保 C5 确定性；
   无 hidden_states / 无 profile / 无 delta → 零新增事件（零回归路径）。
2. **F1 工厂收窄**（codex M3-S4 advisory + S5 复核新向量）：`witnesses` 形参
   Sequence[str]；str/bytes/dict 拒（str 是 Sequence，须先查；dict 可迭代键
   会洗白成见证人——S5 复核发现的 "ghost" 向量）。
3. **B-B2 日切挂载**（m3-plan 批次 B「世界循环在固定执行序事件结算后调用」）：
   run_world_driver 增 on_day_switch(day) 钩子；**跨越判定**（prev_day != new_day
   逐日各一次）而非 reflection_due 等值判定——帧驱动一帧 0..N tick，16x 下
   ~16 tick/帧，等值点会被整帧跳过（75-94% 的日切丢失）；每帧恰好一次回调，
   多日跨越按日序逐个补发（missed days 不静默吞）。
"""

from __future__ import annotations

import contextlib

import pytest

# ---------------------------------------------------------------------------
# 1. F2 生产发射方 — NpcRuntime.tick 第 0 步产 E1
# ---------------------------------------------------------------------------


def _hidden_profile(npc_id: str, attr_id: str, trigger: str):
    from sim.npc.hidden import HiddenAttribute, HiddenProfile

    return HiddenProfile(
        npc_id=npc_id,
        attributes=(
            HiddenAttribute(
                id=attr_id,
                category="disease",
                label="咳疾",
                descriptors=("咳嗽",),
                triggers=(trigger,),
            ),
        ),
    )


def _bare_runtime():
    """最小 runtime：两个 L1 NPC（lod=1），不依赖 NpcStore 物化。"""
    from sim.core.events import npc_act_event  # noqa: F401  # 语义锚：消费方同层
    from sim.npc.model import Need, NpcProfileData
    from sim.npc.runtime import NpcRuntime
    from sim.npc.utility import UtilityModel

    def _profile(nid: str) -> NpcProfileData:
        return NpcProfileData(
            npc_id=nid,
            name=nid,
            lod=1,
            needs=(Need(name="hunger", value=0.8, weight=1.0),),
        )

    return NpcRuntime(
        profiles={"npc:01": _profile("npc:01"), "npc:02": _profile("npc:02")},
        utility=UtilityModel(n_npc=2),
    )


class TestE1ProductionEmission:
    """F2 收口：delta 装配进 NpcRuntime.tick（钉子原来用测试替身验证语义）。"""

    def test_emerge_event_emitted_on_new_trigger(self) -> None:
        from sim.core.events import EventKind
        from sim.npc.contract import HiddenState

        runtime = _bare_runtime()
        hidden = {
            "npc:01": HiddenState(
                profile=_hidden_profile("npc:01", "npc:01.health_1", "阴雨"),
                triggered=frozenset(),
            )
        }
        events = runtime.tick(
            1, hidden_states=hidden, context_of=lambda nid: "阴雨天" if nid == "npc:01" else ""
        )
        emerges = [e for e in events if e.event_type is EventKind.NPC_HIDDEN_EMERGE]
        assert len(emerges) == 1
        ev = emerges[0]
        # 身份口径同 npc_act_event：身份进 payload（actor_id 是世界事件字段，NPC 事件不设）
        assert ev.payload["npc_id"] == "npc:01"
        assert list(ev.payload["attr_ids"]) == ["npc:01.health_1"]  # type: ignore[arg-type]

    def test_emerge_precedes_npc_act_in_batch(self) -> None:
        """固定执行序：第 0 步浮现事件先于同 NPC 的 NPC_ACT（证据链根先行）。"""
        from sim.core.events import EventKind

        runtime = _bare_runtime()
        from sim.npc.contract import HiddenState

        hidden = {
            "npc:01": HiddenState(
                profile=_hidden_profile("npc:01", "npc:01.health_1", "阴雨"),
                triggered=frozenset(),
            )
        }
        events = runtime.tick(
            1, hidden_states=hidden, context_of=lambda _nid: "阴雨天"
        )
        kinds = [e.event_type for e in events]
        assert EventKind.NPC_HIDDEN_EMERGE in kinds
        emerge_idx = kinds.index(EventKind.NPC_HIDDEN_EMERGE)
        act_idxs = [i for i, k in enumerate(kinds) if k is EventKind.NPC_ACT]
        if act_idxs:
            assert emerge_idx < act_idxs[0]

    def test_no_delta_no_emerge_event(self) -> None:
        """窗口无新增 → 不发（B 契约：窗口抖动=事件流噪声污染）。"""
        from sim.core.events import EventKind
        from sim.npc.contract import HiddenState

        runtime = _bare_runtime()
        hidden = {
            "npc:01": HiddenState(
                profile=_hidden_profile("npc:01", "npc:01.health_1", "阴雨"),
                triggered=frozenset({"npc:01.health_1"}),
            )
        }
        events = runtime.tick(1, hidden_states=hidden, context_of=lambda _nid: "阴雨天")
        assert all(e.event_type is not EventKind.NPC_HIDDEN_EMERGE for e in events)

    def test_no_hidden_states_zero_new_events(self) -> None:
        """不带 hidden_states（bench/soak 现状调用形）→ 零 emerge、行为不变。"""
        from sim.core.events import EventKind

        runtime = _bare_runtime()
        events = runtime.tick(1)
        assert all(e.event_type is not EventKind.NPC_HIDDEN_EMERGE for e in events)
        assert events, "L0 过滤后 hunger 0.8 的 L1 NPC 仍应产出 NPC_ACT"

    def test_attr_ids_sorted_for_c5(self) -> None:
        """多属性同 tick 浮现 → 单事件合并 + attr_ids 排序（C5，frozenset 序漂移禁入）。"""
        from sim.core.events import EventKind
        from sim.npc.contract import HiddenState
        from sim.npc.hidden import HiddenAttribute, HiddenProfile

        attrs = (
            HiddenAttribute(
                id="npc:01.health_9",
                category="trauma",
                label="乙",
                descriptors=("乙",),
                triggers=("河边",),
            ),
            HiddenAttribute(
                id="npc:01.health_2",
                category="disease",
                label="甲",
                descriptors=("甲",),
                triggers=("河边",),
            ),
        )
        profile = HiddenProfile(npc_id="npc:01", attributes=attrs)
        runtime = _bare_runtime()
        hidden = {"npc:01": HiddenState(profile=profile, triggered=frozenset())}
        events = runtime.tick(1, hidden_states=hidden, context_of=lambda _nid: "河边")
        emerges = [e for e in events if e.event_type is EventKind.NPC_HIDDEN_EMERGE]
        assert len(emerges) == 1
        assert list(emerges[0].payload["attr_ids"]) == [  # type: ignore[arg-type]
            "npc:01.health_2",
            "npc:01.health_9",
        ]

    def test_emerge_carries_no_word_fragments(self) -> None:
        """X4 红线：descriptors/label 词面永不入事件（payload 只允许 npc_id+attr_ids）。"""
        from sim.npc.contract import HiddenState

        runtime = _bare_runtime()
        hidden = {
            "npc:01": HiddenState(
                profile=_hidden_profile("npc:01", "npc:01.health_1", "阴雨"),
                triggered=frozenset(),
            )
        }
        events = runtime.tick(1, hidden_states=hidden, context_of=lambda _nid: "阴雨天")
        emerges = [e for e in events if e.event_type == "npc.hidden_emerge"]
        assert len(emerges) == 1
        assert set(emerges[0].payload) == {"npc_id", "attr_ids"}
        assert "咳嗽" not in str(emerges[0].payload)
        assert "咳疾" not in str(emerges[0].payload)


# ---------------------------------------------------------------------------
# 2. F1 工厂收窄 — hidden_emerge_event witnesses 形参
# ---------------------------------------------------------------------------


class TestFactoryWitnessesNarrowing:
    """codex S4 advisory F1 + S5 复核新向量：工厂层拒绝可迭代洗白。"""

    def test_rejects_str(self) -> None:
        """str 是 Sequence——原形参会把 "b" 洗白成 ["b"]（S4 实测 ACCEPTED 向量）。"""
        from typing import Any

        from sim.core.events import hidden_emerge_event

        forged: Any = "b"  # Any 通道模拟调用方越型（str 静态上是 Sequence[str]，运行期拒）
        with pytest.raises(TypeError):
            hidden_emerge_event(tick=1, npc_id="chenmo", attr_ids=("a",), witnesses=forged)

    def test_rejects_dict(self) -> None:
        """dict 可迭代出键——S5 复核新向量：{"ghost": 1} 会洗出见证人 "ghost"。"""
        from sim.core.events import hidden_emerge_event

        with pytest.raises(TypeError):
            hidden_emerge_event(tick=1, npc_id="chenmo", attr_ids=("a",), witnesses={"ghost": 1})  # type: ignore[arg-type]

    def test_rejects_bytes(self) -> None:
        from sim.core.events import hidden_emerge_event

        with pytest.raises(TypeError):
            hidden_emerge_event(tick=1, npc_id="chenmo", attr_ids=("a",), witnesses=b"ab")  # type: ignore[arg-type]

    def test_accepts_list_and_tuple_and_default(self) -> None:
        from sim.core.events import hidden_emerge_event

        ev_list = hidden_emerge_event(
            tick=1, npc_id="chenmo", attr_ids=("a",), witnesses=["a", "b"]
        )
        assert ev_list.witnesses == ["a", "b"]
        ev_tuple = hidden_emerge_event(tick=1, npc_id="chenmo", attr_ids=("a",), witnesses=("a",))
        assert ev_tuple.witnesses == ["a"]
        ev_none = hidden_emerge_event(tick=1, npc_id="chenmo", attr_ids=("a",))
        assert ev_none.witnesses == []


# ---------------------------------------------------------------------------
# 3. B-B2 日切挂载 — run_world_driver on_day_switch 钩子
# ---------------------------------------------------------------------------


def _tick_loop_at(tick: int):
    """clock 直接快进的 TickLoop（state.tick 同步，绕过逐 tick 推进）。"""
    from sim.core.clock import GameClock
    from sim.core.events import world_create_event
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus

    loop = TickLoop(
        clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
    )
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    loop.drain_events()
    # 快进：直接把 clock/state 推到 tick（测试驱动不必跑 86_400 次 _tick_once）
    while loop.state.tick < tick:
        loop._tick_once()
    return loop


class TestDaySwitchHook:
    """run_world_driver 日切钩子：跨越判定逐日补发，恰一次，missed days 不吞。

    day 语义 = calendar.game_time(tick).day（**1-based 戏内天号**，界面/消费者
    同口径）；run_reflection 的 0-based day 由接线层换算（day-1），钩子不背两套历法。
    """

    def _drive_frames(self, loop, *, real_dt: float, days_seen: list[int], on_flush=None) -> None:
        import asyncio

        from sim.api.ws import run_world_driver

        class _Mgr:
            count = 0

            async def broadcast_json(self, payload: dict) -> None:
                del payload

        async def _run() -> None:
            task = asyncio.create_task(
                run_world_driver(
                    loop,
                    _Mgr(),  # type: ignore[arg-type]  # 鸭子替身（count/broadcast_json 足形）
                    None,  # type: ignore[arg-type]  # tile_map 本组未消费
                    on_flush=on_flush,
                    on_day_switch=days_seen.append,
                )
            )
            await asyncio.sleep(real_dt)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        asyncio.run(_run())

    def test_no_day_crossing_no_callback(self) -> None:
        loop = _tick_loop_at(0)
        days_seen: list[int] = []
        self._drive_frames(loop, real_dt=0.05, days_seen=days_seen)
        assert days_seen == []

    def test_day_crossing_fires_once(self) -> None:
        """tick 86_399（第 1 天）→ 帧内越入第 2 天：回调 [2]（calendar 1-based）。"""
        loop = _tick_loop_at(86_399)
        days_seen: list[int] = []
        self._drive_frames(loop, real_dt=0.10, days_seen=days_seen)
        assert days_seen == [2]

    def test_multi_day_catchup_fires_each_day(self) -> None:
        """一帧跨多日（防御分支：clock 上限 240 tick/帧不可达，状态跳变模拟）
        → 逐日补发 [2, 3, 4]，missed days 不静默吞。"""
        loop = _tick_loop_at(86_399)
        days_seen: list[int] = []

        async def on_flush(events: list) -> None:
            if events:
                # 白盒：单帧内状态再跳 2 天（clock 不可达，防御分支专用）
                loop.state = loop.state.model_copy(update={"tick": loop.state.tick + 86_400 * 2})

        loop.issue_move("chenmo", [(1, 1)])
        self._drive_frames(loop, real_dt=0.10, days_seen=days_seen, on_flush=on_flush)
        assert days_seen == [2, 3, 4]

    def test_day_switch_after_flush(self) -> None:
        """固定执行序：日切回调在事件落库之后（m3-plan 批次 B「事件结算后」）。"""
        order: list[str] = []
        loop = _tick_loop_at(86_399)
        loop.issue_move("chenmo", [(1, 1)])

        async def on_flush(events: list) -> None:
            if events:
                order.append("flush")

        days_seen: list[int] = []
        self._drive_frames(loop, real_dt=0.10, days_seen=days_seen, on_flush=on_flush)
        assert order == ["flush"], "move 事件帧应先落库"
        assert days_seen == [2], "同一帧内日切应在落库后回调"


# ---------------------------------------------------------------------------
# 4. B-B2 消费侧 — make_day_switch_reflector 适配器（run_reflection 接钩子）
# ---------------------------------------------------------------------------


class TestDaySwitchReflector:
    """on_day_switch → run_reflection 组装（ws.py 零 sim.npc 依赖，适配器在 reflection.py）。"""

    def _pipeline_with_event(self, npc_id: str):
        from sim.llm.memory_scan import MemoryWritePipeline

        pipeline = MemoryWritePipeline()  # InMemoryStore
        pipeline.write(
            npc_id,
            "在河边被水呛过，心有余悸。",
            source="event",
            event_seq=None,
            importance=0.5,
            emotion_tag=None,
        )
        return pipeline

    def test_reflector_writes_reason_entry_per_npc(self) -> None:
        from sim.llm.memory_scan import MemoryEntry
        from sim.npc.reflection import make_day_switch_reflector

        pipeline = self._pipeline_with_event("npc:01")
        reflector = make_day_switch_reflector(pipeline, npc_ids=("npc:01", "npc:02"))
        entries = reflector(2)  # 第 2 天日切（calendar 1-based）
        assert len(entries) == 1
        assert isinstance(entries[0], MemoryEntry)
        assert entries[0].source == "reason"
        assert entries[0].npc_id == "npc:01"

    def test_reflector_no_materials_writes_nothing(self) -> None:
        from sim.npc.reflection import make_day_switch_reflector

        pipeline = self._pipeline_with_event("npc:01")
        reflector = make_day_switch_reflector(pipeline, npc_ids=("npc:02",))
        assert reflector(2) == []

    def test_reflector_day_conversion_zero_based(self) -> None:
        """钩子 day 是 calendar 1-based；适配器换算 0-based 传 run_reflection
        （素材过滤 created // 86400 == day-1）。in-memory 无 tick 列 → 用
        白盒断言换算：反射捕获 run_reflection 收到的 day。"""
        import sim.npc.reflection as refl

        received: list[int] = []
        real = refl.run_reflection

        def spy(**kw):
            received.append(kw["day"])

        refl.run_reflection = spy
        try:
            from sim.llm.memory_scan import MemoryWritePipeline

            reflector = refl.make_day_switch_reflector(MemoryWritePipeline(), npc_ids=("a",))
            reflector(3)
        finally:
            refl.run_reflection = real
        assert received == [2], "1-based 钩子天号须换算 0-based 再传 run_reflection"
