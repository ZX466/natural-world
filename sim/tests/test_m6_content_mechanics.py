"""M6 内容面四模块验收钉 — 生态/动物/语言阶层/迷雾（K4 C1-C5 + S4 FG/EN + A3 口径）。

四条红线在本文件的钉：
- **K4 C1/A3**：纯派生零事件写（生态/动物不入库、无事件源）；fauna 不
  per-tick 产事件；speech 不落列不占 0015（运行态不触发条件判定）；
- **K4 C2/C5 + K5**：零数值出站（生态/动物标签词、speech 语域词——出站面
  字段零 int/float）；S4 speech 三边界（签名不收 power——想传都传不进）；
- **S4 FG/A3**：迷雾 fold=并集幂等（事件化口径，重放第二遍安全）；
- **P4 预算**：到期桶形态（生态派生 O(1) 每查询，无全量扫——规模外推钉）。
"""

from __future__ import annotations

import time

import pytest

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.npc.speech_register import (
    REGISTER_PLAIN,
    REGISTER_REFINED,
    REGISTER_ROUGH,
    SpeechContext,
    SpeechRegisterError,
    speech_register,
)
from sim.world.ecology import (
    ECOLOGY_PERIOD_DAYS,
    PHASE_BLOOM,
    PHASE_PLATEAU,
    PHASE_SCARCE,
    ecology_phase_at,
    ecology_shift_due,
)
from sim.world.fauna import (
    FAUNA_ACTIVE,
    FAUNA_RESTING,
    FAUNA_SPECIES,
    active_species_at,
    fauna_sightings_at,
)
from sim.world.fog import FogOfWar, fold_fog_reveal

# ===========================================================================
# ① 生态（ecology.py）— tick 纯派生 + 相位跨越信号
# ===========================================================================


