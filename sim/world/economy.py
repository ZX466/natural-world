"""sim.world.economy — 最小经济（批次 E3）：价目表 + 进程内余额账本。

余额是 runtime 内存态（禁第二 SQL 驱动）；**入账/出账结果**经 coin.grant
事件落流（C4：账单即真相，余额可由事件流重放重建）。定价确定性哈希浮动
（C5 无 RNG 流）。价目是戏内事实（可出站）；余额数值不出戏内文本。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


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

    def apply_grant(self, owner: str, delta: int, *, tick: int) -> bool:
        """入账/出账（tick 供将来记账扩展；当前纯余额）。False=余额不足拒绝。"""
        current = self._balances.get(owner, 0)
        if current + delta < 0:
            return False
        self._balances[owner] = current + delta
        return True
