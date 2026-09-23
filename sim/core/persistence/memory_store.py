"""SQLite 记忆存储实现 — SqlMemoryStore（TASK-004 / D04）。

接口 MemoryStore 与内存实现 InMemoryStore 定义在 ``sim.llm.memory_scan``（与
Pipeline 同源，避免循环依赖）；本模块只提供落 ``npc_memories`` 表的 SQLite 实现。

对齐 docs/security/memory-scan.md：
- S5：supersede 只 UPDATE superseded_by/invalid_reason，永不改 content；
  iter_visible 过滤 superseded_by IS NOT NULL；get 审计可见。

依赖表：npc_memories（D03 0002 + 治理列 0003）。
"""

from __future__ import annotations

import sqlite3
import uuid

from sim.llm.memory_scan import MemoryEntry, MemorySource, make_entry

# 单世界线 M1 默认分支；多分支由调用方覆盖
DEFAULT_BRANCH_ID = "main"


class SqlMemoryStore:
    """落 ``npc_memories`` 表的记忆存储（同步 sqlite3，匹配同步 Pipeline 接口）。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        branch_id: str = DEFAULT_BRANCH_ID,
        created_at_tick: int = 0,
    ) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._branch_id = branch_id
        self._created_at_tick = created_at_tick

    @classmethod
    def from_path(
        cls,
        db_path: str,
        *,
        branch_id: str = DEFAULT_BRANCH_ID,
        created_at_tick: int = 0,
    ) -> SqlMemoryStore:
        return cls(sqlite3.connect(db_path), branch_id=branch_id, created_at_tick=created_at_tick)

    def persist(
        self,
        *,
        npc_id: str,
        content: str,
        source: MemorySource,
        event_seq: int | None,
        importance: float,
        emotion_tag: str | None,
    ) -> MemoryEntry:
        entry = make_entry(
            entry_id=uuid.uuid4().hex,
            npc_id=npc_id,
            content=content,
            source=source,
            event_seq=event_seq,
            importance=importance,
            emotion_tag=emotion_tag,
        )
        self._conn.execute(
            """
            INSERT INTO npc_memories
                (entry_id, npc_id, event_seq, branch_id, content, source,
                 importance, emotion_tag, distortion, created_at_tick, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?)
            """,
            (
                entry.id,
                npc_id,
                event_seq,
                self._branch_id,
                content,
                source,
                importance,
                emotion_tag,
                self._created_at_tick,
                self._created_at_tick,
            ),
        )
        self._conn.commit()
        return entry

    def get(self, entry_id: str) -> MemoryEntry:
        row = self._conn.execute(
            "SELECT * FROM npc_memories WHERE entry_id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise KeyError(entry_id)
        return self._row_to_entry(row)

    def supersede(self, old_id: str, new_id: str, reason: str) -> MemoryEntry:
        exists = self._conn.execute(
            "SELECT 1 FROM npc_memories WHERE entry_id = ?", (new_id,)
        ).fetchone()
        if exists is None:
            raise KeyError(f"replacement entry {new_id} does not exist")
        # 只更新治理列（S5：永不改 content）
        self._conn.execute(
            "UPDATE npc_memories SET superseded_by = ?, invalid_reason = ? WHERE entry_id = ?",
            (new_id, reason, old_id),
        )
        self._conn.commit()
        return self.get(old_id)

    def iter_visible(self, npc_id: str):
        rows = self._conn.execute(
            "SELECT * FROM npc_memories WHERE npc_id = ? AND superseded_by IS NULL "
            "AND invalid_reason IS NULL ORDER BY id",
            (npc_id,),
        ).fetchall()
        for row in rows:
            yield self._row_to_entry(row)

    def __len__(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM npc_memories").fetchone()[0])

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        return make_entry(
            entry_id=row["entry_id"],
            npc_id=row["npc_id"],
            content=row["content"],
            source=row["source"],
            event_seq=row["event_seq"],
            importance=row["importance"],
            emotion_tag=row["emotion_tag"],
            superseded_by=row["superseded_by"],
            invalid_reason=row["invalid_reason"],
        )
