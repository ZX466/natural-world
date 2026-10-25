"""sqlite-vec 记忆候选与分支向量拷贝（schema.md §6）。

候选在 SQL 内按分支和治理状态过滤，再按距离、rowid 稳定排序。
vec0 虚拟表通过显式初始化函数创建，DDL 不属于 Alembic 迁移。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Final

from sim.llm.memory_scan import MemoryEntry, make_entry

# embedding model 锁定后改这里（schema.md §6：384 或 768）
DEFAULT_EMBEDDING_DIM: Final[int] = 384

VEC_TABLE: Final[str] = "npc_memory_vec"

#: 过滤召回的过取倍数（M5-D2 / F3）。
#:
#: ``k`` 是 vec0 在 JOIN/过滤**之前**的取回上限，故任何 JOIN 侧谓词（分支隔离
#: ``branch_id``、治理列）都会让最终候选少于 ``top_k``。单分支时语料不被复制，
#: 饥饿不明显；读档=分叉后语料按分叉数复制（本分支占比 ≈ 1/F），最近邻极易被他
#: 分支占满 → 候选为空。故按倍数过取后裁到 ``top_k``，产出条数恒 ≤ ``top_k``。
#:
#: 4 的取法：分叉数 F ≤ 4 时本分支占比 ≥ 25%，过取足以补满 ``top_k``；再大需要
#: per-branch 向量分区（vec metadata partition / 按分支建表），属 M5 后续件
#: （已登记为 M5-D2 偏离点，不在本刀范围）。性能侧由 pi 实测 over-fetch 的
#: 距离计算增量（``docs/perf/m5-time-scale-fork-budget.md`` 对账点 5）。
RECALL_OVERFETCH_FACTOR: Final[int] = 4


def create_memory_vec_table(conn: sqlite3.Connection, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
    """创建 ``npc_memory_vec`` vec0 虚拟表（幂等：IF NOT EXISTS）。

    Args:
        conn: 同步 sqlite3 连接；本函数负责加载扩展。
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


#: 向量入参：float64/32 序列，或已打包的 little-endian float32 BLOB（sqlite-vec 直存形）。
VectorInput = Sequence[float] | bytes


def _to_blob(vector: VectorInput) -> bytes:
    """归一化为 sqlite-vec 的 FLOAT32 BLOB（bytes 直通，float 序列则打包）。"""
    import struct

    if isinstance(vector, (bytes, bytearray)):
        return bytes(vector)
    return struct.pack(f"{len(vector)}f", *vector)


def clone_branch_vectors(
    conn: sqlite3.Connection,
    rowid_map: Mapping[int, int],
    *,
    chunk: int = 500,
) -> int:
    """按 rowid 映射**字节**拷贝 vec 行（读档 = 分叉的向量面，M5-D3-b / R-1）。

    V4 裁决：vec 表为准 → 拷贝的是**已有向量字节**，**零 LLM 调用**；重新 embed
    单次分叉就是上万次调用，属红线禁。父行在 vec 表里缺失（未 embed / 已删）时
    跳过——返回实拷条数，由调用方与 ``len(rowid_map)`` 比对决定是否报「待补齐」
    （召回降级为空，**不泄漏**：F3 的分支谓词把别的分支挡在外面）。

    分块（``chunk``）只为把 Python 侧内存压住：384 维 × 4B = 1536B/行，
    10k 行一批是 15MB 量级；``fetchall`` + ``executemany`` 每块两次往返。
    """
    pairs = list(rowid_map.items())
    copied = 0
    for start in range(0, len(pairs), max(chunk, 1)):
        batch = pairs[start : start + max(chunk, 1)]
        src_ids = [src for src, _dst in batch]
        placeholders = ",".join("?" * len(src_ids))
        rows = conn.execute(
            f"SELECT rowid, embedding FROM {VEC_TABLE} WHERE rowid IN ({placeholders})",
            src_ids,
        ).fetchall()
        if not rows:
            continue
        conn.executemany(
            f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
            [(int(rowid_map[int(r[0])]), r[1]) for r in rows],
        )
        copied += len(rows)
    conn.commit()
    return copied


