"""M4-D15 补线钉 — 权力供数 / 陈默记忆切片 / 日切反思（m4-plan 批次 D15）。

三个「机制现成、实况断线」的断点收口钉：

1. **权力供数**：M6 批次 C 机制全在（utility.py 权力列偏置 / NpcRuntime.power
   字段 / PowerStore 读写面 / 0013 迁移），但实况装配链不查表、无人赋
   runtime.power ⇒ 机制在实况恒等于「无权力面」（None）。钉子：attach_power
   装配缝（PowerStore.materialize 产物 → runtime.power）——查表有行必须赋
   字段；空表 = 不赋 = 逐位同旧行为（「无行 ≡ 0」口径下 0 值权力与 None 打分
   逐位相等，test_m6_power_utility 已钉打分面；此处钉装配语义）；
2. **陈默记忆切片**：driver.decide_once 有 memory_entries 参数（prompt 装配
   MemorySlice 现成），但实况调用恒空 ⇒ 陈默无记忆。钉子：sim.agent.chenmo_memory
   模块（observe：感知叙述 source="event" 写入——write() 闸门照扫、原文绝不
   绕闸落库；recall：retrieve 纯基础分 top-k——C5 纯函数，同输入同输出，
   产出 = 叙事句 tuple 直接进 driver.memory_entries）；
3. **日切反思**：run_world_driver 有 on_day_switch 钩子、reflection.py 有
   make_day_switch_reflector 适配器（1-based day 换算已内置）——实况 main.py
   调用时没传 ⇒ 反思批处理一次没跑过。钉子：适配器接缝 + 素材驱动闭环
   （observe 写 event 素材 → 日切压成 reason 摘要 → recall 可检索）。

三条接缝全部复用既有机制面（补线不造轮子）；测试用内存 store，零真实 IO、
全确定性（C5）。
"""

from __future__ import annotations

from typing import Any

import pytest

from sim.content.protagonist import CHENMO_ID
from sim.core.persistence.power_store import PowerState
from sim.llm.memory_scan import InMemoryStore, MemoryWritePipeline
from sim.npc.model import NpcProfileData

# ── 夹具 ────────────────────────────────────────────────────────────


def _runtime() -> Any:
    """最小真 NpcRuntime（真实构造面，不 __new__ 绕道）。"""
    from sim.npc.runtime import NpcRuntime
    from sim.npc.utility import UtilityModel

    return NpcRuntime(
        profiles={"npc0": NpcProfileData(npc_id="npc0", name="甲")},
        utility=UtilityModel(n_npc=1),
    )


@pytest.fixture()
def pipeline() -> MemoryWritePipeline:
    return MemoryWritePipeline(store=InMemoryStore())


# ── 1. 权力供数（attach_power 装配缝） ──────────────────────────────


def test_attach_power_assigns_materialized_values() -> None:
    """查表有行 → runtime.power 必须拿到物化值（机制面开闸）。"""
    from sim.npc.assemble import attach_power

    rt = _runtime()
    attach_power(rt, {"npc0": PowerState(npc_id="npc0", power_level=0.5, updated_at_tick=100)})
    assert rt.power == {"npc0": 0.5}


def test_attach_power_empty_table_is_bitwise_noop() -> None:
    """空表 = 不赋 = 逐位同旧（None 面；0 值与 None 打分逐位相等已钉于 M6）。"""
    from sim.npc.assemble import attach_power

    rt = _runtime()
    attach_power(rt, {})
    assert rt.power is None


def test_attach_power_ignores_ids_outside_roster() -> None:
    """表里有 profiles 外的 id（跨分支残留）→ 不进快照（装配面只认在册人员）。"""
    from sim.npc.assemble import attach_power

    rt = _runtime()
    attach_power(rt, {"ghost": PowerState(npc_id="ghost", power_level=1.0, updated_at_tick=0)})
    assert rt.power is None


# ── 2. 陈默记忆切片（sim.agent.chenmo_memory） ───────────────────────


def test_observe_writes_event_memory_through_gate(pipeline: MemoryWritePipeline) -> None:
    """感知叙述 → source="event" 写入（闸门照扫；通过则落库）。"""
    from sim.agent.chenmo_memory import observe

    observe(pipeline, "雨落青石，街上人影稀疏。", tick=100)
    entries = list(pipeline.iter_visible(CHENMO_ID))
    assert len(entries) == 1
    assert entries[0].source == "event"
    assert entries[0].content == "雨落青石，街上人影稀疏。"


def test_observe_never_stores_raw_meta_text(pipeline: MemoryWritePipeline) -> None:
    """出戏词（「运气」在禁词表）→ 原文绝不原样落库（钉不变量不钉阶梯分支：
    命中词不可映射时拒写、可映射时改写放行——二者都不泄漏原文）。"""
    from sim.agent.chenmo_memory import observe

    raw = "他今天运气不错。"
    observe(pipeline, raw, tick=101)
    for entry in pipeline.iter_visible(CHENMO_ID):
        assert entry.content != raw, "原文不得原样落库（改写或拒写二选一）"


