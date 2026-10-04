"""M5-A12 核实钉 —— soak `entity_count` 的数据面来源与死亡语义影响（零生产码）

派单：`talking.txt` M5-A12 第 1 件（回执答问为准，可附小测试佐证）。被核实的对象是
**性能域的 soak 契约**（`sim/tests/bench/soak.py`、`test_bench_soak.py`），本文件**只读**
它们、零改动；钉子钉的是「数据面事实」，因为契约改法（pi P13：只减不增 + 有界）成不成立
取决于这些事实。

**钉组一览**：

- **来源钉**：`entity_count` = `len(loop.state.entities)`（`WorldState.entities` 字典），
  **不是** `npc_profiles` 行数、**不含** `matter_state`；soak 源码零表查询。
- **结构钉**：`EntityState` 只有 `entity_id/pos/path` —— **没有 lod、没有 alive/dead**
  ⇒ 计数里没有 LOD 维度、也没有「死了但还被数」这个形态的**现状**载体。
- **增删钉**：只有 `world.create` 往字典里插键；`move` 事件与 tick 内移动只改既有键的字段
  ⇒ 今天 `end == start` 恒真的是因为**没有删除路径**，不是因为死亡不计数。
- **LOD 钉**：`npc.lod_change` 在默认总线上**未注册**（进不了 `WorldState`）；`lod > 0`
  过滤只存在于 `sim/npc/runtime.py` 的 L1 决策层 ⇒ LOD 0 既不被计数排除，也不影响计数。
- **采样点钉**：计数在**第一个 tick 之前**与**最后一个 tick 之后**各采一次；稳定性依赖
  「harness 预置实体」（app 形态是 `world.create` 在 tick 1 才落 ⇒ 那里 start 会是 0）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.core.events import EventKind, npc_lod_change_event, world_create_event
from sim.core.tick import TickLoop
from sim.core.world import EntityState, TickContext, WorldState, build_default_bus

REPO_ROOT = Path(__file__).resolve().parents[2]
SOAK_PY = REPO_ROOT / "sim" / "tests" / "bench" / "soak.py"
BENCH_SOAK_PY = REPO_ROOT / "sim" / "tests" / "bench" / "test_bench_soak.py"


def _state(n: int) -> WorldState:
    """预置 n 个实体的世界（harness 同款：bench 用它，app 不用）。"""
    return WorldState(
        world_seed=7,
        entities={f"npc{i}": EntityState(entity_id=f"npc{i}", pos=(i, i)) for i in range(n)},
    )


def _loop(state: WorldState) -> TickLoop:
    from sim.core.clock import GameClock

    return TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)


class TestEntityCountSource:
    def test_count_comes_from_world_state_entities(self) -> None:
        """来源钉：`SoakResult.entity_count_*` 采的是 `len(loop.state.entities)`。"""
        src = SOAK_PY.read_text(encoding="utf-8")
        assert "entity_count_start=len(loop.state.entities)" in src
        assert "result.entity_count_end = len(loop.state.entities)" in src

    def test_soak_never_queries_tables(self) -> None:
        """soak 计数**不查任何表**（不是 `npc_profiles` 行数、不含 `matter_state`）。

        判别力：若将来有人把计数改成「投影表行数」，死亡/降格的可见性会**静默换口径**，
        而契约文案还写着「实体数」——这条钉就是那个口径漂移的绊线。
        """
        src = SOAK_PY.read_text(encoding="utf-8")
        for banned in ("npc_profiles", "matter_state", "npc_power", "structures"):
            assert banned not in src, f"soak.py 引用了 {banned}（计数口径被换掉过？）"

    def test_entity_state_has_no_lod_nor_alive_field(self) -> None:
        """结构钉：`EntityState` 只有 `entity_id/pos/path` ⇒ 没有 LOD、没有生死列。"""
        assert set(EntityState.model_fields) == {"entity_id", "pos", "path"}

    def test_lod_change_event_cannot_reach_world_state(self) -> None:
        """LOD 钉：`npc.lod_change` 在默认总线上**未注册** ⇒ 进不了 `WorldState.entities`。"""
        bus = build_default_bus()
        state = _state(1)
        with pytest.raises(ValueError, match="未注册"):
            bus.apply(state, npc_lod_change_event(1, "npc0", 1, 0, "far"), TickContext())


class TestNoAddNoRemoveToday:
    def test_world_create_is_the_only_key_insert(self) -> None:
        """只有 `world.create` 往实体字典插键（其余 handler 只改既有键的字段）。"""
        bus = build_default_bus()
        result = bus.apply(
            _state(0), world_create_event(tick=0, seed=7, entity_ids=("a", "b")), TickContext()
        )
        assert set(result.state.entities) == {"a", "b"}

    def test_moves_never_change_the_key_set(self) -> None:
        """`move` 与 tick 内移动**只改字段**，键集合恒定 ⇒ 今天没有删除路径。"""
        from sim.core.events import move_event

        bus = build_default_bus()
        state = _state(2)
        for i in range(3):
            out = bus.apply(
                state,
                move_event(
                    # apply 不推进 state.tick ⇒ 事件 tick 必须 ≤ state.tick + 1
                    tick=1,
                    actor_id="npc0",
                    start=(i, 0),
                    goal=(i + 1, 1),
                    path=((i, 0), (i + 1, 1)),
                ),
                TickContext(),
            )
            state = out.state
        assert set(state.entities) == {"npc0", "npc1"}
        assert state.entities["npc0"].path  # 字段确实变了

    def test_tick_movement_keeps_key_set(self) -> None:
        """跑若干 tick（内置移动步进）后键集合不变（增删路径今天不存在）。"""
        loop = _loop(_state(3))
        for _ in range(5):
            loop.advance_frame(0.1)
        assert set(loop.state.entities) == {"npc0", "npc1", "npc2"}


class TestSamplingPoint:
    def test_soak_counts_stay_equal_with_preseeded_entities(self) -> None:
        """采样点钉：预置实体的 loop 上跑短 soak，`start == end`（稳定性来自「无删除路径」）。"""
        from sim.tests.bench.soak import run_soak

        loop = _loop(_state(4))
        result = run_soak(loop, 20, window_ticks=10, drain=True)
        assert (result.entity_count_start, result.entity_count_end) == (4, 4)

    def test_app_shaped_loop_is_stable_too(self) -> None:
        """app 形态同样 start == end（因为 ``enqueue`` 是**立即 apply**，不是排队等 tick）。

        ⇒ 采样点隐患不在「创世晚到」，而在「**窗内插入**」；而窗内插入今天结构上不可能
        （见 `test_world_create_refuses_non_blank_world`）⇒ 计数只可能持平或下降，
        这正是 pi 要把契约改成「只减不增 + 有界」的形状依据。
        """
        from sim.tests.bench.soak import run_soak

        loop = _loop(WorldState(world_seed=42))  # app 同款：空状态 + enqueue create
        loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
        result = run_soak(loop, 3, window_ticks=10, drain=True)
        assert (result.entity_count_start, result.entity_count_end) == (1, 1)

    def test_world_create_refuses_non_blank_world(self) -> None:
        """结构性事实：**窗内新增实体今天不可能**（创世只许作用于空白世界）。

        判别力：这是 pi 契约形状的硬依据——`end == start` 在 M0-M5 恒真，是因为
        「既不新增也不删除」；M6 加删除路径后正确的契约不是放宽成「只减不增」，而是
        **照旧能证明没有新增**（新增被创世门结构挡住）。
        """
        bus = build_default_bus()
        state = _state(1)
        with pytest.raises(ValueError, match="创世事件只能作用于空白世界状态"):
            bus.apply(state, world_create_event(tick=1, seed=7, entity_ids=("x",)), TickContext())


class TestBenchAssertionShape:
    def test_both_sites_use_structural_entity_guard(self) -> None:
        """契约形状钉（**M6-P1 阶段 A 追改**，原钉名 `…assert_equality`）：

        本钉原本钉「两处都硬断言 `end == start`」= M5-P14 的派单背景。
        阶段 A 落地后（`docs/perf/m6-soak-contract-preplan.md` §2，裁 36-4）该形状**按设计退役**，
        改为「两处都走**结构量**共用判据 `_assert_entity_stable`」：
          · 旧等式断言 **0 次**（已移入共用判据，防双真相源）；
          · 共用判据在 `_assert_no_runaway` / `_assert_smoke` 各 **1 次** ⇒ 共 2 次。
        **阶段 A 不预设死亡**：`SOAK_ENTITY_LOSS_PER_GAME_DAY == 0` ⇒ 净减上界 0 ⇒
        与旧 `end == start` **语义等价**（故仍与下面那条「今天无死亡 kind」钉相容）。
        阶段 B（生命落点 a 落地同 CR）提常量值，本钉不随动。
        """
        src = BENCH_SOAK_PY.read_text(encoding="utf-8")
        assert src.count("assert result.entity_count_end == result.entity_count_start") == 0
        assert src.count("_assert_entity_stable(result, label=label, profile_ids=profile_ids)") == 2

    def test_event_kind_registry_has_no_removal_kind(self) -> None:
        """事件白名单里**没有**任何「删除实体/死亡」类 kind ⇒ 死亡语义在 M6 之前无载体。

        判别力：pi 的契约改法依赖「M6 会让计数下降」；而下降必须有一条**可重放**的删除路径
        （红线 A：新增 kind 需授权）。这条钉把「载体还不存在」钉成事实，避免契约先行。
        """
        names = {kind.value for kind in EventKind}
        # `structure.removed` 是**结构**生命周期事件（批次 D 火灾域），与实体删除无关 ⇒
        # 这里只查「死亡/退场」语义的 kind。
        death_like = {n for n in names if any(w in n for w in ("death", "dead", "despawn", "kill"))}
        assert death_like == set(), f"已有死亡类 kind：{death_like}（契约前提要重算）"
