"""NPC L2 服务的模型边界、成本闸与异步退路（全部使用 Fake LLM）。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from structlog.testing import capture_logs

from sim.agent.dialogue import template_line
from sim.llm.client import LlmCallResult, ProfileSnapshot
from sim.llm.prompts.assembler import (
    InputSlice,
    MemorySlice,
    PlanSlice,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.identity import IdentityAnchor
from sim.npc.contract import HiddenState
from sim.npc.hidden import HiddenAttribute, HiddenProfile
from sim.npc.model import NpcProfileData
from sim.npc.speech_register import SpeechContext

if TYPE_CHECKING:
    from sim.agent.npc_l2 import L2Policy, NpcL2Service

pytestmark = pytest.mark.t1

_ACTIVE = ProfileSnapshot(
    profile_name="test-provider",
    base_url="https://llm.invalid/v1",
    model="fake-model",
    temperature=0.1,
    max_tokens=512,
    api_key_plain="fake-key-for-unit-tests",
)
_ENV_NAMES = (
    "NPC_L2_MIN_INTERVAL_SECONDS",
    "NPC_L2_CALLS_PER_MINUTE",
    "NPC_L2_TIMEOUT_SECONDS",
)
_GOOD_JSON = '{"action":"work","thought":"先把手里的木活做好。","line":""}'


@pytest.mark.parametrize("thought", ["先歇一会儿。", "我想和你一起走。", "河风一直吹着。"])
async def test_non_quantitative_everyday_phrases_remain_natural(thought: str) -> None:
    service = _service(_FakeLlm(json.dumps({"action": "rest", "thought": thought, "line": ""})))
    decision = await service.decide_once(_profile(), perception="", tick=7)
    assert decision is not None
    assert decision.thought == thought


@dataclass
class _Call:
    profile: ProfileSnapshot
    messages: list[dict[str, str]]
    max_tokens: int | None


class _FakeLlm:
    def __init__(self, content: str = _GOOD_JSON, *, error: BaseException | None = None) -> None:
        self.content = content
        self.error = error
        self.calls: list[_Call] = []
        self.entered = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.cancelled = False

    async def complete(
        self,
        profile: ProfileSnapshot,
        messages: list[dict[str, str]],
        *,
        max_tokens_override: int | None = None,
    ) -> LlmCallResult:
        self.calls.append(_Call(profile, messages, max_tokens_override))
        self.entered.set()
        try:
            if self.release is not None:
                await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.error is not None:
            raise self.error
        return LlmCallResult(
            request_id="fake-request",
            content=self.content,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=0.0,
            attempt=1,
            cache_hit=False,
        )


@dataclass
class _Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


def _service(
    llm: _FakeLlm,
    *,
    policy: L2Policy | None = None,
    clock: Callable[[], float] | None = None,
    provider: Callable[[], ProfileSnapshot | None] | None = None,
) -> NpcL2Service:
    from sim.agent.npc_l2 import L2Policy, NpcL2Service

    return NpcL2Service(
        llm=llm,
        profile_provider=provider or (lambda: _ACTIVE),
        policy=policy if policy is not None else L2Policy(),
        clock=clock or _Clock(),
    )


def _profile(npc_id: str = "villager_internal") -> NpcProfileData:
    return NpcProfileData(
        npc_id=npc_id,
        name="阿禾",
        occupation="木匠",
        lod=2,
        ocean=(73.125, 42.0, 37.0, 68.0, 15.0),
        skills={"woodwork": 83},
        identity_anchor="我是阿禾，我愿守住祖传的木工手艺。",
    )


def _hidden(*, triggered: bool = False) -> HiddenState:
    return HiddenState(
        profile=HiddenProfile(
            npc_id="villager_internal",
            attributes=(
                HiddenAttribute(
                    id="old_fear",
                    category="trauma",
                    label="怕火",
                    descriptors=("怕火",),
                    triggers=("火星",),
                ),
            ),
        ),
        triggered=frozenset({"old_fear"}) if triggered else frozenset(),
    )


async def test_l2_human_calls_model_with_only_narrative_prompt() -> None:
    llm = _FakeLlm()
    clock = _Clock()
    service = _service(llm, clock=clock)
    profile = _profile()

    first = await service.decide_once(
        profile,
        perception="集市刚收摊，有人向我招手。",
        tick=12,
        listener_id="listener_internal",
        listener_name="小满",
        memory_entries=("昨日替小满修好木凳。",),
        norms_entries=("借来的工具须归还。",),
    )
    clock.now = 60.0
    second = await service.decide_once(profile, perception="雨声渐近。", tick=99)

    assert first is not None and second is not None
    assert (first.action, first.thought, first.line, first.listener_id) == (
        "work",
        "先把手里的木活做好。",
        "",
        None,
    )
    assert len(llm.calls) == 2
    assert llm.calls[0].profile is _ACTIVE
    assert llm.calls[0].max_tokens == 192
    messages = llm.calls[0].messages
    assert messages[0] == llm.calls[1].messages[0]
    assert messages[0] == {"role": "system", "content": profile.identity_anchor + "\n\n"}
    assert "昨日替小满修好木凳。" in messages[1]["content"]
    assert "借来的工具须归还。" in messages[1]["content"]
    assert "集市刚收摊，有人向我招手。" in messages[1]["content"]
    assert "小满" in messages[1]["content"]
    assert "thought" in messages[1]["content"] and "line" in messages[1]["content"]
    assert "request_chat" in messages[1]["content"]
    for forbidden in ("villager_internal", "listener_internal", "73.125", "woodwork", "target_pos"):
        assert forbidden not in str(messages)


@pytest.mark.parametrize(
    ("species", "lod", "anchor"),
    [
        ("dog", 2, "我是阿黄。"),
        ("human", 0, "我是阿禾。"),
        ("human", 1, "我是阿禾。"),
        ("human", 2, "  "),
    ],
)
async def test_only_l2_human_with_identity_can_request(species: str, lod: int, anchor: str) -> None:
    llm = _FakeLlm()
    service = _service(llm)
    profile = replace(_profile(), species=species, lod=lod, identity_anchor=anchor)
    assert await service.decide_once(profile, perception="天色渐暗。", tick=1) is None
    assert llm.calls == []


@pytest.mark.parametrize("provider_failure", [False, True])
async def test_missing_or_unreadable_provider_is_silent_and_does_not_spend_budget(
    provider_failure: bool,
) -> None:
    from sim.agent.npc_l2 import L2Policy

    enabled = False

    def provider() -> ProfileSnapshot | None:
        if enabled:
            return _ACTIVE
        if provider_failure:
            raise RuntimeError("private-provider-error-material")
        return None

    llm = _FakeLlm()
    service = _service(llm, policy=L2Policy(max_calls_per_minute=1), provider=provider)
    with capture_logs() as logs:
        assert await service.decide_once(_profile(), perception="街上安静。", tick=1) is None
        enabled = True
        decision = await service.decide_once(_profile(), perception="街上安静。", tick=2)
    assert decision is not None
    assert len(llm.calls) == 1
    assert "private-provider-error-material" not in str(logs)


@pytest.mark.parametrize("field", ["profile_name", "base_url", "model", "api_key_plain"])
async def test_incomplete_active_provider_does_not_call_or_spend_budget(field: str) -> None:
    from sim.agent.npc_l2 import L2Policy

    active = replace(_ACTIVE, **{field: "  "})
    llm = _FakeLlm()
    service = _service(llm, policy=L2Policy(max_calls_per_minute=1), provider=lambda: active)
    assert await service.decide_once(_profile(), perception="", tick=1) is None
    assert llm.calls == []
    active = _ACTIVE
    assert await service.decide_once(_profile(), perception="", tick=2) is not None
    assert len(llm.calls) == 1


async def test_minimum_interval_is_per_npc() -> None:
    llm = _FakeLlm()
    clock = _Clock()
    service = _service(llm, clock=clock)
    assert await service.decide_once(_profile("a"), perception="", tick=1) is not None
    clock.now = 59.0
    assert await service.decide_once(_profile("a"), perception="", tick=2) is None
    assert await service.decide_once(_profile("b"), perception="", tick=2) is not None
    clock.now = 60.0
    assert await service.decide_once(_profile("a"), perception="", tick=3) is not None
    assert len(llm.calls) == 3


async def test_global_budget_uses_sliding_minute_and_reserves_before_failure() -> None:
    from sim.agent.npc_l2 import L2Policy

    llm = _FakeLlm(error=RuntimeError("private-model-error-material"))
    clock = _Clock()
    service = _service(llm, policy=L2Policy(max_calls_per_minute=2), clock=clock)
    with capture_logs() as logs:
        assert await service.decide_once(_profile("a"), perception="", tick=1) is None
        clock.now = 10.0
        assert await service.decide_once(_profile("b"), perception="", tick=2) is None
        clock.now = 59.0
        assert await service.decide_once(_profile("c"), perception="", tick=3) is None
        assert len(llm.calls) == 2
        clock.now = 60.0
        assert await service.decide_once(_profile("a"), perception="", tick=4) is None
        assert len(llm.calls) == 3
        clock.now = 69.0
        assert await service.decide_once(_profile("c"), perception="", tick=5) is None
        assert len(llm.calls) == 3
        clock.now = 70.0
        assert await service.decide_once(_profile("c"), perception="", tick=6) is None
    assert len(llm.calls) == 4
    assert "private-model-error-material" not in str(logs)


async def test_busy_request_returns_immediately_without_spending_budget() -> None:
    from sim.agent.npc_l2 import L2Policy

    llm = _FakeLlm()
    llm.release = asyncio.Event()
    service = _service(llm, policy=L2Policy(max_calls_per_minute=2))
    first = asyncio.create_task(service.decide_once(_profile("a"), perception="", tick=1))
    try:
        await asyncio.wait_for(llm.entered.wait(), timeout=0.5)
        busy = await asyncio.wait_for(
            service.decide_once(_profile("b"), perception="", tick=2), timeout=0.1
        )
        assert busy is None
        assert not first.done()
        llm.release.set()
        assert await first is not None
        assert await service.decide_once(_profile("b"), perception="", tick=3) is not None
    finally:
        llm.release.set()
        await first
    assert len(llm.calls) == 2


async def test_timeout_cancels_network_await_and_uses_existing_template() -> None:
    from sim.agent.npc_l2 import L2Policy

    llm = _FakeLlm()
    llm.release = asyncio.Event()
    service = _service(llm, policy=L2Policy(timeout_seconds=0.01, max_calls_per_minute=1))
    decision = await asyncio.wait_for(
        service.decide_once(
            _profile(),
            perception="小满朝我走来。",
            tick=7,
            listener_id="other",
            listener_name="小满",
        ),
        timeout=0.5,
    )
    assert decision is not None
    assert decision.action == "request_chat" and decision.listener_id == "other"
    assert decision.thought == ""
    assert decision.line == template_line(
        "villager_internal", "小满", 7, speech_context=SpeechContext("平民", in_circle=False)
    )
    assert llm.cancelled
    assert await service.decide_once(_profile("other"), perception="", tick=8) is None
    assert len(llm.calls) == 1


async def test_task_cancellation_propagates_and_releases_single_flight_slot() -> None:
    from sim.agent.npc_l2 import L2Policy

    llm = _FakeLlm()
    llm.release = asyncio.Event()
    service = _service(llm, policy=L2Policy(max_calls_per_minute=2))
    task = asyncio.create_task(service.decide_once(_profile("a"), perception="", tick=1))
    await asyncio.wait_for(llm.entered.wait(), timeout=0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    llm.release.set()
    assert await service.decide_once(_profile("b"), perception="", tick=2) is not None
    assert await service.decide_once(_profile("c"), perception="", tick=3) is None
    assert len(llm.calls) == 2


@pytest.mark.parametrize(
    "content",
    [
        "not JSON: raw-provider-output-private",
        "[]",
        "{}",
        '{"action":"buy","thought":"我想去买米。"}',
        '{"action":"work","thought":{},"line":""}',
        '{"action":"work","thought":42,"line":""}',
        '{"action":"work","thought":"做好木活。","raw":"private"}',
        '{"action":"work","thought":"   ","line":""}',
        '{"action":"request_chat","thought":"问问他。","line":""}',
        json.dumps({"action": "work", "thought": "木" * 161}),
        json.dumps({"action": "request_chat", "line": "话" * 161}),
    ],
)
async def test_bad_model_payload_falls_back_without_raw_output(content: str) -> None:
    llm = _FakeLlm(content)
    service = _service(llm)
    with capture_logs() as logs:
        decision = await service.decide_once(
            _profile(), perception="", tick=7, listener_id="other", listener_name="小满"
        )
    assert decision is not None and decision.action == "request_chat"
    assert decision.listener_id == "other" and decision.thought == ""
    assert decision.line == template_line(
        "villager_internal", "小满", 7, speech_context=SpeechContext("平民", in_circle=False)
    )
    assert "raw-provider-output-private" not in str(logs)


@pytest.mark.parametrize(
    "unsafe",
    [
        "我有０点力气。",
        "我还有٣分气力。",
        "我只剩२分力气。",
        "我已到二级。",
        "我的等级是二。",
        "我的档位：三。",
        "我的档位是贰。",
        "我的等级是Ⅲ。",
        "我的等级是III。",
        "我的体力是iii点。",
        "我的体力是ＩＩＩ点。",
        "我的体力是三十点。",
        "我的band是二。",
        "我的LOD已升高。",
        "villager_internal正在等我。",
        "listener_internal在门口。",
        "opaque_forbidden在门口。",
        "我的怕火又犯了。",
        '{"thought":"我要做木活。"}',
    ],
)
@pytest.mark.parametrize("field", ["thought", "line"])
async def test_both_text_fields_pass_safety_gate_before_becoming_decision(
    unsafe: str, field: str
) -> None:
    body = {"action": "request_chat", "thought": "问问眼前的人。", "line": "今天可好？"}
    body[field] = unsafe
    service = _service(_FakeLlm(json.dumps(body, ensure_ascii=False)))
    decision = await service.decide_once(
        _profile(),
        perception="",
        tick=7,
        listener_id="listener_internal",
        listener_name="小满",
        hidden=_hidden(),
        forbidden_ids=("opaque_forbidden",),
    )
    assert decision is not None
    assert decision.thought == ""
    assert decision.line == template_line(
        "villager_internal", "小满", 7, speech_context=SpeechContext("平民", in_circle=False)
    )


async def test_triggered_hidden_text_can_be_used_but_untriggered_memory_is_excluded() -> None:
    llm = _FakeLlm('{"action":"rest","thought":"怕火的旧事又想起来了。"}')
    service = _service(llm)
    rejected = await service.decide_once(
        _profile("a"),
        perception="街上很静。",
        tick=1,
        hidden=_hidden(),
        memory_entries=("我怕火。", "昨日修好木凳。"),
    )
    accepted = await service.decide_once(
        _profile("b"), perception="火星飞起。", tick=2, hidden=_hidden(triggered=True)
    )
    assert rejected is None
    assert "我怕火。" not in str(llm.calls[0].messages)
    assert "昨日修好木凳。" in str(llm.calls[0].messages)
    assert accepted is not None and accepted.thought == "怕火的旧事又想起来了。"


async def test_request_chat_uses_caller_listener_and_cleans_whitespace() -> None:
    service = _service(
        _FakeLlm('{"action":"request_chat","thought":"  问问  近况。  ","line":"  您近来可好？  "}')
    )
    decision = await service.decide_once(
        _profile(), perception="", tick=1, listener_id="real_listener", listener_name="小满"
    )
    assert decision is not None
    assert (decision.thought, decision.line, decision.listener_id) == (
        "问问 近况。",
        "您近来可好？",
        "real_listener",
    )


@pytest.mark.parametrize("action", ["eat", "rest", "work", "wander"])
async def test_finite_non_chat_actions_return_safe_thought(action: str) -> None:
    service = _service(_FakeLlm(json.dumps({"action": action, "thought": "先顾好手头的事。"})))
    decision = await service.decide_once(_profile(), perception="", tick=1)
    assert decision is not None
    assert (decision.action, decision.thought, decision.line, decision.listener_id) == (
        action,
        "先顾好手头的事。",
        "",
        None,
    )


@pytest.mark.parametrize(
    "content",
    [
        '{"action":"request_chat","thought":"想问问。","line":"您好。"}',
        '{"action":"work","thought":"","line":"您好。"}',
        "bad JSON",
    ],
)
async def test_no_listener_cannot_emit_dialogue_or_empty_success(content: str) -> None:
    service = _service(_FakeLlm(content))
    assert await service.decide_once(_profile(), perception="", tick=1) is None


async def test_unsafe_listener_name_cannot_leak_via_failure_template() -> None:
    service = _service(_FakeLlm(error=RuntimeError("unavailable")))
    decision = await service.decide_once(
        _profile(), perception="", tick=7, listener_id="other", listener_name="秘密23"
    )
    assert decision is not None
    assert "秘密23" not in decision.line and not any(c.isdecimal() for c in decision.line)
    assert decision.line == template_line(
        "villager_internal", "眼前的人", 7, speech_context=SpeechContext("平民", in_circle=False)
    )


@pytest.mark.parametrize(
    ("key", "raw", "field", "expected"),
    [
        (_ENV_NAMES[0], "oops", "min_interval_seconds", 60),
        (_ENV_NAMES[0], "NaN", "min_interval_seconds", 60),
        (_ENV_NAMES[0], "Infinity", "min_interval_seconds", 60),
        (_ENV_NAMES[0], "-1", "min_interval_seconds", 60),
        (_ENV_NAMES[0], "1", "min_interval_seconds", 5),
        (_ENV_NAMES[0], "0", "min_interval_seconds", 5),
        (_ENV_NAMES[1], "oops", "max_calls_per_minute", 4),
        (_ENV_NAMES[1], "NaN", "max_calls_per_minute", 4),
        (_ENV_NAMES[1], "Infinity", "max_calls_per_minute", 4),
        (_ENV_NAMES[1], "-1", "max_calls_per_minute", 4),
        (_ENV_NAMES[1], "1.5", "max_calls_per_minute", 4),
        (_ENV_NAMES[2], "oops", "timeout_seconds", 8),
        (_ENV_NAMES[2], "NaN", "timeout_seconds", 8),
        (_ENV_NAMES[2], "Infinity", "timeout_seconds", 8),
        (_ENV_NAMES[2], "0", "timeout_seconds", 8),
        (_ENV_NAMES[2], "-1", "timeout_seconds", 8),
    ],
)
def test_policy_environment_invalid_values_are_conservative(
    monkeypatch: pytest.MonkeyPatch, key: str, raw: str, field: str, expected: float
) -> None:
    from sim.agent.npc_l2 import L2Policy

    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(key, raw)
    assert getattr(L2Policy.from_environment(), field) == expected


async def test_environment_zero_budget_disables_all_model_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sim.agent.npc_l2 import L2Policy

    monkeypatch.setenv(_ENV_NAMES[1], "0")
    llm = _FakeLlm()
    service = _service(llm, policy=L2Policy.from_environment())
    assert await service.decide_once(_profile(), perception="", tick=1) is None
    assert llm.calls == []


def test_environment_accepts_explicit_positive_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    from sim.agent.npc_l2 import L2Policy

    monkeypatch.setenv(_ENV_NAMES[0], "7.5")
    monkeypatch.setenv(_ENV_NAMES[1], "2")
    monkeypatch.setenv(_ENV_NAMES[2], "0.25")
    policy = L2Policy.from_environment()
    assert (policy.min_interval_seconds, policy.max_calls_per_minute, policy.timeout_seconds) == (
        7.5,
        2,
        0.25,
    )


def test_l2_decision_rejects_action_outside_finite_set() -> None:
    from sim.agent.npc_l2 import L2Decision

    with pytest.raises(ValueError, match="action"):
        L2Decision(action="buy", thought="想去买米。")


def test_assembler_default_contract_is_unchanged_by_optional_requirements() -> None:
    anchor = IdentityAnchor(
        entity_id="opaque", self_narrative="我是阿禾。", persona_summary="", long_term_goal=""
    )
    default = assemble_prompt(
        anchor, MemorySlice(), SituationSlice(), PlanSlice(), InputSlice(), chain_id="default"
    )
    explicit = assemble_prompt(
        anchor,
        MemorySlice(),
        SituationSlice(),
        PlanSlice(),
        InputSlice(),
        chain_id="explicit",
        output_requirements=None,
    )
    custom = assemble_prompt(
        anchor,
        MemorySlice(),
        SituationSlice(),
        PlanSlice(),
        InputSlice(),
        chain_id="custom",
        output_requirements="只输出 action、thought、line。",
    )
    assert explicit.messages == default.messages
    assert "target_pos" in default.messages[1]["content"]
    assert custom.messages[0] == default.messages[0]
    assert "只输出 action、thought、line。" in custom.messages[1]["content"]
    assert "target_pos" not in custom.messages[1]["content"]


def test_custom_output_requirements_still_pass_assembler_terminal_scan() -> None:
    from sim.llm.prompts.assembler import PromptAssemblyError

    anchor = IdentityAnchor(
        entity_id="opaque", self_narrative="我是阿禾。", persona_summary="", long_term_goal=""
    )
    with pytest.raises(PromptAssemblyError):
        assemble_prompt(
            anchor,
            MemorySlice(),
            SituationSlice(),
            PlanSlice(),
            InputSlice(),
            chain_id="unsafe-custom",
            output_requirements="我是一个模型。",
        )
