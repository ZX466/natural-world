"""检索缝基准（性能域，pi）— M3-P2 红线配套（m3-plan A5，裁 7 四红线落地）。
前置：opencode M3-D2（A4 治理 JOIN 收口）把 `VEC_CANDIDATE_PER_NPC_LIMIT_MS` 等
四常量随 `caddcdd` 落地；本文件按裁 7 数值在 bench 侧给四条断言用例。
口径：暖态中位（`harness.assert_median_threshold` + `warmup_rounds=1`），与感知/嗅觉红线同源。

四条红线（docs/perf/m3-retrieval-budget.md §1.3）：
  ① `VEC_CANDIDATE_PER_NPC_LIMIT_MS=0.30` —— 候选生成（vec k-NN）单次上限；
  ② `RETRIEVAL_SCORE_PER_NPC_LIMIT_MS=0.30` —— 打分链（20 候选 × 2 钩子）单次上限；
  ③ `RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS=2.00` —— **退化哨兵**：候选未收缩（600 全量
     × 2 钩子）上限。破限语义 = 向量缝断链（召回端治理 JOIN 失败 / 候选生成器没接上）
     → 查 A4 接线，**不是性能回退、不放宽红线**；
  ④ `RETRIEVAL_TICK_LIMIT_MS=12.0` —— 单 tick 检索总量（50 NPC 各一次）上限。破限先查
     **触发频次退化**（防呆红线：检索必须决策/prompt 驱动，禁每 tick 全量），不是单次成本。

A4 参考实现成本实测（本机，暖态中位；2026-09-23 M3-P2）：
  候选生成 0.233ms → ① 余量 **1.29x**（偏紧：80 参 IN 列表 + 过取开销）；
  打分链 20 候选 0.057ms → ② 余量 5.3x；600 全量 0.970ms → ③ 余量 2.06x；
  **④ 模型修正**：M3-P1 建模型按纯 numpy 0.05ms/NPC（估 50×0.05=2.5ms），实测 A4
  参考实现（cosine + 治理 JOIN 过取 + IN 列表）是 **0.29ms/NPC** → 50 NPC 一次全链
  **15.6ms = tick 预算 94%**，模型低估 6x。故 ④ 拆两个口径：
  - 常态（决策驱动 10 次/tick）≤ 12ms —— 实测 2.9ms，余量 4.1x；
  - 反模式（50 NPC 广播）≤ 16.6ms 天花板自证 —— 实测 15.6ms，94% 即防呆论据。
  更省形态（sqlite-vec 单 SQL JOIN，无 IN 列表）待 opencode A4 真实现落地后复核对账。
注：A4 的真实实现（vec-preplan §5 `VecCandidateSource.candidates`）在 opencode 域；
本文件用**同语义参考实现**（numpy 余弦 + JOIN 过取）卡红线的成本走势——M2 感知红线
同款「参考实现版」模式（真接线后按 opencode 实现复核对账，红线值不变）。
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
import structlog

from sim.agent.cognition import Beliefs, CognitionParams
from sim.llm.memory_scan import MemoryEntry, make_entry
from sim.npc.memory import MemoryQuery, retrieve

from .harness import assert_median_threshold
from .thresholds import (
    RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS,
    RETRIEVAL_SCORE_PER_NPC_LIMIT_MS,
    RETRIEVAL_TICK_LIMIT_MS,
    TICK_BUDGET_MS,
    VEC_CANDIDATE_PER_NPC_LIMIT_MS,
)

# 与 vec-preplan §3 规模对齐：每 NPC 可见 600 条、总 5 万条、d=384（见 §1 尾注的 d 说明）
N_VISIBLE = 600  # 每 NPC 可见条目（候选池规模）
N_NPC = 50  # L1 规模（tick 总量口径）
TOP_K = 20  # vec 候选数（A4 前的固定候选规模）
OVERFETCH = 4  # 治理 JOIN 过取倍率（JOIN 会吃掉被治理条目 → 过取补回）
EMBED_DIM = 4  # bench 用小维度（成本大头是 Python 侧；真实 384 见 §1 尾注说明）
_SEED = 7
_CONTENT = "酒馆里的争吵与雨，第 {} 条"

logger = structlog.get_logger(__name__)
_CANDIDATES_SQL = (
    "SELECT * FROM npc_memories WHERE id IN ({marks})"
    " AND superseded_by IS NULL AND invalid_reason IS NULL"
)


def _perf_counter() -> float:
    return time.perf_counter()


class _VecBenchWorld:
    """检索链参考世界：numpy 余弦候选 + 治理 JOIN（A4 语义同构）。

    与 A4 真实实现的差别只在「向量后端」（sqlite-vec vec0 vs numpy）：
    **治理过滤 SQL 与打分链逐字节同语义**（vec-preplan §18：向量只换候选生成器）。
    """

    def __init__(self, n_visible: int = N_VISIBLE, n_npc: int = N_NPC) -> None:
        rng = np.random.default_rng(_SEED)
        self._rng = rng
        self._tmp = tempfile.mktemp(suffix=".db")
        self._path = Path(self._tmp)
        # 直建最小表（不走 ORM/Alembic：bench 只要候选池 + 治理列两件事）
        self._conn = sqlite3.connect(self._tmp)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            "CREATE TABLE npc_memories("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " entry_id TEXT NOT NULL, npc_id TEXT NOT NULL, content TEXT NOT NULL,"
            " source TEXT NOT NULL, event_seq INTEGER, importance REAL,"
            " emotion_tag TEXT, superseded_by TEXT, invalid_reason TEXT)"
        )
        for i in range(n_visible):
            self._conn.execute(
                "INSERT INTO npc_memories(entry_id, npc_id, content, source, event_seq,"
                " importance, emotion_tag) VALUES (?,?,?,?,?,?,?)",
                (
                    f"m{i:05d}",
                    f"npc-{i % n_npc:02d}",
                    _CONTENT.format(i),
                    "event",
                    i,
                    0.5,
                    "anger" if i % 3 == 0 else None,
                ),
            )
        self._conn.commit()
        self._ids = [r[0] for r in self._conn.execute("SELECT id FROM npc_memories").fetchall()]
        self._vectors = rng.random((n_visible, EMBED_DIM)).astype(np.float32)
        # 写入时归一化（真实 A2 写路径的 embedding 归一化在生成侧；检索侧省一次除法）
        self._matrix = self._vectors / np.linalg.norm(self._vectors, axis=1)[:, None]
        self._queries = rng.random((n_npc, EMBED_DIM)).astype(np.float32)
        self._qhat = self._queries / np.linalg.norm(self._queries, axis=1)[:, None]

    def candidates(self, npc_index: int = 0, top_k: int = TOP_K) -> list[MemoryEntry]:
        """A4 语义候选生成：余弦 top-(k×过取) → JOIN 治理过滤 → 按距离序取 top_k。"""
        sims = self._matrix @ self._qhat[npc_index]
        k = min(top_k * OVERFETCH, len(sims))
        pre = np.argpartition(-sims, k - 1)[:k]
        pre = pre[np.argsort(-sims[pre])]  # 距离降序（治理过滤前保持序）
        rowids = [self._ids[j] for j in pre]
        marks = ",".join("?" * len(rowids))
        rows = self._conn.execute(_CANDIDATES_SQL.format(marks=marks), rowids).fetchall()
        # 过滤后仍按原距离序（JOIN 保序 = sqlite IN 保序不可依赖 → 显式重排）
        pos = {r["id"]: i for i, r in enumerate(rows)}
        rows = sorted(rows, key=lambda r: pos[r["id"]])
        return [_row_to_entry(r) for r in rows[:top_k]]

    def all_entries(self, limit: int = N_VISIBLE) -> list[MemoryEntry]:
        """全量候选（退化哨兵口径：候选未收缩时的打分输入）。"""
        rows = self._conn.execute("SELECT * FROM npc_memories LIMIT ?", (limit,)).fetchall()
        return [_row_to_entry(r) for r in rows]

    def query_for(self) -> MemoryQuery:
        return MemoryQuery(npc_id="npc-00", now_tick=10**9, top_k=8)

    def close(self) -> None:
        self._conn.close()
        self._path.unlink(missing_ok=True)


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    return make_entry(
        entry_id=str(row["id"]),  # bench 直接用 rowid 作稳定 id
        npc_id=row["npc_id"],
        content=row["content"],
        source=row["source"],
        event_seq=row["event_seq"],
        importance=row["importance"],
        emotion_tag=row["emotion_tag"],
        superseded_by=row["superseded_by"],
        invalid_reason=row["invalid_reason"],
    )


def _beliefs() -> tuple:
    """认知两钩子（confirmation + mood；M2-P4 §3.1 同口径）。"""
    return CognitionParams(beliefs=Beliefs(keywords=("雨", "酒馆"))).retrieval_scorers()


@pytest.fixture
def vec_world() -> Iterator[_VecBenchWorld]:
    w = _VecBenchWorld()
    yield w
    w.close()


# ---------------------------------------------------------------------------
# ① 候选生成红线（VEC_CANDIDATE_PER_NPC_LIMIT_MS=0.30）
# ---------------------------------------------------------------------------


@pytest.mark.bench
def test_vec_candidate_generation_per_npc(vec_world: _VecBenchWorld, benchmark) -> None:
    """候选生成（A4 语义：余弦 + 治理 JOIN 过取）≤ 0.30ms/NPC（暖态中位）。

    A4 前实测 0.233ms（n=600、k=20、过取 4x、d=4）。破限 = 候选缝退化：
    查过取倍率/治理 JOIN 形态，不回退红线。
    """

    def _run() -> float:
        t0 = _perf_counter()
        vec_world.candidates()
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    assert_median_threshold(
        benchmark.stats, VEC_CANDIDATE_PER_NPC_LIMIT_MS, "向量候选生成 单 NPC（A4 语义·暖态中位）"
    )


# ---------------------------------------------------------------------------
# ② 打分链红线（RETRIEVAL_SCORE_PER_NPC_LIMIT_MS=0.30）
# ---------------------------------------------------------------------------


@pytest.mark.bench
def test_retrieval_scoring_20_candidates(vec_world: _VecBenchWorld, benchmark) -> None:
    """打分链（20 候选 × confirmation/mood 双钩子）≤ 0.30ms/NPC（暖态中位）。

    A4 前实测 0.057ms（余量 5.3x）。候选数涨（top_k 上调/多物质）先看这条。
    """
    candidates = vec_world.candidates()
    scorers = _beliefs()
    query = vec_world.query_for()

    def _run() -> float:
        t0 = _perf_counter()
        retrieve(candidates, query, scorers=scorers)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=200)
    assert_median_threshold(
        benchmark.stats, RETRIEVAL_SCORE_PER_NPC_LIMIT_MS, "检索打分链 20 候选（暖态中位）"
    )


# ---------------------------------------------------------------------------
# ③ 退化哨兵红线（RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS=2.00）
# ---------------------------------------------------------------------------


@pytest.mark.bench
def test_retrieval_full_scan_degraded_sentinel(vec_world: _VecBenchWorld, benchmark) -> None:
    """退化哨兵：候选未收缩（600 全量 × 2 钩子）≤ 2.00ms/NPC（暖态中位）。

    **破限不是性能回退**——语义 = 向量候选缝断链（召回端治理 JOIN 失败 /
    `candidates()` 没接上、退化成 iter_visible 全量）。处置：查 A4 接线
    （`VecCandidateSource.candidates` 是否真的过 vec + JOIN），**不放宽红线**。
    A4 前实测 0.970ms（余量 2.06x）。
    """
    entries = vec_world.all_entries()
    scorers = _beliefs()
    query = vec_world.query_for()

    def _run() -> float:
        t0 = _perf_counter()
        retrieve(entries, query, scorers=scorers)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=100)
    assert_median_threshold(
        benchmark.stats, RETRIEVAL_FULL_SCAN_PER_NPC_LIMIT_MS, "检索退化哨兵 600 全量（暖态中位）"
    )


# ---------------------------------------------------------------------------
# ④ tick 总量红线（RETRIEVAL_TICK_LIMIT_MS=12.0；M3-P2 拆常态/反模式两口径）
# ---------------------------------------------------------------------------

#: 决策驱动频次（DESIGN §8：L2 决策装 prompt 时才检索；L1 断线兜底低频）。≤10 次/tick
#: 是 M2 稳态近似（m3-retrieval-budget.md §2）——④ 的常态口径按它测，不按 50 NPC。
DECISION_DRIVEN_CALLS = 10


@pytest.mark.bench
def test_retrieval_tick_total_decision_driven(vec_world: _VecBenchWorld, benchmark) -> None:
    """单 tick 检索总量-常态口径（决策驱动 10 次全链）≤ 12ms（暖态中位）。

    `RETRIEVAL_TICK_LIMIT_MS` 的本义是「破限先查触发频次退化」，所以常态口径按
    DESIGN §8 的决策驱动频次（≤10 次/tick）测：A4 参考实现实测 **2.9ms**（余量 4.1x）。
    若本用例红 → 单次成本退化（先看 ①/②/③），不是频次问题。
    """
    scorers = _beliefs()

    def _run() -> float:
        t0 = _perf_counter()
        for npc_index in range(DECISION_DRIVEN_CALLS):
            retrieve(vec_world.candidates(npc_index), vec_world.query_for(), scorers=scorers)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=20)
    assert_median_threshold(
        benchmark.stats, RETRIEVAL_TICK_LIMIT_MS, "检索 tick 总量-决策驱动 10 次（暖态中位）"
    )


@pytest.mark.bench
def test_retrieval_broadcast_anti_pattern_probe(vec_world: _VecBenchWorld, benchmark) -> None:
    """反模式天花板**探测量**：50 NPC 各检索一次（暖态中位，刻意不设硬断言）。

    **这是防呆红线的反模式本体**（每 tick 广播式检索）。本用例只记录「反模式吃掉
    多少 tick 预算」作防呆论据，判据是 docstring 里的对照表，不是断言。

    A4 参考实现实测（本机，暖态中位，2026-09-23 M3-P2）：
    | 候选实现 | 50 NPC 一次全链 | 占 16.6ms 预算 |
    |---|---|---|
    | cosine + 80 参 IN-JOIN（本文件参考实现） | **~16.8ms** | **101%** |
    | cosine + 逐行 SELECT（无 JOIN） | ~38.9ms | 234% |
    | 全表 SELECT + numpy 掩码 | ~131.2ms | 790% |
    → 三种实现**全部破 tick 预算**（最好那个也刚好顶满）=「每 tick 广播」形态不可用；
    M3-P1 建模型按纯 numpy 0.05ms/NPC（估 2.5ms/50NPC）**低估 6~52x**。
    结论不变（防呆红线延续）：检索触发必须决策驱动 → 见决策驱动常态用例。
    M3 接线后 sqlite-vec 单 SQL JOIN（无 IN 列表）预计更省——本用例转硬红线需先实测再裁。
    """
    scorers = _beliefs()

    def _run() -> float:
        t0 = _perf_counter()
        for npc_index in range(N_NPC):
            retrieve(vec_world.candidates(npc_index), vec_world.query_for(), scorers=scorers)
        return (_perf_counter() - t0) * 1000.0

    benchmark.pedantic(_run, rounds=9, warmup_rounds=1, iterations=20)
    measured_ms = benchmark.stats.stats.median * 1000.0
    logger.info(
        "bench.retrieval.anti_pattern_broadcast",
        median_ms=round(measured_ms, 3),
        tick_budget_ms=TICK_BUDGET_MS,
        budget_share_pct=round(measured_ms / TICK_BUDGET_MS * 100.0, 1),
        note="anti-pattern ceiling probe; no hard assert (see docstring table)",
    )


# ---------------------------------------------------------------------------
# 契约守卫（非 bench）：候选形状 + 降级语义自证（不越 A4 的域）
# ---------------------------------------------------------------------------


def test_candidate_shape_contract(vec_world: _VecBenchWorld) -> None:
    """候选 = MemoryEntry 且治理过滤同 iter_visible 语义（不越 A4 断言其实现）。"""
    cands = vec_world.candidates()
    assert len(cands) == TOP_K
    assert all(isinstance(c, MemoryEntry) for c in cands)
    assert all(c.superseded_by is None and c.invalid_reason is None for c in cands)
    assert all(npc_id.startswith("npc-") for npc_id in (c.npc_id for c in cands))


def test_governance_join_filters_superseded(vec_world: _VecBenchWorld) -> None:
    """治理 JOIN：把一条改成 superseded 后不再进候选（R2 红线的最小自证）。"""
    rowid = vec_world._ids[0]
    vec_world._conn.execute(
        "UPDATE npc_memories SET superseded_by = ? WHERE id = ?", ("m99999", rowid)
    )
    vec_world._conn.commit()
    cands = vec_world.candidates()
    assert rowid not in {int(c.id) for c in cands}


def test_degraded_sentinel_semantics_is_bigger_than_normal() -> None:
    """哨兵口径自证：600 全量打分成本显著 > 20 候选打分（哨兵有区分度）。"""
    w = _VecBenchWorld()
    try:
        cands = w.candidates()
        scorers = _beliefs()
        query = w.query_for()
        for _ in range(20):
            retrieve(cands, query, scorers=scorers)
            retrieve(w.all_entries(), query, scorers=scorers)
        t0 = _perf_counter()
        retrieve(cands, query, scorers=scorers)
        ms_small = (_perf_counter() - t0) * 1000.0
        t0 = _perf_counter()
        retrieve(w.all_entries(), query, scorers=scorers)
        ms_full = (_perf_counter() - t0) * 1000.0
        assert ms_full > ms_small, (
            f"退化哨兵无区分度（全量 {ms_full:.3f}ms ≤ 20 候选 {ms_small:.3f}ms）——"
            "哨兵失效，无法检出候选缝断链"
        )
    finally:
        w.close()
