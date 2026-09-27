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

**M5-D2 追加（裁 11 采，M5 硬前置）**：`TestVecBranchIsolation` 类补向量召回面的
**分支隔离**钉子。A4 收口时 `vector.py` 全文无 `branch_id`（`rg` 零命中），
`vec_candidate_ids` 的召回 SQL 只 JOIN + 过滤治理列，**没有 `m.branch_id = ?`**
——单世界线下是潜伏问题，**读档=分叉（§12）一旦存在，NPC 就会召回父分支/已弃分支
的记忆**（T1 信息边界破口 + 出戏：NPC 记得本时间线里没发生的事）。本类锁死：
1. 跨分支不召回（父分支/已弃分支天然不可见，隔离靠 branch_id 等值，**不 JOIN
   branches 表**——那是给热路径加跨表 JOIN，status 语义由 driver 的 active 分支
   概念保证）；2. 未知分支 → 空候选（fail-closed，**禁回落全库**）；
3. 分支参数必填、keyword-only、无默认（fail-closed 签名守卫：fork 后新分支不是
   'main'，默认值会静默读到错分支）；4. 过滤必须**进召回句**（同 R2 纪律：不得挪到
   Python 侧后过滤）；5. 过滤后候选不足 `top_k` 时按 over-fetch 补足，候选数恒 ≤ `top_k`。
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
    branch_id: str = "main",
    superseded_by: str | None = None,
    invalid_reason: str | None = None,
) -> int:
    """插一条 npc_memories 行，返回其自增 id（= vec rowid 关联键）。

    branch_id：F3 分支隔离钉子用（M5-D2 追加）；默认 'main' 与既有治理钉子同侧。
    """
    cur = conn.execute(
        "INSERT INTO npc_memories"
        " (entry_id, npc_id, branch_id, content, superseded_by, invalid_reason)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (entry_id, "chenmo", branch_id, "内容", superseded_by, invalid_reason),
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

            source = VecCandidateSource(conn, branch_id="main")
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

            source = VecCandidateSource(conn, branch_id="main")
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
            source = VecCandidateSource(conn, branch_id="main")
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
                branch_id="main",
            )
            assert ids == [live]
            assert old not in ids and bad not in ids
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# M5-D2 / 裁 11：向量召回面的分支隔离（F3，M5 硬前置）
# ---------------------------------------------------------------------------


def _insert_vec_distinct(conn: sqlite3.Connection, rowid: int, dim: int = 8, axis: int = 0) -> None:
    """插一条向量，方向由 axis 指定（便于制造「另一分支更近」的饥饿场景）。"""
    vals = [0.0] * dim
    vals[axis] = 1.0
    conn.execute(
        f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
        (rowid, _blob(vals)),
    )


