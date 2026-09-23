"""sqlite-vec 向量索引（npc_memory_vec）— schema.md §6。

设计说明：
- ``npc_memory_vec`` 是 sqlite-vec 的 **vec0 虚拟表**，维度在 M3 embedding model
  选定后才锁定（见 schema.md §6 注：384 或 768）。docs/data/migration.md 明确
  虚拟表 DDL 在 Alembic 范围之外（需先 ``LOAD EXTENSION``）——故本模块提供
  显式初始化函数，由 M3 接线时调用，不放进 0002 迁移。
- 维度通过参数/常量传入；本 M1 阶段只提供脚手架 + 建表能力与测试。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Final, Protocol, runtime_checkable

from sim.llm.memory_scan import MemoryEntry, make_entry

# embedding model 锁定后改这里（schema.md §6：384 或 768）
DEFAULT_EMBEDDING_DIM: Final[int] = 384

VEC_TABLE: Final[str] = "npc_memory_vec"


def load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """在同步 sqlite3 连接上加载 sqlite-vec 扩展。

    需要连接允许扩展加载（``enable_load_extension(True)``）。
    """
    import sqlite_vec

    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)


def create_memory_vec_table(conn: sqlite3.Connection, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
    """创建 ``npc_memory_vec`` vec0 虚拟表（幂等：IF NOT EXISTS）。

    Args:
        conn: 已加载 sqlite-vec 扩展的同步连接。
        dim: embedding 维度（固定，sqlite-vec 要求）。
    """
    conn.enable_load_extension(True)
    try:
        import sqlite_vec

        sqlite_vec.load(conn)
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_TABLE} USING vec0(embedding FLOAT32[{dim}])"
        )
        conn.commit()
    finally:
        conn.enable_load_extension(False)


def memory_vec_exists(conn: sqlite3.Connection) -> bool:
    """检查 npc_memory_vec 虚拟表是否已存在。"""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (VEC_TABLE,),
    ).fetchone()
    return row is not None


def memory_vec_rowid(npc_memory_id: int) -> int:
    """npc_memories.id → npc_memory_vec.rowid 关联键（schema.md §6）。

    D04 约定：npc_memories 与 memory_vec 的**业务关联键**为
    ``(event_seq, entry_id)``（entry_id = npc_memories.entry_id，稳定句柄）；
    vec0 表只存向量，其 ``rowid`` 直接取 ``npc_memories.id`` 自增主键。
    嵌入生成 M3 再做，本函数固定关联语义，避免返工。
    """
    return npc_memory_id


# ---------------------------------------------------------------------------
# M3-A3：VectorIndex 接口草案（裁 3 / V1：sqlite-vec 主 + numpy 余弦降级）
# ---------------------------------------------------------------------------
#
# 边界（m3-plan 批次 A3 起步，A4 全量实现）：
# - 本批只**立接口 + 两实现骨架**，治理过滤 JOIN 留给 A4（R2 钉子）。
# - 接口返回 ``rowid``（= npc_memories.id，见 memory_vec_rowid），
#   候选源再据此取回 ``MemoryEntry``（形状与 M2 iter_visible 一致，§18 硬边界）。
# - 两实现同接口，M3 按 sqlite-vec 扩展可用性切换（A 主 / B 降级）。

#: 一次向量检索的单条命中：(rowid, distance)。距离越小越近。
VectorHit = tuple[int, float]

#: 向量入参：float64/32 序列，或已打包的 little-endian float32 BLOB（sqlite-vec 直存形）。
VectorInput = Sequence[float] | bytes


def _to_blob(vector: VectorInput) -> bytes:
    """归一化为 sqlite-vec 的 FLOAT32 BLOB（bytes 直通，float 序列则打包）。"""
    import struct

    if isinstance(vector, (bytes, bytearray)):
        return bytes(vector)
    return struct.pack(f"{len(vector)}f", *vector)


def _to_floats(vector: VectorInput, dim: int) -> list[float]:
    """归一化为 float 列表（供 numpy 降级实现）。"""
    import struct

    if isinstance(vector, (bytes, bytearray)):
        return list(struct.unpack(f"{len(vector) // 4}f", bytes(vector)))
    return [float(v) for v in vector]


@runtime_checkable
class VectorIndex(Protocol):
    """向量索引接口（候选生成器的后端）。

    M3 候选源（`VecCandidateSource`）只依赖本协议；A(sqite-vec)/B(numpy)
    两实现可互换（裁 3 / V1）。**纯读 + 确定性**：同距离按 rowid 稳定排序。
    """

    def upsert(self, rowid: int, vector: VectorInput) -> None:
        """写入/覆盖一条向量（rowid = npc_memories.id）。"""
        ...

    def remove(self, rowid: int) -> None:
        """删除一条向量（npc_memories 行删除/治理级联时）。"""
        ...

    def knn(self, query_vector: VectorInput, top_k: int) -> list[VectorHit]:
        """返回最近邻 ``top_k`` 条 (rowid, distance)；距离升序、同距按 rowid 稳定。"""
        ...


class SqliteVecIndex:
    """方案 A（主）：sqlite-vec ``vec0`` 虚拟表后端。

    依赖 ``npc_memory_vec`` 已建（``create_memory_vec_table``）+ 连接已加载扩展。
    本批为**骨架**：knn 走 vec0 ``MATCH``；治理过滤由候选源层 A4 接入。
    """

    def __init__(self, conn: sqlite3.Connection, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self._conn = conn
        self._dim = dim

    def upsert(self, rowid: int, vector: VectorInput) -> None:
        conn = self._conn
        conn.execute(f"DELETE FROM {VEC_TABLE} WHERE rowid = ?", (memory_vec_rowid(rowid),))
        conn.execute(
            f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
            (memory_vec_rowid(rowid), _to_blob(vector)),
        )

    def remove(self, rowid: int) -> None:
        self._conn.execute(f"DELETE FROM {VEC_TABLE} WHERE rowid = ?", (memory_vec_rowid(rowid),))

    def knn(self, query_vector: VectorInput, top_k: int) -> list[VectorHit]:
        rows = self._conn.execute(
            f"SELECT rowid, distance FROM {VEC_TABLE}"
            " WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (_to_blob(query_vector), top_k),
        ).fetchall()
        # 同距按 rowid 稳定排序（确定性 C5，与 M2 打分 tiebreak 同款）。
        hits = [(int(r[0]), float(r[1])) for r in rows]
        hits.sort(key=lambda h: (h[1], h[0]))
        return hits


class NumpyCosineIndex:
    """方案 B（降级）：内存 numpy 余弦暴力检索（同 `VectorIndex` 接口）。

    用于 sqlite-vec 扩展在 aiosqlite/async 下加载失败时的降级路径（V1）。
    本批为**骨架**（内存 dict + 余弦 top-k）。
    """

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self._dim = dim
        self._vectors: dict[int, list[float]] = {}

    def upsert(self, rowid: int, vector: VectorInput) -> None:
        self._vectors[memory_vec_rowid(rowid)] = _to_floats(vector, self._dim)

    def remove(self, rowid: int) -> None:
        self._vectors.pop(memory_vec_rowid(rowid), None)

    def knn(self, query_vector: VectorInput, top_k: int) -> list[VectorHit]:
        import numpy as np

        q = np.asarray(_to_floats(query_vector, self._dim), dtype=np.float64)
        qn = float(np.linalg.norm(q))
        if qn == 0.0 or not self._vectors:
            return []
        sims: list[tuple[int, float]] = []
        for rowid, vec in self._vectors.items():
            v = np.asarray(vec, dtype=np.float64)
            vn = float(np.linalg.norm(v))
            cos = 0.0 if vn == 0.0 else float(np.dot(q, v) / (qn * vn))
            sims.append((rowid, 1.0 - cos))  # 距离 = 1 - 余弦相似度（越小越近）
        # 距离升序、同距按 rowid 稳定（确定性 C5）。
        sims.sort(key=lambda h: (h[1], h[0]))
        return sims[:top_k]


def vec_candidate_ids(conn: sqlite3.Connection, query_vector: VectorInput, top_k: int) -> list[int]:
    """向量召回 → 候选 rowid 列表（= npc_memories.id），按距离升序稳定。

    **R2/V6 召回端红线（M3-A4 收口）**：k-NN 结果在 SQL 内 ``JOIN npc_memories``
    并按治理列过滤——``superseded_by IS NULL AND invalid_reason IS NULL``
    （与 ``iter_visible`` 同口径：任一非空即不可见）。过滤发生在**进打分缝之前**
    （候选集已收缩，非召回后再放行），治理条目对向量候选的占比恒为 0。

    即时性：治理列 UPDATE 落库（同事务）后，同一连接直读、无缓存层 → 候选视图
    立即不含旧条目（无窗口期，R2 契约 3）。
    """
    rows = conn.execute(
        f"SELECT v.rowid, v.distance FROM {VEC_TABLE} v"
        " JOIN npc_memories m ON m.id = v.rowid"
        " WHERE v.embedding MATCH ? AND k = ?"
        " AND m.superseded_by IS NULL AND m.invalid_reason IS NULL"
        " ORDER BY v.distance",
        (_to_blob(query_vector), top_k),
    ).fetchall()
    # 同距按 rowid 稳定排序（确定性 C5，与 M2 打分 tiebreak 同款）。
    hits = [(int(r[0]), float(r[1])) for r in rows]
    hits.sort(key=lambda h: (h[1], h[0]))
    return [rowid for rowid, _ in hits]


def _rowid_to_entry(conn: sqlite3.Connection, rowid: int) -> MemoryEntry | None:
    """按 vec rowid 取回 ``MemoryEntry``。

    R2 契约（codex 钉子）以 **vec rowid = npc_memories.id** 为候选身份
    （见 ``memory_vec_rowid`` 与 R2 钉子 ``_insert_memory`` 的返回值语义），
    故候选的 ``MemoryEntry.id`` 即该 rowid。其余字段取 ``npc_memories`` 行。
    治理过滤已在 ``vec_candidate_ids`` 的召回 SQL 内完成（R2/V6）；本函数只按键
    取回**已通过治理**的行。
    """
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM npc_memories WHERE id = ?", (rowid,)).fetchone()
    if row is None:
        return None
    return make_entry(
        entry_id=rowid,  # type: ignore[arg-type]  # vec 候选身份 = rowid（R2 契约）
        npc_id=row["npc_id"],
        content=row["content"],
        source=row["source"],
        event_seq=row["event_seq"],
        importance=row["importance"],
        emotion_tag=row["emotion_tag"],
        superseded_by=row["superseded_by"],
        invalid_reason=row["invalid_reason"],
    )


class VecCandidateSource:
    """候选源（M3-A3 形状）：向量 k-NN → ``MemoryEntry``（与 M2 iter_visible 同形）。

    接口（vec-preplan §5）：``candidates(query_vector, top_k) -> list[MemoryEntry]``，
    供 `retrieve` 的候选来源替换；**打分链一字不改**（§18 硬边界）。

    **R2/V6 召回端红线（M3-A4 收口）**：候选集由 ``vec_candidate_ids`` 在召回 SQL
    内 JOIN+过滤治理列得到——治理条目（``superseded_by``/``invalid_reason`` 任一
    非空）永不进候选，占比恒为 0。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def candidates(self, query_vector: VectorInput, top_k: int) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for rowid in vec_candidate_ids(self._conn, query_vector, top_k):
            entry = _rowid_to_entry(self._conn, rowid)
            if entry is not None:
                entries.append(entry)
        return entries
