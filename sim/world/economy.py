"""sim.world.economy — 最小经济：价目表、余额与材料事件投影。

余额是 runtime 内存态（禁第二 SQL 驱动）；**入账/出账结果**经 coin.grant
事件落流（C4：账单即真相，余额可由事件流重放重建）。定价确定性哈希浮动
（C5 无 RNG 流）。价目是戏内事实（可出站）；余额数值不出戏内文本。
材料持有量复用 material.moved 的既有守恒规则，不另建背包或 SQL 写路径。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sim.core.events import EventKind, MaterialMovedPayload, WorldEvent


@dataclass(frozen=True)
class Good:
    """一件货（id 是戏外主键；name 是戏内名）。"""

    id: str
    name: str
    price: int  # 基准价（文）


#: E3 最小三件（药铺语境）。
GOODS: tuple[Good, ...] = (
    Good(id="herb", name="草药", price=12),
    Good(id="salve", name="药膏", price=30),
    Good(id="meal", name="饭食", price=8),
    Good(id="wine", name="米酒", price=8),
)

_GOOD_INDEX: dict[str, Good] = {g.id: g for g in GOODS}


def name_index() -> dict[str, Good]:
    """只索引唯一货名；内部 ID 目录仍由 _GOOD_INDEX 持有。"""
    from collections import Counter

    counts = Counter(good.name for good in _GOOD_INDEX.values())
    return {good.name: good for good in _GOOD_INDEX.values() if counts[good.name] == 1}


def buy_price(good_id: str, *, tick: int, seed: int) -> int:
    """基准价 ±20% 确定性浮动（sha256(good:tick:seed)，C5 同输入同输出）。"""
    good = _GOOD_INDEX[good_id]
    digest = hashlib.sha256(f"price:{good_id}:{tick}:{seed}".encode()).digest()
    jitter = (int.from_bytes(digest[0:4], "big") % 41) - 20  # [-20, +20]%
    return max(1, good.price * (100 + jitter) // 100)


class CoinLedger:
    """{owner: 余额}；apply_grant 拒绝负余额（买不起=结构化拒绝，非异常）。"""

    def __init__(self) -> None:
        self._balances: dict[str, int] = {}

    def balance_of(self, owner: str) -> int:
        return self._balances.get(owner, 0)

    def reset(self) -> None:
        """清空全部余额（读档=分叉：账本是本分支投影，分叉即失效——review I2）。"""
        self._balances.clear()

    def restore_from_events(self, events: Iterable[Mapping[str, Any]]) -> None:
        """按谱系顺序重放账单；坏账拒绝恢复，不伪造余额或夹带旧分支金额。"""
        from sim.core.events import CoinGrantPayload

        restored = CoinLedger()
        for event in events:
            if event.get("event_type") != "coin.grant":
                continue
            payload = CoinGrantPayload.model_validate(event["payload"])
            if not restored.apply_grant(payload.owner_id, payload.delta, tick=int(event["tick"])):
                raise ValueError("recorded coin grant would produce a negative balance")
        self._balances = restored._balances

    def apply_grant(self, owner: str, delta: int, *, tick: int) -> bool:
        """入账/出账（tick 供将来记账扩展；当前纯余额）。False=余额不足拒绝。"""
        current = self._balances.get(owner, 0)
        if current + delta < 0:
            return False
        self._balances[owner] = current + delta
        return True


class MaterialLedger:
    """Applied material-event view of the existing material_balances projection.

    This cache never writes SQL or creates stock. Observe only events accepted by
    the event bus; restoring a branch replaces the entire view atomically.
    """

    def __init__(self) -> None:
        self._balances: dict[tuple[str, str], float] = {}
        self.sequence = 0

    def reset(self) -> None:
        self._balances = {}
        self.sequence = 0

    def balance_of(self, owner_id: str, material_id: str) -> float:
        return self._balances.get((f"npc:{owner_id}", material_id), 0.0)

    def _apply(self, payload: MaterialMovedPayload) -> None:
        # The runtime and SQL/replay projection use the same conservation rule.
        from sim.core.persistence.npc_store import NpcStoreError, fold_material_balance

        source = (payload.from_ref, payload.material_id)
        destination = (payload.to_ref, payload.material_id)
        try:
            debit, credit = fold_material_balance(
                self._balances.get(source, 0.0),
                self._balances.get(destination, 0.0),
                quantity=payload.quantity,
                from_ref=payload.from_ref,
            )
        except NpcStoreError as exc:
            raise ValueError("recorded material transfer would overdraw stock") from exc
        self._balances[source], self._balances[destination] = debit, credit
        self.sequence += 1

    def observe(self, event: WorldEvent) -> None:
        if event.event_type is EventKind.MATERIAL_MOVED:
            self._apply(MaterialMovedPayload.model_validate(event.payload))

    def restore_from_events(self, events: Iterable[Mapping[str, Any]]) -> None:
        restored = MaterialLedger()
        for event in events:
            if event.get("event_type") == EventKind.MATERIAL_MOVED.value:
                restored._apply(MaterialMovedPayload.model_validate(event["payload"]))
        self._balances, self.sequence = restored._balances, restored.sequence
