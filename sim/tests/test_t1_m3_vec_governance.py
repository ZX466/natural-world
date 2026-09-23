"""T1 RED 钉子 ①— R2 向量召回治理过滤缝（M3-S1，docs/security/m3-preplan.md §1/R2）。

**RED 状态（本文件按 M3-S1 任务书零实现提交，预期失败即验收）**：

- 裁 3 / V6 裁决（2026-09-23）：vec 候选必须 JOIN npc_memories 过滤治理列——
  「召回端红线」。本文件是它的验收契约（A4 实现后转绿）。
- 现状：`vector.py` 无任何治理概念（grep 治理/supersede 零命中），
  vec0 虚拟表只有 (rowid, embedding)，候选生成器（A4/批次 A）尚未存在。

契约锁定（self-unknown.md §4 + memory-scan.md S5 的向量面延伸）：

1. **候选视图红线**：向量召回产生的候选集，被治理条目
   （superseded_by / invalid_reason 任一非空）必须为 0——与 iter_visible 同口径；
2. **JOIN 语义**：vec rowid → npc_memories.id 关联取回 MemoryEntry 时，
   治理过滤必须发生在「进打分缝之前」（不能召回后再放行）；
3. **级联时机**：supersede 落库（同事务 UPDATE 治理列）之后，
   同一数据的向量候选视图立即不包含旧条目（无窗口期）；
4. **shape 不变**：过滤只影响候选集合，不改 MemoryEntry / Scorer / retrieve 形状
   （vec-preplan §18 硬边界：打分链一字不改）。

失败指纹（实现前运行）：
- TestVecGovernanceContract::test_candidates_view_excludes_governed_entries
  → ImportError: VecCandidateSource 不存在（候选源未实现，pyright 同报）；
- test_supersede_cascade_immediate
  → 同上（无候选源可驱动）；
- test_query_join_filters_governed_rows_sql
  → OperationalError/AssertionError: SQL 无治理 JOIN（现 vec 表无治理列可查）。

实现归属：opencode A4（批次 A，前置 A3 VectorIndex 接口）。
CI：test_t1_m3_* 前缀随 `-m "not bench"` 全量跑（m3-plan §6 钉子清单口径）。
"""

from __future__ import annotations

import sqlite3
import struct

import pytest

from sim.core.persistence.vector import (
    VEC_TABLE,
    create_memory_vec_table,
    memory_vec_rowid,
)

