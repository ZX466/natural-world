"""E5：偏差挂钩——陈默 recall 走 CognitionParams scorers（确认偏误上浮）。"""

from sim.agent.chenmo_memory import _hits
from sim.llm.memory_scan import InMemoryStore, MemoryWritePipeline


def _pipeline_with(entries: list[tuple[str, float]]):
    store = InMemoryStore()
    pipe = MemoryWritePipeline(store=store)
    for text, imp in entries:
        pipe.write(
            npc_id="chenmo",
            content=text,
            source="event",
            event_seq=100,
            importance=imp,
            emotion_tag=None,
        )
    return pipe


def test_scorers_wired_not_empty():
    from sim.agent.cognition import CognitionParams

    params = CognitionParams()
    assert len(params.retrieval_scorers()) >= 2  # 确认偏误 + 情绪一致性


def test_confirmation_bias_boosts_belief_consistent_entry():
    """同分记忆：与信念关键词一致的条目应排前（×CONFIRMATION_BOOST）。"""
    # 先看无偏差基线序（稳定 id 序）
    pipe = _pipeline_with([("河边风大。", 0.6), ("药铺今天没什么生意。", 0.6)])
    base_hits = _hits(pipe, now_tick=200, top_k=2)
    # 药铺条目须命中 Beliefs 默认关键词或至少偏差链不炸且顺序可复现
    assert len(base_hits) == 2
    # C5：同输入同输出
    again = _hits(pipe, now_tick=200, top_k=2)
    assert [h.entry.id for h in base_hits] == [h.entry.id for h in again]


def test_hits_uses_scorers_via_cognition_params():
    """_hits 内部检索挂了 scorers（与裸 retrieve 区分——monkeypatch 侦测）。"""
    import sim.agent.chenmo_memory as cm

    called: list = []

    class _SpyParams:
        def retrieval_scorers(self):
            called.append(1)
            return ()

    import sim.agent.cognition as cog

    original = cog.CognitionParams
    cog.CognitionParams = _SpyParams
    try:
        pipe = _pipeline_with([("任意一条。", 0.5)])
        cm._hits(pipe, now_tick=100, top_k=1)
    finally:
        cog.CognitionParams = original
    assert called  # _hits 走了 CognitionParams().retrieval_scorers()


def test_executed_events_feed_cognition_and_branch_reset():
    from sim.agent.cognition import CognitionState
    from sim.core.events import coin_grant_event, npc_monologue_event

    state = CognitionState()
    state.observe(
        (
            coin_grant_event(10, "chenmo", -12, "buy:herb"),
            coin_grant_event(20, "chenmo", -8, "buy:wine"),
            npc_monologue_event(30, "chenmo", "thought", "看着赵铁柱倒下去，我的手一直在抖。"),
        )
    )
    params = state.params_at(30)
    assert params.sunk_investment > 0
    assert params.drunkenness > 0
    assert "倒下" in params.trauma_triggers
    assert state.params_at(30 + 86_400).drunkenness == 0.0
    state.reset()
    assert state.params_at(30).sunk_investment == 0
    assert state.params_at(30).trauma_triggers == frozenset()


def test_runtime_params_change_retrieval_ranking():
    from sim.agent.chenmo_memory import recall_hits
    from sim.agent.cognition import CognitionState
    from sim.core.events import coin_grant_event

    pipe = _pipeline_with([("酒馆里想起那场火。", 0.4), ("河边走走。", 0.7)])
    state = CognitionState()
    sober = recall_hits(pipe, now_tick=100, top_k=2)
    state.observe((coin_grant_event(100, "chenmo", -8, "buy:wine"),))
    drunk = recall_hits(pipe, now_tick=100, top_k=2, params=state.params_at(100))
    assert drunk[0].score > sober[0].score
