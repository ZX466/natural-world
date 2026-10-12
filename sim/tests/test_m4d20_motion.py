"""批次 D20（表现三修）钉子——用户截图三问收敛。

1. **路径扰动**：同起终点恒同一条路（A* 确定性）→ 50 人走同街=列车化
   「固定轨迹」。修：plan_npc_move 出的路径做**确定性横向扰动**——
   (npc_id, tick) 哈希在「等价偏移格」间挑点（C5 保逐位一致；只扰可走格
   且不改起终点，长度可控）。
2. **快照时刻**（前端漂移的 sim 侧配合面）：delta 帧无时刻字段（出戏
   边界），前端用收到帧的本地时刻对齐——纯前端修，本文件只钉 sim 侧
   路径扰动。
3. 心之声/街谈巷议分栏：纯前端（PanelHost 布局 + cap），无 sim 钉。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

pytestmark = pytest.mark.t1

REPO = Path(__file__).resolve().parents[2]
_TOWN_JSON = REPO / "sim" / "content" / "linhe-town.json"


def _town_pf():
    from sim.world.map import TileMap
    from sim.world.pathfinding import Pathfinder

    return Pathfinder(TileMap.from_json_file(_TOWN_JSON))


def _state_at(**positions):
    from sim.core.world import EntityState, WorldState

    return WorldState(
        world_seed=42,
        entities={eid: EntityState(entity_id=eid, pos=pos) for eid, pos in positions.items()},
    )


class TestPathJitter:
    def test_same_od_different_npcs_diverge(self) -> None:
        """同起终点、不同 npc/tick → 路径有差异（不再人人踩同一条街）。"""
        from sim.npc.sim_exec import _jitter_path

        pf = _town_pf()
        base = pf.find((95, 52), (100, 52))
        paths = {
            _jitter_path(base, f"villager_{i:02d}", tick=100, pathfinder=pf) for i in range(1, 11)
        }
        assert len(paths) >= 2, "10 人同 OD 全走同一条路（扰动未生效）"

    def test_jitter_is_deterministic(self) -> None:
        """同 (path, npc, tick) 恒同路径（C5）。"""
        from sim.npc.sim_exec import _jitter_path

        pf = _town_pf()
        base = pf.find((95, 52), (100, 52))
        a = _jitter_path(base, "villager_01", tick=100, pathfinder=pf)
        b = _jitter_path(base, "villager_01", tick=100, pathfinder=pf)
        assert a == b

    def test_jitter_keeps_endpoints(self) -> None:
        """扰动不换起终点；全格可走。"""
        from sim.npc.sim_exec import _jitter_path

        pf = _town_pf()
        base = pf.find((95, 52), (100, 52))
        for tick in range(30):
            p = _jitter_path(base, "villager_02", tick=tick, pathfinder=pf)
            assert p[0] == base[0] and p[-1] == base[-1]
            assert all(pf.tile_map.is_walkable(x, y) for x, y in p)

    def test_jitter_bounded_length(self) -> None:
        """扰动后路径长度 ≤ 基线 ×1.6（不绕远路——绕远=另一个极端）。"""
        from sim.npc.sim_exec import _jitter_path

        pf = _town_pf()
        base = pf.find((95, 52), (100, 52))
        for tick in range(30):
            p = _jitter_path(base, "villager_03", tick=tick, pathfinder=pf)
            assert len(p) <= max(2, int(len(base) * 1.6) + 1), (
                f"tick={tick} 扰动路径 {len(p)} 远超基线 {len(base)}"
            )

    def test_short_path_untouched(self) -> None:
        """≤2 格短路径不扰（扰动收益低、端点约束高）。"""
        from sim.npc.sim_exec import _jitter_path

        pf = _town_pf()
        base = pf.find((95, 52), (97, 52))
        assert _jitter_path(base, "villager_01", tick=7, pathfinder=pf) == base

    def test_plan_move_applies_jitter(self) -> None:
        """plan_npc_move 产出的 move 事件路径已含扰动（接线钉）。"""
        from sim.npc.sim_exec import plan_npc_move

        pf = _town_pf()
        paths = set()
        for i in range(1, 11):
            nid = f"villager_{i:02d}"
            st = _state_at(**{nid: (100, 53)})  # 换图：药铺（村广场带可走）
            ev = plan_npc_move(st, nid, "eat", pf, seed=42, tick=100 + i)
            if ev is not None:
                path = cast("list[list[int]]", ev.payload["path"])
                paths.add(tuple((int(x), int(y)) for x, y in path))
        assert len(paths) >= 2, "10 人同 OD 同路径（plan_npc_move 未接扰动）"
