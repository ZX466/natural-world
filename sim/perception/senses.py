"""感知引擎 — 每 tick 装配感知帧（DESIGN §7，C06-③ 核心）。

职责边界：
- 输入：WorldState（真相）+ TileMap（静态遮挡）+ 事件流（本 tick 动静）
- 输出：每 observer 一帧 PerceptionFrame（信息边界 C2 的产出物）
- 永不做：帧内不出任何出戏字段（tick 除外——它进帧是 debug/测试坐标，
  叙事端从不消费；其余零 entity_id/seed/内部枚举）

性能设计（docs/perf/hotspots.md H-1 方案 1+3）：
- 视觉：半径预过滤候选 → 候选对上打 Bresenham 射线；光照修正低频缓存
- 听觉：半径预过滤 → base/r × 穿墙衰减（不阻断）
- 显著性截断单帧 ≤ profile.max_observations 条（prompt 体积治理）
- 视听分离节拍（视觉每 2 tick / 听觉每 tick）由调用方决定，引擎幂等纯读

M0 内核移动是插值制（路径段事件 + 每 tick 挪一格），没有逐 tick 移动事件——
「谁在动」从 EntityState.path 判定（每 tick 发脚步声）；门声走 tile_changed。
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple

import structlog

from sim.core.events import WorldEvent
from sim.core.world import WorldState
from sim.perception.frame import Channel, PerceptionFrame
from sim.perception.narrate import (
    narrate_motion,
    narrate_move_end,
    narrate_presence,
    narrate_smell,
    narrate_sound,
)
from sim.perception.profiles.base import PerceptionProfile
from sim.perception.propagation import (
    LIGHT_INTERVAL,
    WALL_DECAY,
    light_factor,
)
from sim.perception.salience import _select_raw

logger = structlog.get_logger(__name__)

FOOTSTEP_BASE = 1.0  # 脚步声基准强度（空地有效听距 ~25 tile，被 hearing_radius 截断）
DOOR_BASE = 0.8  # 开关门声（tile_changed 占位语义，M3 起细化）

_SOUND_DESC_CACHE: dict[tuple[str, str | None], str] = {}


def _sound_desc(kind: str, src_label: str | None) -> str:
    """narrate_sound 的缓存层（同 kind+label 的描述串重复率高）。"""
    key = (kind, src_label)
    cached = _SOUND_DESC_CACHE.get(key)
    if cached is None:
        cached = narrate_sound(kind, src_label)
        if len(_SOUND_DESC_CACHE) >= 4096:
            _SOUND_DESC_CACHE.clear()
        _SOUND_DESC_CACHE[key] = cached
    return cached


_RTOKEN_PREFIX = "rt-"
_RTOKEN_CACHE: dict[str, str] = {}  # entity_id → rtoken（进程级，实体数有限）


def rtoken_of(entity_id: str) -> str:
    """entity_id → rtoken（不透明替身，哈希截断 12 字符，进程级缓存）。

    真相源在 sim.api.ws._rtoken；此处为感知域复刻——两处实现必须逐字节一致，
    test_perception.py 有同步断言锚（改一处必改另一处）。
    """
    cached = _RTOKEN_CACHE.get(entity_id)
    if cached is not None:
        return cached
    import hashlib

    rt = _RTOKEN_PREFIX + hashlib.sha256(entity_id.encode()).hexdigest()[:12]
    _RTOKEN_CACHE[entity_id] = rt
    return rt


def _human_profile() -> PerceptionProfile:
    from sim.perception.profiles.human import HUMAN

    return HUMAN


class _SoundEvent(NamedTuple):
    """一桩可听事件：位置 + 基准强度 + 种类。source_id 为空串 = 环境声。"""

    pos: tuple[int, int]
    base: float
    kind: str  # footstep | door
    source_id: str


def _sound_events_from(
    tick_events: list[WorldEvent], moving_ids: set[str], state: WorldState
) -> list[_SoundEvent]:
    """从本 tick 事件流 + 移动实体提取声学事件。

    移动中实体每 tick 发脚步声（FOOTSTEP_BASE）；tile_changed → 门声。
    「街对面只闻闷响」由 1/r 衰减 + 穿墙衰减自然涌现，不靠规则枚举。
    """
    sounds: list[_SoundEvent] = []
    for eid in sorted(moving_ids):
        ent = state.entities.get(eid)
        if ent is not None:
            sounds.append(_SoundEvent(ent.pos, FOOTSTEP_BASE, "footstep", eid))
    for ev in tick_events:
        if ev.event_type == "tile_changed":
            x = int(ev.payload.get("x", 0))  # type: ignore[arg-type]  # payload 由 schema 保证
            y = int(ev.payload.get("y", 0))  # type: ignore[arg-type]
            sounds.append(_SoundEvent((x, y), DOOR_BASE, "door", ""))
    return sounds


class PerceptionEngine:
    """装配器：绑定一张图（实例级 LOS 缓存 + 扁平碰撞网格随图）。

    assemble 纯读不改状态。性能底座（H-1）：
    - collision_grid：pydantic Chunk 属性链 → bytes 索引（热循环唯一开销）
    - _los_cache：射线对称 key 字典序归一，同对只算一个方向
    """

    _LOS_CACHE_MAX = 65536  # 32×32 全图对子数封顶足够；超出整表清（防膨胀）

    def __init__(self, tile_map, profile: PerceptionProfile | None = None) -> None:
        self._map = tile_map
        self._profile = profile if profile is not None else _human_profile()
        self._light_cache: tuple[int, float] | None = None  # (bucket_tick, factor)
        from sim.perception.propagation import collision_grid

        self._grid = collision_grid(tile_map)
        self._grid_bytes = memoryview(self._grid)  # 热路径局部绑定
        self._map_width = tile_map.width
        self._map_height = tile_map.height
        self._los_cache: dict[tuple[tuple[int, int], tuple[int, int]], bool] = {}
        self._walls_cache: dict[tuple[tuple[int, int], tuple[int, int]], int] = {}

    def _line_blocked(self, a: tuple[int, int], b: tuple[int, int]) -> bool:
        """实例级 LOS 缓存（射线对称：key 字典序归一，同对只算一个方向）。"""
        key = (a, b) if a <= b else (b, a)
        cached = self._los_cache.get(key)
        if cached is not None:
            return cached
        from sim.perception.propagation import line_blocked_grid

        result = line_blocked_grid(self._grid, self._map.width, self._map.height, key[0], key[1])
        if len(self._los_cache) >= self._LOS_CACHE_MAX:
            self._los_cache.clear()
        self._los_cache[key] = result
        return result

    def _walls_crossed(self, a: tuple[int, int], b: tuple[int, int]) -> int:
        """穿墙计数（热路径内联 + 对称缓存：A→B 与 B→A 同数，每对只算一次）。"""
        key = (a, b) if a <= b else (b, a)
        cached = self._walls_cache.get(key)
        if cached is not None:
            return cached
        grid = self._grid_bytes
        w = self._map_width
        h = self._map_height
        x0, y0 = key[0]
        x1, y1 = key[1]
        dx = x1 - x0 if x1 > x0 else x0 - x1
        dy_raw = y1 - y0 if y1 > y0 else y0 - y1
        dy = -dy_raw  # Bresenham 约定：dy = -abs(y1-y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        crossed = 0
        while True:
            if (
                (x0, y0) != key[0]
                and (x0, y0) != key[1]
                and not (0 <= x0 < w and 0 <= y0 < h and grid[y0 * w + x0])
            ):
                crossed += 1
            if x0 == x1 and y0 == y1:
                if len(self._walls_cache) >= self._LOS_CACHE_MAX:
                    self._walls_cache.clear()
                self._walls_cache[key] = crossed
                return crossed
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def light_for_tick(self, tick: int) -> float:
        """光照修正（低频缓存：每 LIGHT_INTERVAL tick 重算，H-1 方案 3）。"""
        cached = self._light_cache
        bucket = tick - (tick % LIGHT_INTERVAL)
        if cached is not None and cached[0] == bucket:
            return cached[1]
        factor = light_factor(tick)
        self._light_cache = (bucket, factor)
        return factor

    def assemble(
        self,
        state: WorldState,
        observer_id: str,
        tick_events: list[WorldEvent] | None = None,
        sounds: list[_SoundEvent] | None = None,
        concentrations: dict[str, float] | None = None,
    ) -> PerceptionFrame:
        """为 observer 装配本 tick 感知帧。纯读：不改 state、无全局态。

        sounds 可由批量入口传入（run_perception_step 共享一次提取结果，
        避免 50 旁听者 × 每人重建声源表）。
        concentrations 可由批量入口传入（嗅觉批量采样结果 {entity_id: 浓度}；
        M2 §5.1 视听之后追加嗅觉观测）。
        性能关键：候选以原始元组参与显著性截断，仅入选者构造 pydantic
        Observation（bench 实测 90% 候选被截断，白建对象占大头）。
        """
        tick_events = tick_events or []
        observer = state.entities.get(observer_id)
        if observer is None:
            msg = f"感知对象不存在: {observer_id}"
            raise KeyError(msg)

        profile = self._profile
        positions = {eid: e.pos for eid, e in state.entities.items()}
        moving = {eid for eid, e in state.entities.items() if e.path}
        light = self.light_for_tick(state.tick)

        # 候选池：(channel, subject, description, strength) 原始元组
        raw: list[tuple[Channel, str, str, float]] = []

        # --- 视觉：半径剪枝候选 → 射线遮挡 → 1/r × 光照，HARD floor 过滤 ---
        # 内联距离剪枝（热路径：省去 candidates_in_radius 的函数调用+排序开销；
        # 顺序 = dict 插入序，确定性由显著性层排序保证）
        ox, oy = observer.pos
        vision_radius = profile.vision_radius
        hearing_radius = profile.hearing_radius
        for eid, p in positions.items():
            if eid == observer_id:
                continue
            dist = math.hypot(p[0] - ox, p[1] - oy)
            if dist > vision_radius:
                continue
            if self._line_blocked(observer.pos, p):
                continue
            strength = (1.0 / max(dist, 1.0)) * light
            if strength < profile.vision_floor:
                continue
            label = rtoken_of(eid)
            if eid in moving:
                desc = narrate_motion(label)
            elif dist <= 2.0:  # 近距离才能分辨「停步」的细节
                desc = narrate_move_end(label)
            else:
                desc = narrate_presence(label)
            raw.append((Channel.VISION, label, desc, strength))

        # --- 听觉：声学事件 → 半径内 base/r × 穿墙衰减（不阻断）---
        if sounds is None:
            sounds = _sound_events_from(tick_events, moving, state)
        hearing_floor = profile.hearing_floor
        wall_decay = WALL_DECAY
        for pos, base, kind, src_id in sounds:
            if src_id == observer_id:
                continue  # 自己的脚步/动静不进自己的听觉（自己的身体走内感受）
            dx = pos[0] - ox
            dy = pos[1] - oy
            dist = math.hypot(dx, dy)
            if dist > hearing_radius or dist <= 0.0:
                continue
            # 穿墙计算前剪枝：即使 0 墙也低于地板的源，免算 Bresenham
            # （墙只会再打折，0 墙上限 = base/dist；这是保守上界，不丢真观测）
            zero_wall = base / dist
            if zero_wall < hearing_floor:
                continue
            walls = self._walls_crossed(observer.pos, pos)
            strength = zero_wall * (wall_decay**walls)
            if strength <= hearing_floor:
                continue
            if strength > 1.0:
                strength = 1.0
            src_label = rtoken_of(src_id) if src_id in state.entities else None
            desc = _sound_desc(kind, src_label)
            subject = src_label if src_label else f"sound:{pos[0]},{pos[1]}"
            raw.append((Channel.HEARING, subject, desc, strength))

        # --- 触觉/内感受（M1 最小闭环：贴身接触 + 无数值身体感）---
        # M1 需求系统未接入（M2 扩展）：此处先占位挂载点，见 DESIGN §7 通道表

        # --- 嗅觉（M2 §5.1：视听之后）：他人浓度 → floor 过滤 → 单条观测 ---
        # subject="smell" 全场去重（一帧最多一条嗅觉）。环境气味语义：报「空气里
        # 有味道」（含自己站进去的云，不归属来源）；零元信息，风向叙事 M3 起。
        if concentrations:
            smell_floor = profile.hearing_floor  # 显著性地板暂与听觉同档
            others_max = max(
                (c for eid2, c in concentrations.items() if eid2 != observer_id),
                default=0.0,
            )
            if others_max >= smell_floor:
                raw.append(
                    (
                        Channel.SMELL,
                        "smell",
                        narrate_smell(others_max),
                        min(1.0, others_max),
                    )
                )

        chosen = _select_raw(raw, profile)
        return PerceptionFrame(
            observer=rtoken_of(observer_id),
            tick=state.tick,
            observations=chosen,
            light=light,
        )


def run_perception_step(
    state: WorldState, tile_map, tick_events: list[WorldEvent]
) -> dict[str, PerceptionFrame]:
    """TickLoop 感知挂载点钩子（attach_perception 的标准实现）。

    对状态内每个实体装配一帧；键为 rtoken（C2：全项目对外标识一个真相源）。
    每 tick 全员装配（真实红线 3ms/tick 由 bench 卡，见 test_bench_perception）。
    共享单引擎实例（LOS/光照缓存跨 tick 复用）+ 声源表一次提取全员共享。
    嗅觉（M2 §5.1）：视听之后推进场 + 批量采样（场随图常驻，_SHARED_SMELL_WORLD）。
    """
    engine = _shared_engine(tile_map)
    smell_world = _shared_smell_world(tile_map)
    moving = {eid for eid, e in state.entities.items() if e.path}
    sounds = _sound_events_from(tick_events, moving, state)
    # 嗅觉：源=全体实体（含观察者自己——他人靠风/扩散把气味带过来）；
    # wind = weather.wind_at 纯函数派生（档内恒定），档位缓存免每 tick 重算哈希。
    wind = _wind_for_tick(state.tick, state.world_seed)
    concentrations = smell_world.step(
        {eid: e.pos for eid, e in state.entities.items()}, wind=wind
    )
    frames: dict[str, PerceptionFrame] = {}
    for eid in state.entities:
        frames[rtoken_of(eid)] = engine.assemble(state, eid, tick_events, sounds, concentrations)
    return frames


_SHARED_ENGINES: dict[int, PerceptionEngine] = {}  # id(tile_map) → engine
_SHARED_SMELL_WORLDS: dict[int, Any] = {}  # id(tile_map) → SmellWorld

# (day, phase) 档位 + world_seed → 每 tick 位移（风档内恒定，weather.wind_slot 口径）
_WIND_CACHE: dict[tuple[object, int], tuple[float, float]] = {}


def _wind_for_tick(tick: int, world_seed: int) -> tuple[float, float]:
    """weather.wind_at 的档位缓存（纯函数，同档同种子必同风；缓存键=档位+种子）。"""
    from sim.core.rng import RngRegistry
    from sim.world.weather import wind_at, wind_slot

    slot = wind_slot(tick)
    key = (slot, world_seed)
    cached = _WIND_CACHE.get(key)
    if cached is None:
        cached = wind_at(tick, RngRegistry(world_seed=world_seed)).vector
        if len(_WIND_CACHE) >= 256:  # 天花板防御：档位数天然有界，防测试膨胀
            _WIND_CACHE.clear()
        _WIND_CACHE[key] = cached
    return cached


def _shared_smell_world(tile_map):
    """同一张图复用同一嗅觉场（TileMap frozen，id 即身份；跨 tick 常驻）。"""
    world = _SHARED_SMELL_WORLDS.get(id(tile_map))
    if world is None:
        from sim.perception.smell_world import SmellWorld

        world = SmellWorld(height=tile_map.height, width=tile_map.width)
        _SHARED_SMELL_WORLDS[id(tile_map)] = world
    return world


def _shared_engine(tile_map) -> PerceptionEngine:
    """同一张图复用同一引擎（TileMap frozen，id 即身份）。"""
    eng = _SHARED_ENGINES.get(id(tile_map))
    if eng is None:
        eng = PerceptionEngine(tile_map)
        _SHARED_ENGINES[id(tile_map)] = eng
    return eng
