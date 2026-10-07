"""批次 D12（聚团消解 + 街谈巷议署名）钉子。

三个面：
1. 站点散点化：eat/rest/work 目的地从「全镇 1~2 个固定点」改为「站点邻域
   内确定性散点」——50 人目的地 distinct 数显著上升（聚团根因是站点经济）；
   request_chat 到站后不再钉在人堆中心（目标格 = 目标人的邻域散点）。
2. 街谈巷议署名：bubble 帧携带 `name`（戏内显示名，可选字段）——前端
   「谁在说」可读（monologue 帧 W7 字段最小化订正：bubble 是外在可观察面，
   带说话人名字不破出戏——头顶气泡本来就署名）。
3. 回归：既有钉（冷却散布/配额/到站退化/防抖）全数保持。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.t1

REPO = Path(__file__).resolve().parents[2]
_TOWN_JSON = REPO / "sim" / "content" / "linhe-town.json"


class TestSiteScatter:
    """站点邻域散点：同拍同动作的人不再挤同一格。"""

    def test_eat_goals_scatter_in_neighborhood(self) -> None:
        """12 个 NPC 同时 eat → 目的地 distinct 数 ≥6（修前 = 1 格全堆）。"""
        from sim.api.main import _fallback_map
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import _resolve_goal
        from sim.world.pathfinding import Pathfinder

        pf = Pathfinder(_fallback_map())
        w, h = pf.tile_map.width, pf.tile_map.height
        state = WorldState(
            world_seed=42,
            entities={
                f"npc_{i:02d}": EntityState(entity_id=f"npc_{i:02d}", pos=(5 + i % 3, 15))
                for i in range(1, 13)
            },
        )
        goals = [
            _resolve_goal(
                state, f"npc_{i:02d}", "eat", seed=42, tick=1000, w=w, h=h, pathfinder=pf
            )
            for i in range(1, 13)
        ]
        distinct = len(set(goals))
        assert distinct >= 6, f"12 人 eat 目的地只 {distinct} 格（站点散点失效）"
        # 全部落在食摊邻域（曼哈顿 ≤4）——散点不是乱跑
        from sim.npc.sim_exec import EAT_SITE

        for g in goals:
            assert g is not None
            assert abs(g[0] - EAT_SITE[0]) + abs(g[1] - EAT_SITE[1]) <= 4, (
                f"eat 散点 {g} 越出食摊邻域"
            )

    def test_eat_scatter_is_deterministic(self) -> None:
        """同 (npc, tick) 恒同散点（C5）。"""
        from sim.api.main import _fallback_map
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import _resolve_goal
        from sim.world.pathfinding import Pathfinder

        pf = Pathfinder(_fallback_map())
        w, h = pf.tile_map.width, pf.tile_map.height
        state = WorldState(
            world_seed=42,
            entities={"npc_01": EntityState(entity_id="npc_01", pos=(5, 15))},
        )
        g1 = _resolve_goal(
            state, "npc_01", "eat", seed=42, tick=1000, w=w, h=h, pathfinder=pf
        )
        g2 = _resolve_goal(
            state, "npc_01", "eat", seed=42, tick=1000, w=w, h=h, pathfinder=pf
        )
        assert g1 == g2

    def test_all_scatter_goals_walkable(self) -> None:
        """散点全可走（寻路不炸；不可走格由散点生成器排除，非路径失败兜底）。
        用真实小镇地图（REST_SITES (34,39) 越出 32×32 fallback——站点坐标
        是按 linhe-town 48×48 定的）。"""
        from sim.content.villagers import build_roster
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import _resolve_goal
        from sim.world.map import TileMap
        from sim.world.pathfinding import Pathfinder

        town = TileMap.from_json_file(_TOWN_JSON)
        pf = Pathfinder(town)
        w, h = pf.tile_map.width, pf.tile_map.height
        roster = build_roster()
        state = WorldState(
            world_seed=42,
            entities={
                p.npc_id: EntityState(entity_id=p.npc_id, pos=(8, 16)) for p in roster
            },
        )
        for i, p in enumerate(roster):
            for action in ("eat", "rest", "work"):
                g = _resolve_goal(
                    state, p.npc_id, action, seed=42, tick=1000 + i, w=w, h=h, pathfinder=pf
                )
                assert g is not None
                assert pf.tile_map.is_walkable(g[0], g[1]), f"{action} 散点不可走: {g}"

    def test_chat_goal_not_exact_target_cell(self) -> None:
        """request_chat 目的地 = 目标人的**邻域**散点（修前 = 精确踩到人所在格）。
        D12 散点 tick 无关（每人固定私位）——多 tick 采样恒同点，这里钉「邻域内
        （散点半径 R=4）」。"""
        from sim.api.main import _fallback_map
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import _SITE_SCATTER_RADIUS, _resolve_goal
        from sim.world.pathfinding import Pathfinder

        pf = Pathfinder(_fallback_map())
        w, h = pf.tile_map.width, pf.tile_map.height
        state = WorldState(
            world_seed=42,
            entities={
                "npc_01": EntityState(entity_id="npc_01", pos=(8, 16)),
                "npc_02": EntityState(entity_id="npc_02", pos=(20, 20)),
            },
        )
        # npc_01 的 chat 目标恒是 npc_02（2 人 deterministic）——目的地在
        # npc_02 的散点邻域内（同散点半径口径）
        goals = {
            _resolve_goal(
                state, "npc_01", "request_chat", seed=42, tick=t, w=w, h=h, pathfinder=pf
            )
            for t in range(1000, 1020)
        }
        assert goals != {(20, 20)}, "chat 目的地不应恒精确踩目标格"
        for g in goals:
            dist = abs(g[0] - 20) + abs(g[1] - 20)
            assert dist <= _SITE_SCATTER_RADIUS, (
                f"chat 目的地 {g} 距目标人 {dist} 格（越出散点半径）"
            )

    def test_50npc_goal_distinct_count_doubles(self) -> None:
        """端到端：50 人同拍目的地 distinct ≥30（修前 23）+ 最热点 ≤6 人
        （修前 13——「围成一团」的直接量度）。真实小镇地图（站点坐标按 48×48 定）。
        实测 D12 散点后 distinct=34 / 最热 4（eat 12 人散进食摊邻域可走格
        ~10 格 + chat 25 人去 25 目标邻域有自然重叠——再拧死会逼出乱跑）。"""
        from collections import Counter

        from sim.content.villagers import build_roster
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import _resolve_goal
        from sim.npc.utility import UtilityModel, evaluate_batch
        from sim.world.map import TileMap
        from sim.world.pathfinding import Pathfinder

        town = TileMap.from_json_file(_TOWN_JSON)
        pf = Pathfinder(town)
        w, h = pf.tile_map.width, pf.tile_map.height
        roster = list(build_roster())
        state = WorldState(
            world_seed=42,
            entities={p.npc_id: EntityState(entity_id=p.npc_id, pos=(8, 16)) for p in roster},
        )
        decisions = evaluate_batch(roster, UtilityModel(n_npc=50))
        goals = [
            _resolve_goal(
                state, d.npc_id, d.action, seed=42, tick=1000, w=w, h=h, pathfinder=pf
            )
            for d in decisions
        ]
        agg = Counter(goals)
        distinct = len(agg)
        top_share = agg.most_common(1)[0][1]
        assert distinct >= 30, f"50 人目的地只 {distinct} 个（修前 23；散点失效？）"
        assert top_share <= 6, f"最热目的地仍吸 {top_share} 人（修前 13；聚团未解）"


class TestBubbleAttribution:
    """bubble 帧署名：monologue_events_to_frames 投影带 name（可选）。"""

    def test_bubble_frame_carries_name(self) -> None:
        import sim.api.ws as ws_mod
        from sim.api.ws import monologue_events_to_frames
        from sim.core.events import npc_monologue_event

        saved = ws_mod._DISPLAY_NAMES
        ws_mod._DISPLAY_NAMES = {"villager_01": "赵铁柱"}
        try:
            e = npc_monologue_event(tick=1, npc_id="villager_01", form="bubble", content="唔")
            frames = monologue_events_to_frames([e])
        finally:
            ws_mod._DISPLAY_NAMES = saved
        (actor_id, frame) = frames[0]
        assert actor_id == "villager_01"
        assert frame.get("name") == "赵铁柱"
        assert frame["form"] == "bubble"

    def test_thought_frame_has_no_name(self) -> None:
        """thought 是私密面（只投本人）：名字无意义，帧保持无 name（W7 不回退）。"""
        import sim.api.ws as ws_mod
        from sim.api.ws import monologue_events_to_frames
        from sim.core.events import npc_monologue_event

        saved = ws_mod._DISPLAY_NAMES
        ws_mod._DISPLAY_NAMES = {"villager_01": "赵铁柱"}
        try:
            e = npc_monologue_event(tick=1, npc_id="villager_01", form="thought", content="心里话")
            frames = monologue_events_to_frames([e])
        finally:
            ws_mod._DISPLAY_NAMES = saved
        assert "name" not in frames[0][1]

    def test_bubble_without_mapping_has_no_name(self) -> None:
        """未装配显示名 → 无 name 键（向后兼容；协议 name 可选）。"""
        import sim.api.ws as ws_mod
        from sim.api.ws import monologue_events_to_frames
        from sim.core.events import npc_monologue_event

        saved = ws_mod._DISPLAY_NAMES
        ws_mod._DISPLAY_NAMES = None
        try:
            e = npc_monologue_event(tick=1, npc_id="villager_01", form="bubble", content="唔")
            frames = monologue_events_to_frames([e])
        finally:
            ws_mod._DISPLAY_NAMES = saved
        assert "name" not in frames[0][1]

    def test_bubble_name_never_entity_id(self) -> None:
        """名字缺失时不得退化出 entity_id（出戏边界：内部 id 禁出站）。"""
        import sim.api.ws as ws_mod
        from sim.api.ws import monologue_events_to_frames
        from sim.core.events import npc_monologue_event

        saved = ws_mod._DISPLAY_NAMES
        ws_mod._DISPLAY_NAMES = {}  # 空映射（装配了但查不到）
        try:
            e = npc_monologue_event(tick=1, npc_id="villager_01", form="bubble", content="唔")
            frames = monologue_events_to_frames([e])
        finally:
            ws_mod._DISPLAY_NAMES = saved
        frame = frames[0][1]
        assert "name" not in frame or frame["name"] != "villager_01"
