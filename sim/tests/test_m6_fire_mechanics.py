"""火灾机制面验收钉 — `sim/world/fire.py`（批次 D 机制面；P11/P14 红线的消费兑现）。

四条红线在本文件的钉：
- **O(G) 蔓延**（P11：禁 O(G²) 成对扫描）——**规模外推钉**：格数 ×10 ⇒ 耗时必须
  同阶（≤ ~12x；O(G²) 会是 ~100x）。这是「接法红线」的机器可测形态（不是阈值数字）；
- **W-D3 事件预算**（N=2 / 每 tick ≤1 条聚合跃迁）——一次 step 的 matter.damage
  + material.moved 至多各 1 条，多格同烧不放大事件数；
- **F4 守恒**——烧毁必带 `material.moved{reason="burned", to_ref="world:burned"}`；
- **纯函数**——同输入两次 step 输出逐位一致（C5）。
"""

from __future__ import annotations

import time

from sim.core.events import EventKind
from sim.world.fire import BURNED_TO_REF, FireCell, step_fires


def _cells(n: int, *, seed: int = 1) -> tuple[FireCell, ...]:
    """n 个火格（确定性布局：网格排布，互不相邻不重叠）。"""
    cells = []
    side = max(1, int(n**0.5) + 1)
    for i in range(n):
        x = (i % side) * 4  # 间隔 4 格：四邻不重叠
        y = (i // side) * 4
        cells.append(FireCell(x=x, y=y, fire_id=f"f{i}", fuel_ticks=30, ignited_tick=0))
    return tuple(cells)


class TestSpreadComplexity:
    def test_spread_is_linear_in_cell_count(self) -> None:
        """规模外推：格数 ×10 ⇒ 耗时同阶（中位数 ≤ ~15x）。O(G²) 会 ~100x，当场红。

        中位数 + 多轮（抗环境抖动——P6 判例：计时类单跑偶发假红，取中位判据）。
        """
        results = []
        for n in (64, 640):
            cells = _cells(n)
            samples = []
            for _ in range(5):
                t0 = time.perf_counter()
                step_fires(cells, tick=1)
                samples.append(time.perf_counter() - t0)
            samples.sort()
            results.append(samples[len(samples) // 2])
        ratio = results[1] / max(results[0], 1e-7)
        assert ratio < 15.0, (
            f"蔓延耗时 10x 格数放大 {ratio:.1f}x（≥15x 即 O(G²) 嫌疑）——"
            "P11 红线：蔓延必须 O(格数)，禁成对扫描"
        )


class TestEventBudget:
    def test_one_damage_and_one_moved_per_tick_regardless_of_cells(self) -> None:
        """多格同烧：matter.damage + material.moved 各**至多 1 条**（W-D3 聚合）。"""
        cells = _cells(37)
        result = step_fires(cells, tick=5)
        damage = [
            e
            for e in result.burn_damage
            if getattr(e, "event_type", None) is EventKind.MATTER_DAMAGE
        ]
        moved = [
            e
            for e in result.burn_damage
            if getattr(e, "event_type", None) is EventKind.MATERIAL_MOVED
        ]
        assert len(damage) <= 1, f"matter.damage 超 1 条：{len(damage)}"
        assert len(moved) <= 1, f"material.moved 超 1 条：{len(moved)}"
        assert damage and moved, "有格在烧却零事件（状态变更零事件口径的反面）"

    def test_spread_budget_respects_max_active_fires(self) -> None:
        """全场数逼近 MAX_ACTIVE_FIRES 时**不再新增**（F≤50 约束式的机制面防御）。"""
        from sim.world.fire import MAX_ACTIVE_FIRES

        cells = _cells(MAX_ACTIVE_FIRES)
        result = step_fires(cells, tick=1)
        assert result.spread_to == (), (
            f"已达 F 上界仍蔓延：+{len(result.spread_to)}（约束式 2F≤100 被破）"
        )


class TestConservation:
    def test_burn_carries_burned_to_ref(self) -> None:
        """烧毁材料去向 = world:burned（F4/T1 守恒；A8/K12 定案）。"""
        cells = _cells(3)
        result = step_fires(cells, tick=2)
        moved = [
            e
            for e in result.burn_damage
            if getattr(e, "event_type", None) is EventKind.MATERIAL_MOVED
        ]
        assert moved, "有格在烧却无 material.moved"
        payload = moved[0].payload
        assert payload["to_ref"] == BURNED_TO_REF, payload
        assert payload["reason"] == "burned", payload

    def test_burned_out_cells_reported(self) -> None:
        """燃料尽的格进 burned_out（调用方走 set_fire_end("fuel_out")，本层不写）。

        按**坐标**断言（同场蔓延的新格与旧格同 fire_id 是合法——烧尽的是「这一格」，
        不是「这一场」）。
        """
        cell = FireCell(x=1, y=1, fire_id="f0", fuel_ticks=1, ignited_tick=0)
        result = step_fires((cell,), tick=3)
        assert result.burned_out == ("f0",)
        assert (1, 1) not in {(c.x, c.y) for c in result.cells}, (
            "烧尽的格不该留在下一 tick 输入（同场新格蔓延合法）"
        )


class TestPurity:
    def test_same_input_same_output(self) -> None:
        """C5：同输入两次 step 输出逐位一致（无隐藏随机/时钟）。"""
        cells = _cells(9)
        a = step_fires(cells, tick=4)
        b = step_fires(cells, tick=4)
        assert a.cells == b.cells
        assert a.spread_to == b.spread_to
        assert a.burned_out == b.burned_out
        assert [e.payload for e in a.burn_damage] == [e.payload for e in b.burn_damage]

    def test_no_rng_is_deterministic_spread(self) -> None:
        """不传 rng_draw = 确定性蔓延（前沿全部点燃，受预算约束）。"""
        cells = _cells(1)
        result = step_fires(cells, tick=1)
        assert len(result.spread_to) >= 1, "确定性蔓延下前沿应被点燃"