class TestEcologyPhase:
    def test_same_tick_same_phase(self) -> None:
        """C5：同 tick 恒同相位（无隐藏随机/时钟）。"""
        a = ecology_phase_at(12345)
        b = ecology_phase_at(12345)
        assert a == b

    def test_phase_cycles_over_period(self) -> None:
        """相位按周期循环：一个周期内三档全出现，跨周期同位同相（比标签不比 tick）。"""
        span = ECOLOGY_PERIOD_DAYS * TICKS_PER_GAME_DAY
        seen = {
            ecology_phase_at(t).phase
            for t in range(0, span, TICKS_PER_GAME_DAY)
        }
        assert seen == {PHASE_BLOOM, PHASE_PLATEAU, PHASE_SCARCE}, f"三档未全出现：{seen}"
        period_ticks = ECOLOGY_PERIOD_DAYS * TICKS_PER_GAME_DAY
        a = ecology_phase_at(0)
        b = ecology_phase_at(period_ticks)
        assert (a.phase, a.prey_trend, a.predator_trend) == (
            b.phase,
            b.prey_trend,
            b.predator_trend,
        ), "跨周期同位应同相（标签三元组逐位）"

    def test_predator_lags_prey_half_period(self) -> None:
        """捕食者滞后猎物半周期（design 口径）：predator_trend(t) == prey_trend(t+half)。

        实现 = 捕食者相位取「猎物曲线平移半周期」——即 t 时刻的捕食者趋势
        应等于 t+半周期 时刻的猎物趋势（捕食者繁盛跟随猎物繁盛之后）。
        """
        half = (ECOLOGY_PERIOD_DAYS // 2) * TICKS_PER_GAME_DAY
        for t in (0, TICKS_PER_GAME_DAY, 3 * TICKS_PER_GAME_DAY):
            now = ecology_phase_at(t)
            future = ecology_phase_at(t + half)
            assert now.predator_trend == future.prey_trend, (
                f"t={t}: predator_trend {now.predator_trend} ≠ prey_trend(t+half) "
                f"{future.prey_trend}（滞后半周期口径破）"
            )

    def test_labels_are_narrative_words_not_numbers(self) -> None:
        """K4 C2/C5：相位标签是词非数值（零数值出站面）。"""
        ph = ecology_phase_at(0)
        for f in (ph.phase, ph.prey_trend, ph.predator_trend):
            assert isinstance(f, str) and not f.replace(".", "").isdigit(), f


class TestEcologyShiftSignal:
    def test_shift_due_on_phase_cross(self) -> None:
        """相位跨越 ⇒ shift（首尾标签不同——帧驱动跨越式判定口径）。

        相位按**游戏日**推进（周期 7 游戏日）⇒ 跨越发生在日界 tick（86400 的
        倍数）；同周期内日界两端标签相同（繁盛期跨一天）⇒ 用第 2→3 天（繁盛
        →平稳）验真跨越。
        """
        day2 = 1 * TICKS_PER_GAME_DAY
        day3 = 2 * TICKS_PER_GAME_DAY
        assert ecology_phase_at(day2).phase != ecology_phase_at(day3).phase, (
            "周期第 2/3 天应异相位（繁盛→平稳）"
        )
        assert ecology_shift_due(day2, day3) is True

    def test_no_shift_within_phase(self) -> None:
        """同相位内推进零 shift（信号≠状态——档内重算恒同值）。"""
        assert ecology_shift_due(0, TICKS_PER_GAME_DAY - 1) is False

    def test_no_shift_on_reverse_or_equal(self) -> None:
        """倒退/相等 tick 零 shift（防御分支）。"""
        assert ecology_shift_due(100, 100) is False
        assert ecology_shift_due(100, 50) is False


# ===========================================================================
# ② 动物三只（fauna.py）— 计数面纯派生（不进 entities——soak 契约）
# ===========================================================================


class TestFaunaSightings:
    def test_three_species_each_tick(self) -> None:
        """三只各一条节律态（物种全集恒出现——计数面 O(物种数)=O(1)）。"""
        out = fauna_sightings_at(100)
        assert {s.species for s in out} == set(FAUNA_SPECIES)

    def test_same_tick_same_sightings(self) -> None:
        """C5：同 tick 恒同节律。"""
        assert fauna_sightings_at(7) == fauna_sightings_at(7)

    def test_states_are_words_only(self) -> None:
        """K4 C2/C5：节律态是词非数值（出站面零 int/float）。"""
        for s in fauna_sightings_at(0):
            assert s.state in (FAUNA_ACTIVE, FAUNA_RESTING)

    def test_day_night_rhythm_differs(self) -> None:
        """昼夜节律差异：鸟昼行、狼夜行（calendar 口径：phase_of_day 按**游戏小时**
        推进，1 tick=1 游戏秒 ⇒ 小时 h 的 tick = h*3600）。

        采样一个游戏日的**每小时** tick，找「鸟出没且狼蛰伏」（昼行/夜行分野）。
        """
        for hour in range(24):
            t = hour * 3600
            states = {s.species: s.state for s in fauna_sightings_at(t)}
            if states["鸟"] == FAUNA_ACTIVE and states["狼"] == FAUNA_RESTING:
                return
        raise AssertionError("整天未找到「鸟出没+狼蛰伏」——节律退化成常量")

    def test_no_events_produced(self) -> None:
        """K4 C1：派生**零事件**（fauna 不 per-tick 产事件——W-D3 口径）。

        派生函数返回 dataclass 而非 WorldEvent（类型层即钉）。
        """
        from sim.core.events import WorldEvent

        for s in fauna_sightings_at(0):
            assert not isinstance(s, WorldEvent)
        assert not isinstance(active_species_at(0), WorldEvent)


# ===========================================================================
# ③ 语言阶层（speech_register.py）— S4 三边界
# ===========================================================================


class TestSpeechRegister:
    def test_three_registers(self) -> None:
        """三档语域可达（粗/日常/文雅全集可由输入触发）。"""
        seen = {
            speech_register(SpeechContext(class_register="士绅", in_circle=True)),
            speech_register(SpeechContext(class_register="士绅", in_circle=False)),
            speech_register(SpeechContext(class_register="平民", in_circle=False)),
        }
        assert seen == {REGISTER_REFINED, REGISTER_PLAIN, REGISTER_ROUGH}

    def test_signature_has_no_power_input(self) -> None:
        """S4 边界①（签名层兑现）：SpeechContext 无 power/authority 字段——想传都传不进。"""
        import dataclasses

        fields = {f.name for f in dataclasses.fields(SpeechContext)}
        assert "power" not in fields and "authority" not in fields
        with pytest.raises(TypeError):
            SpeechContext(class_register="平民", in_circle=True, power=0.9)  # type: ignore[call-arg]

    def test_output_is_register_word_only(self) -> None:
        """S4 边界②：输出只有语域词（零数值零索引零档号）。"""
        for ctx in (
            SpeechContext(class_register="平民"),
            SpeechContext(class_register="士绅", in_circle=False),
            SpeechContext(class_register="行内"),
        ):
            r = speech_register(ctx)
            assert r in (REGISTER_ROUGH, REGISTER_PLAIN, REGISTER_REFINED)

    def test_empty_register_rejected(self) -> None:
        """空静态档 fail-closed（SpeechRegisterError）。"""
        with pytest.raises(SpeechRegisterError):
            SpeechContext(class_register="")


# ===========================================================================
# ④ 迷雾（fog.py fold）— S4 FG/A3 事件化口径
# ===========================================================================


class TestFogFold:
    def test_fold_is_union(self) -> None:
        """fold=并集：两批揭示合并（A3 §2.4 口径）。"""
        fog = FogOfWar()
        fog = fold_fog_reveal(fog, ((0, 0), (1, 1)))
        fog = fold_fog_reveal(fog, ((1, 1), (2, 2)))
        assert fog.is_revealed(0, 0) and fog.is_revealed(1, 1) and fog.is_revealed(2, 2)
        assert fog.revealed_count == 3

    def test_fold_idempotent(self) -> None:
        """幂等：同一批揭示重放第二遍结果不变（重放安全）。"""
        fog = fold_fog_reveal(FogOfWar(), ((0, 0), (1, 1)))
        again = fold_fog_reveal(fog, ((0, 0), (1, 1)))
        assert again == fog
        assert again.revealed_count == fog.revealed_count == 2

    def test_fold_replay_deterministic(self) -> None:
        """C5：同事件序列两次重放 ⇒ 同揭示集（T2 逐位口径）。"""
        batches = [((0, 0),), ((1, 1), (0, 0)), ((2, 2),)]
        def replay() -> FogOfWar:
            fog = FogOfWar()
            for b in batches:
                fog = fold_fog_reveal(fog, b)
            return fog
        assert replay() == replay()


# ===========================================================================
# ⑤ P4 预算：生态派生到期桶形态（无全量扫——规模外推钉）
# ===========================================================================


class TestEcologyBudget:
    def test_phase_derivation_is_o1_per_query(self) -> None:
        """P4 红线：派生 O(1) 每查询——规模外推（tick 跨度 ×1000 ⇒ 耗时同阶）。

        「每 tick 全量扫」形态的耗时随 tick 历史长度线性增长（400µs 必红形态）；
        纯桶键派生的耗时与历史长度**无关**。用「远 tick vs 近 tick」等价对比钉。
        """
        near = min(time.perf_counter() - time.perf_counter() for _ in range(50))  # 基线噪声校准
        del near
        t0 = min(_time_phase(1_000) for _ in range(50))
        t1 = min(_time_phase(1_000_000_000) for _ in range(50))
        # 远 tick 派生不因「历史更长」而变慢（同阶：比值有界）
        assert t1 < max(t0 * 50, 1e-6), f"远 tick 派生耗时异常放大（全量扫嫌疑）：{t0} vs {t1}"


def _time_phase(tick: int) -> float:
    t0 = time.perf_counter()
    ecology_phase_at(tick)
    return time.perf_counter() - t0
