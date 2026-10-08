"""sim.agent.chenmo_memory — 陈默记忆切片（M4-D15 补线）。

三面接缝、零新机制（补线不造轮子）：

- **observe**：感知叙述 → ``MemoryWritePipeline.write(source="event")`` 唯一
  写入口——闸门照扫（banned 词面照命中、改写/拒写由既有判梯处置），原文
  绝不绕闸落库；
- **recall**：``sim.npc.memory.retrieve`` 纯基础分检索（importance ×
  0.5**(age/86400)，半衰期 = 1 游戏日），同分按 entry.id 稳定序——C5 纯函数，
  同输入同输出；产出 = 叙事句 tuple，直接进
  ``ChenmoDriver.decide_once(memory_entries=...)``（MemorySlice 既有面）。
- event_seq 存 tick：``recency_factor`` 的既定近似口径（sim/npc/memory.py
  docstring 已钉「M2 以 event_seq 作单调基准的近似」，86400 = 1 游戏日）。

**进程内记忆**（InMemoryStore）：M4 阶段记忆与决策同进程同生命周期；SQL
落库（npc_memories 表 + 分支隔离）留待异步持久化批次——刻意不用
SqlMemoryStore：其 sync sqlite3 连接与实况 flush 的 aiosqlite 单写者共库会
产生跨驱动锁风险；此处钉为「M4 实况 = 进程内，SQL 化随持久化批次收口」。

实况侧记忆不进重放面（与 needs/节流账本同口径：C4 世界真相仍是事件流，
记忆只服务 LLM 决策输入——driver 循环本就在重放面之外）。
"""

from __future__ import annotations

from sim.content.protagonist import CHENMO_ID
from sim.llm.memory_scan import MemoryWritePipeline, WriteResult
from sim.npc.memory import MemoryHit, MemoryQuery, retrieve

#: 感知叙述写入的重要性档（0.6 = 目击级；低于反思摘要上限 0.9）。
_OBSERVE_IMPORTANCE = 0.6

#: recall 缺省 top-k（prompt 预算：3 条短句 ≈ 数十字，决策 prompt 增量可控）。
_RECALL_TOP_K = 3


def observe(
    pipeline: MemoryWritePipeline,
    text: str,
    *,
    tick: int,
    npc_id: str = CHENMO_ID,
) -> WriteResult:
    """感知叙述 → write() 唯一写入口（闸门照扫；原文绝不绕闸落库）。

    返回 WriteResult 原样（accepted=False 不抛——拒写是闸门的正常处置，
    调用方按需自查）；原文不落库的保证由 write() 的既有判梯承担。
    """
    return pipeline.write(
        npc_id=npc_id,
        content=text,
        source="event",
        event_seq=tick,  # 近因近似：event_seq 存 tick（recency_factor 既定口径）
        importance=_OBSERVE_IMPORTANCE,
        emotion_tag=None,
    )


def recall(
    pipeline: MemoryWritePipeline,
    *,
    now_tick: int,
    top_k: int = _RECALL_TOP_K,
) -> tuple[str, ...]:
    """纯基础分检索 → 叙事句 tuple（C5：同输入同输出；空记忆返回 ()）。"""
    return tuple(h.entry.content for h in _hits(pipeline, now_tick=now_tick, top_k=top_k))


def recall_hits(
    pipeline: MemoryWritePipeline,
    *,
    now_tick: int,
    top_k: int = _RECALL_TOP_K,
) -> tuple[MemoryHit, ...]:
    """打分细节版 recall（观测/调参面；与 recall 同源同分——C5 同输入同输出）。"""
    return _hits(pipeline, now_tick=now_tick, top_k=top_k)


def _hits(
    pipeline: MemoryWritePipeline,
    *,
    now_tick: int,
    top_k: int,
) -> tuple[MemoryHit, ...]:
    """共享检索核：retrieve 纯基础分（无 scorers——偏差挂载缝留 cognition）。"""
    query = MemoryQuery(npc_id=CHENMO_ID, now_tick=now_tick, top_k=top_k)
    return tuple(retrieve(pipeline, query))
