"""M2-A2 第二批：matter 结算器（m2-npc-cognition §4）。

TDD RED 先行。结算语义（§4.1/§4.2）：
- MATTER_DECAY：自然衰减批量结算——RNG 分桶（每 tick 一次批量 draw，非逐实体）；
- damage/build：交互事件直通；collapse：integrity<=0 或显式塌（简化版，M4 承重前）；
- tick 内固定序末尾结算（pi 对账提示 #2：C5 确定性）；
- 事件经 factory（MatterPayload extra=forbid），结算器不绕过事件流。
"""

from __future__ import annotations

import pytest

from sim.core.events import EventKind, WorldEvent
from sim.world.matter import MatterLedger, settle_decay

# ---------------------------------------------------------------------------
# MatterLedger — tick 结算账本（内存态；投影落库由 NpcStore.flush_tick 负责）
# ---------------------------------------------------------------------------


class TestMatterLedger:
    def test_register_and_state(self) -> None:
        ledger = MatterLedger()
        ledger.register("food_1", integrity=1.0, decay_rate=0.01)
        s = ledger.state("food_1")
        assert s.integrity == 1.0
        assert s.decay_rate == 0.01

    def test_unknown_state_raises(self) -> None:
        ledger = MatterLedger()
        with pytest.raises(KeyError):
            ledger.state("ghost")

    def test_decay_lowers_integrity(self) -> None:
        ledger = MatterLedger()
        ledger.register("food_1", integrity=1.0, decay_rate=0.1)
        events = ledger.settle(tick=100, seed=0)
        s = ledger.state("food_1")
        # 抖动系数 0.5..1.5：衰减量在 (0, 0.15) 内（0.1×jitter），方向必然下降
        assert 0.85 < s.integrity < 1.0
        assert len(events) == 1
        assert events[0].event_type == EventKind.MATTER_DECAY
        assert events[0].payload["amount"] == pytest.approx(s.integrity - 1.0)

    def test_zero_decay_no_event(self) -> None:
        # decay_rate=0 的对象不产事件（无谓事件不进日志）
        ledger = MatterLedger()
        ledger.register("stone", integrity=1.0, decay_rate=0.0)
        assert ledger.settle(tick=1) == []

    def test_collapse_at_zero_integrity(self) -> None:
        # 耐久归零 → MATTER_COLLAPSE（简化版：无承重链）
        ledger = MatterLedger()
        ledger.register("hut_1", integrity=0.05, decay_rate=0.1)
        events = ledger.settle(tick=200)
        kinds = [e.event_type for e in events]
        assert EventKind.MATTER_COLLAPSE in kinds
        assert EventKind.MATTER_DECAY not in kinds  # 塌了就不再单独发 decay
        assert ledger.state("hut_1").is_rubble

    def test_rubble_no_further_settle(self) -> None:
        # rubble 终态不再衰减（永不恢复，§14）
        ledger = MatterLedger()
        ledger.register("hut_1", integrity=0.0, decay_rate=0.1)
        ledger.mark_rubble("hut_1")
        assert ledger.settle(tick=5) == []

    def test_damage_and_build_direct(self) -> None:
        ledger = MatterLedger()
        ledger.register("wall_1", integrity=1.0, decay_rate=0.0)
        dmg = ledger.damage("wall_1", amount=-0.3, tick=10)
        bld = ledger.build("wall_1", amount=0.2, tick=11)
        assert dmg.event_type == EventKind.MATTER_DAMAGE
        assert bld.event_type == EventKind.MATTER_BUILD
        assert ledger.state("wall_1").integrity == pytest.approx(0.9)

    def test_damage_clamps_and_collapses(self) -> None:
        ledger = MatterLedger()
        ledger.register("wall_1", integrity=0.2, decay_rate=0.0)
        ledger.damage("wall_1", amount=-0.5, tick=10)
        assert ledger.state("wall_1").is_rubble
        assert ledger.state("wall_1").integrity == 0.0


class TestSettleDecay:
    def test_batch_rng_bucketing_deterministic(self) -> None:
        """C5：同 seed 两次批量结算结果一致（RNG 分桶=每 tick 一次批量 draw）。"""
        ledger_a, ledger_b = MatterLedger(), MatterLedger()
        for i in range(20):
            ledger_a.register(f"m_{i}", integrity=1.0, decay_rate=0.01)
            ledger_b.register(f"m_{i}", integrity=1.0, decay_rate=0.01)
        ev_a = settle_decay(ledger_a, tick=1, seed=42)
        ev_b = settle_decay(ledger_b, tick=1, seed=42)
        assert len(ev_a) == len(ev_b)
        assert [e.payload["matter_id"] for e in ev_a] == [e.payload["matter_id"] for e in ev_b]

    def test_batch_returns_events_only_for_changed(self) -> None:
        ledger = MatterLedger()
        ledger.register("a", integrity=1.0, decay_rate=0.01)
        ledger.register("b", integrity=1.0, decay_rate=0.0)
        events = settle_decay(ledger, tick=1, seed=7)
        ids = [e.payload["matter_id"] for e in events]
        assert "a" in ids
        assert "b" not in ids

    def test_events_are_factory_built(self) -> None:
        # 事件必须走工厂（MatterPayload 白名单）；这里只验 kind 与 payload 形
        ledger = MatterLedger()
        ledger.register("a", integrity=0.5, decay_rate=0.1)
        events = settle_decay(ledger, tick=9, seed=1)
        assert events
        for e in events:
            assert isinstance(e, WorldEvent)
            assert set(e.payload.keys()) == {
                "matter_id",
                "x",
                "y",
                "amount",
                "durability",
                "note",
            }
