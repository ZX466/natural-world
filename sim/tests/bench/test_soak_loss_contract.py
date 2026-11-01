"""soak 实体流失契约（2026-11-01 用户裁定）。

**裁定**：良性场景的净流失上界**保持 0**；另立一条契约「**流失须被死亡解释**」——
净流失必须逐等于本次 run 中已记录的 `npc.death` 数，**无解释流失恒为 0**。

**为什么不按受控危害实测值（4.0/游戏日）抬线**：那个数来自
`.orca/audits/soak-loss-2026-11-01/measurement.json` 的**受控危害夹具**
（每小时强制一对近身互殴），不是自然人口流失率。现有 soak 用 `make_mock_feeder`，
**没有任何死亡源**，实体结构性守恒；把上界抬到 4.0 会在 604,800 tick 的里程碑跑里
允许 **28 个实体凭空消失**而不报红——把泄漏检测变成瞎子。

**本契约的形式化**：`净流失 - 已记录死亡 = 无解释流失`，后者必须为 0。
"""

from __future__ import annotations

import pytest

from sim.core.clock import GameClock
from sim.core.events import npc_death_event
from sim.core.tick import TickLoop
from sim.core.world import TickContext, build_default_bus
from sim.tests.bench.harness import make_state
from sim.tests.bench.soak import TICKS_PER_GAME_DAY, make_mock_feeder, run_soak
from sim.tests.bench.test_bench_soak import (
    SOAK_ENTITY_LOSS_PER_GAME_DAY,
    _assert_entity_stable,
    _entity_loss_bound,
)


def _loop(n: int = 8) -> TickLoop:
    return TickLoop(
        clock=GameClock(speed=1.0),
        bus=build_default_bus(),
        state=make_state(n, grid_w=8, grid_h=8),
        context=TickContext(),
    )


def test_benign_bound_stays_zero() -> None:
    """良性场景上界仍是 0（用户裁定：不按危害实测值抬线）。"""
    assert SOAK_ENTITY_LOSS_PER_GAME_DAY == 0
    assert _entity_loss_bound(TICKS_PER_GAME_DAY) == 0
    assert _entity_loss_bound(7 * TICKS_PER_GAME_DAY) == 0


def test_unexplained_loss_is_zero_with_no_deaths() -> None:
    """无死亡源的 run：净流失必须为 0（现有 soak 的形态）。"""
    loop = _loop()
    result = run_soak(loop, 600, window_ticks=300, feeder=make_mock_feeder(grid_w=8, grid_h=8))
    _assert_entity_stable(result, label="良性 soak")
    assert result.entity_count_start == result.entity_count_end


def test_explained_loss_passes_when_equals_deaths() -> None:
    """死亡事件被真实落地 ⇒ 净流失 == 死亡数 ⇒ 契约成立。"""
    loop = _loop()
    victim = sorted(loop.state.entities)[0]

    def killer(state, tick):
        if tick == 1 and victim in state.entities:
            return [npc_death_event(tick, entity_id=victim)]
        return None

    loop.attach_maintenance(killer)
    result = run_soak(loop, 10, window_ticks=10)
    net_loss = result.entity_count_start - result.entity_count_end
    assert net_loss == 1, (
        f"npc.death 未真实移除实体：{result.entity_count_start}→{result.entity_count_end}"
    )
    _assert_entity_stable(
        result,
        label="有解释流失",
        explained_deaths=1,
    )


def test_unexplained_loss_is_red() -> None:
    """净流失 > 已记录死亡数 ⇒ 无解释流失 ⇒ 必须红。"""
    loop = _loop()
    victim = sorted(loop.state.entities)[0]

    def killer(state, tick):
        if tick == 1 and victim in state.entities:
            return [npc_death_event(tick, entity_id=victim)]
        return None

    loop.attach_maintenance(killer)
    result = run_soak(loop, 10, window_ticks=10)
    # 声称 0 死亡，实际少了 1 个 ⇒ 无解释流失
    with pytest.raises(AssertionError, match="无解释流失"):
        _assert_entity_stable(result, label="无解释", explained_deaths=0)


def test_explained_deaths_cannot_exceed_net_loss() -> None:
    """反向：声称的死亡数超过实际净流失 ⇒ 记账造假，必须红。"""
    loop = _loop()
    result = run_soak(loop, 10, window_ticks=10)
    with pytest.raises(AssertionError, match="无解释流失"):
        _assert_entity_stable(result, label="多报死亡", explained_deaths=3)
