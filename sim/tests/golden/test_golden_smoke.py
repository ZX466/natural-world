"""T5 golden 脚手架冒烟：1 种子 × 1 游戏日（**不含断言组**，M4-C3）。

存在意义：证明「虚拟时钟驱动器 + 确定性喂给器」能**跑通一整个游戏日**且事件流非空，
让 D 批填断言组时不必先怀疑 harness。断言组本体（守恒 / 差事完成率 / 无孤儿变更）
按 `docs/arch/t5-golden-scaffold.md` 另填，本文件**只断言 harness 自身**。

跑法（与 soak 家族同惯例，§16：T5 每日跑、不进每提交 CI）：

```bash
# 满一日（86,400 tick，默认）
PI_GOLDEN_SMOKE=1 uv run pytest sim/tests/golden/test_golden_smoke.py -q
# 1 游戏小时切片（秒级）
GOLDEN_SMOKE_TICKS=3600 PI_GOLDEN_SMOKE=1 uv run pytest sim/tests/golden/test_golden_smoke.py -q
```

未置 `PI_GOLDEN_SMOKE=1` 时整文件跳过（每提交 CI 秒过，不烧 CPU）。
"""

from __future__ import annotations

import os

import pytest

from sim.tests.golden import driver
from sim.tests.golden.seeds import GOLDEN_SMOKE_SEED, TICKS_PER_GAME_DAY

pytestmark = pytest.mark.skipif(
    os.environ.get("PI_GOLDEN_SMOKE") != "1",
    reason="T5 golden 冒烟默认跳过（§16：T5 每日跑，不进每提交 CI）；置 PI_GOLDEN_SMOKE=1 触发",
)


def _ticks() -> int:
    """目标 tick 数：默认满一游戏日（86,400），可用 GOLDEN_SMOKE_TICKS 做秒级切片。"""
    raw = os.environ.get("GOLDEN_SMOKE_TICKS")
    return int(raw) if raw else TICKS_PER_GAME_DAY


def test_golden_smoke_one_game_day() -> None:
    """1 种子 × 1 游戏日：harness 跑通 + 事件流非空 + 逐日窗口可取数。"""
    ticks = _ticks()
    loop = driver.smoke_loop(n_entities=10, world_seed=GOLDEN_SMOKE_SEED)
    run = driver.run_golden(loop, ticks, feeder=driver.mock_feeder(), seed=GOLDEN_SMOKE_SEED)

    # 1) 跑满：虚拟时钟推进量必须等于请求量（不早退、不超跑）
    assert run.ticks_run == ticks, f"ticks_run={run.ticks_run} != {ticks}"
    assert loop.state.tick == ticks, f"state.tick={loop.state.tick} != {ticks}"
    # 2) 事件流非空：证明喂给器→内核→事件真的在动（否则「跑通」是空转）
    assert run.total_events > 0, "事件流为空——harness 跑通但没产出事件，断言组将无从取数"
    # 3) 逐日窗口可取数：满一日时必须有窗口且日切跨越判定生效
    assert run.windows, "无逐日窗口——日切判定失效"
    if ticks >= TICKS_PER_GAME_DAY:
        assert run.days_covered >= 1, f"days_covered={run.days_covered}（满一日却没跨日）"
        assert any(w.n_events > 0 for w in run.windows), "所有日窗口事件数皆 0"
    # 4) 每 tick 均耗时已记录（runtime 估算输入，见 scaffold §4）
    assert run.mean_tick_ms() > 0.0, "mean_tick_ms 未记录——无法估算 10 游戏日墙钟"
