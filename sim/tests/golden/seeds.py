"""T5 golden 种子清单（M4-C3 脚手架）。

C5 纪律：种子是**写死常量**，不用 `random.*` / `time` 派生——golden 的定义就是
「这一组种子 × 10 游戏日」，种子清单本身即验收口径的一部分，改动等同改断言。

选值理由（可辩护 + 覆盖不同 RNG 流相位）：小素数步进的十个 3-4 位数，
彼此量级拉开但都远小于 2^32（PCG64  seeding 无退化顾虑），且与 soak 家族的
`world_seed=7` 不冲突（冒烟默认用它，见 `GOLDEN_SMOKE_SEED`）。
"""

from __future__ import annotations

TICKS_PER_GAME_DAY = 86_400  # 与 sim/core/calendar.py 一致（1 tick = 1 游戏秒）
GAME_DAYS = 10  # DESIGN §16 T5：10 游戏日
TICKS_PER_SEED = TICKS_PER_GAME_DAY * GAME_DAYS  # 864,000 tick / 种子

#: T5 十个种子（写死；见模块 docstring 的选值理由）
GOLDEN_SEEDS: tuple[int, ...] = (7, 11, 101, 1009, 2003, 3001, 4001, 5003, 6007, 7001)

#: 冒烟默认种子（与 soak 家族 world_seed=7 同源，便于横向对比 tick 成本）
GOLDEN_SMOKE_SEED = 7


def seed_matrix() -> tuple[tuple[int, int], ...]:
    """(seed, ticks) 矩阵——workflow 按种子分片时直接取（每片一个种子）。"""
    return tuple((s, TICKS_PER_SEED) for s in GOLDEN_SEEDS)
