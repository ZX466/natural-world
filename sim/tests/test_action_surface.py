"""B4：prompt 里的地图尺寸必须是真的；动作面各层必须一一对应。"""

from __future__ import annotations

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


def test_the_known_silent_actions_are_explicitly_listed() -> None:
    """take/give 本轮不动（用户裁定单列）：它们落到尾部独白、零副作用。

    这条把「已知的技术债」显式钉住，防止它悄悄扩大，也防止有人删掉白名单项
    却忘了同步这个清单。
    """
    known_silent = {"take", "give"}
    assert known_silent <= M1_SUPPORTED_ACTIONS, "技术债项若已移除，请同步更新本测试"