# ---------------------------------------------------------------------------
# 夹具：最小 npc_memories 形状（与 SqlMemoryStore 落库列一致；治理列齐备）
# 钉子不重复建全套 alembic——候选源的治理过滤语义只依赖这三列：
# id（= vec rowid 关联键）/ superseded_by / invalid_reason。
# ---------------------------------------------------------------------------


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE npc_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL,
            npc_id TEXT NOT NULL,
            event_seq INTEGER,
            branch_id TEXT NOT NULL DEFAULT 'main',
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'event',
            importance REAL NOT NULL DEFAULT 0.5,
            emotion_tag TEXT,
            distortion REAL NOT NULL DEFAULT 0.0,
            embedding BLOB,
            created_at_tick INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL DEFAULT 0.0,
            last_accessed_tick INTEGER,
            superseded_by TEXT,
            invalid_reason TEXT
        );
        """
    )
    return conn


def _blob(vals: list[float]) -> bytes:
    return struct.pack(f"{len(vals)}f", *vals)


def _vec_conn(dim: int = 8) -> sqlite3.Connection:
    conn = _memory_conn()
    create_memory_vec_table(conn, dim=dim)
    return conn


def _insert_memory(
    conn: sqlite3.Connection,
    entry_id: str,
    *,
    superseded_by: str | None = None,
    invalid_reason: str | None = None,
) -> int:
    """插一条 npc_memories 行，返回其自增 id（= vec rowid 关联键）。"""
    cur = conn.execute(
        "INSERT INTO npc_memories (entry_id, npc_id, content, superseded_by, invalid_reason)"
        " VALUES (?, ?, ?, ?, ?)",
        (entry_id, "chenmo", "内容", superseded_by, invalid_reason),
    )
    rowid = cur.lastrowid
    assert rowid is not None
    return int(rowid)


def _insert_vec(conn: sqlite3.Connection, rowid: int, dim: int = 8) -> None:
    vals = [0.0] * dim
    vals[0] = 1.0
    conn.execute(
        f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
        (rowid, _blob(vals)),
    )


# ---------------------------------------------------------------------------
# 契约 1+3：候选视图红线 + 级联即时性
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestVecGovernanceContract:
    """R2/V6 召回端红线：治理条目永不进向量候选（RED：候选源未实现）。"""

    def test_candidates_view_excludes_governed_entries(self) -> None:
        """superseded_by / invalid_reason 任一非空 → 不得出现在向量候选。"""
        from sim.core.persistence.vector import VecCandidateSource

        conn = _vec_conn()
        try:
            live = _insert_memory(conn, "e-live")
            superseded = _insert_memory(conn, "e-old", superseded_by="e-new")
            invalidated = _insert_memory(conn, "e-bad", invalid_reason="banned_word")
            for rid in (live, superseded, invalidated):
                _insert_vec(conn, rid)
            conn.commit()

            source = VecCandidateSource(conn)
            candidates = source.candidates(query_vector=_blob([1.0, 0, 0, 0, 0, 0, 0, 0]), top_k=10)
            got_ids = {c.id for c in candidates}
            assert superseded not in got_ids, "superseded 条目泄漏进向量候选"
            assert invalidated not in got_ids, "invalidated 条目泄漏进向量候选"
            assert got_ids == {live}
        finally:
            conn.close()

    def test_supersede_cascade_immediate(self) -> None:
        """治理列 UPDATE 同事务落库后，候选视图立即不含旧条目（无窗口期）。"""
        from sim.core.persistence.vector import VecCandidateSource

        conn = _vec_conn()
        try:
            old = _insert_memory(conn, "e-old")
            new = _insert_memory(conn, "e-new")
            _insert_vec(conn, old)
            _insert_vec(conn, new)
            conn.commit()

            source = VecCandidateSource(conn)
            q = _blob([1.0, 0, 0, 0, 0, 0, 0, 0])
            assert {c.id for c in source.candidates(query_vector=q, top_k=10)} == {old, new}

            # supersede（与 SqlMemoryStore.supersede 同款 UPDATE，只动治理列）
            conn.execute(
                "UPDATE npc_memories SET superseded_by = ?, invalid_reason = ? WHERE entry_id = ?",
                ("e-new", "banned_word", "e-old"),
            )
            conn.commit()

            assert {c.id for c in source.candidates(query_vector=q, top_k=10)} == {new}, (
                "supersede 落库后旧条目仍在向量候选（治理缝，R2）"
            )
        finally:
            conn.close()

    def test_shape_unchanged_entries_are_memory_entry(self) -> None:
        """候选产出 = MemoryEntry（打分缝形状不变，vec-preplan §18）。"""
        from sim.core.persistence.vector import VecCandidateSource
        from sim.llm.memory_scan import MemoryEntry

        conn = _vec_conn()
        try:
            rid = _insert_memory(conn, "e-live")
            _insert_vec(conn, rid)
            conn.commit()
            source = VecCandidateSource(conn)
            candidates = source.candidates(query_vector=_blob([1.0, 0, 0, 0, 0, 0, 0, 0]), top_k=10)
            assert candidates
            assert all(isinstance(c, MemoryEntry) for c in candidates)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 契约 2：JOIN 语义（召回 SQL 本身必须携带治理过滤）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestVecQueryJoinSemantics:
    """治理过滤必须在召回 SQL/查询层（A4 实现后，此处 SQL 形即契约）。"""

    def test_rowid_keying_contract(self) -> None:
        """vec rowid = npc_memories.id（vector.py 已冻结的关联语义，防止漂移）。"""
        assert memory_vec_rowid(42) == 42

    def test_query_join_filters_governed_rows_sql(self) -> None:
        """召回 SQL 必须 JOIN npc_memories 且过滤治理列（V6 裁决的 SQL 形）。"""
        conn = _vec_conn()
        try:
            live = _insert_memory(conn, "e-live")
            old = _insert_memory(conn, "e-old", superseded_by="e-live")
            bad = _insert_memory(conn, "e-bad", invalid_reason="manual_review")
            for rid in (live, old, bad):
                _insert_vec(conn, rid)
            conn.commit()

            # 契约 SQL：k-NN 命中的 rowid 必须再过治理 JOIN（此形进 A4 实现）。
            # 现状 npc_memory_vec 无治理可查 → 该查询形式在实现前不可用，
            # 这里直接断言「带治理过滤的召回语句」能产出正确候选集（RED：无实现）。
            from sim.core.persistence.vector import vec_candidate_ids

            ids = vec_candidate_ids(
                conn,
                query_vector=_blob([1.0, 0, 0, 0, 0, 0, 0, 0]),
                top_k=10,
            )
            assert ids == [live]
            assert old not in ids and bad not in ids
        finally:
            conn.close()
