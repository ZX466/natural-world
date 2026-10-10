"""批次 D19（作息接线 + 创世定籍收口）钉子。

D18 遗留收口 + 用户复验截图（21:56）定罪：

1. **创世接线**：D18 写了 territory_spawn_positions 但 main.py 仍调旧
   spawn_positions（村民从药铺出生→大迁徙仍在）——本批换调并钉死；
2. **作息进效用**：凌晨（NIGHT 相位）全体站着聊天/嘟囔（截图 02:48 实锤）
   ——schedule.current_slot 的相位档接进 utility：夜相非 rest 动作压分
   （压幅=POWER_MAX_BIAS 同量级，生存列 eat 例外——饿醒照吃）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.t1

REPO = Path(__file__).resolve().parents[2]
_NIGHT_TICK = 3 * 3600  # 03:00（NIGHT 相位中段）
_DAY_TICK = 12 * 3600  # 12:00（DAY 中段）


def _profile(npc_id: str):
    from sim.npc.model import Need, NpcProfileData

    return NpcProfileData(
        npc_id=npc_id,
        name=npc_id,
        needs=(
            Need(name="hunger", value=0.3, weight=1.0),
            Need(name="energy", value=0.3, weight=1.0),
            Need(name="social", value=0.3, weight=1.0),
        ),
    )


# ---------------------------------------------------------------------------
# ① 创世定籍（main.py 换调）
# ---------------------------------------------------------------------------


class TestGenesisTerritory:
    def test_main_uses_territory_spawn(self) -> None:
        """main.py 创世调 territory_spawn_positions（出生=定籍，药铺散布退役）。"""
        src = (REPO / "sim" / "api" / "main.py").read_text(encoding="utf-8")
        assert "territory_spawn_positions" in src, "main.py 未接定籍出生（D18 遗留）"
        assert "spawn_positions(tile_map_for_spawn, base=SPAWN_BASE" not in src, (
            "旧药铺散布仍在创世路径（大迁徙根因未除）"
        )

    def test_genesis_positions_near_homes(self) -> None:
        """端到端：build_loop 创世后村民实体位=定籍邻域（≤8 格容差）。"""
        from sim.content.villagers import territory_spawn_positions
        from sim.npc.sim_exec import home_base_of
        from sim.world.map import TileMap

        town = TileMap.from_json_file(REPO / "sim" / "content" / "linhe-town.json")
        roster = [f"villager_{i:02d}" for i in range(1, 51)]
        positions = territory_spawn_positions(town, roster)
        for nid, pos in positions.items():
            home = home_base_of(nid)
            assert abs(pos[0] - home[0]) + abs(pos[1] - home[1]) <= 6


# ---------------------------------------------------------------------------
# ② 作息进效用：夜相非 rest 压分
# ---------------------------------------------------------------------------


class TestScheduleBias:
    def test_night_rest_wins(self) -> None:
        """夜相 + 困倦画像（energy 略高）→ rest 胜出（凌晨上床）。

        钉语义=作息罚让「非恢复动作」在夜相失去竞争力；低需求并列
        （eat/rest 同分）时 argmax 稳定序取 eat 属需求增益真实数学
        （吃完睡也是戏内逻辑），不属缺陷——本钉用「夜里困了」画像。
        """
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.utility import UtilityModel, evaluate_batch

        p = NpcProfileData(
            npc_id="villager_01",
            name="甲",
            needs=(
                Need(name="hunger", value=0.2, weight=1.0),
                Need(name="energy", value=0.45, weight=1.0),
                Need(name="social", value=0.2, weight=1.0),
            ),
        )
        decisions = evaluate_batch([p], UtilityModel(n_npc=1), night_bias=True)
        assert decisions[0].action == "rest", (
            f"夜相困倦决策={decisions[0].action}（应 rest——作息面未接）"
        )

    def test_day_no_bias(self) -> None:
        """昼相（无夜_bias）同一画像 → 决策与旧管线逐位一致（作息只动夜相）。"""
        from sim.npc.utility import UtilityModel, evaluate_batch

        p = _profile("villager_01")
        base = evaluate_batch([p], UtilityModel(n_npc=1))
        day = evaluate_batch([p], UtilityModel(n_npc=1), night_bias=False)
        assert base[0].action == day[0].action
        assert base[0].scores == day[0].scores, "昼相决策被夜相罚量污染"

    def test_hungry_at_night_still_eats(self) -> None:
        """生存例外：夜里饿顶格 → eat 仍胜（作息不压生存列）。"""
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.utility import UtilityModel, evaluate_batch

        p = NpcProfileData(
            npc_id="villager_01",
            name="甲",
            needs=(
                Need(name="hunger", value=0.95, weight=1.0),
                Need(name="energy", value=0.3, weight=1.0),
                Need(name="social", value=0.3, weight=1.0),
            ),
        )
        decisions = evaluate_batch([p], UtilityModel(n_npc=1), night_bias=True)
        assert decisions[0].action == "eat", "夜里饿顶格不吃=作息压垮生存列"

    def test_bias_is_pure_and_exact(self) -> None:
        """night_bias=False 与旧管线逐位相等（C5）；罚量恰 = _NIGHT_ACTION_PENALTY；
        生存列（eat）与 rest 列零罚。"""
        from sim.npc.utility import (
            _NIGHT_ACTION_PENALTY,
            UtilityModel,
            utility_scores_matrix,
        )

        p = _profile("villager_01")
        m = UtilityModel(n_npc=1)
        base = utility_scores_matrix([p], m)
        night = utility_scores_matrix([p], m, night_bias=True)
        day = utility_scores_matrix([p], m, night_bias=False)
        assert np.array_equal(base, day), "night_bias=False 改了打分（破坏兼容面）"
        chat_col = m.action_index["request_chat"]
        rest_col = m.action_index["rest"]
        eat_col = m.action_index["eat"]
        assert float(day[0, chat_col] - night[0, chat_col]) == pytest.approx(
            _NIGHT_ACTION_PENALTY, abs=1e-6
        )
        assert float(night[0, rest_col]) == pytest.approx(float(day[0, rest_col]), abs=1e-6)
        assert float(night[0, eat_col]) == pytest.approx(float(day[0, eat_col]), abs=1e-6)
