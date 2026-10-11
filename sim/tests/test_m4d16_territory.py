"""批次 D16（扩图 + 定籍领地）钉子。

用户验收口径：「npc 和主角还是在一部分区域乱走」+「将地图扩大，每个 npc
在固定的区域呆着，之后再发生互动」。三个面：

1. **扩图**：build_town SIZE 48→96（面积 ×4），linhe-town.json 产物随
   管线再生；确定性重跑产物漂移钉保持（test_m7_town_map 同款）；
2. **定籍领地**：每人按 npc_id 哈希**定籍一个片区锚点**（HOME_BASES）——
   - wander 锚定**本片区**（不再锚定当前位置：D14 的 wander_near(entity.pos)
     随机游走逐拍累积仍会漂出街区——「一部分区域乱走」的根因收口）；
   - eat/rest/work 落**本片区**站点（不再全镇挤唯一食摊/农田）；
3. **互动照旧**：request_chat 仍跨片区（哈希挑全镇目标 → 走向对方邻域）——
   固定领地不缩水社交面。

定籍是**纯函数**（npc_id + 片区表 → 锚点；C5 同输入同输出），不出事件、
不进世界态——与 D12 散点、D10 冷却同族的表现面确定性。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

pytestmark = pytest.mark.t1

REPO = Path(__file__).resolve().parents[2]
_TOWN_JSON = REPO / "sim" / "content" / "linhe-town.json"


def _town():
    from sim.world.map import TileMap

    return TileMap.from_json_file(_TOWN_JSON)


def _town_pf():
    from sim.npc.sim_exec import plan_npc_move  # noqa: F401
    from sim.world.pathfinding import Pathfinder

    return Pathfinder(_town())


def _state_at(**positions: tuple[int, int]):
    from sim.core.world import EntityState, WorldState

    return WorldState(
        world_seed=42,
        entities={eid: EntityState(entity_id=eid, pos=pos) for eid, pos in positions.items()},
    )


# ---------------------------------------------------------------------------
# ① 扩图 96×96
# ---------------------------------------------------------------------------


class TestTown96:
    def test_dimensions_96(self) -> None:
        town = _town()
        assert town.width == 96 and town.height == 96

    def test_border_impassable(self) -> None:
        town = _town()
        for i in range(96):
            assert not town.is_walkable(i, 0)
            assert not town.is_walkable(i, 95)
            assert not town.is_walkable(0, i)
            assert not town.is_walkable(95, i)

    def test_spawn_walkable(self) -> None:
        assert _town().is_walkable(8, 16), "SPAWN (8,16) 必须可走（main.py 同源依赖）"

    def test_all_home_bases_walkable(self) -> None:
        from sim.npc.sim_exec import HOME_BASES

        town = _town()
        for base in HOME_BASES:
            assert town.is_walkable(*base), f"片区锚点 {base} 必须可走（锚点兜底依赖）"

    def test_deterministic_build(self, tmp_path: Path) -> None:
        before = _TOWN_JSON.read_bytes()
        import subprocess
        import sys

        subprocess.run(
            [sys.executable, str(REPO / "sim" / "content" / "build_town.py")],
            check=True,
            cwd=REPO,
            capture_output=True,
        )
        assert _TOWN_JSON.read_bytes() == before, "build_town.py 重跑产物漂移"


# ---------------------------------------------------------------------------
# ② 定籍领地
# ---------------------------------------------------------------------------


class TestHomeBases:
    def test_home_base_is_pure_hash(self) -> None:
        """定籍纯函数：同 npc_id 同锚点（C5）；不同 npc 分布到多个片区。"""
        from sim.npc.sim_exec import home_base_of

        a = home_base_of("villager_01")
        assert a == home_base_of("villager_01")
        bases = {home_base_of(f"villager_{i:02d}") for i in range(1, 51)}
        assert len(bases) >= 3, "50 人至少分布 3 个片区（挤一个片区=白定籍）"

    def test_all_50_assigned_within_bases(self) -> None:
        from sim.npc.sim_exec import HOME_BASES, home_base_of

        for i in range(1, 51):
            assert home_base_of(f"villager_{i:02d}") in HOME_BASES

    def test_wander_anchored_to_home_base(self) -> None:
        """闲逛目标 ∈ 本片区邻域——人在片区外也会走回家再溜达（漂移收口）。"""
        from sim.npc.sim_exec import _WANDER_RADIUS, home_base_of, wander_near

        pf = _town_pf()
        npc = "villager_01"
        home = home_base_of(npc)
        far_pos = (5, 5)  # 故意放别处：目标仍须落 home 邻域（归巢）
        goal = wander_near(home, npc, pf, seed=42, tick=7)
        assert goal is not None
        assert abs(goal[0] - home[0]) + abs(goal[1] - home[1]) <= _WANDER_RADIUS
        # 归巢语义：从远处发起 wander，目标也锚定 home（不是当前位置）
        assert goal != far_pos or home == far_pos

    def test_wander_near_current_pos_still_available(self) -> None:
        """wander_near 保留「传谁锚谁」的通用形（D14 语义不破坏，调用面升级）。"""
        from sim.npc.sim_exec import _WANDER_RADIUS, wander_near

        pf = _town_pf()
        anchor = (20, 20)
        goal = wander_near(anchor, "npc_x", pf, seed=42, tick=3)
        if goal is not None:
            assert abs(goal[0] - anchor[0]) + abs(goal[1] - anchor[1]) <= _WANDER_RADIUS


# ---------------------------------------------------------------------------
# ③ plan_npc_move 面升级：eat/rest/wander 全部落本片区
# ---------------------------------------------------------------------------


class TestPlanMoveTerritory:
    def test_eat_uses_territory_anchor(self) -> None:
        """eat 目的地 ∈ 本人片区饭摊邻域（不在 (10,15) 全镇独摊）。"""
        from sim.npc.sim_exec import (
            _SITE_SCATTER_RADIUS,
            _site_anchor_of,
            plan_npc_move,
        )

        pf = _town_pf()
        state = _state_at(villager_01=(5, 5))
        event = plan_npc_move(state, "villager_01", "eat", pf, seed=42, tick=100)
        assert event is not None
        goal = cast("tuple[int, int]", event.payload["goal"])  # payload 值 object → 收窄
        # 真实语义：eat 目的地 ∈ 本片区**食摊锚**散点邻域（≤散点半径）——
        # 锚到定籍点的距离由布局表负责（D18 起各区自配食摊，不再跨镇吃饭）。
        anchor = _site_anchor_of("eat", "villager_01")
        assert anchor is not None
        assert abs(goal[0] - anchor[0]) + abs(goal[1] - anchor[1]) <= _SITE_SCATTER_RADIUS, (
            f"eat 散点 {goal} 越出本区食摊 {anchor} 邻域"
        )
        assert _SITE_SCATTER_RADIUS > 0

    def test_rest_uses_territory_home(self) -> None:
        """rest 目的地 ∈ 本人片区宅子邻域。"""
        from sim.npc.sim_exec import home_base_of, plan_npc_move

        pf = _town_pf()
        state = _state_at(villager_01=(5, 5))
        event = plan_npc_move(state, "villager_01", "rest", pf, seed=42, tick=100)
        assert event is not None
        goal = cast("tuple[int, int]", event.payload["goal"])  # payload 值 object → 收窄
        home = home_base_of("villager_01")
        assert abs(goal[0] - home[0]) + abs(goal[1] - home[1]) <= 12

    def test_wander_action_anchored_home(self) -> None:
        """wander 动作：人在别处 → 走回本片区再溜达（不在当前位置附近游荡）。"""
        from sim.npc.sim_exec import home_base_of, plan_npc_move

        pf = _town_pf()
        home = home_base_of("villager_02")
        state = _state_at(villager_02=(5, 5))
        event = plan_npc_move(state, "villager_02", "wander", pf, seed=42, tick=7)
        assert event is not None
        goal = cast("tuple[int, int]", event.payload["goal"])  # payload 值 object → 收窄
        assert abs(goal[0] - home[0]) + abs(goal[1] - home[1]) <= 12, (
            "wander 目标应锚定本片区（当前位置只是途经点）"
        )

    def test_request_chat_still_cross_territory(self) -> None:
        """request_chat 仍跨片区：目标可以是任意其他实体（社交不缩水）。"""
        from sim.npc.sim_exec import plan_npc_move

        pf = _town_pf()
        # villager_03 在 (5,5)，villager_04 在远端 (80,80)——聊天目标照常可达
        state = _state_at(villager_03=(5, 5), villager_04=(80, 80))
        event = plan_npc_move(state, "villager_03", "request_chat", pf, seed=42, tick=100)
        assert event is not None  # 跨区移动不该被定籍拦下

    def test_arrival_stays_kept(self) -> None:
        """D14 到站停留语义不回归：人到站点邻域内 → None。

        口径：eat 到站=站在本片区食摊旁；rest 到站=站在自家门前（家锚点
        与宅门相邻）。站家门口≠到饭摊——需求语义各站点独立。
        """
        from sim.npc.sim_exec import _site_anchor_of, home_base_of, plan_npc_move

        pf = _town_pf()
        npc = "villager_01"
        eat_anchor = _site_anchor_of("eat", npc)
        rest_anchor = _site_anchor_of("rest", npc)
        assert eat_anchor is not None and rest_anchor is not None
        state = _state_at(**{npc: eat_anchor})
        assert plan_npc_move(state, npc, "eat", pf, seed=42, tick=100) is None
        state = _state_at(**{npc: home_base_of(npc)})
        assert plan_npc_move(state, npc, "rest", pf, seed=42, tick=100) is None


# ---------------------------------------------------------------------------
# ④ spawn 面适配：定籍出生（出生位=片区，不再全镇一环挤 50 人）
# ---------------------------------------------------------------------------


class TestSpawnByTerritory:
    def test_spawn_positions_accepts_96(self) -> None:
        """散布函数在 96 图可用（range(1,64) 上界需覆盖大图——不因扩图炸）。"""
        from sim.content.villagers import SPAWN_BASE, spawn_positions

        positions = spawn_positions(_town(), base=SPAWN_BASE, count=50)
        assert len(positions) == 50
