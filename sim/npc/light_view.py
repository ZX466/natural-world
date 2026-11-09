"""Pure physical light projection; no event, SQL or causal/attribution output."""

import hashlib
from collections.abc import Iterable
from typing import TypedDict

from sim.world.fire import FireCell


class LightRow(TypedDict):
    rtoken: str
    x: int
    y: int
    kind: str
    radius: float
    flicker: float


def fire_lights(cells: Iterable[FireCell]) -> list[LightRow]:
    """Expose only six existing light fields for each current physical cell."""
    rows: dict[str, LightRow] = {}
    for cell in cells:
        identity = f"{cell.fire_id}:{cell.x}:{cell.y}"
        token = "lt-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        rows[token] = LightRow(
            rtoken=token,
            x=cell.x,
            y=cell.y,
            kind="fire",
            radius=5.0,
            flicker=0.4,
        )
    return [rows[token] for token in sorted(rows)]
