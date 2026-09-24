"""RelationshipStore — relationships 表 CRUD（M3 批次 B-B3；m3-plan §3）。

照 memory_store.py 惯例：纯同步 sqlite3、无缓存层、branch_id 隔离（构造注入）。
双向两行（A→B、B→A 各一行，DESIGN §7 有向不对称）；ensure_row 幂等；
adjust 单字段漂移 + clamp [0,1] + last_interaction 刷新。

R6 社会面边界：只按 (owner, other) 取单行——不提供跨人批量读接口
（关系面不出感知帧，社会未知轴）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sim.core.persistence.models import Relationship

#: 关系值域（trust/affection/fear/debt/face 统一 [0,1]）。
_REL_RANGE = (0.0, 1.0)

_ADJUSTABLE = ("trust", "affection", "fear", "debt", "face")


@dataclass(frozen=True)
class RelationshipView:
    """关系单行只读视图（models.Relationship 是 ORM 形；SQL 侧用轻量视图）。"""

    owner_id: str
    other_id: str
    trust: float
    affection: float
    fear: float
    debt: float
    face: float
    last_interaction: int


class RelationshipStore:
    def __init__(self, conn: sqlite3.Connection, *, branch_id: str, current_tick: int) -> None:
        self._conn = conn
        self._branch_id = branch_id
        self._current_tick = current_tick

    def get(self, owner_id: str, other_id: str) -> RelationshipView | None:
        row = self._conn.execute(
            "SELECT * FROM relationships WHERE branch_id=? AND owner_id=? AND other_id=?",
            (self._branch_id, owner_id, other_id),
        ).fetchone()
        if row is None:
            return None
        return RelationshipView(
            owner_id=row["owner_id"],
            other_id=row["other_id"],
            trust=row["trust"],
            affection=row["affection"],
            fear=row["fear"],
            debt=row["debt"],
            face=row["face"],
            last_interaction=row["last_interaction"],
        )

    def ensure_row(self, owner_id: str, other_id: str) -> None:
        """幂等建双向两行（默认值 0；已存在则不动）。"""
        import time

        now = time.time()
        for owner, other in ((owner_id, other_id), (other_id, owner_id)):
            self._conn.execute(
                """
                INSERT INTO relationships
                    (owner_id, other_id, trust, affection, fear, debt, face,
                     last_interaction, branch_id, created_at)
                VALUES (?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, ?, ?, ?)
                ON CONFLICT(branch_id, owner_id, other_id) DO NOTHING
                """,
                (owner, other, self._current_tick, self._branch_id, now),
            )
        self._conn.commit()

    def adjust(self, owner_id: str, other_id: str, **deltas: float) -> RelationshipView:
        """单字段漂移：delta 加到现值并 clamp [0,1]；last_interaction 刷到当前 tick。

        只接受 _ADJUSTABLE 字段（未知字段 KeyError——调用方拼错即暴露）。
        """
        unknown = set(deltas) - set(_ADJUSTABLE)
        if unknown:
            raise KeyError(f"不可调整的关系字段: {sorted(unknown)}")
        self.ensure_row(owner_id, other_id)
        current = self.get(owner_id, other_id)
        assert current is not None  # ensure_row 后必在
        sets: list[str] = []
        params: list[float | str] = []
        for field, delta in deltas.items():
            value = getattr(current, field) + delta
            value = min(_REL_RANGE[1], max(_REL_RANGE[0], value))
            sets.append(f"{field}=?")
            params.append(value)
        sets.append("last_interaction=?")
        params.append(float(self._current_tick))
        params.append(self._branch_id)
        params.append(owner_id)
        params.append(other_id)
        self._conn.execute(
            f"UPDATE relationships SET {', '.join(sets)} "
            "WHERE branch_id=? AND owner_id=? AND other_id=?",
            params,
        )
        self._conn.commit()
        updated = self.get(owner_id, other_id)
        assert updated is not None
        return updated


__all__ = ["Relationship", "RelationshipStore", "RelationshipView"]
