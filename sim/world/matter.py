"""sim.world.matter — 物质熵增结算（M2-A1 §4；matter_state 表 = 事件流持久化投影）。

MatterLedger 是 tick 结算的内存账本（frozen 快照 + settle 产事件）；
落库经 opencode 的 NpcStore.flush_tick 投影（MATTER_* → matter_state UPSERT），
本模块不碰 SQL。结算在 tick 固定序末尾（§4.2；pi 对账提示 #2，C5 确定性）。

RNG 纪律（§4.1）：自然衰减**每 tick 一次批量 draw**（分桶），禁止逐实体 draw
（C5 预算内；与 cline weather 同款「先派生后抽签」思路——本模块用显式 seed
派生 Generator，调用序无关）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

import numpy as np

from sim.core.events import EventKind, WorldEvent, matter_event
from sim.core.rng import RngRegistry


@dataclass(frozen=True)
class MatterSnapshot:
    """单个物质对象的结算状态（frozen；变更走 replace）。"""

    matter_id: str
    integrity: float = 1.0  # 0..1（matter_state.integrity 同义，投影折算）
    decay_rate: float = 0.0  # 每 tick 衰减率（0=不衰减，如石墙）
    is_rubble: bool = False  # 塌毁终态（不可逆，schema §14）


@dataclass
class MatterLedger:
    """tick 结算账本：{matter_id: MatterSnapshot}。settle/damage/build 产事件。"""

    _items: dict[str, MatterSnapshot]

    def __init__(self) -> None:
        self._items = {}

    @classmethod
    def from_snapshots(cls, snapshots: Iterable[MatterSnapshot]) -> MatterLedger:
        """从一组快照构造账本（M3-C1/C2 读路径共用构造点）。

        快照路径（SELECT matter_state）与重放路径（事件折叠）都经此构造，
        保证两入口产出**逐位相等**的 `MatterLedger`（§19.3 一致性判据）。
        key 取 `snapshot.matter_id`（不重算，避免与折叠规则分叉）。
        """
        ledger = cls()
        for snap in snapshots:
            ledger._items[snap.matter_id] = snap
        return ledger

    def register(self, matter_id: str, *, integrity: float, decay_rate: float) -> None:
        if matter_id in self._items:
            msg = f"物质对象重复注册: {matter_id}"
            raise ValueError(msg)
        self._items[matter_id] = MatterSnapshot(
            matter_id=matter_id,
            integrity=float(np.clip(integrity, 0.0, 1.0)),
            decay_rate=max(0.0, decay_rate),
        )

    def state(self, matter_id: str) -> MatterSnapshot:
        return self._items[matter_id]

    def mark_rubble(self, matter_id: str) -> None:
        self._items[matter_id] = replace(self._items[matter_id], integrity=0.0, is_rubble=True)

    # -----------------------------------------------------------------------
    # 结算（tick 固定序末尾；产事件批次）
    # -----------------------------------------------------------------------

    def settle(self, tick: int, *, seed: int = 0) -> list[WorldEvent]:
        """自然衰减结算：产 DECAY/COLLAPSE 事件 + 账本更新。rubble 跳过。"""
        return settle_decay(self, tick=tick, seed=seed)

    def damage(self, matter_id: str, *, amount: float, tick: int) -> WorldEvent:
        """交互损伤（amount<0；integrity 夹到 0，归零即塌）。decay_rate -1=不变更。"""
        s = self._items[matter_id]
        new_integrity = float(np.clip(s.integrity + amount, 0.0, 1.0))
        event = matter_event(
            tick=tick,
            kind=EventKind.MATTER_DAMAGE,
            matter_id=matter_id,
            amount=amount,
            durability=new_integrity,
        )
        self._items[matter_id] = replace(s, integrity=new_integrity, is_rubble=new_integrity <= 0.0)
        return event

    def build(self, matter_id: str, *, amount: float, tick: int) -> WorldEvent:
        """建造/修复（amount>0；M4 承重前为简化版）。携带账本静态率（§17.2 方案 A）。"""
        s = self._items[matter_id]
        new_integrity = float(np.clip(s.integrity + amount, 0.0, 1.0))
        event = matter_event(
            tick=tick,
            kind=EventKind.MATTER_BUILD,
            matter_id=matter_id,
            amount=amount,
            durability=new_integrity,
            decay_rate=s.decay_rate,
        )
        self._items[matter_id] = replace(s, integrity=new_integrity)
        return event


def settle_decay(ledger: MatterLedger, *, tick: int, seed: int = 0) -> list[WorldEvent]:
    """批量自然衰减（模块级纯入口，测试可直接驱动）。

    RNG 分桶：显式 seed 派生一个 Generator，**一次**抽全部衰减抖动系数
    （不是逐实体 draw）；同 seed 恒同结果，调用序无关。
    """
    live = [m for m in ledger._items.values() if m.decay_rate > 0.0 and not m.is_rubble]
    if not live:
        return []
    # 抖动系数 0.5..1.5（每 tick 批量 draw 一组；对象按 matter_id 排序取系数——确定性）
    rng = np.random.default_rng(seed)
    jitter = rng.uniform(0.5, 1.5, size=len(live))

    events: list[WorldEvent] = []
    for m, j in zip(live, jitter, strict=True):
        drop = m.decay_rate * float(j)
        new_integrity = float(np.clip(m.integrity - drop, 0.0, 1.0))
        if new_integrity <= 0.0:
            ledger._items[m.matter_id] = replace(m, integrity=0.0, is_rubble=True)
            events.append(
                matter_event(
                    tick=tick,
                    kind=EventKind.MATTER_COLLAPSE,
                    matter_id=m.matter_id,
                    amount=-m.integrity,
                    durability=0.0,
                    decay_rate=m.decay_rate,
                    note="耐久归零坍塌",
                )
            )
        else:
            ledger._items[m.matter_id] = replace(m, integrity=new_integrity)
            events.append(
                matter_event(
                    tick=tick,
                    kind=EventKind.MATTER_DECAY,
                    matter_id=m.matter_id,
                    amount=-drop,
                    durability=new_integrity,
                    decay_rate=m.decay_rate,
                )
            )
    return events


def wind_smell_decay_hint(rng: RngRegistry) -> float:
    """预留：嗅觉场衰减系数派生位（smell.py 接线用，本批不启用）。"""
    _ = rng
    return 0.99
