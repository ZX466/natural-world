"""M5-K7 state_delta plan 字段 + cue 钩子缝（kilo 域施工）。

判据源自 docs/arch/m4-plan.md §6 裁 14-3：计划看板数据源=PlanSlice/Intent 流，渲染归
前端；**后端只保证 plan 状态进 state_delta**。本文把该承诺的协议面与 sim 实发面钉住：

 - `plan` 是 state_delta 顶层可选数组（与 actors/lights 并列，不塞进 ActorDelta——
   改计划不必伴随移动，塞 ActorDelta 会被 moved 过滤漏掉；m4-plan 裁 14-3 语义）。
 - 每项 `{rtoken, text}`：rtoken 不透明替身（出戏边界，§5 禁 entity_id）；
   text=当前计划文本（可空串=无计划）。项的组件 schema 是
   `PlanDelta`（`sim/api/openapi_ext.py` → shared/openapi.json → shared/protocol.ts），
   `additionalProperties:false`；**M5-K10（裁 19）前该组件缺失**——K7 曾把这条
   不成立的假设写成判据，现由 `TestPlanDeltaSchema` 引真实 schema 钉住（§1.5）。
 - cue 钩子缝对齐 WillingnessExpression.band（will.py 纯函数）：band→cue 映射表
   放在 sim/agent 侧（真源），ws.py 占位规则表迁走，保留占位语义不回退。

 EXTEND/DROP 模式先于 WS 分发出轨：plan 数据经显式 delta 传播，不依赖 moved 集。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from sim.agent.will import WillingnessExpression, WillingnessVerdict
from sim.api.ws import _rtoken
from sim.core.tick import TickLoop
from sim.npc.plan_view import (
    PlanDeltaStore,
    band_to_cue,
    reset_plan_registry,
)

#: plan 字段的合法键（出戏边界：无 entity_id/tick/plan_id 内部结构）。
PLAN_ITEM_KEYS = {"rtoken", "text"}


@pytest.fixture(autouse=True)
def _clean_plan_registry() -> Iterator[None]:
    reset_plan_registry()
    yield
    reset_plan_registry()


class TestPlanDeltaStore:
    """K7-① 进程内 plan 账本（npc 域产物；m4 真实执行器写入前的占位落点）。"""

    def test_set_get_roundtrip(self) -> None:
        store = PlanDeltaStore()
        store.set_plan("chenmo", "去河边看看")
        assert store.plan_of("chenmo") == "去河边看看"

    def test_set_overwrites(self) -> None:
        store = PlanDeltaStore()
        store.set_plan("chenmo", "A")
        store.set_plan("chenmo", "B")
        assert store.plan_of("chenmo") == "B"

    def test_unknown_entity_returns_none(self) -> None:
        store = PlanDeltaStore()
        assert store.plan_of("no_such") is None

    def test_empty_text_allowed(self) -> None:
        """空串=明确无计划（与 None=从没报过 是两种状态）。"""
        store = PlanDeltaStore()
        store.set_plan("chenmo", "")
        assert store.plan_of("chenmo") == ""

    def test_clear_removes(self) -> None:
        store = PlanDeltaStore()
        store.set_plan("chenmo", "A")
        store.clear_plan("chenmo")
        assert store.plan_of("chenmo") is None

    def test_clear_missing_is_noop(self) -> None:
        store = PlanDeltaStore()
        store.clear_plan("no_such")  # 不得抛

    def test_non_string_rejected(self) -> None:
        store = PlanDeltaStore()
        with pytest.raises(TypeError):
            store.set_plan("chenmo", 123)  # type: ignore[arg-type]

    def test_empty_entity_id_rejected(self) -> None:
        store = PlanDeltaStore()
        with pytest.raises(ValueError):
            store.set_plan("", "A")

    def test_delta_only_changed(self) -> None:
        """二次传播过滤：只回相对上次广播变了键的项（增量契约最小化）。"""
        store = PlanDeltaStore()
        store.set_plan("a", "1")
        store.set_plan("b", "2")
        first = store.drain_changes()
        assert {i["entity_id"] for i in first} == {"a", "b"}
        assert store.drain_changes() == []

    def test_module_registry_shared(self) -> None:
        """ws.py 与 npc 域共用同一进程内账本（plan_view 模块单例）。"""
        from sim.npc import plan_view

        plan_view.set_plan("chenmo", "看看天气")
        assert plan_view.plan_of("chenmo") == "看看天气"
        assert plan_view.entries() == {"chenmo": "看看天气"}


class TestCueHookMapping:
    """K7-② cue 钩子缝：band→cue 映射表归 sim/agent 真源（可单测、可替换）。"""

    @pytest.mark.parametrize(
        "band,cue",
        [
            (0, "accepted"),
            (1, "hesitation"),
            (2, "complaint"),
            (3, "resistance"),
        ],
    )
    def test_band_mapping(self, band: int, cue: str) -> None:
        assert band_to_cue(band) == cue

    def test_expression_band_drives_cue(self) -> None:
        """钩子缝：WillingnessExpression.band → cue（M4 真实表接入后只换表）。"""
        verdict = WillingnessVerdict(score=0.95, band=3)
        from sim.agent.will import willingness_expression

        expr = willingness_expression(verdict, npc_name="陈默")
        assert isinstance(expr, WillingnessExpression)
        assert band_to_cue(expr.band) == "resistance"

    def test_band_none_means_no_expression(self) -> None:
        """band 0 无表现 expression → cue 恒 accepted（映射表兜底）。"""
        verdict = WillingnessVerdict(score=0.1, band=0)
        from sim.agent.will import willingness_expression

        assert willingness_expression(verdict, npc_name="陈默") is None
        assert band_to_cue(0) == "accepted"

    def test_out_of_range_band_falls_back(self) -> None:
        """越界 band 不抛——钩子表是防御性映射（未知档按最强表现）。"""
        assert band_to_cue(9) == "resistance"

    def test_negative_band_is_accepted(self) -> None:
        assert band_to_cue(-1) == "accepted"


class TestDeltaPayloadPlan:
    """K7-① delta_payload 实发面：plan 键存在性与形状（出戏边界）。"""

    def _loop(self) -> TickLoop:
        from sim.core.clock import GameClock
        from sim.core.events import world_create_event
        from sim.core.world import WorldState, build_default_bus

        loop = TickLoop(
            clock=GameClock(speed=1.0),
            bus=build_default_bus(),
            state=WorldState(world_seed=1),
        )
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=("chenmo", "lin")))
        return loop

    def test_plan_absent_when_store_empty(self) -> None:
        """空账本 → 不带 plan 键（可选字段，不制造噪声）。"""
        from sim.api.ws import delta_payload

        loop = self._loop()
        payload = delta_payload(loop, set(loop.state.entities))
        assert "plan" not in payload
        assert set(payload) == {"type", "channel", "v", "ws_seq", "actors"}

    def test_plan_present_when_set(self) -> None:
        from sim.api.ws import delta_payload
        from sim.npc import plan_view

        plan_view.set_plan("chenmo", "去河边看看")
        loop = self._loop()
        payload = delta_payload(loop, set(loop.state.entities))
        assert payload["plan"] == [{"rtoken": _rtoken("chenmo"), "text": "去河边看看"}]

    def test_plan_keys_exact(self) -> None:
        from sim.api.ws import delta_payload
        from sim.npc import plan_view

        plan_view.set_plan("chenmo", "A")
        loop = self._loop()
        payload = delta_payload(loop, set(loop.state.entities))
        for item in payload["plan"]:
            assert set(item) == PLAN_ITEM_KEYS

    def test_plan_uses_rtoken_not_entity_id(self) -> None:
        """出戏边界：plan 项只含 rtoken 替身，禁 entity_id 直出。"""
        from sim.api.ws import delta_payload
        from sim.npc import plan_view

        plan_view.set_plan("chenmo", "A")
        loop = self._loop()
        payload = delta_payload(loop, set(loop.state.entities))
        assert "chenmo" not in str(payload["plan"])
        assert all(i["rtoken"].startswith("rt-") for i in payload["plan"])

    def test_plan_ignores_entities_not_in_world(self) -> None:
        """账本可能有已注销实体残留——按世界表过滤（与 actors 同口径）。"""
        from sim.api.ws import delta_payload
        from sim.npc import plan_view

        plan_view.set_plan("ghost", "不存在的我")
        loop = self._loop()
        payload = delta_payload(loop, set(loop.state.entities))
        assert "plan" not in payload

    def test_plan_independent_of_moved_set(self) -> None:
        """moved 为空也可发 plan（改计划≠移动；裁 14-3 顶层字段的核心理由）。"""
        from sim.api.ws import delta_payload
        from sim.npc import plan_view

        plan_view.set_plan("chenmo", "待着不动也想点事")
        loop = self._loop()
        payload = delta_payload(loop, set())
        assert payload["plan"] == [{"rtoken": _rtoken("chenmo"), "text": "待着不动也想点事"}]
        assert payload["actors"] == []

    def test_cleared_plan_sent_as_empty_text(self) -> None:
        """计划被清 → 发空串（前端据此收起看板），不是删键。"""
        from sim.api.ws import delta_payload
        from sim.npc import plan_view

        plan_view.set_plan("chenmo", "A")
        plan_view.set_plan("chenmo", "")
        loop = self._loop()
        payload = delta_payload(loop, set(loop.state.entities))
        assert payload["plan"] == [
            {"rtoken": "rt-" + __import__("hashlib").sha256(b"chenmo").hexdigest()[:12], "text": ""}
        ]


class TestImpulseFeedbackUsesHook:
    """K7-② ws.py 占位 cue 规则迁到钩子表：行为不回退。"""

    def test_cue_matches_previous_placeholder_semantics(self) -> None:
        from sim.api.ws import _impulse_cue

        # 疑问句 → hesitation；感叹句 → complaint；其余 accepted
        assert _impulse_cue("去河边？") == "hesitation"
        assert _impulse_cue("去河边!") == "complaint"
        assert _impulse_cue("去河边！") == "complaint"
        assert _impulse_cue("去河边") == "accepted"

    def test_feedback_frame_shape(self) -> None:
        from sim.api.ws import _handle_player_impulse

        reply = _handle_player_impulse({"text": "去河边看看？"})
        assert reply is not None
        assert reply["type"] == "impulse_feedback"
        assert reply["cue"] == "hesitation"
        assert set(reply) == {
            "type",
            "channel",
            "v",
            "ws_seq",
            "injected",
            "cue",
            "reaction_monologue",
        }


class TestPlanDeltaSchema:
    """M5-K10（裁 19 CRITICAL 修复）：plan 项引**真实** `PlanDelta` 组件。

    K7 原钉子在模块 docstring 写「`PlanDelta.additionalProperties:false`」时该
    组件并不存在（实现先跑、schema 未补，K9 抓为 CRITICAL）。现组件已落
    `sim/api/openapi_ext.py` 并经 `gen-protocol` 生成为 `shared/protocol.ts`；
    本类把「假设」换成「对真实组件的断言」，防未来再漂：
      1. `PlanDelta` 组件存在且封闭（additionalProperties:false）；
      2. 字段集恰为 {rtoken, text} 且均 required（对拍 delta_payload 实发）；
      3. `state_delta.plan` 属性确实引 PlanDelta 且**不进 required**（可选）；
      4. delta_payload 实发项不越 PlanDelta 边界（额外字段=越界）。
    """

    @staticmethod
    def _snapshot() -> dict:
        """shared/openapi.json 快照（gen-protocol 的唯一真相源）。"""
        import json
        from pathlib import Path

        path = Path(__file__).parents[2] / "shared" / "openapi.json"
        return json.loads(path.read_text(encoding="utf-8"))["components"]["schemas"]

    def test_component_exists_and_is_closed(self) -> None:
        schema = self._snapshot()["PlanDelta"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False

    def test_fields_exact_and_required(self) -> None:
        schema = self._snapshot()["PlanDelta"]
        assert set(schema["properties"]) == {"rtoken", "text"}
        assert set(schema["required"]) == {"rtoken", "text"}

    def test_rtoken_refs_the_opaque_substitute(self) -> None:
        """出戏边界：rtoken 引用共享替身组件，不是裸 string（禁内部 id 直出）。"""
        schema = self._snapshot()["PlanDelta"]
        assert schema["properties"]["rtoken"] == {"$ref": "#/components/schemas/RToken"}

    def test_state_delta_plan_refs_component_and_stays_optional(self) -> None:
        delta = self._snapshot()["StateDeltaMessage"]
        assert delta["properties"]["plan"] == {
            "type": "array",
            "items": {"$ref": "#/components/schemas/PlanDelta"},
        }
        # 可选：账本空时 delta_payload 不发该键（test_plan_absent_when_store_empty 钉）
        assert "plan" not in delta["required"]

    def test_emitted_items_within_component_bounds(self) -> None:
        """实发项不得含 PlanDelta 之外的字段（additionalProperties:false 镜像）。"""
        from sim.api.ws import delta_payload
        from sim.npc.plan_view import set_plan

        set_plan("chenmo", "去河边看看")
        try:
            loop = TestDeltaPayloadPlan()._loop()
            payload = delta_payload(loop, set(loop.state.entities))
            allowed = set(self._snapshot()["PlanDelta"]["properties"])
            for item in payload["plan"]:
                assert set(item) <= allowed
        finally:
            from sim.npc.plan_view import reset_plan_registry

            reset_plan_registry()

    def test_ext_source_matches_snapshot(self) -> None:
        """sim 侧组件定义（openapi_ext）与快照逐字段相等——防两处定义漂移。

        顺序敏感：`openapi_ext` 顶层 `from sim.api.main import app`，而 `main`
        模块级又 `from sim.api.openapi_ext import install`——先 import main 避开
        循环初始化（反向导入会拿到半初始化模块）。
        """
        import sim.api.main  # noqa: F401  # 先初始化 main，防循环 import
        from sim.api.openapi_ext import _SUB_SCHEMAS

        assert _SUB_SCHEMAS["PlanDelta"] == self._snapshot()["PlanDelta"]

    def test_generated_ts_type_carries_plan(self) -> None:
        """生成物 protocol.ts 已含 `plan?`（前端可达性的最终判据）。"""
        from pathlib import Path

        text = (Path(__file__).parents[2] / "shared" / "protocol.ts").read_text(encoding="utf-8")
        assert "readonly PlanDelta: {" in text
        assert "readonly plan?: readonly components['schemas']['PlanDelta'][];" in text
