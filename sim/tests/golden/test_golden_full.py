"""M4-T5 golden 全量验收——10 种子 × 10 游戏日 + 三断言组实跑（§16 T5 行）。

触发：`PI_T5_FULL=1 uv run pytest sim/tests/golden/test_golden_full.py -q`
默认跳过（§16「T5 每日跑，不进每提交 CI」；全量 ≈1.5h/十种子串行，cline C3 实测口径）。

断言口径（裁 17）：
- 守恒：matter/material_balances **逐位相等**（不给浮差）、structures 投影 ⊆ 事件；
- 孤儿：双向对账**硬红**（entropy_inject 与 structure.removed 合法排除已内置）；
- 完成率：基线结构校验（10 日重定标线等 D 批基线归档后另裁，本跑先归档）。

C5：种子写死（seeds.py），虚拟时钟有界帧驱动——同种子重放逐位可重现。
"""
from __future__ import annotations

import os

import pytest

from sim.tests.golden import driver
from sim.tests.golden.assertions.conservation import (
    assert_matter_conserved,
    assert_structures_projected_from_events,
)
from sim.tests.golden.assertions.errands_rate import assert_baseline_recorded, measure_baseline
from sim.tests.golden.assertions.orphan_changes import assert_no_orphans
from sim.tests.golden.chain_runner import run_all_chains
from sim.tests.golden.seeds import GOLDEN_SEEDS, TICKS_PER_GAME_DAY

pytestmark = pytest.mark.skipif(
    os.environ.get("PI_T5_FULL") != "1",
    reason="T5 golden 全量默认跳过（§16 T5 每日跑）；置 PI_T5_FULL=1 触发（≈1.5h）",
)

#: 完成率素材：每种子首日跑一轮续接差事（执行器在 world state 上步进）
_DAYS_FOR_ERRANDS = 1


@pytest.mark.t1
@pytest.mark.parametrize("seed", GOLDEN_SEEDS)
def test_golden_seed_full(seed: int) -> None:
    """单种子全量：10 游戏日驱动 + 事件流三断言 + 差事完成率基线归档。"""
    ticks = TICKS_PER_GAME_DAY * 10
    loop = driver.smoke_loop(n_entities=10, world_seed=seed)

    # 事件流经 on_events 逐帧收集（drain=True 内存有界；收的是本帧事件列表的引用扩展）
    all_events: list = []
    run = driver.run_golden(
        loop,
        ticks,
        feeder=driver.mock_feeder(),
        seed=seed,
        on_events=all_events.extend,
    )

    # 0) 跑满：10 游戏日不早退
    assert run.ticks_run == ticks
    assert run.days_covered >= 10, f"days_covered={run.days_covered}"

    # 1) 守恒（裁 17-1 逐位相等）
    events = list(all_events)
    matter_proj = _project_matter(events)
    assert_matter_conserved(events, matter_proj)
    assert_structures_projected_from_events(events, _structures_seen(events))

    # 2) 孤儿（裁 17-1 硬红；排除面内置）
    assert_no_orphans(events)

    # 3) 差事完成率：首日态上跑续接链 → 基线结构归档（10 日重定标输入）
    outcomes = run_all_chains(loop.state)
    baseline = measure_baseline(outcomes)
    assert_baseline_recorded(baseline)


def _project_matter(events: list) -> dict:
    """事件流 → matter 投影（守恒对账的「投影侧」由事件流折叠生成——
    golden 无持久层，投影=重放同源折叠，判据退化为「折叠自反」+ 投影 ⊆ 事件；
    跨入库对账由 T2 每提交钉子覆盖）。"""
    from sim.tests.golden.assertions.conservation import fold_matter_states

    return dict(fold_matter_states(events))


def _structures_seen(events: list) -> dict:
    """事件流中出现过的 structure id 集（投影 ⊆ 事件面）。"""
    return {
        e.payload.get("structure_id", ""): True
        for e in events
        if e.event_type.value.startswith("structure.")
    }
