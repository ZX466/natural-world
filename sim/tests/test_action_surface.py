"""B4：prompt 里的地图尺寸必须是真的；动作面各层必须一一对应。"""

from __future__ import annotations

import re
from typing import get_args

from sim.agent.gate import M1_SUPPORTED_ACTIONS
from sim.agent.intent import IntentAction
from sim.llm.prompts.assembler import _REQUIREMENTS_TEXT


def test_prompt_states_the_real_map_size() -> None:
    assert "140×100" in _REQUIREMENTS_TEXT
    assert "96×96" not in _REQUIREMENTS_TEXT


def test_only_demolish_and_use_are_parseable_but_gated_out() -> None:
    """这两个有意保留在解析层、被闸门明确拒（明确拒绝 > 解析错误）。"""
    assert set(get_args(IntentAction)) - M1_SUPPORTED_ACTIONS == {"demolish", "use"}


def test_prompt_lists_every_supported_executable_action() -> None:
    actions = re.search(r"action（必须是这些之一：(.*?)）", _REQUIREMENTS_TEXT)
    assert actions is not None
    assert set(actions[1].split("、")) == M1_SUPPORTED_ACTIONS


def test_transfer_prompt_defines_item_and_quantity_without_exposing_stock_refs() -> None:
    assert "take" in _REQUIREMENTS_TEXT and "give" in _REQUIREMENTS_TEXT
    assert "item" in _REQUIREMENTS_TEXT and "quantity" in _REQUIREMENTS_TEXT
    assert "木料" in _REQUIREMENTS_TEXT
    assert "npc:" not in _REQUIREMENTS_TEXT and "world:" not in _REQUIREMENTS_TEXT
