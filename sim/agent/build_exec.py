"""sim.agent.build_exec — 施工 runtime（批次 E4；事件为真相，进度是内存态）。

DESIGN §14 最小闭环：build Intent → STRUCTURE_STARTED（2×2 木棚）→
每日 STRUCTURE_CHECKPOINT（复用 structure.advance_build 规则）→
STRUCTURE_COMPLETED → TILE_CHANGED 占格（4 格全不可走）→ 寻路缓存失效。
``cost``（铜钱）由 driver 侧扣（E4 最小面：只有陈默会开工）。
C5：进度=elapsed/duration 纯函数；格序排序确定（sorted tiles）。
"""

from __future__ import annotations

from dataclasses import dataclass

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.events import (
    WorldEvent,
    structure_checkpoint_event,
    structure_completed_event,
    structure_started_event,
    tile_changed_event,
)
from sim.world.map import TileMap
from sim.world.structure import (
    BUILD_RULE_VERSION,
    BuildProgress,
    advance_build,
    checkpoint_due,
)

#: E4 最小施工单：2×2 木棚，2 游戏日完工，工料 40 文。
BUILD_TILES = 2
BUILD_DURATION_TICKS = TICKS_PER_GAME_DAY * 2
BUILD_COST_COINS = 40


@dataclass
class _Site:
    """一处在建工地（内存态；事件流才是真相）。"""

    progress: BuildProgress
    tiles: tuple[tuple[int, int], ...]
    owner_id: str
    kind: str
    material: str


class BuildRuntime:
    """施工账本（E4 最小面：全镇同时一处工地——多工地留扩展）。

    持有 tile_map 引用并**替换式更新**（frozen map → with_collision 新实例）：
    调用方（main.py）每次 on_tick 后从 runtime.tile_map 取最新图喂寻路。
    """

    def __init__(self, tile_map: TileMap, *, seed: int) -> None:
        self.tile_map = tile_map
        self.seed = seed
        self._site: _Site | None = None

    def active_duration(self) -> int:
        return BUILD_DURATION_TICKS

    @property
    def build_cost(self) -> int:
        return BUILD_COST_COINS

    def reset(self) -> None:
        """丢弃内存工地账本（读档=分叉时调用）。

        事件流才是真相：新分支的 `_site` 由 `restore_from_events` 从该分支
        （含祖先前缀）的 `structure_started/checkpoint` 重建；不清零会让
        旧分支的工地跨分支继续推进并发出旧 `structure_id` 的事件。
        """
        self._site = None

    def restore_from_events(self, events: list[dict]) -> None:
        """从事件流重建在建工地（读档/启动；须先 `reset()`）。

        只认「started 之后没有 completed/collapsed/removed」的那一处工地——
        E4 仍是单工地模型，遇到多处未终态工地取**最后一条 started**（与
        运行时行为一致：新工地开始时旧工地必然已终态）。
        """
        site: _Site | None = None
        for raw in events:
            kind = raw.get("event_type")
            payload = raw.get("payload") or {}
            if kind == "structure.started":
                site = _Site(
                    progress=BuildProgress(
                        structure_id=str(payload["structure_id"]),
                        progress=0.0,
                        quality=0.8,
                        integrity=1.0,
                        build_rule_version=str(payload["build_rule_version"]),
                        started_tick=int(raw["tick"]),
                        planned_duration_ticks=int(payload["planned_duration_ticks"]),
                    ),
                    tiles=tuple(tuple(t) for t in payload["tiles"]),
                    owner_id=str(payload.get("owner_id", "")),
                    kind=str(payload["kind"]),
                    material=str(payload["material"]),
                )
            elif kind == "structure.checkpoint" and site is not None:
                if payload.get("structure_id") == site.progress.structure_id:
                    site.progress = site.progress.__class__(
                        structure_id=site.progress.structure_id,
                        progress=float(payload["progress"]),
                        quality=float(payload["quality"]),
                        integrity=float(payload["integrity"]),
                        build_rule_version=str(payload["build_rule_version"]),
                        started_tick=site.progress.started_tick,
                        planned_duration_ticks=site.progress.planned_duration_ticks,
                        last_checkpoint_tick=int(raw["tick"]),
                    )
            elif (
                kind in ("structure.completed", "structure.collapsed", "structure.removed")
                and site is not None
                and payload.get("structure_id") == site.progress.structure_id
            ):
                site = None
        self._site = site

    def start(self, owner_id: str, pos: tuple[int, int], *, tick: int) -> WorldEvent | None:
        """2×2 选格 → started 事件（None=格不可走/已有工地）。"""
        if self._site is not None:
            return None
        # 行主序生成（y 优先——瓦片语义；schema _canonical_tiles 会再归一化为
        # sorted 元组序，此处序只影响生成序、不影响落库形）。
        tiles = sorted(
            ((pos[0] + dx, pos[1] + dy) for dx in range(BUILD_TILES) for dy in range(BUILD_TILES)),
        )
        if not all(self.tile_map.is_walkable(x, y) for x, y in tiles):
            return None
        structure_id = f"structure_{self.seed}_{tick}"
        progress = BuildProgress(
            structure_id=structure_id,
            progress=0.0,
            quality=0.8,  # E4 固定手艺（技能面留 M6）
            integrity=1.0,
            build_rule_version=BUILD_RULE_VERSION,
            started_tick=tick,
            planned_duration_ticks=BUILD_DURATION_TICKS,
        )
        self._site = _Site(
            progress=progress, tiles=tuple(tiles), owner_id=owner_id, kind="shed", material="wood"
        )
        return structure_started_event(
            tick,
            structure_id=structure_id,
            tiles=tiles,
            kind="shed",
            material="wood",
            planned_duration_ticks=BUILD_DURATION_TICKS,
            recipe_id="shed_2x2",
            recipe_version="e4-v1",
            build_rule_version=BUILD_RULE_VERSION,
            owner_id=owner_id,
            built_by=owner_id,
        )

    def on_tick(self, tick: int) -> list[WorldEvent]:
        """每 tick 推进：checkpoint cadence 到点发 checkpoint；到完工发
        completed + 4 条 tile_changed 并落世界占格（寻路缓存由调用方失效）。"""
        if self._site is None:
            return []
        site = self._site
        out: list[WorldEvent] = []
        progressed = advance_build(site.progress, target_tick=tick)
        if checkpoint_due(progressed, tick=tick):
            progressed = progressed.__class__(
                structure_id=progressed.structure_id,
                progress=progressed.progress,
                quality=progressed.quality,
                integrity=progressed.integrity,
                build_rule_version=progressed.build_rule_version,
                started_tick=progressed.started_tick,
                planned_duration_ticks=progressed.planned_duration_ticks,
                last_checkpoint_tick=tick,
            )
            out.append(
                structure_checkpoint_event(
                    tick,
                    structure_id=progressed.structure_id,
                    progress=progressed.progress,
                    quality=progressed.quality,
                    integrity=progressed.integrity,
                    build_rule_version=progressed.build_rule_version,
                )
            )
        if progressed.progress >= 1.0:
            out.append(
                structure_completed_event(
                    tick,
                    structure_id=progressed.structure_id,
                    quality=progressed.quality,
                    integrity=progressed.integrity,
                )
            )
            out.extend(
                tile_changed_event(tick, x, y, 0)  # tile_id=0：墙体占位（前端图集语义定）
                for x, y in site.tiles
            )
            # 占格生效（frozen map → with_collision 重建引用）
            for x, y in site.tiles:
                self.tile_map = self.tile_map.with_collision(x, y, walkable=False)
            self._site = None
        else:
            self._site.progress = progressed
        return out
