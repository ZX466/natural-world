"""V4a single-cell editing: deterministic clock, one owner, committed material stock.

The runtime proposes events. Only a successful store flush is observed as an edit
or inventory change. Pending reservations prevent repeated inputs overspending.
Collision restoration remains exclusively TILE_CHANGED, shared with structures.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sim.core.events import (
    EventKind,
    VoxelEditedPayload,
    WorldEvent,
    material_moved_event,
    move_event,
    tile_changed_event,
    voxel_edited_event,
)
from sim.core.world import WorldState
from sim.world.map import TileMap

DIG_TICKS = 30
VOXEL_REACH = 4
STATE_EVERY_TICKS = 6
PLAYER = "chenmo"
STOCK = "npc:chenmo"
_MATERIAL_BY_HEIGHT = {1: "earth", 2: "stone", 3: "wood"}
_MATERIAL_LABELS = {"earth": "土", "stone": "石料", "wood": "木料"}
type Action = Literal["dig", "place"]


class VoxelRejected(ValueError):
    """An invalid request has no world events; its message is already diegetic."""


@dataclass(frozen=True)
class Dig:
    x: int
    y: int
    started: int
    owner: object | None


class VoxelRuntime:
    def __init__(
        self,
        *,
        tile_map: Callable[[], TileMap],
        height_of: Callable[[int, int], int],
        ground_gid: Callable[[int, int], int],
        occupied: Callable[[int, int], bool],
    ) -> None:
        self._map = tile_map
        self._height = height_of
        self._ground = ground_gid
        self._occupied = occupied
        self.reset()

    def reset(self) -> None:
        self._dig: Dig | None = None
        self._elapsed = 0
        self._reported = 0
        self._inventory = dict.fromkeys(_MATERIAL_BY_HEIGHT.values(), 0)
        self._reserved = dict.fromkeys(_MATERIAL_BY_HEIGHT.values(), 0)
        self._pending: dict[tuple[int, int], tuple[Action, str]] = {}
        self._heights: dict[tuple[int, int], int] = {}
        self._updates: list[tuple[object | None, dict[str, Any]]] = []

    def height_at(self, x: int, y: int) -> int:
        return self._heights.get((x, y), self._height(x, y))

    def _observe_height(self, edit: VoxelEditedPayload) -> None:
        self._heights[(edit.x, edit.y)] = edit.result_height(self.height_at(edit.x, edit.y))

    def snapshot(self) -> dict[str, Any]:
        return {
            "dig": None
            if self._dig is None
            else {
                "x": self._dig.x,
                "y": self._dig.y,
                "progress": self._elapsed / DIG_TICKS,
            },
            "inventory": dict(self._inventory),
        }

    def _notify(self, owner: object | None = None) -> None:
        self._updates.append((owner, self.snapshot()))

    def drain_updates(self) -> list[tuple[object | None, dict[str, Any]]]:
        updates, self._updates = self._updates, []
        return updates

    def _validate(self, state: WorldState, x: int, y: int, action: Action) -> str:
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, int)
            or not isinstance(y, int)
        ):
            raise VoxelRejected("那处地方碰不到。")
        actor = state.entities.get(PLAYER)
        if actor is None or actor.incapacitated_until is not None:
            raise VoxelRejected("此刻手上使不上劲。")
        if (
            not self._map().in_bounds(x, y)
            or abs(actor.pos[0] - x) + abs(actor.pos[1] - y) > VOXEL_REACH
        ):
            raise VoxelRejected("离得太远，够不着那里。")
        height = self.height_at(x, y)
        if height == 0:
            raise VoxelRejected("水面上动不了土。")
        material = _MATERIAL_BY_HEIGHT.get(height)
        if material is None:
            raise VoxelRejected("这处材料辨不清。")
        if self._occupied(x, y):
            raise VoxelRejected("这里已有屋舍，不能动土。")
        if (x, y) in self._pending:
            raise VoxelRejected("这块地方刚动过，稍等一等。")
        if self._map().is_walkable(x, y) != (action == "place"):
            raise VoxelRejected("这块地方不用再动了。")
        if action == "place" and height >= 3:
            raise VoxelRejected("这块地方不用再动了。")
        return material

    def request(
        self,
        action: str,
        x: int,
        y: int,
        state: WorldState,
        *,
        owner: object | None = None,
    ) -> list[WorldEvent]:
        if action == "dig_cancel":
            if not self.cancel(owner):
                self._notify(owner)
            return []
        if action not in ("dig_start", "place"):
            raise VoxelRejected("这会儿做不了这件事。")
        kind: Action = "dig" if action == "dig_start" else "place"
        material = self._validate(state, x, y, kind)
        if kind == "dig":
            if (
                self._dig is not None
                and (self._dig.x, self._dig.y) == (x, y)
                and self._dig.owner is owner
            ):
                return []
            self._dig = Dig(x, y, state.tick, owner)
            self._elapsed = self._reported = 0
            self._notify()
            return []
        # Read committed stock, excluding earlier unflushed placement reservations.
        if self._inventory[material] - self._reserved[material] < 1:
            raise VoxelRejected(f"行囊里没有{_MATERIAL_LABELS[material]}了。")
        events = self._edit(state.tick, x, y, "place", material)
        self._reserved[material] += 1
        self._pending[(x, y)] = ("place", material)
        return [*events, *self._stop_paths(state, state.tick)]

    def cancel(self, owner: object | None) -> bool:
        if self._dig is None or self._dig.owner is not owner:
            return False
        self._dig = None
        self._elapsed = self._reported = 0
        self._notify()
        return True

    def tick(self, state: WorldState, tick: int) -> list[WorldEvent]:
        stopped = self._stop_paths(state, tick)
        dig = self._dig
        if dig is None:
            return stopped
        self._elapsed = max(0, min(DIG_TICKS, tick - dig.started))
        if self._elapsed < DIG_TICKS:
            if self._elapsed - self._reported >= STATE_EVERY_TICKS:
                self._reported = self._elapsed
                self._notify()
            return stopped
        self._dig = None
        try:
            material = self._validate(state, dig.x, dig.y, "dig")
            events = self._edit(tick, dig.x, dig.y, "dig", material)
        except VoxelRejected as exc:
            self._updates.append((dig.owner, {"error": str(exc)}))
            self._notify()
            return stopped
        self._pending[(dig.x, dig.y)] = ("dig", material)
        # Completion is published only when the event batch has committed.
        return [*events, *stopped]

    def _edit(self, tick: int, x: int, y: int, action: Action, material: str) -> list[WorldEvent]:
        height = self.height_at(x, y) + (-1 if action == "dig" else 1)
        gid = self._ground(x, y) if height == 1 else 0
        if height == 1 and gid <= 0:
            raise VoxelRejected("这处没有能落脚的土面。")
        edit = voxel_edited_event(tick, x=x, y=y, action=action)
        payload = VoxelEditedPayload.model_validate(
            {**edit.payload, "material_id": material, "height": height}
        )
        return [
            edit.model_copy(update={"payload": payload.model_dump(mode="json")}),
            material_moved_event(
                tick,
                transfer_id=f"voxel:{action}:{tick}:{x}:{y}",
                material_id=material,
                quantity=1,
                from_ref="world:tile" if action == "dig" else STOCK,
                to_ref=STOCK if action == "dig" else "world:tile",
                reason="dig_yield" if action == "dig" else "place_consumed",
            ),
            tile_changed_event(tick, x, y, gid),
        ]

    def _stop_paths(self, state: WorldState, tick: int) -> list[WorldEvent]:
        blocked = tuple(
            sorted(pos for pos, (action, _) in self._pending.items() if action == "place")
        )
        if not blocked:
            return []
        events = []
        for entity_id in sorted(state.entities):
            entity = state.entities[entity_id]
            if any(pos in entity.path for pos in blocked):
                events.append(move_event(tick, entity_id, entity.pos, entity.pos, (entity.pos,)))
        return events

    def _material(self, payload: Mapping[str, Any]) -> bool:
        material = payload.get("material_id")
        if not isinstance(material, str) or material not in self._inventory:
            return False
        if payload.get("from_ref") != STOCK and payload.get("to_ref") != STOCK:
            return False
        quantity = float(payload["quantity"])
        if not quantity.is_integer():
            raise ValueError("material stock must contain whole units")
        change = (
            int(payload.get("to_ref") == STOCK) - int(payload.get("from_ref") == STOCK)
        ) * int(quantity)
        balance = self._inventory[material] + change
        if balance < 0:
            raise ValueError("negative material stock")
        self._inventory[material] = balance
        return change != 0

    def observe(self, events: Sequence[WorldEvent]) -> None:
        changed = False
        for event in events:
            if event.event_type is EventKind.MATERIAL_MOVED:
                changed = self._material(event.payload) or changed
            elif event.event_type is EventKind.VOXEL_EDITED:
                edit = VoxelEditedPayload.model_validate(event.payload)
                self._observe_height(edit)
                pos = (edit.x, edit.y)
                pending = self._pending.pop(pos, None)
                if pending is not None and pending[0] == "place":
                    self._reserved[pending[1]] -= 1
                changed = True
        if changed:
            self._notify()

    def restore_from_events(self, events: Iterable[Mapping[str, Any]]) -> None:
        self.reset()
        for event in events:
            if str(event["event_type"]) == EventKind.MATERIAL_MOVED.value:
                self._material(event["payload"])
            elif str(event["event_type"]) == EventKind.VOXEL_EDITED.value:
                self._observe_height(VoxelEditedPayload.model_validate(event["payload"]))
        self._notify()
