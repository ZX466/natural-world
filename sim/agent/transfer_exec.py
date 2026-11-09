"""Validated take/give requests over the existing three-material inventory."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sim.agent.voxel_exec import _MATERIAL_LABELS
from sim.core.events import WorldEvent, material_moved_event
from sim.world.economy import MaterialLedger


class TransferRejected(ValueError):
    """Structured execution failure; never render raw model input."""


@dataclass(frozen=True)
class TransferRequest:
    material: str
    quantity: int


def parse_transfer_params(params: Mapping[str, str]) -> TransferRequest:
    if set(params) - {"item", "quantity"}:
        raise TransferRejected("unsupported_parameter")
    item = params.get("item")
    material = next(
        (key for key, label in _MATERIAL_LABELS.items() if item in (key, label, label[0])),
        None,
    )
    if material is None:
        raise TransferRejected("unknown_item")
    raw = params.get("quantity", "1")
    if not isinstance(raw, str) or re.fullmatch(r"[1-9][0-9]{0,5}", raw) is None:
        raise TransferRejected("invalid_quantity")
    return TransferRequest(material, int(raw))


def material_transfer_event(
    *,
    tick: int,
    action: Literal["take", "give"],
    actor_id: str,
    target_id: str,
    request: TransferRequest,
    ledger: MaterialLedger,
) -> WorldEvent:
    if actor_id == target_id:
        raise TransferRejected("same_owner")
    source, destination = (target_id, actor_id) if action == "take" else (actor_id, target_id)
    if ledger.balance_of(source, request.material) < request.quantity:
        raise TransferRejected("insufficient_stock")
    identity = (
        f"{tick}:{ledger.sequence}:{action}:{source}:{destination}:"
        f"{request.material}:{request.quantity}"
    )
    token = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return material_moved_event(
        tick,
        transfer_id=f"{action}-{token}",
        material_id=request.material,
        quantity=request.quantity,
        from_ref=f"npc:{source}",
        to_ref=f"npc:{destination}",
        reason=action,
    )
