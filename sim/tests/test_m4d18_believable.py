"""批次 D18（可信度三修）钉子——用户截图四问的收敛修复。

1. **出生=定籍点**：创世村民出生在本人片区（无开局大迁徙、无药铺挤巷）；
   定籍表**均衡轮转**（每区 10 人——哈希分布实测 14/14/10/6/6 不均，仍挤）；
2. **request_chat 本区化**：聊天目标优先同片区（村内社交），跨区低概率
   （稀罕事）——治「多人同拍抽中同一目标全村互吸」的聚团主源；
3. **模板池扩容 4→12/档**（50 人同屏复读概率压制）+ band3 计划文本带动作
   语境（看板不再是单一句复读）。
"""

from __future__ import annotations

from collections import Counter

import pytest

pytestmark = pytest.mark.t1

# ---------------------------------------------------------------------------
# ① 定籍均衡 + 出生=定籍
# ---------------------------------------------------------------------------


class TestBalancedHomes:
    def test_territory_equal_split(self) -> None:
        """50 村民五区各 10 人（均衡轮转制，哈希只在区内排序）。"""
        from sim.npc.sim_exec import HOME_BASES, home_base_of

        counts = Counter(home_base_of(f"villager_{i:02d}") for i in range(1, 51))
        assert set(counts.keys()) == set(HOME_BASES)
        assert all(v == 10 for v in counts.values()), f"均衡被破坏：{dict(counts)}"

    def test_home_base_still_pure(self) -> None:
        """纯函数不破（C5）：同 id 恒同区。"""
        from sim.npc.sim_exec import home_base_of

        assert home_base_of("villager_01") == home_base_of("villager_01")

    def test_genesis_spawn_uses_territory(self) -> None:
        """创世出生位 = 本人片区锚点邻域（而非药铺环形散布）。"""
        from pathlib import Path

        from sim.content.villagers import territory_spawn_positions
        from sim.npc.sim_exec import home_base_of
        from sim.world.map import TileMap

        town = TileMap.from_json_file(
            Path(__file__).resolve().parents[2] / "sim" / "content" / "linhe-town.json"
        )
        roster = [f"villager_{i:02d}" for i in range(1, 51)]
        positions = territory_spawn_positions(town, roster)
        assert len(positions) == 50
        for npc_id, pos in positions.items():
            home = home_base_of(npc_id)
            dist = abs(pos[0] - home[0]) + abs(pos[1] - home[1])
            assert dist <= 6, f"{npc_id} 出生 {pos} 离定籍点 {home} {dist} 格（应 ≤6）"


# ---------------------------------------------------------------------------
# ② request_chat 本区化
# ---------------------------------------------------------------------------


class TestChatTerritory:
    def test_chat_target_prefers_same_territory(self) -> None:
        """同区目标在场 → 聊天目标落在同区（村内社交优先）。

        用真实正册名（定籍确定）：villager_01 的同区=villager_07/09，
        异区=villager_02/03（测试硬钉这组关系，替身名字反直觉会假红）。
        """
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import _chat_target_of, home_base_of

        h0 = home_base_of("villager_01")
        assert home_base_of("villager_07") == h0 and home_base_of("villager_09") == h0
        assert home_base_of("villager_02") != h0 and home_base_of("villager_03") != h0
        state = WorldState(
            world_seed=42,
            entities={
                f"villager_{i:02d}": EntityState(entity_id=f"villager_{i:02d}", pos=(28 + i, 42))
                for i in (1, 2, 3, 7, 9)
            },
        )
        for tick in range(20):
            target = _chat_target_of(state, "villager_01", tick=tick)
            assert target in ("villager_07", "villager_09"), f"tick={tick} 抽中异区 {target}"

    def test_chat_target_falls_back_cross_territory(self) -> None:
        """同区无人 → 跨区照常（社交不缩水）。"""
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import _chat_target_of

        state = WorldState(
            world_seed=42,
            entities={
                "villager_01": EntityState(entity_id="villager_01", pos=(28, 42)),
                "villager_02": EntityState(entity_id="villager_02", pos=(82, 38)),
            },
        )
        assert _chat_target_of(state, "villager_01", tick=7) == "villager_02"

    def test_chat_no_self(self) -> None:
        from sim.core.world import EntityState, WorldState
        from sim.npc.sim_exec import _chat_target_of

        state = WorldState(
            world_seed=42,
            entities={"villager_01": EntityState(entity_id="villager_01", pos=(28, 42))},
        )
        assert _chat_target_of(state, "villager_01", tick=7) is None


# ---------------------------------------------------------------------------
# ③ 模板池扩容 + 计划语境
# ---------------------------------------------------------------------------


class TestTemplateDiversity:
    def test_pool_expanded(self) -> None:
        """每档模板 ≥12（50 人同屏复读概率压制）。"""
        from sim.agent.will import _TEMPLATES

        for band, pool in _TEMPLATES.items():
            assert len(pool) >= 12, f"band{band} 池只 {len(pool)} 句"
            assert len(set(pool)) == len(pool), f"band{band} 池内重复"

    def test_no_pool_collision_in_one_screen(self) -> None:
        """20 人同屏（一区 10 人 ×2 区）同档独白 distinct ≥8（扩池后可达）。"""
        from sim.agent.will import _TEMPLATES, _pick_index

        pool = _TEMPLATES[1]
        picks = {pool[_pick_index(f"villager_{i:02d}", len(pool))] for i in range(1, 21)}
        assert len(picks) >= 8, f"20 人同档只 {len(picks)} 句（复读依旧）"

    def test_defer_plan_carries_action_context(self) -> None:
        """band3 计划带动作语境（干活的「先去别处，等会儿再干活」≠找人的同款）。"""
        from sim.npc.runtime import _defer_label  # 实现面提取成纯函数

        assert _defer_label("work") == "干活"
        assert _defer_label("request_chat") == "找人说话"
        assert _defer_label("eat") == "吃点东西"
        assert _defer_label("rest") == "歇口气"
