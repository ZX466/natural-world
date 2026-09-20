"""感知引擎测试 — C2 信息边界 + 零元信息 + 确定性（T1 级，无 LLM）。

DESIGN §7 验收核心：
- 遮挡阻断视觉（墙后的人看不见）
- 听觉穿墙衰减不阻断（隔墙仍可闻，强度更低）
- 动机永不输出：帧里只有行为，没有数值关系字段
- 零元信息：帧文本无 tick/entity_id/禁词
- 纯函数确定性：同输入同输出
"""

from __future__ import annotations

import pytest

from sim.core.events import tile_changed_event
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.perception import Channel, PerceptionEngine, PerceptionFrame
from sim.perception.frame import Observation
from sim.perception.profiles.human import HUMAN
from sim.perception.propagation import (
    WALL_DECAY,
    hearing_propagate,
    light_factor,
    line_blocked,
    walls_crossed,
)
from sim.perception.senses import rtoken_of
from sim.world.map import Chunk, TileMap

CHUNK = 16


def make_map(
    width: int = 32, height: int = 32, walls: set[tuple[int, int]] | None = None
) -> TileMap:
    """构造测试图：全通行，walls 里的 tile 不可通行。"""
    wallset = walls or set()
    chunks: dict[tuple[int, int], Chunk] = {}
    for cy in range((height + CHUNK - 1) // CHUNK):
        for cx in range((width + CHUNK - 1) // CHUNK):
            collision = tuple(
                (cx * CHUNK + lx, cy * CHUNK + ly) not in wallset
                for ly in range(CHUNK)
                for lx in range(CHUNK)
            )
            chunks[(cx, cy)] = Chunk(
                cx=cx, cy=cy, ground=(1,) * (CHUNK * CHUNK), collision=collision
            )
    return TileMap(width=width, height=height, chunks=chunks)


def make_state(
    entities: dict[str, tuple[int, int]],
    tick: int = 100,
    paths: dict[str, tuple[tuple[int, int], ...]] | None = None,
) -> WorldState:
    pathmap = paths or {}
    ents = {
        eid: EntityState(entity_id=eid, pos=pos, path=pathmap.get(eid, ()))
        for eid, pos in entities.items()
    }
    return WorldState(world_seed=7, tick=tick, entities=ents)


TICK_EV: list = []  # 多数用例无事件流


class TestPropagation:
    def test_vision_blocked_by_wall(self):
        """视觉：遮挡完全阻断。墙在两点之间 → 不可见。"""
        m = make_map(walls={(10, 5), (10, 6)})
        assert line_blocked(m, (8, 5), (12, 5)) is True  # 直线穿墙
        assert line_blocked(m, (8, 5), (12, 8)) is False  # 绕开墙的斜线

    def test_vision_endpoints_not_blocking(self):
        """端点不算障碍：站在墙 tile 上的实体本身可见（贴墙不瞎）。"""
        m = make_map(walls={(10, 5)})
        assert line_blocked(m, (8, 5), (10, 5)) is False

    def test_hearing_wall_decay(self):
        """听觉：穿墙衰减不阻断。同距下隔墙强度 = 空地 × WALL_DECAY^walls。"""
        open_strength = hearing_propagate(5.0, 0, radius=14.0, floor=0.04).strength
        walled = hearing_propagate(5.0, 2, radius=14.0, floor=0.04).strength
        assert open_strength > 0
        assert walled == pytest.approx(open_strength * WALL_DECAY**2)

    def test_hearing_radius_cutoff(self):
        assert hearing_propagate(30.0, 0, radius=14.0, floor=0.04).strength == 0.0

    def test_walls_crossed_counts_only_between(self):
        m = make_map(walls={(10, 5)})
        assert walls_crossed(m, (8, 5), (12, 5)) == 1
        assert walls_crossed(m, (8, 5), (8, 5)) == 0

    def test_light_factor_phases(self):
        """光照修正：白天 1.0，夜间 <1，黎明过渡。tick 对齐 calendar。"""
        day_tick = 12 * 3600  # 12:00 → DAY
        night_tick = 23 * 3600  # 23:00 → NIGHT
        assert light_factor(day_tick) == 1.0
        assert 0.0 < light_factor(night_tick) < 1.0
        assert 1.0 > light_factor(6 * 3600) > light_factor(night_tick)  # 黎明介于昼夜

    def test_light_factor_is_monotonic_table(self):
        """光照只取有限档位：修正系数是常量表，不是连续函数（可缓存依据）。"""
        from sim.perception.propagation import LIGHT_NIGHT

        assert light_factor(23 * 3600) == LIGHT_NIGHT


class TestRtokenParity:
    def test_rtoken_matches_ws_gateway(self):
        """rtoken 真相源同步锚：感知域复刻必须与 WS 网关逐字节一致。"""
        from sim.api.ws import _rtoken as ws_rtoken

        for eid in ("chenmo", "e001", "npc_barkeep"):
            assert rtoken_of(eid) == ws_rtoken(eid)

    def test_rtoken_is_opaque(self):
        """rtoken 不含 entity_id 原文（C2 出戏边界）。"""
        rt = rtoken_of("chenmo")
        assert rt.startswith("rt-")
        assert len(rt) == 15  # rt- + 12 hex
        assert "chenmo" not in rt


class TestEngineVision:
    def test_sees_person_in_open(self):
        eng = PerceptionEngine(make_map())
        state = make_state({"a": (5, 5), "b": (8, 5)})
        frame = eng.assemble(state, "a", TICK_EV)
        subjects = [ob.subject for ob in frame.observations]
        assert rtoken_of("b") in subjects
        assert all(ob.channel == Channel.VISION for ob in frame.observations)

    def test_wall_hides_person(self):
        """C2 物理实现：一墙之隔 = 不知道。信息边界不是规则是物理。"""
        eng = PerceptionEngine(make_map(walls={(10, 5), (10, 6)}))
        state = make_state({"a": (8, 5), "b": (12, 5)})
        frame = eng.assemble(state, "a", TICK_EV)
        assert rtoken_of("b") not in [ob.subject for ob in frame.observations]

    def test_out_of_radius_not_seen(self):
        eng = PerceptionEngine(make_map())
        state = make_state({"a": (0, 0), "b": (20, 0)})  # 20 > vision_radius 12
        frame = eng.assemble(state, "a", TICK_EV)
        assert frame.observations == ()

    def test_self_not_observed(self):
        eng = PerceptionEngine(make_map())
        state = make_state({"a": (5, 5)})
        frame = eng.assemble(state, "a", TICK_EV)
        assert frame.observations == ()

    def test_night_shrinks_vision(self):
        """夜间光照修正：同一观测夜间强度 = 白天 × LIGHT_NIGHT（0.4）。"""
        eng = PerceptionEngine(make_map())
        far_day = make_state({"a": (5, 5), "b": (16, 5)}, tick=12 * 3600)  # r=11 → 0.091
        far_night = make_state({"a": (5, 5), "b": (16, 5)}, tick=23 * 3600)  # ×0.4=0.036 ≥ floor
        f_day = eng.assemble(far_day, "a", TICK_EV)
        f_night = eng.assemble(far_night, "a", TICK_EV)
        s_day = next(ob for ob in f_day.observations if ob.subject == rtoken_of("b"))
        s_night = next(ob for ob in f_night.observations if ob.subject == rtoken_of("b"))
        assert s_night.strength == pytest.approx(s_day.strength * 0.4)
        assert f_night.light == pytest.approx(0.4)


class TestEngineHearing:
    def test_hears_footsteps_through_wall(self):
        """听觉穿墙：隔墙的人在移动 → 仍可闻（衰减不阻断）。"""
        walls = {(10, 5), (10, 6), (10, 7)}
        eng = PerceptionEngine(make_map(walls=walls))
        state = make_state(
            {"a": (8, 5), "b": (12, 5)},
            paths={"b": ((13, 5), (14, 5))},
        )
        frame = eng.assemble(state, "a", TICK_EV)
        hearing = [ob for ob in frame.observations if ob.channel == Channel.HEARING]
        assert hearing, "隔墙移动者应被听见（穿墙衰减不阻断）"

    def test_footstep_needs_movement(self):
        """静止的人不发光脚步声（M0 语义：path 非空才在动）。"""
        eng = PerceptionEngine(make_map(walls={(10, 5), (10, 6), (10, 7)}))
        state = make_state({"a": (8, 5), "b": (12, 5)})  # b 静止
        frame = eng.assemble(state, "a", TICK_EV)
        assert all(ob.channel != Channel.HEARING for ob in frame.observations)

    def test_door_sound_from_tile_changed(self):
        """tile_changed → 门声事件（环境声，无主体）。"""
        eng = PerceptionEngine(make_map())
        state = make_state({"a": (5, 5), "b": (20, 20)})
        ev = tile_changed_event(tick=state.tick, x=7, y=5, tile_id=2)
        frame = eng.assemble(state, "a", [ev])
        hearing = [ob for ob in frame.observations if ob.channel == Channel.HEARING]
        assert len(hearing) == 1
        assert "动静" in hearing[0].description or "门" in hearing[0].description

    def test_own_footstep_excluded(self):
        """自己移动不给自己发脚步声（身体走内感受，不走听觉）。"""
        eng = PerceptionEngine(make_map())
        state = make_state({"a": (5, 5)}, paths={"a": ((6, 5), (7, 5))})
        frame = eng.assemble(state, "a", TICK_EV)
        assert all(ob.channel != Channel.HEARING for ob in frame.observations)


class TestFrameInvariants:
    def test_no_entity_id_in_frame(self):
        """零元信息：帧内任何文本字段不出 entity_id 原文。

        用长 id（alice/bob）——单字符 id 会是 rtoken 十六进制的巧合子串。
        """
        eng = PerceptionEngine(make_map())
        state = make_state({"alice": (5, 5), "bob": (7, 5)})
        frame = eng.assemble(state, "alice", TICK_EV)
        blob = (
            frame.narrated()
            + frame.observer
            + "".join(ob.subject + ob.description for ob in frame.observations)
        )
        assert rtoken_of("alice") == frame.observer
        assert "alice" not in blob
        assert "bob" not in blob
        assert rtoken_of("bob") in blob  # 对外标识只有 rtoken

    def test_narrated_no_meta_words(self):
        """禁词扫描：感知文本过 codex 禁词表（AI/游戏/tick/玩家…零命中）。"""
        from sim.llm.prompts.banned_words import scan

        eng = PerceptionEngine(make_map())
        state = make_state({"a": (5, 5), "b": (7, 5)}, paths={"b": ((8, 5),)})
        ev = tile_changed_event(tick=state.tick, x=6, y=6, tile_id=2)
        frame = eng.assemble(state, "a", [ev])
        result = scan(frame.narrated())
        assert result.ok, f"感知文本出戏禁词: {[h.word for h in result.hits]}"

    def test_no_numeric_field_leak(self):
        """§7 转换规则反向：帧文本无 hunger:72 / HP:10 类数值字段。"""
        import re

        eng = PerceptionEngine(make_map())
        state = make_state({"a": (5, 5), "b": (7, 5)})
        frame = eng.assemble(state, "a", TICK_EV)
        assert not re.search(r"(?i)(hp|energy|mood|trust)\s*[:：=]\s*\d+", frame.narrated())

    def test_no_motivation_fields(self):
        """动机永不输出：Observation 字段白名单里没有关系数值。"""
        assert set(Observation.model_fields) == {
            "channel",
            "subject",
            "description",
            "strength",
        }

    def test_empty_frame_narration(self):
        eng = PerceptionEngine(make_map())
        state = make_state({"a": (0, 0)})
        frame = eng.assemble(state, "a", TICK_EV)
        assert frame.narrated() == "四周很安静。"

    def test_frame_sorted_for_stability(self):
        """帧内观测排序确定：同输入两次装配逐位一致（C5）。"""
        eng = PerceptionEngine(make_map())
        ents = {"a": (8, 8), "b": (10, 8), "c": (6, 8), "d": (9, 8)}
        paths = {"d": ((10, 8),)}
        state = make_state(ents, paths=paths)
        f1 = eng.assemble(state, "a", TICK_EV)
        f2 = eng.assemble(state, "a", TICK_EV)
        assert f1 == f2


class TestSalience:
    def test_truncates_to_max_observations(self):
        """单帧截断：50 人的开阔地 → 最多 max_observations 条。"""
        eng = PerceptionEngine(make_map(width=64, height=64))
        ents = {"a": (32, 32)}
        for i in range(50):
            ents[f"n{i:02d}"] = (5 + (i % 7), 5 + (i // 7) * 2)  # 近处密集
        state = make_state(ents)
        frame = eng.assemble(state, "a", TICK_EV)
        assert len(frame.observations) <= HUMAN.max_observations

    def test_subject_dedup_keeps_strongest(self):
        """同 subject 多源（视觉+听觉）→ 保留强度最高一条。"""
        from sim.perception.salience import select_observations

        label = rtoken_of("b")
        obs = [
            Observation(channel=Channel.HEARING, subject=label, description="甲", strength=0.3),
            Observation(channel=Channel.VISION, subject=label, description="乙", strength=0.9),
            Observation(channel=Channel.HEARING, subject=label, description="丙", strength=0.5),
        ]
        chosen = select_observations(list(obs), HUMAN)
        assert len(chosen) == 1
        assert chosen[0].description == "乙"

    def test_interoception_priority_first(self):
        """内感受永远排最前（身体优先，铁律 7）。"""
        from sim.perception.salience import select_observations

        obs = [
            Observation(channel=Channel.VISION, subject="rt-x", description="看", strength=1.0),
            Observation(
                channel=Channel.INTEROCEPTION, subject="self", description="饿", strength=0.1
            ),
        ]
        chosen = select_observations(list(obs), HUMAN)
        assert chosen[0].channel == Channel.INTEROCEPTION


class TestNarrate:
    def test_hp_narrative_table(self):
        from sim.perception.narrate import narrate_hp

        assert "硬朗" in narrate_hp(0.95)
        assert "疼" in narrate_hp(0.4)
        assert "黑" in narrate_hp(0.1)
        for v in (0.95, 0.4, 0.1, 0.0):
            text = narrate_hp(v)
            assert not any(ch.isdigit() for ch in text), f"hp 叙事漏数字: {text}"

    def test_hunger_narrative_no_numbers(self):
        from sim.perception.narrate import narrate_hunger

        for v in (0.9, 0.6, 0.3, 0.0):
            assert not any(ch.isdigit() for ch in narrate_hunger(v))

    def test_time_narrative_no_tick_number(self):
        """tick → 「天色暗下来了」，绝不出现数字（§7 转换表第 4 行）。"""
        from sim.perception.narrate import narrate_time

        for tick in (4820, 86399, 43200):
            text = narrate_time(tick)
            assert not any(ch.isdigit() for ch in text), f"time 叙事漏 tick 数字: {text}"


class TestUnknownObserver:
    def test_missing_observer_raises(self):
        eng = PerceptionEngine(make_map())
        state = make_state({"a": (5, 5)})
        with pytest.raises(KeyError):
            eng.assemble(state, "ghost", TICK_EV)


class TestTickLoopMount:
    """感知挂载进 TickLoop 固定执行序（第 3 步，m0-core §5.2）。"""

    def _loop_with_map(self, walls=None):
        from sim.core.clock import GameClock
        from sim.core.tick import TickLoop
        from sim.perception.senses import run_perception_step

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=make_state({"alice": (5, 5), "bob": (12, 5)}, tick=0),
        )
        loop.attach_perception(
            lambda state, evs: run_perception_step(state, make_map(walls=walls), evs)
        )
        return loop

    def test_unmounted_loop_unchanged(self):
        """不挂感知钩子：内核行为与 M0 完全一致（零 import 感知域）。"""
        from sim.core.clock import GameClock
        from sim.core.tick import TickLoop

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=make_state({"alice": (5, 5)}, tick=0),
        )
        loop.advance_frame(1 / 60)
        assert loop.state.tick == 1
        assert loop.perception_frames == {}

    def test_mounted_loop_produces_frames(self):
        loop = self._loop_with_map()
        loop.advance_frame(1 / 60)
        assert loop.state.tick == 1
        # 第 0 tick（tick%2==0）装配了帧
        assert len(loop.perception_frames) == 2
        frame = loop.perception_frames[rtoken_of("alice")]
        assert isinstance(frame, PerceptionFrame)
        subjects = [ob.subject for ob in frame.observations]
        assert rtoken_of("bob") in subjects  # 距离 7 < 12，无遮挡 → 可见

    def test_downsample_tick_skips(self):
        """奇数 tick 跳过装配（H-1 方案 3 视觉降采样），帧保持上一帧。"""
        loop = self._loop_with_map()
        loop.advance_frame(1 / 30)  # 2 tick
        assert loop.state.tick == 2
        # tick0 装配、tick1 跳过 → frames 仍是 tick0 的
        frames = [f for f in loop.perception_frames.values() if isinstance(f, PerceptionFrame)]
        assert frames and all(f.tick == 0 for f in frames)

    def test_wall_blocks_across_mount(self):
        """挂载态下遮挡生效：一墙之隔帧里没有对方。"""
        loop = self._loop_with_map(walls={(8, 5), (8, 6)})
        loop.advance_frame(1 / 60)
        frame = loop.perception_frames[rtoken_of("alice")]
        assert isinstance(frame, PerceptionFrame)
        assert rtoken_of("bob") not in [ob.subject for ob in frame.observations]

    def test_move_events_flow_to_perception(self):
        """移动事件 → 脚步声 → 旁听者听觉观测（端到端链路）。

        bob 在 13 格外：视觉半径 12（看不见）但听觉半径 14（听得见脚步）。
        路径给两步——固定执行序「移动→感知」下单步路径会在感知前走完
        （走完的人这一步已经迈完，不再发声，语义正确）。
        """
        loop = self._loop_with_map()
        loop.state = make_state({"alice": (5, 5), "bob": (18, 5)}, tick=0)
        loop.issue_move("bob", [(19, 5), (20, 5)])
        loop.advance_frame(1 / 60)
        frame = loop.perception_frames[rtoken_of("alice")]
        assert isinstance(frame, PerceptionFrame)
        channels = {ob.channel for ob in frame.observations}
        assert Channel.HEARING in channels, "13 格外的移动者应被听见（脚步声 1/r）"
        assert Channel.VISION not in channels, "视觉半径外不应看见"