@pytest.mark.t1
class TestVecBranchIsolation:
    """F3：向量候选必须分支内（跨分支/父分支/已弃分支不可见，fail-closed）。"""

    def test_candidates_exclude_other_branch(self) -> None:
        """同 npc_id、同向量、两个分支 → 候选只含本分支（隔离对称于 iter_visible）。"""
        from sim.core.persistence.vector import VecCandidateSource

        conn = _vec_conn()
        try:
            mine = _insert_memory(conn, "e-mine", branch_id="main")
            theirs = _insert_memory(conn, "e-theirs", branch_id="fork-a")
            for rid in (mine, theirs):
                _insert_vec(conn, rid)
            conn.commit()

            q = _blob([1.0, 0, 0, 0, 0, 0, 0, 0])
            got = {c.id for c in VecCandidateSource(conn, branch_id="main").candidates(q, 10)}
            assert got == {mine}, "另一分支的记忆泄漏进向量候选（F3）"
            got_fork = {
                c.id for c in VecCandidateSource(conn, branch_id="fork-a").candidates(q, 10)
            }
            assert got_fork == {theirs}, "分支隔离不对称：fork 侧看不到自己的行"
        finally:
            conn.close()

    def test_parent_branch_invisible_after_fork(self) -> None:
        """读档=分叉后，父分支（已弃）记忆对新分支不可见。

        口径：隔离靠 branch_id 等值，**不 JOIN branches 表**（不给热路径加跨表
        JOIN）。已弃分支天然不可见——新分支的 branch_id 是新 id，与父分支不相等。
        """
        from sim.core.persistence.vector import VecCandidateSource

        conn = _vec_conn()
        try:
            parent = _insert_memory(conn, "e-parent", branch_id="main")
            child = _insert_memory(conn, "e-child", branch_id="fork-b")
            for rid in (parent, child):
                _insert_vec(conn, rid)
            conn.commit()

            q = _blob([1.0, 0, 0, 0, 0, 0, 0, 0])
            assert {
                c.id for c in VecCandidateSource(conn, branch_id="fork-b").candidates(q, 10)
            } == {child}, "新分支召回了父分支/已弃分支的记忆（历史泄漏进新时间线）"
        finally:
            conn.close()

    def test_unknown_branch_returns_empty_fail_closed(self) -> None:
        """未知分支 → 空候选；**禁回落全库**（回落即泄漏）。"""
        from sim.core.persistence.vector import vec_candidate_ids

        conn = _vec_conn()
        try:
            rid = _insert_memory(conn, "e-live")
            _insert_vec(conn, rid)
            conn.commit()
            assert (
                vec_candidate_ids(conn, _blob([1.0, 0, 0, 0, 0, 0, 0, 0]), 10, branch_id="ghost")
                == []
            )
        finally:
            conn.close()

    def test_branch_filter_does_not_starve_local_candidates(self) -> None:
        """另一分支占据最近邻时，本分支候选仍按 top_k 补足（over-fetch），且恒 ≤ top_k。"""
        from sim.core.persistence.vector import vec_candidate_ids

        conn = _vec_conn()
        try:
            # 8 条他分支的「极近」向量 + 3 条本分支的「较远」向量。
            for i in range(8):
                _insert_vec_distinct(
                    conn, _insert_memory(conn, f"e-o{i}", branch_id="other"), axis=0
                )
            mine = [_insert_memory(conn, f"e-m{i}", branch_id="main") for i in range(3)]
            for rid in mine:
                _insert_vec_distinct(conn, rid, axis=7)
            conn.commit()

            ids = vec_candidate_ids(conn, _blob([1.0, 0, 0, 0, 0, 0, 0, 0]), 3, branch_id="main")
            assert len(ids) == 3, f"本分支候选被过取饿死了：{ids}"
            assert set(ids) == set(mine)
            assert all(i in mine for i in ids)
        finally:
            conn.close()

    def test_recall_sql_carries_branch_predicate(self) -> None:
        """形状钉：分支过滤必须在**召回句内**（同 R2 纪律，禁 Python 侧后过滤）。"""
        import inspect

        from sim.core.persistence.vector import vec_candidate_ids

        src = inspect.getsource(vec_candidate_ids)
        assert "m.branch_id = ?" in src, "召回 SQL 未携带 m.branch_id = ?（F3 未落或被挪走）"

    def test_branch_param_required_keyword_only(self) -> None:
        """签名守卫：branch_id 必填 + keyword-only + 无默认（fail-closed）。"""
        import inspect

        from sim.core.persistence.vector import VecCandidateSource, vec_candidate_ids

        for func in (vec_candidate_ids, VecCandidateSource.__init__):
            param = inspect.signature(func).parameters["branch_id"]
            assert param.kind is inspect.Parameter.KEYWORD_ONLY, (
                f"{func.__qualname__}: branch_id 非 keyword-only"
            )
            assert param.default is inspect.Parameter.empty, (
                f"{func.__qualname__}: branch_id 有默认值——fork 后新分支不是 'main'，"
                "默认值会静默读到错分支（必须 fail-closed）"
            )
