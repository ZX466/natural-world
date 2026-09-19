"""临河镇模拟内核（DESIGN.md v2.1 冻结基线）。

导入根是仓库根目录：`import sim.core.clock`。
子包划分见 DESIGN.md §5；M0 只落地 sim/core（clock/rng/entropy/events/calendar/persistence）
与 sim/world（map/pathfinding），其余为占位骨架。
"""
