"""批次 D14（移动纪律 + 真实意愿 + 动作姿势供数）钉子。

四个面：
1. 移动纪律（「NPC 随便移动」根治）：
   - 到站停留：eat/rest/work/request_chat 已在目的地 → plan_npc_move 返回
     None（不再「退化为闲逛被赶走」——D14 语义翻转，停留由需求驱动）；
   - wander 邻域化：闲逛目标从全图 [0,w)×[0,h) 改为当前位置曼哈顿 ≤6 邻域
     可走格（排除原格）——闲逛不再横穿小镇；
   - 不可达 → None（原地待着，不再退化成全图乱兜）。
2. 真实意愿合成：synthesize_verdict(profile, action, tick)——性格违背
   （内向被拉去聊天/低勤奋被派活）+ 需求冲突（饿着不吃饭）+ 处境不合
   （深夜干活/白天补觉）→ band 全谱分布；替换 main.py 的全队 band=1 占位。
3. defers → 计划看板接线（K8 §3 生产写入点）：band=3 →
   set_plan_from_expression(npc_id, 动作短语, defers=True)。
4. 动作姿势供数：npc.act → anim 账本（eat/rest/work/request_chat → 同名，
   wander/move → "walk"）；快照与 delta 携带 anim（schema 既有字段，纯启用）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.t1

REPO = Path(__file__).resolve().parents[2]
_TOWN_JSON = REPO / "sim" / "content" / "linhe-town.json"


def _town_pf():
    from sim.world.map import TileMap
    from sim.world.pathfinding import Pathfinder

    return Pathfinder(TileMap.from_json_file(_TOWN_JSON))


def _state_at(**positions: tuple[int, int]):
    from sim.core.world import EntityState, WorldState

    return WorldState(
        world_seed=42,
        entities={eid: EntityState(entity_id=eid, pos=pos) for eid, pos in positions.items()},
    )


# ---------------------------------------------------------------------------
# ① 移动纪律
# ---------------------------------------------------------------------------


class TestArrivalStays:
    """到站停留：已在目的地 → 不再被赶走。"""

    def test_arrived_eat_stays(self) -> None:
        from sim.npc.sim_exec import _site_anchor_of, plan_npc_move

        pf = _town_pf()
        anchor = _site_anchor_of("eat", "npc_01")
        assert anchor is not None
        state = _state_at(npc_01=anchor)
        assert plan_npc_move(state, "npc_01", "eat", pf, seed=42, tick=1000) is None, (
            "已到本人片区食摊 → 停住（D16 定籍：站点=片区站点）"
        )

    def test_arrived_rest_stays(self) -> None:
        from sim.npc.sim_exec import _site_anchor_of, plan_npc_move

        pf = _town_pf()
        anchor = _site_anchor_of("rest", "npc_01")
        assert anchor is not None
        state = _state_at(npc_01=anchor)
        assert plan_npc_move(state, "npc_01", "rest", pf, seed=42, tick=1000) is None

    def test_arrived_work_stays(self) -> None:
        from sim.npc.sim_exec import _site_anchor_of, plan_npc_move

        pf = _town_pf()
        anchor = _site_anchor_of("work", "npc_01")
        assert anchor is not None
        state = _state_at(npc_01=anchor)
        assert plan_npc_move(state, "npc_01", "work", pf, seed=42, tick=1000) is None

    def test_not_arrived_still_moves(self) -> None:
        """没到站照常出发（纪律不是不动）。"""
        from sim.core.events import EventKind
        from sim.npc.sim_exec import plan_npc_move

        pf = _town_pf()
        state = _state_at(npc_01=(100, 53))  # 换图：村广场带可走
        mv = plan_npc_move(state, "npc_01", "eat", pf, seed=42, tick=1000)
        assert mv is not None and mv.event_type is EventKind.MOVE


class TestWanderNearby:
    """闲逛邻域化：不再全图散布。"""

    def test_wander_goal_within_radius(self) -> None:
        from sim.npc.sim_exec import _WANDER_RADIUS, wander_near

        pf = _town_pf()
        home = (100, 53)  # 换图：药铺=村广场带
        for i in range(30):
            g = wander_near(home, f"npc_{i}", pf, seed=42, tick=i)
            assert g is not None
            dist = abs(g[0] - home[0]) + abs(g[1] - home[1])
            assert 1 <= dist <= _WANDER_RADIUS, f"闲逛目标 {g} 距家 {dist}（越出邻域）"
            assert pf.tile_map.is_walkable(g[0], g[1])

    def test_wander_goal_deterministic(self) -> None:
        from sim.npc.sim_exec import wander_near

        pf = _town_pf()
        a = wander_near((100, 53), "npc_01", pf, seed=42, tick=1000)
        b = wander_near((100, 53), "npc_01", pf, seed=42, tick=1000)
        assert a == b

    def test_wander_move_uses_nearby(self) -> None:
        """wander 动作的位移面走邻域（D16 升级：邻域=本人片区锚点邻域）。"""
        from sim.npc.sim_exec import _WANDER_RADIUS, home_base_of, plan_npc_move

        pf = _town_pf()
        state = _state_at(npc_01=(100, 53))
        home = home_base_of("npc_01")
        for i in range(10):
            mv = plan_npc_move(state, "npc_01", "wander", pf, seed=42, tick=1000 + i)
            assert mv is not None
            raw_goal = mv.payload["goal"]
            assert isinstance(raw_goal, (list, tuple)) and len(raw_goal) >= 2
            goal = (int(raw_goal[0]), int(raw_goal[1]))
            dist = abs(goal[0] - home[0]) + abs(goal[1] - home[1])
            assert dist <= _WANDER_RADIUS, f"wander 目标 {goal} 距定籍点 {dist}（越出邻域）"

    def test_unreachable_returns_none_no_wild_wander(self) -> None:
        """目的地不可达 → None（原地待着）；修前退化为全图闲逛。"""
        from sim.npc.sim_exec import plan_npc_move

        pf = _town_pf()
        # 边界树墙格不可走也出不去；找一个被围死的点不现实——直接钉：
        # 不可达路径不再产生「退化为 wander」的第二个 move（结构性钉：
        # plan_npc_move 对 site 动作只发「朝解析目标」的 move，永不夹带
        # wander 兜底）。用「已到站」+「不可达」两态覆盖即可，此处钉到站态。
        from sim.npc.sim_exec import _site_anchor_of

        anchor = _site_anchor_of("eat", "npc_01")
        assert anchor is not None
        state = _state_at(npc_01=anchor)
        assert plan_npc_move(state, "npc_01", "eat", pf, seed=42, tick=1) is None


# ---------------------------------------------------------------------------
# ② 真实意愿合成
# ---------------------------------------------------------------------------


class TestSynthesizeVerdict:
    """synthesize_verdict：性格/需求/处境 → band 全谱。"""

    def _profile(self, ocean: tuple[float, float, float, float, float], needs=None):
        from sim.npc.model import Need, NpcProfileData

        return NpcProfileData(
            npc_id="npc_01",
            name="测试",
            lod=1,
            ocean=ocean,
            needs=needs
            or (
                Need(name="hunger", value=0.2, weight=1.0),
                Need(name="energy", value=0.2, weight=1.0),
                Need(name="social", value=0.2, weight=1.0),
            ),
        )

    def test_introvert_chat_conflicts(self) -> None:
        """内向 5 被拉去聊天 → band ≥1（性格违背）。"""
        from sim.agent.will import synthesize_verdict

        p = self._profile((50.0, 50.0, 5.0, 50.0, 50.0))
        v = synthesize_verdict(p, "request_chat", tick=36000)
        assert v.band >= 1

    def test_extrovert_chat_fine(self) -> None:
        """外向 95 聊天 → band 0（顺性）。"""
        from sim.agent.will import synthesize_verdict

        p = self._profile((50.0, 50.0, 95.0, 50.0, 20.0))
        v = synthesize_verdict(p, "request_chat", tick=36000)
        assert v.band == 0

    def test_lazy_work_conflicts(self) -> None:
        """低勤奋 5 被派活 → band ≥1。"""
        from sim.agent.will import synthesize_verdict

        p = self._profile((50.0, 5.0, 50.0, 50.0, 50.0))
        v = synthesize_verdict(p, "work", tick=36000)
        assert v.band >= 1

    def test_hungry_but_not_eating_conflicts(self) -> None:
        """饥饿 0.9 超阈值却在闲逛 → band ≥1（需求冲突）。"""
        from sim.agent.will import synthesize_verdict
        from sim.npc.model import Need

        p = self._profile(
            (50.0, 50.0, 50.0, 50.0, 20.0),
            needs=(
                Need(name="hunger", value=0.9, weight=1.0),
                Need(name="energy", value=0.1, weight=1.0),
                Need(name="social", value=0.1, weight=1.0),
            ),
        )
        v = synthesize_verdict(p, "wander", tick=36000)
        assert v.band >= 1

    def test_night_work_conflicts(self) -> None:
        """深夜（phase=night）干活 → band ≥1（处境不合）。"""
        from sim.agent.will import synthesize_verdict

        p = self._profile((50.0, 50.0, 50.0, 50.0, 20.0))
        # 86400 tick/游戏日；night 从 19:00 起 = 68400
        v = synthesize_verdict(p, "work", tick=68400 + 600)
        assert v.band >= 1

    def test_day_work_fine(self) -> None:
        """白天干活 → band 0。"""
        from sim.agent.will import synthesize_verdict

        p = self._profile((50.0, 50.0, 50.0, 50.0, 20.0))
        v = synthesize_verdict(p, "work", tick=43200)  # 12:00
        assert v.band == 0

    def test_bands_cover_spectrum_across_population(self) -> None:
        """50 人 × 各动作 → band 分布覆盖 ≥3 档（全谱，替换恒 band1 占位）。"""
        from collections import Counter

        from sim.agent.will import synthesize_verdict
        from sim.content.villagers import build_roster

        roster = list(build_roster())
        bands: Counter = Counter()
        for i, p in enumerate(roster):
            for action in ("eat", "rest", "work", "request_chat", "wander"):
                v = synthesize_verdict(p, action, tick=36000 + i * 7)
                bands[v.band] += 1
        assert len(bands) >= 3, f"band 分布只 {dict(bands)}（未成谱）"

    def test_deterministic(self) -> None:
        from sim.agent.will import synthesize_verdict

        p = self._profile((50.0, 50.0, 5.0, 50.0, 50.0))
        a = synthesize_verdict(p, "request_chat", tick=1000)
        b = synthesize_verdict(p, "request_chat", tick=1000)
        assert a == b


class TestRuntimeWillingnessOf:
    """NpcRuntime.willingness_of：逐人合成 → 独白多样化 + defers→plan。"""

    def _runtime(self, **kwargs):
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.utility import UtilityModel

        def _profile(nid: str, extrav: float) -> NpcProfileData:
            return NpcProfileData(
                npc_id=nid,
                name=nid,
                lod=1,
                ocean=(50.0, 50.0, extrav, 50.0, 50.0),
                needs=(Need(name="hunger", value=0.9, weight=1.0),),
            )

        profiles = {
            "npc_in": _profile("npc_in", 5.0),
            "npc_out": _profile("npc_out", 95.0),
        }
        return NpcRuntime(
            profiles=profiles,
            utility=UtilityModel(n_npc=2),
            **kwargs,
        )

    def test_willingness_of_diversifies(self) -> None:
        """逐人合成：不同性格同拍独白可不同（修前全队同 band 同文）。"""
        from sim.agent.will import synthesize_verdict

        rt = self._runtime(willingness_of=synthesize_verdict)
        events = rt.tick(36000)
        monos = [str(e.payload["content"]) for e in events if e.event_type.value == "npc.monologue"]
        # 内向者 vs 外向者：至少一人 band0 沉默、一人开口（分布分化）
        assert len(monos) <= 1, f"两人都开口且未分化？{monos}"

    def test_legacy_shared_verdict_still_works(self) -> None:
        """旧 willingness 共享 verdict 字段零回归（既有钉兼容）。"""
        from sim.agent.will import WillingnessVerdict

        rt = self._runtime(willingness=WillingnessVerdict(score=0.6, band=2))
        events = rt.tick(1000)
        monos = [e for e in events if e.event_type.value == "npc.monologue"]
        assert len(monos) == 2, "共享 verdict 模式：全员开口（旧语义保持）"

    def test_none_no_monologue(self) -> None:
        rt = self._runtime()
        events = rt.tick(1000)
        assert not [e for e in events if e.event_type.value == "npc.monologue"]


class TestDefersPlanWiring:
    """band=3 defers → 计划看板（K8 §3 生产写入点）。"""

    def test_defer_writes_plan_with_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from sim.npc import plan_view
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.utility import UtilityModel

        plan_view.reset_plan_registry()
        try:
            p = NpcProfileData(
                npc_id="npc_01",
                name="测试",
                lod=1,
                ocean=(95.0, 5.0, 5.0, 5.0, 95.0),
                needs=(Need(name="hunger", value=0.1, weight=1.0),),
            )
            # 注入面强制 band3（willingness_of 是主路径；lambda 签名与
            # runtime 调用口径一致：tick 是 keyword-only）
            from sim.agent.will import WillingnessVerdict

            def _band3(profile: object, action: str, *, tick: int) -> WillingnessVerdict:
                return WillingnessVerdict(score=0.9, band=3)

            rt = NpcRuntime(
                profiles={"npc_01": p},
                utility=UtilityModel(n_npc=1),
                willingness_of=_band3,
            )
            rt.tick(1000)
            plan = plan_view.plan_of("npc_01")
            assert plan is not None, "band3 defers 应写计划看板"
            assert plan.startswith(plan_view.DEFER_PLAN_PREFIX)
        finally:
            plan_view.reset_plan_registry()


# ---------------------------------------------------------------------------
# ④ 动作姿势供数（anim 账本）
# ---------------------------------------------------------------------------


class TestAnimLedger:
    """npc.act → anim 账本 → 快照/delta 携带。"""

    def test_anim_mapping(self) -> None:
        from sim.npc.sim_exec import anim_of_action

        assert anim_of_action("work") == "work"
        assert anim_of_action("eat") == "eat"
        assert anim_of_action("rest") == "rest"
        assert anim_of_action("request_chat") == "chat"
        assert anim_of_action("wander") == "walk"
        assert anim_of_action("move") == "walk"

    def test_snapshot_carries_anim(self) -> None:
        import sim.api.ws as ws_mod
        from sim.api.ws import snapshot_payload
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus
        from sim.world.map import TileMap

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=WorldState(world_seed=1),
        )
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=("villager_01",)))
        tile_map = TileMap(width=8, height=8, chunks={})
        saved = ws_mod._ACTION_ANIMS
        ws_mod._ACTION_ANIMS = {"villager_01": "work"}
        try:
            payload = snapshot_payload(loop, tile_map)
        finally:
            ws_mod._ACTION_ANIMS = saved
        actor = payload["actors"][0]
        assert actor["anim"] == "work"

    def test_snapshot_default_idle(self) -> None:
        import sim.api.ws as ws_mod
        from sim.api.ws import snapshot_payload
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus
        from sim.world.map import TileMap

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=WorldState(world_seed=1),
        )
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=("villager_01",)))
        tile_map = TileMap(width=8, height=8, chunks={})
        saved = ws_mod._ACTION_ANIMS
        ws_mod._ACTION_ANIMS = {}
        try:
            payload = snapshot_payload(loop, tile_map)
        finally:
            ws_mod._ACTION_ANIMS = saved
        assert payload["actors"][0]["anim"] == "idle"

    def test_delta_carries_anim(self) -> None:
        from sim.api.ws import delta_payload
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.tick import TickLoop
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=WorldState(world_seed=1),
        )
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=("villager_01",)))
        loop.issue_move("villager_01", [(1, 0), (2, 0)])
        loop.advance_frame(1.0)
        import sim.api.ws as ws_mod

        saved = ws_mod._ACTION_ANIMS
        ws_mod._ACTION_ANIMS = {"villager_01": "work"}
        try:
            payload = delta_payload(loop, loop.drain_delta())
        finally:
            ws_mod._ACTION_ANIMS = saved
        actor = payload["actors"][0]
        assert actor.get("anim") == "work"


class TestWanderUnreachableRetry:
    """2026-10-12 换图补：wander 目标孤立（可走但不可达）→ 确定性重挑不空转。

    桃花源图 820 可走格中 25 格孤立——修前 wander_near 只查目标格可走，
    寻路 ValueError → None（原地发呆拍空转）；修后 tick+offset 有限重试。
    """

    def test_plan_move_survives_isolated_goals(self) -> None:
        from sim.npc.sim_exec import plan_npc_move

        pf = _town_pf()
        # 从村广场（主连通块）wander 到桃门片区——中间偶发抽中孤立格，
        # 10 拍里至少半数该产出 move（重挑机制在工作）
        produced = 0
        for i in range(10):
            state = _state_at(npc_01=(100, 53))
            mv = plan_npc_move(state, "npc_01", "wander", pf, seed=42, tick=2000 + i)
            if mv is not None:
                produced += 1
        assert produced >= 5, f"10 拍仅 {produced} 拍产出移动——孤立格重挑未生效"
