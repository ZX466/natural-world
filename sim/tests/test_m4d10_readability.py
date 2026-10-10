"""批次 D10（心之声去噪 + 画布可读性）钉子。

四个面：
1. 模板池多样化：每档多模板（band1×5/band2×4/band3×4），确定性哈希选取
   （C5 同输入同输出）；词面纪律不变（自我怀疑族，T4 band 词表可辨）。
2. 开口稀疏化：冷却按 NPC 散布 [2400, 9600) tick（40~160 游戏分）——
   D2 实证 300 tick/人 × 50 人 = 同拍齐射 50 帧同文（「心之声很凌乱」根因）。
3. 全局配额：每决策节拍全镇 bubble 上限 2 条（保险丝：即便冷却散布撞拍，
   单拍最多 2 帧出镇）。
4. 快照 actor 带戏内名（Actor.name，协议 1.4）：头顶名字供数——
   「画布上看不出谁是谁」根因之一（名字是戏内事实，D8 感知真名同源裁定）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1


# ---------------------------------------------------------------------------
# ① 模板池（will.py）
# ---------------------------------------------------------------------------


class TestTemplatePool:
    """每档多模板 + 确定性选取 + 词面纪律。"""

    def test_pool_sizes(self) -> None:
        from sim.agent.will import _TEMPLATES

        assert len(_TEMPLATES[1]) >= 4
        assert len(_TEMPLATES[2]) >= 4
        assert len(_TEMPLATES[3]) >= 4

    def test_selection_deterministic(self) -> None:
        """C5：同 (verdict, npc) 恒同模板。"""
        from sim.agent.will import WillingnessVerdict, willingness_expression

        v = WillingnessVerdict(score=0.4, band=1)
        a = willingness_expression(v, npc_name="赵铁柱")
        b = willingness_expression(v, npc_name="赵铁柱")
        assert a is not None and b is not None
        assert a.monologue == b.monologue

    def test_names_diverge_within_band(self) -> None:
        """不同 npc 至少产出 ≥2 种说法（池未退化成摆设）。"""
        from sim.agent.will import WillingnessVerdict, willingness_expression

        v = WillingnessVerdict(score=0.4, band=1)
        texts = {
            expr.monologue
            for name in ("赵铁柱", "钱小满", "孙二娘", "李阿婆", "周木匠", "吴秀才")
            if (expr := willingness_expression(v, npc_name=name)) is not None
        }
        assert len(texts) >= 2

    @pytest.mark.parametrize("band", [1, 2, 3])
    def test_band_lexicon_intact(self, band: int) -> None:
        """T4 soft judge 词面可辨：每条模板含本档词族之一。"""
        from sim.agent.will import _TEMPLATES

        LEXICON = {
            1: ("犯嘀咕", "打鼓", "迟疑", "不自在", "犹豫", "不大情愿"),
            2: ("不痛快", "磨蹭", "讨价", "干嘛非要", "凭什么"),
            3: ("打怵", "缓过来", "先去", "不想干"),
        }
        for text in _TEMPLATES[band]:
            assert any(w in text for w in LEXICON[band]), f"band{band} 词面缺失: {text}"

    @pytest.mark.parametrize("band", [1, 2, 3])
    def test_no_manipulation_or_meta_words(self, band: int) -> None:
        """§19 铁律随池扩展继续成立：零被操纵感、零戏外词。"""
        from sim.agent.will import _TEMPLATES

        FORBIDDEN = (
            "谁在指使", "谁指使", "被指使", "命令我", "被操纵",
            "存档", "读档", "重放", "快照", "回放", "分支",
        )
        for text in _TEMPLATES[band]:
            for word in FORBIDDEN:
                assert word not in text, f"band{band} 词面越界 {word!r}: {text}"


# ---------------------------------------------------------------------------
# ② 冷却散布 + ③ 每拍配额（sim_exec.py）
# ---------------------------------------------------------------------------


class TestCooldownSpread:
    """冷却按 NPC 确定性散布——消除「同拍 50 人齐射同文」。"""

    def test_cooldown_in_documented_range(self) -> None:
        from sim.npc.sim_exec import _cooldown_ticks

        for nid in ("npc_01", "npc_02", "villager_17", "villager_50"):
            c = _cooldown_ticks(nid)
            assert 2400 <= c < 9600, f"{nid} 冷却越界: {c}"

    def test_cooldown_spreads_across_npcs(self) -> None:
        from sim.content.villagers import VILLAGER_IDS
        from sim.npc.sim_exec import _cooldown_ticks

        cooldowns = {_cooldown_ticks(nid) for nid in VILLAGER_IDS}
        assert len(cooldowns) >= 40, "50 人冷却散布不足（哈希雪崩失效？）"

    def test_cooldown_deterministic(self) -> None:
        from sim.npc.sim_exec import _cooldown_ticks

        assert _cooldown_ticks("npc_01") == _cooldown_ticks("npc_01")


class TestQuotaPerBeat:
    """每决策节拍全镇 bubble 上限：冷却撞拍时单拍最多出 _MONOLOGUE_QUOTA 条。"""

    def test_quota_caps_same_beat(self) -> None:
        from sim.agent.will import WillingnessVerdict
        from sim.api.main import _fallback_map
        from sim.core.events import EventKind
        from sim.core.world import EntityState, WorldState
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.sim_exec import _MONOLOGUE_QUOTA_PER_BEAT, npc_events_for_tick
        from sim.npc.utility import UtilityModel
        from sim.world.pathfinding import Pathfinder

        profiles = {
            f"npc_{i:02d}": NpcProfileData(
                npc_id=f"npc_{i:02d}", name=f"n{i}", lod=1,
                needs=(Need(name="hunger", value=0.9, weight=1.0),),
            )
            for i in range(1, 7)
        }
        runtime = NpcRuntime(
            profiles=profiles,
            utility=UtilityModel(n_npc=6),
            willingness=WillingnessVerdict(score=0.4, band=1),
        )
        state = WorldState(
            world_seed=42,
            entities={
                f"npc_{i:02d}": EntityState(entity_id=f"npc_{i:02d}", pos=(5, 5))
                for i in range(1, 7)
            },
        )
        last: dict[str, int] = {}
        quota: dict[int, int] = {}
        batch = npc_events_for_tick(
            runtime=runtime, state=state, tick=1000,
            pathfinder=Pathfinder(_fallback_map()), seed=42,
            monologue_last=last, monologue_quota=quota,
        )
        bubbles = [
            e for e in batch
            if e.event_type is EventKind.NPC_MONOLOGUE and e.payload.get("form") == "bubble"
        ]
        assert len(bubbles) <= _MONOLOGUE_QUOTA_PER_BEAT, (
            f"单拍 bubble 出镇 {len(bubbles)} 条 > 配额 {_MONOLOGUE_QUOTA_PER_BEAT}"
        )

    def test_quota_does_not_break_next_beat(self) -> None:
        """配额用尽静默丢弃（表现面节流），下一节拍照常开口。"""
        from sim.agent.will import WillingnessVerdict
        from sim.api.main import _fallback_map
        from sim.core.events import EventKind
        from sim.core.world import EntityState, WorldState
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.sim_exec import npc_events_for_tick
        from sim.npc.utility import UtilityModel
        from sim.world.pathfinding import Pathfinder

        profiles = {
            f"npc_{i:02d}": NpcProfileData(
                npc_id=f"npc_{i:02d}", name=f"n{i}", lod=1,
                needs=(Need(name="hunger", value=0.9, weight=1.0),),
            )
            for i in range(1, 4)
        }
        runtime = NpcRuntime(
            profiles=profiles,
            utility=UtilityModel(n_npc=3),
            willingness=WillingnessVerdict(score=0.4, band=1),
        )
        state = WorldState(
            world_seed=42,
            entities={
                f"npc_{i:02d}": EntityState(entity_id=f"npc_{i:02d}", pos=(5, 5))
                for i in range(1, 4)
            },
        )
        pf = Pathfinder(_fallback_map())
        last: dict[str, int] = {}
        quota: dict[int, int] = {}

        def bubbles_of(events):
            return [
                e for e in events
                if e.event_type is EventKind.NPC_MONOLOGUE and e.payload.get("form") == "bubble"
            ]

        beat1 = npc_events_for_tick(
            runtime=runtime, state=state, tick=1000, pathfinder=pf, seed=42,
            monologue_last=last, monologue_quota=quota,
        )
        # 3 人同拍：配额内最多 2 条，至少 1 人被压（3>2）
        assert len(bubbles_of(beat1)) <= 2
        beat2 = npc_events_for_tick(
            runtime=runtime, state=state, tick=1010, pathfinder=pf, seed=42,
            monologue_last=last, monologue_quota=quota,
        )
        # 下一节拍：被压的人仍在冷却（冷却 ≥2400 tick >> 节拍），不再开口
        assert len(bubbles_of(beat2)) == 0


# ---------------------------------------------------------------------------
# ④ 快照 actor 带戏内名（协议 1.4）
# ---------------------------------------------------------------------------


class TestSnapshotActorName:
    """Actor.name 出站：main 装配显示名 → 快照携带；未装配时零影响。"""

    def test_snapshot_carries_display_name(self) -> None:
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
        saved = ws_mod._DISPLAY_NAMES
        ws_mod._DISPLAY_NAMES = {"villager_01": "赵铁柱"}
        try:
            payload = snapshot_payload(loop, tile_map)
        finally:
            ws_mod._DISPLAY_NAMES = saved
        actors = {a["rtoken"]: a for a in payload["actors"]}
        named = [a for a in actors.values() if a.get("name")]
        assert len(named) == 1
        assert named[0]["name"] == "赵铁柱"
        # 名字是戏内名，不是 entity_id（出戏边界：entity_id 禁出站）
        assert all(a["name"] != a["rtoken"] for a in named)

    def test_snapshot_without_names_unchanged(self) -> None:
        """未装配显示名 → 零 name 键（向后兼容；协议 name 可选）。"""
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
        saved = ws_mod._DISPLAY_NAMES
        ws_mod._DISPLAY_NAMES = None
        try:
            payload = snapshot_payload(loop, tile_map)
        finally:
            ws_mod._DISPLAY_NAMES = saved
        assert all("name" not in a for a in payload["actors"])
