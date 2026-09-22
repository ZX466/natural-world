"""sim.npc.memory — 记忆检索打分缝（M2-D3，m2-npc-cognition §3.1/§3.2）。

**读侧 only**：本模块只读记忆、只算分，不写、不改存储（写路径与守卫在
`sim.llm.memory_scan.MemoryWritePipeline`，本模块绝不触碰）。

架构定位（§3.2 cognition 是纯函数层）：
- 输入 `(profile, needs, mood, memory_scores, context)` → 输出修正后的分数；
- 本模块负责 **memory_scores** 这一段：把候选记忆集 + 上下文 → 可注入打分的
  结构化结果；偏差（确认偏误/情绪一致性）由 `sim/agent/cognition.py` 后期以
  `RetrieveFn` **钩子**注册，本模块**不写死任何偏差逻辑**（§3.1 挂载缝）。

M2 用**标量检索**：候选 = `iter_visible(npc_id)`（S5 已过滤被取代条目），
打分 = 基础分（重要性 + 近因）× 各钩子系数项；向量检索 `npc_memory_vec` 仍锁 M3。

确定性（C5）：同输入同输出；同分按 `entry.id` 稳定排序（不依赖 store 迭代序）。

------------------------------------------------------------------------------
契约（API 输入输出 / 注入点语义 / M3 边界）— M2-D4 补全
------------------------------------------------------------------------------

**1. 输入（``MemoryQuery``，frozen 纯数据，无 IO）**

| 字段 | 类型 | 语义 | 缺省行为 |
|---|---|---|---|
| `npc_id` | str | 检索主体，**必填**；交 store 作可见性过滤键 | — |
| `context` | str | 当前情境文本 | `""`；本模块基础分不解析，供 M3 上下文钩子 |
| `mood` | `tuple[p,r,d]` 或 None | 当前 PAD（-1..1 三元组） | `None`=未知 → 情绪钩子恒等 |
| `now_tick` | int 或 None | 近因衰减基准 tick | `None` → 全按 `age=0`（近因=1.0） |
| `top_k` | int | 返回条数上限 | `DEFAULT_TOP_K=8`；`≤0`=不限 |

**2. 输出（``list[MemoryHit]``，已排序截断）**
``MemoryHit = { entry: MemoryEntry, score: float, breakdown: tuple[(name, value)] }``
- 顺序：`score` 降序，同分按 `entry.id` **升序稳定**（C5；不依赖 store 迭代序）；
- `top_k>0` 时截断，否则全量；
- `breakdown` 为 `("base", base)`+各钩子 `(scorer.name, value)` 的纯诊断分解，
  **不参与下游计算**——观测/调参基准；
- ``scores_of(hits) -> {entry_id: score}`` 即 §3.2 cognition 的 `memory_scores` 形。

**3. 打分公式**
``score = base_score × Π(mul 系数) + Σ(add 项)``，``base_score = importance × recency_factor``。
基础分**不含偏差**、纯函数；`scorers=()` 时即纯基础分。

**4. 注入点语义（偏差挂载缝，§3.1）**
钩子 ``RetrieveFn = Callable[[MemoryEntry, MemoryQuery], float]``，以
``Scorer(name, fn, mode∈{"mul","add"})`` 注册（``mode="mul"`` 默认 1.0 恒等 /
``"add"`` 默认 0.0 恒等）；``RetrievalScorers`` 为 **frozen 不可变注册表**
（`register` 返回新表，默认空表=无偏差）。本模块只定义缝，**偏差逻辑归 cognition**：
- **确认偏误**（`confirmation_bias`，mul）：条目内容命中既有 `beliefs.keywords` → ×1.5；
- **情绪一致性**（`mood_bias`，mul）：`query.mood` 极性与 `entry.emotion_tag` 极性同向
  → ×1.3 / 反向 → ×0.7。
挂载形态由 `sim/agent/cognition.py::CognitionParams.retrieval_scorers()` 产出 tuple，
调用方 `retrieve(store, query, scorers=params.retrieval_scorers())`。偏差名与参数
**零元信息**：绝不进 prompt/戏内文本，只作用于打分（DESIGN §7）。

**5. 与 M3 向量检索的边界（`npc_memory_vec` 仍锁）**
- M2 为**标量**检索：候选来自 `MemoryStoreLike.iter_visible(npc_id)`（S5 过滤
  `superseded_by`），无语义相似度、无 ANN；
- `npc_memory_vec`（schema §6，sqlite-vec）**M2 不接**：向量召回 M3 才启用，
  届时作为**候选生成器**替换/前置 `iter_visible`，本模块打分 API 形状不变
  （钩子仍作用于 `MemoryEntry`）；
- 本模块**不含** embedding、不读 vec 表、不依赖 sqlite-vec 扩展。

**6. 读侧 guardrail（铁律，不得越界）**
- `retrieve`/`base_score`/`recency_factor`/`scores_of` 均为纯函数或只读；
  **不写库、不触发写路径与 S1 守卫、不触碰 `MemoryWritePipeline`**；
- store 依赖仅限于 ``MemoryStoreLike``（`iter_visible` 一个方法）——鸭子类型，
  不绑定具体存储。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import structlog

from sim.llm.memory_scan import MemoryEntry

logger = structlog.get_logger(__name__)

#: 默认检索条数（§3.2 检索打分供给上行；top_k 由调用方按 prompt 预算覆盖）。
DEFAULT_TOP_K = 8

#: 近因半衰期（游戏 tick）：recency = 0.5 ** (age / HALF_LIFE)。M2 占位常量。
RECENCY_HALF_LIFE_TICKS = 86_400.0


@dataclass(frozen=True)
class MemoryQuery:
    """一次检索的上下文（纯数据；不含 IO）。

    - ``npc_id``：检索主体（必填）。
    - ``context``：当前情境文本（供关键词/情境钩子用；本模块基础分不解析它）。
    - ``mood``：当前 PAD（-1..1 三元组；供情绪一致性钩子用；None=未知）。
    - ``now_tick``：当前 tick（近因衰减基准；None=不做近因，全按 age=0）。
    - ``top_k``：返回条数上限（≤0 视为不限）。
    """

    npc_id: str
    context: str = ""
    mood: tuple[float, float, float] | None = None
    now_tick: int | None = None
    top_k: int = DEFAULT_TOP_K


@dataclass(frozen=True)
class MemoryHit:
    """一条打分后的检索结果。

    ``breakdown`` 是「来源 → 系数/分项」的分解，供观测与偏差调参（纯诊断，
    不参与下游计算）；``score`` 为最终标量分。
    """

    entry: MemoryEntry
    score: float
    breakdown: tuple[tuple[str, float], ...] = ()


#: 打分钩子：纯函数 (entry, query) -> 分数。偏差模块（cognition）后期注册；
#: 可返回加法分或乘法系数——由 `RetrieveFn.mode` 语义约定，见 register 说明。
RetrieveFn = Callable[[MemoryEntry, "MemoryQuery"], float]


@runtime_checkable
class MemoryStoreLike(Protocol):
    """检索只需 store 的只读可见视图（S5：iter_visible 已过滤被取代条目）。"""

    def iter_visible(self, npc_id: str) -> Iterable[MemoryEntry]: ...


def recency_factor(entry: MemoryEntry, now_tick: int | None) -> float:
    """近因系数 ∈ (0,1]：age = now_tick - event_seq 关联 tick（缺则 age=0）。

    MemoryEntry 不带 tick 字段（event_seq 是事件序号非 tick），M2 以
    ``event_seq`` 作单调基准的近似：age = now_tick - event_seq 时 clamp≥0。
    event_seq 为 None（推理转述）视作最新（age=0）。"""
    if now_tick is None or entry.event_seq is None:
        return 1.0
    age = max(0.0, float(now_tick - entry.event_seq))
    return float(0.5 ** (age / RECENCY_HALF_LIFE_TICKS))


def base_score(entry: MemoryEntry, query: MemoryQuery) -> float:
    """基础分（**不含偏差**）：重要性 × 近因。∈ [0,1]。

    纯函数、与偏差正交——偏差由钩子叠加，基础分保持不变（§3.2：偏差只作用
    于检索打分与效用计算，不改存储）。"""
    return float(entry.importance) * recency_factor(entry, query.now_tick)


@dataclass(frozen=True)
class Scorer:
    """注册的打分钩子（名字 + 纯函数 + 语义 mode）。

    ``mode``：``"mul"`` 乘法系数（默认 1.0 恒等）、``"add"`` 加法项（默认 0.0）。
    """

    name: str
    fn: RetrieveFn
    mode: str = "mul"

    def apply(self, entry: MemoryEntry, query: MemoryQuery) -> float:
        return float(self.fn(entry, query))


def retrieve(
    store: MemoryStoreLike | Iterable[MemoryEntry],
    query: MemoryQuery,
    *,
    scorers: Sequence[Scorer] = (),
) -> list[MemoryHit]:
    """读侧检索：候选 → 打分 → 稳定排序 → top_k。

    候选来源：``store`` 若是 ``MemoryStoreLike`` 则调 ``iter_visible``（S5 过滤）；
    否则当作已给的条目可迭代对象（便于测试与上层预筛）。

    打分 = base_score × Π(mul 系数) + Σ(add 项)；``scorers`` 为空时即纯基础分。
    同分按 ``entry.id`` 升序稳定（C5 确定性）。
    """
    entries: Iterable[MemoryEntry] = (
        store.iter_visible(query.npc_id) if isinstance(store, MemoryStoreLike) else store
    )

    hits: list[MemoryHit] = []
    for entry in entries:
        base = base_score(entry, query)
        score = base
        breakdown: list[tuple[str, float]] = [("base", base)]
        for scorer in scorers:
            value = scorer.apply(entry, query)
            breakdown.append((scorer.name, value))
            if scorer.mode == "mul":
                score *= value
            else:
                score += value
        hits.append(MemoryHit(entry=entry, score=score, breakdown=tuple(breakdown)))

    hits.sort(key=lambda h: (-h.score, h.entry.id))
    if query.top_k > 0:
        hits = hits[: query.top_k]
    logger.debug(
        "memory.retrieve",
        npc_id=query.npc_id,
        candidates=len(hits),
        top_k=query.top_k,
        scorers=[s.name for s in scorers],
    )
    return hits


def scores_of(hits: Sequence[MemoryHit]) -> dict[str, float]:
    """把命中集规约为 ``{entry_id: score}``（§3.2 cognition 的 memory_scores 形）。"""
    return {h.entry.id: h.score for h in hits}


@dataclass(frozen=True)
class RetrievalScorers:
    """钩子注册表（偏差模块后期往这里挂；本模块默认空 = 无偏差）。

    bias 模块（cognition）示例（后期接入，非本模块职责）：

        RetrievalScorers().register(
            Scorer("confirmation_bias", fn, mode="mul")
        )

    M2 默认空表：``retrieve(..., scorers=())`` 即纯基础分，不引入任何偏差。
    """

    _scorers: tuple[Scorer, ...] = field(default_factory=tuple)

    def register(self, scorer: Scorer) -> RetrievalScorers:
        """注册一个钩子，返回新注册表（frozen；不原地改）。"""
        return RetrievalScorers((*self._scorers, scorer))

    def as_sequence(self) -> tuple[Scorer, ...]:
        return self._scorers
