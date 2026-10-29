"""Process-local voxel presentation projection; the event stream is authoritative."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from sim.core.events import EventKind, TileChangedPayload, VoxelEditedPayload, WorldEvent

_VOXEL_EDITS: dict[tuple[int, int], dict[str, Any]] = {}
_broadcast: dict[tuple[int, int], dict[str, Any]] = {}


def set_voxel_edit(x: int, y: int, action: str, gid: int, height: int) -> None:
    _VOXEL_EDITS[(x, y)] = {
        "x": x,
        "y": y,
        "action": action,
        "gid": gid if height == 1 else 0,
        "height": height,
    }


def reset_voxel_edits() -> None:
    _VOXEL_EDITS.clear()
    _broadcast.clear()


def apply_voxel_events(
    events: Sequence[WorldEvent],
    *,
    ground_gid: Callable[[int, int], int],
    height_of: Callable[[int, int], int],
) -> None:
    for event in events:
        if event.event_type is EventKind.VOXEL_EDITED:
            edit = VoxelEditedPayload.model_validate(event.payload)
            previous = _VOXEL_EDITS.get((edit.x, edit.y))
            height = edit.result_height(
                previous["height"] if previous is not None else height_of(edit.x, edit.y)
            )
            set_voxel_edit(
                edit.x,
                edit.y,
                edit.action,
                ground_gid(edit.x, edit.y) if height == 1 else 0,
                height,
            )
        elif event.event_type is EventKind.TILE_CHANGED:
            tile = TileChangedPayload.model_validate(event.payload)
            old = _VOXEL_EDITS.get((tile.x, tile.y))
            if old is not None:
                set_voxel_edit(tile.x, tile.y, old["action"], tile.tile_id, old["height"])


def restore_voxel_edits(
    rows: Iterable[Mapping[str, Any]],
    *,
    ground_gid: Callable[[int, int], int],
    height_of: Callable[[int, int], int],
) -> None:
    reset_voxel_edits()
    # read_branch_history already orders bounded ancestor prefixes before children;
    # branch-local seq values must never be globally sorted together here.
    for row in rows:
        kind = str(row["event_type"])
        if kind not in (EventKind.VOXEL_EDITED.value, EventKind.TILE_CHANGED.value):
            continue
        event = WorldEvent(
            tick=int(row["tick"]), event_type=EventKind(kind), payload=row["payload"]
        )
        apply_voxel_events([event], ground_gid=ground_gid, height_of=height_of)


def voxel_snapshot_rows() -> list[dict[str, Any]]:
    # Full snapshots must not consume another connection's pending delta.
    return [dict(_VOXEL_EDITS[pos]) for pos in sorted(_VOXEL_EDITS)]


def voxel_delta_rows() -> list[dict[str, Any]]:
    rows = [
        dict(_VOXEL_EDITS[pos])
        for pos in sorted(_VOXEL_EDITS)
        if _broadcast.get(pos) != _VOXEL_EDITS[pos]
    ]
    _broadcast.clear()
    _broadcast.update({pos: dict(row) for pos, row in _VOXEL_EDITS.items()})
    return rows
