"""Review 修复验证：C1 闸门白名单放行 buy/sell/build + prompt 动作表同步。

端到端经闸门路径（不绕 validate）——修复前 validate 拒绝 unsupported_action。
"""

from sim.agent.gate import IntentGate
from sim.agent.intent import Intent, IntentAction
from sim.core.world import EntityState, WorldState
from sim.llm.prompts.assembler import _REQUIREMENTS_TEXT


def test_gate_accepts_buy_sell_build():
    """C1：buy/sell/build 过闸门（E3/E4 执行面已就位，白名单收口）。"""
    gate = IntentGate()
    state = WorldState(
        world_seed=42,
        entities={
            "chenmo": EntityState(entity_id="chenmo", pos=(30, 46)),
        },
    )
    cases: tuple[tuple[IntentAction, dict[str, object]], ...] = (
        ("buy", {"target_id": "herb"}),
        ("sell", {"target_id": "herb"}),
        ("build", {"target_pos": (34, 46)}),
    )
    for action, kwargs in cases:
        intent = Intent(action=action, reason="铺子里该进货了", confidence=0.9, **kwargs)  # type: ignore[arg-type]
        verdict = gate.validate(intent, state, "chenmo")
        assert verdict.accepted, f"{action} 被闸门拒绝: {verdict.reason}"


def test_gate_still_rejects_demolish_and_use():
    """无执行面的动作仍拒绝（白名单收口不扩面）。"""
    gate = IntentGate()
    state = WorldState(world_seed=42)
    for action in ("demolish", "use"):
        intent = Intent(action=action, reason="试试", confidence=0.9, target_id="chenmo")
        verdict = gate.validate(intent, state, "chenmo")
        assert verdict.rejected and verdict.reason == "unsupported_action"


def test_prompt_requirements_list_trade_and_build():
    """C1 配套：LLM 输出契约列出 buy/sell/build（模型才知道能输出什么）。"""
    assert "buy" in _REQUIREMENTS_TEXT
    assert "sell" in _REQUIREMENTS_TEXT
    assert "build" in _REQUIREMENTS_TEXT
    assert "attack" in _REQUIREMENTS_TEXT
    assert "talk_to" in _REQUIREMENTS_TEXT
