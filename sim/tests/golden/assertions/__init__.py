"""T5 golden 断言组（裁 17 口径，M4-C4 落码；断言实现归配置/文档域 = cline）。

三条口径（`docs/arch/t5-golden-scaffold.md` §7 裁 17，2026-09-26）：

1. **守恒 = 逐位相等**——不给浮点容差。可成立的前提是「事件流折叠」与「投影」**同源同序**
   （§19.3：两入口共用 `npc_store.fold_*` 单一折叠规则），故精确相等是有效判据。
2. **差事完成率 = 10 日重定标**——M1 的 80% 是**单决策**口径；跨日续接 fixture 落地后先测
   基线再定线。本轮只落**基线实测壳**（`errands_rate`），**不设阈值**。
3. **无孤儿变更 = 硬红**——不降级告警；方向 B 必须排除 `entropy_inject`（熵只进事件流、
   world state 永不留痕，裁 14-5 + 脚手架 §3.3 写死的坑）。

**折叠规则一律复用数据域单一实现**（`npc_store.fold_matter_snapshot` /
`fold_structure_snapshot` / `fold_material_balance`）：断言只做「事件流折叠结果 ↔ 投影」对账，
**不重算领域算术**——否则断言自己就会与投影/重放分叉，正是 §19.3 要防的那类 bug。

事件顺序前置条件：调用方必须给 **seq 升序**（`driver.run_golden` 的 `on_events` 收集天然有序；
DB 侧 `read_range` 已升序）。折叠对顺序敏感，故本包**不内部排序**。
"""

from .conservation import (
    MaterialBalanceRow,
    assert_material_balances_conserved,
    assert_matter_conserved,
    assert_structures_projected_from_events,
    diff_matter_states,
    fold_material_balances,
    fold_matter_states,
    fold_structure_phases,
)
from .errands_rate import (
    ErrandBaseline,
    ErrandOutcome,
    assert_baseline_recorded,
    completion_rate,
    measure_baseline,
)
from .orphan_changes import (
    OrphanReport,
    assert_no_orphans,
    find_orphans,
)

__all__ = [
    "ErrandBaseline",
    "ErrandOutcome",
    "MaterialBalanceRow",
    "OrphanReport",
    "assert_baseline_recorded",
    "assert_material_balances_conserved",
    "assert_matter_conserved",
    "assert_no_orphans",
    "assert_structures_projected_from_events",
    "completion_rate",
    "diff_matter_states",
    "find_orphans",
    "fold_material_balances",
    "fold_matter_states",
    "fold_structure_phases",
    "measure_baseline",
]
