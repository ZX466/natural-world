"""B4：prompt 里的地图尺寸必须是真的；动作面各层必须一一对应。"""

from __future__ import annotations

import json
import re
from typing import get_args

import pytest

from sim.agent.gate import M1_SUPPORTED_ACTIONS, IntentGate
from sim.agent.intent import IntentAction, parse_intent
from sim.core.world import EntityState, WorldState
from sim.llm.prompts.assembler import _REQUIREMENTS_TEXT
from sim.npc.hidden import HiddenAttribute, HiddenProfile


@pytest.fixture()
def self_action_state() -> WorldState:
    return WorldState(
        world_seed=7,
        tick=100,
        entities={"chenmo": EntityState(entity_id="chenmo", pos=(100, 53))},
    )


def test_prompt_states_the_real_map_size() -> None:
    assert "140×100" in _REQUIREMENTS_TEXT
    assert "96×96" not in _REQUIREMENTS_TEXT


def test_only_demolish_and_use_are_parseable_but_gated_out() -> None:
    """这两个有意保留在解析层、被闸门明确拒（明确拒绝 > 解析错误）。"""
    assert set(get_args(IntentAction)) - M1_SUPPORTED_ACTIONS == {"demolish", "use"}


def test_prompt_lists_every_supported_executable_action() -> None:
    actions = re.search(r"action（必须是这些之一：(.*?)）", _REQUIREMENTS_TEXT)
    assert actions is not None
    listed_actions = set(actions[1].split("、"))
    assert {"work", "eat", "rest"} <= listed_actions
    assert listed_actions == M1_SUPPORTED_ACTIONS


def test_transfer_prompt_defines_item_and_quantity_without_exposing_stock_refs() -> None:
    assert "take" in _REQUIREMENTS_TEXT and "give" in _REQUIREMENTS_TEXT
    assert "item" in _REQUIREMENTS_TEXT and "quantity" in _REQUIREMENTS_TEXT
    assert "木料" in _REQUIREMENTS_TEXT
    assert "npc:" not in _REQUIREMENTS_TEXT and "world:" not in _REQUIREMENTS_TEXT


@pytest.mark.parametrize("action", ("work", "eat", "rest"))
def test_self_actions_pass_both_gates_without_a_target(
    action: str, self_action_state: WorldState
) -> None:
    intent = parse_intent(json.dumps({"action": action, "reason": "先顾好眼下的事。"}))
    assert intent.action == action
    assert intent.target_id is None and intent.target_pos is None

    gate = IntentGate()
    assert gate.validate(intent, self_action_state, "chenmo").accepted
    assert gate.revalidate_at_execution(intent, self_action_state, "chenmo", 99).accepted


@pytest.mark.parametrize("action", ("work", "eat", "rest"))
def test_self_actions_do_not_bypass_unknown_target_rejection(
    action: str, self_action_state: WorldState
) -> None:
    intent = parse_intent(
        json.dumps({"action": action, "target_id": "药铺", "reason": "先顾好眼下的事。"})
    )
    verdict = IntentGate().validate(intent, self_action_state, "chenmo")
    assert verdict.rejected and verdict.reason == "unknown_target"


@pytest.mark.parametrize("action", ("work", "eat", "rest"))
def test_self_actions_do_not_bypass_banned_reason_scan(
    action: str, self_action_state: WorldState
) -> None:
    intent = parse_intent(json.dumps({"action": action, "reason": "先读档重来。"}))
    verdict = IntentGate().validate(intent, self_action_state, "chenmo")
    assert verdict.rejected and verdict.reason == "banned_reason"


@pytest.mark.parametrize("action", ("work", "eat", "rest"))
def test_self_actions_do_not_bypass_hidden_reason_scan(
    action: str, self_action_state: WorldState
) -> None:
    hidden = HiddenProfile(
        npc_id="chenmo",
        attributes=(
            HiddenAttribute(
                id="chenmo.trauma",
                category="trauma",
                label="暗夜惊惧",
                descriptors=("暗夜惊惧",),
                triggers=("入夜",),
            ),
        ),
    )
    intent = parse_intent(json.dumps({"action": action, "reason": "暗夜惊惧又犯了。"}))
    gate = IntentGate()
    verdict = gate.revalidate_at_execution(intent, self_action_state, "chenmo", 99, hidden)
    assert verdict.rejected and verdict.reason == "hidden_attribute_leak"
    assert gate.revalidate_at_execution(
        intent, self_action_state, "chenmo", 99, hidden, frozenset({"chenmo.trauma"})
    ).accepted