def vec_candidate_ids(
    conn: sqlite3.Connection,
    query_vector: VectorInput,
    top_k: int,
    *,
    branch_id: str,
) -> list[int]:
    """向量召回 → 候选 rowid 列表（= npc_memories.id），按距离升序稳定、最多 ``top_k`` 条。

    **R2/V6 召回端红线（M3-A4 收口）**：k-NN 结果在 SQL 内 ``JOIN npc_memories``
    并按治理列过滤——``superseded_by IS NULL AND invalid_reason IS NULL``
    （与 ``iter_visible`` 同口径：任一非空即不可见）。过滤发生在**进打分缝之前**
    （候选集已收缩，非召回后再放行），治理条目对向量候选的占比恒为 0。

    即时性：治理列 UPDATE 落库（同事务）后，同一连接直读、无缓存层 → 候选视图
    立即不含旧条目（无窗口期，R2 契约 3）。

    **分支隔离红线（F3，M5-D2 / 裁 11，M5 硬前置）**：召回句再带
    ``m.branch_id = ?``——向量表 ``npc_memory_vec`` 本身无分支列（rowid 直接取
    ``npc_memories.id``），隔离只能由 JOIN 侧等值承担。A4 收口时此处**无分支谓词**
    （单世界线下潜伏）；读档=分叉（DESIGN §12）一旦存在，NPC 就会召回父分支/
    已弃分支的记忆（T1 信息边界破口 + 出戏：记得本时间线里没发生的事）。

    - **``branch_id`` 必填、keyword-only、无默认值**（fail-closed）：fork 后的新
      分支不是 ``DEFAULT_BRANCH_ID``，给默认值会让漏传的调用方静默读到错分支。
    - **不 JOIN ``branches`` 表**：status/abandoned 语义由 driver 的「当前活动
      分支」概念保证（读档=分叉会把旧分支标 abandoned，新分支的 id 与之不相等
      → 已弃分支天然不可见），不值得给召回热路径加一次跨表 JOIN。
    - **未知分支 → 空候选**，禁回落全库（回落即泄漏）。

    **过取（``RECALL_OVERFETCH_FACTOR``）**：`k` 是 vec0 在 JOIN/过滤**之前**的
    取回上限，过滤会使候选少于 ``top_k``。多分支下语料按分叉数复制（本分支占比
    ≈ 1/F），最近邻极易被他分支占满 → 候选饥饿。故按倍数过取再裁到 ``top_k``：
    分支与治理两类过滤共用同一过取系数，产出条数恒 ``≤ top_k``（打分缝形状不变，
    vec-preplan §18 硬边界）。

    即时性与过取的边界：过取只影响 vec0 的取回上限，不影响过滤位置——治理与分支
    谓词仍在同一句内（禁挪到 Python 侧后过滤，R2 纪律）。
    """
    rows = conn.execute(
        f"SELECT v.rowid, v.distance FROM {VEC_TABLE} v"
        " JOIN npc_memories m ON m.id = v.rowid"
        " WHERE v.embedding MATCH ? AND k = ?"
        " AND m.branch_id = ?"
        " AND m.superseded_by IS NULL AND m.invalid_reason IS NULL"
        " ORDER BY v.distance",
        (_to_blob(query_vector), top_k * RECALL_OVERFETCH_FACTOR, branch_id),
    ).fetchall()
    # 同距按 rowid 稳定排序（确定性 C5，与 M2 打分 tiebreak 同款）。
    hits = [(int(r[0]), float(r[1])) for r in rows]
    hits.sort(key=lambda h: (h[1], h[0]))
    return [rowid for rowid, _ in hits[:top_k]]


def _rowid_to_entry(conn: sqlite3.Connection, rowid: int) -> MemoryEntry | None:
    """按 vec rowid 取回 ``MemoryEntry``。

    R2 契约（codex 钉子）以 **vec rowid = npc_memories.id** 为候选身份
    （见 ``memory_vec_rowid`` 与 R2 钉子 ``_insert_memory`` 的返回值语义），
    故候选的 ``MemoryEntry.id`` 即该 rowid。其余字段取 ``npc_memories`` 行。
    治理过滤已在 ``vec_candidate_ids`` 的召回 SQL 内完成（R2/V6）；本函数只按键
    取回**已通过治理**的行。

    F3（M5-D2）：本查询**不再自带分支谓词**——rowid 来自 ``vec_candidate_ids``
    的召回句，已在 JOIN 侧按 ``m.branch_id`` 过滤过（分支过滤与治理过滤同处一句，
    禁拆到 Python 侧：M2-D2 教训「A4 后勿把过滤拆到 Python 侧」）。此处再加
    一次等值谓词属冗余，且会让人误以为「单查本函数也安全」——单查本函数是
    审计面（等价于 ``SqlMemoryStore.get`` 的跨分支可读语义），不是召回面。
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

    **分支隔离红线（F3，M5-D2 / 裁 11）**：``branch_id`` 必填——候选只来自本分支
    的记忆行，父分支/已弃分支天然不可见（与 ``iter_visible`` 的分支隔离对称）。
    缺省不给：fork 后新分支不是 ``DEFAULT_BRANCH_ID``，默认值会静默读错分支。
    """

    def __init__(self, conn: sqlite3.Connection, *, branch_id: str) -> None:
        self._conn = conn
        self._branch_id = branch_id

    def candidates(self, query_vector: VectorInput, top_k: int) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for rowid in vec_candidate_ids(self._conn, query_vector, top_k, branch_id=self._branch_id):
            entry = _rowid_to_entry(self._conn, rowid)
            if entry is not None:
                entries.append(entry)
        return entries
