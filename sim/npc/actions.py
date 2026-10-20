"""sim.npc.actions — L1 动作白名单（M2-A1 §2.1；codex M2-S2 审查对象）。

六个基础动作加显式 build；payload 白名单防扩展时夹带字段。
"""

from __future__ import annotations

from typing import Final

ACTION_WHITELIST: Final[frozenset[str]] = frozenset(
    {
        "move",  # 移动（沿用 pathfinding）
        "work",  # 工作（日程/差事）
        "eat",
        "rest",
        "wander",  # 闲逛（RNG 目的点）
        "request_chat",  # 交谈请求（升格 L2 触发器之一）
        "build",  # 显式建造意图；坐标和资金在执行边界再次校验
    }
)

# NPC_ACT payload 允许字段（NpcAction 之外的动作参数面）
ACTION_PAYLOAD_KEYS: Final[dict[str, frozenset[str]]] = {
    "move": frozenset({"path"}),
    "work": frozenset({"site"}),
    "eat": frozenset({"food_id"}),
    "rest": frozenset({"hours"}),
    "wander": frozenset({"radius"}),
    "request_chat": frozenset({"to_npc"}),
    "build": frozenset({"x", "y"}),
}


def is_action_allowed(action: str) -> bool:
    return action in ACTION_WHITELIST


def payload_keys_allowed(action: str, keys: set[str]) -> bool:
    return is_action_allowed(action) and keys <= set(ACTION_PAYLOAD_KEYS[action])