def test_observe_event_seq_is_tick(pipeline: MemoryWritePipeline) -> None:
    """event_seq 存 tick（recency_factor 既定近似口径：半衰期=1 游戏日）。"""
    from sim.agent.chenmo_memory import observe

    observe(pipeline, "药铺的药柜又要清点了。", tick=12345)
    entries = list(pipeline.iter_visible(CHENMO_ID))
    assert entries[0].event_seq == 12345


def test_observe_custom_subject(pipeline: MemoryWritePipeline) -> None:
    """npc_id 可指定（默认 CHENMO_ID；村民侧复用同一入口）。"""
    from sim.agent.chenmo_memory import observe

    observe(pipeline, "西巷的王婆买了三文钱的醋。", tick=50, npc_id="npc_wang")
    assert len(list(pipeline.iter_visible("npc_wang"))) == 1
    assert len(list(pipeline.iter_visible(CHENMO_ID))) == 0


def test_recall_empty_memory_returns_empty(pipeline: MemoryWritePipeline) -> None:
    """无记忆 → recall 返回空（决策面照常运转——记忆缺位是常态路径）。"""
    from sim.agent.chenmo_memory import recall

    assert recall(pipeline, now_tick=500) == ()


def test_recall_orders_by_recency(pipeline: MemoryWritePipeline) -> None:
    """同重要性时近条压远条（打分 = importance × 0.5**(age/86400)，C5 可复算）。"""
    from sim.agent.chenmo_memory import observe, recall_hits

    observe(pipeline, "旧事：春分那天集市的布商吵了一架。", tick=0)
    observe(pipeline, "今早：街口的水洼映着晨光。", tick=40_000)
    hits = recall_hits(pipeline, now_tick=86_400)
    assert len(hits) == 2
    assert hits[0].entry.content.startswith("今早")
    fresh = hits[0].entry
    assert hits[0].score == pytest.approx(
        fresh.importance * 0.5 ** ((86_400 - 40_000) / 86_400)
    )


def test_recall_top_k(pipeline: MemoryWritePipeline) -> None:
    """top_k 生效（超条时截断——决策 prompt 预算控制）。"""
    from sim.agent.chenmo_memory import observe, recall

    for i in range(6):
        observe(pipeline, f"记事第{i}条：寻常一天。", tick=i)
    hits = recall(pipeline, now_tick=10, top_k=3)
    assert len(hits) == 3


def test_recall_returns_plain_string_tuple(pipeline: MemoryWritePipeline) -> None:
    """产出形态 = 叙事句 tuple（driver.memory_entries 的既有形，直接可传）。"""
    from sim.agent.chenmo_memory import observe, recall

    observe(pipeline, "西巷的狗今晨叫得凶。", tick=7)
    got = recall(pipeline, now_tick=7)
    assert got == ("西巷的狗今晨叫得凶。",)


# ── 3. 日切反思（钩子接缝 + 素材闭环） ───────────────────────────────


def test_day_switch_reflector_compresses_events_to_reason(
    pipeline: MemoryWritePipeline,
) -> None:
    """适配器钉：observe 写 event 素材 → 日切钩子压成 reason 摘要（1-based day）。"""
    from sim.agent.chenmo_memory import observe
    from sim.npc.reflection import make_day_switch_reflector

    observe(pipeline, "白日里帮师父晒了药。", tick=10)
    reflector = make_day_switch_reflector(pipeline, npc_ids=(CHENMO_ID,))
    written = reflector(1)  # 戏内 1-based 天号
    assert len(written) == 1
    reasons = [e for e in pipeline.iter_visible(CHENMO_ID) if e.source == "reason"]
    assert len(reasons) == 1
    assert "晒了药" in reasons[0].content


def test_day_switch_reflector_no_material_no_output(pipeline: MemoryWritePipeline) -> None:
    """无素材 → 零产物（反思是素材驱动批处理，不硬造内容）。"""
    from sim.npc.reflection import make_day_switch_reflector

    reflector = make_day_switch_reflector(pipeline, npc_ids=(CHENMO_ID,))
    assert reflector(1) == []


def test_observe_reflection_recall_closed_loop() -> None:
    """集成钉：observe(感知) → 日切反思 → recall 检索到 reason 摘要——
    「记忆→反思→再记忆」闭环装配面（不 mock 任何机制件）。"""
    from sim.agent.chenmo_memory import observe, recall_hits
    from sim.npc.reflection import make_day_switch_reflector

    pl = MemoryWritePipeline(store=InMemoryStore())
    observe(pl, "清晨在药铺门口遇见了钱小满。", tick=5)
    make_day_switch_reflector(pl, npc_ids=(CHENMO_ID,))(1)
    hits = recall_hits(pl, now_tick=90_000)
    assert len(hits) == 2, "event 原条 + reason 摘要都应可检索"
    assert "钱小满" in hits[0].entry.content, "摘要 importance 上浮应居首"
    assert any("钱小满" in h.entry.content for h in hits)
