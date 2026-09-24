"""sim.npc.reflection — 反思批处理（M3 批次 B-B2；DESIGN §15「每游戏日 1 次」）。

m3-plan 批次 B 架构细化：
- reflection_due(tick)：日切纯函数（tick % TICKS_PER_GAME_DAY == 0，weather 同款
  判日切模式）——由世界循环在固定执行序「事件结算后」调用，**不进每 tick 路径**
  （防呆红线：反思是批处理，不是每事件/tick 的常驻成本）；
- run_reflection(...)：gather（source="event" 的可见记忆为素材）→ 摘要文本
  → write(source="reason")。R7：反思产物走 write() 唯一入口，banned+hidden
  扫描照扫（被拒素材天然进不了 store，也就进不了摘要——S1 闭环）；
- M3 阶段摘要 = 规则化拼装（素材句拼接）；LLM 摘要挂载点预留 _llm_summarize
  （DESIGN §15：反思批处理是成本治理手段，摘要替代逐事件独白，零额外调用
  原则下复用 reason 通道——M3 先立骨架，LLM 接入随批次 D 决策缝）；
- 降级：无素材 → None（零产物）；LLM 缺位 → 规则化摘要兜底（世界照转）。
"""

from __future__ import annotations

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.llm.memory_scan import MemoryEntry, MemoryWritePipeline


def reflection_due(tick: int) -> bool:
    """日切判定：每游戏日首个 tick（tick 为 86,400 的整数倍）触发反思。"""
    return tick % TICKS_PER_GAME_DAY == 0


def _day_materials(pipeline: MemoryWritePipeline, npc_id: str, day: int) -> list[MemoryEntry]:
    """当日素材：source="event" 的可见记忆（reason/dialogue 不进素材——防自我吞尾）。

    日过滤约定：MemoryEntry 是内存形（无 created_at_tick 列——SQL 侧列在 store），
    M3 阶段素材窗口由调用方保证（世界循环在日切调用时传当日 day；SQL store 的
    tick 过滤随 B3/后续 store 扩展接入，接口先行不锁死）。
    """
    materials: list[MemoryEntry] = []
    for entry in pipeline.iter_visible(npc_id):
        if entry.source != "event":
            continue
        created = getattr(entry, "created_at_tick", None)
        if created is not None and created // TICKS_PER_GAME_DAY != day:
            continue
        materials.append(entry)
    return materials


def _llm_summarize(materials: list[MemoryEntry]) -> str | None:
    """LLM 摘要挂载点（M3 骨架：未接 LLM，返回 None 走规则化兜底）。

    接入时的纪律（DESIGN §15）：复用 reason 通道（零额外调用原则）、prompt 走
    assemble 唯一出口、产物必须过 write() 扫描面（本模块不截流）。
    """
    return None


def _rule_summarize(materials: list[MemoryEntry]) -> str:
    """规则化摘要：素材句以「、」衔接的世界内拼装（无数值无系统词——素材本身
    已过写入门扫描，拼装不改写词面）。"""
    parts = [m.content.rstrip("。.") for m in materials]
    return "这些日子，" + "；".join(parts) + "。"


def run_reflection(*, pipeline: MemoryWritePipeline, npc_id: str, day: int):
    """日切反思：当日 event 素材 → 摘要 → write(source="reason")。

    返回写入的 MemoryEntry；无素材或写入被拒 → None（降级是常态路径）。
    """
    materials = _day_materials(pipeline, npc_id, day)
    if not materials:
        return None
    summary = _llm_summarize(materials) or _rule_summarize(materials)
    result = pipeline.write(
        npc_id=npc_id,
        content=summary,
        source="reason",
        event_seq=None,
        # 反思摘要重要性取素材均值上浮（摘要是压缩后的高密度条目）；
        # 无素材时不走到这里。上浮封顶 0.9（低于 witnessed 链根置信）。
        importance=min(0.9, sum(m.importance for m in materials) / len(materials) + 0.1),
        emotion_tag=None,
    )
    if not result.accepted or result.entry is None:
        return None
    return result.entry


def make_day_switch_reflector(
    pipeline: MemoryWritePipeline, *, npc_ids: tuple[str, ...] | list[str]
):
    """日切钩子适配器（B-B2 消费侧）：on_day_switch(day) → 逐 NPC run_reflection。

    day 语义换算：世界循环钩子传 calendar 1-based 戏内天号（game_time(tick).day，
    界面同口径）；run_reflection/_day_materials 用 0-based（created // 86400），
    适配器在此换算——钩子不背两套历法。

    返回同步回调（run_world_driver 在事件结算后调用）；产出 = 本日写入的
    reason 条目列表（无素材的 NPC 自然缺位）。本批仍无生产 MemoryWritePipeline
    装配点（M3 批次 D 随 agent 循环接线），主树 lifespan 挂接本适配器时传入
    既有 pipeline 实例即可。
    """

    def _on_day_switch(day: int) -> list:
        written: list = []
        for npc_id in npc_ids:
            entry = run_reflection(pipeline=pipeline, npc_id=npc_id, day=day - 1)
            if entry is not None:
                written.append(entry)
        return written

    return _on_day_switch
