"""意图闸门 — LLM 永不直接修改世界（C1，DESIGN §8，TASK-C06-⑤）。

两道校验：
- 规划时预检（validate）：闸门建议性检查——动作枚举已由 schema 保证，
  这里查语义（目标存在/距离可达/reason 非空/置信度）。拒绝 = 结构化
  原因反馈重规划（§19：不静默丢弃）。
- 执行时二次校验（revalidate_at_execution）：Intent 入队后在执行 tick
  再校验一次——世界已变化导致的过期 Intent 丢弃并触发重规划。
  LLM 异步延迟因此天然无害（§8）。

幻觉隔离（铁律 4）：闸门拒绝的 Intent 不产生任何事件；
validate/revalidate 都是纯读（世界快照前后一致，测试断言）。
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from sim.agent.intent import REPLAN_CONFIDENCE_THRESHOLD, Intent
from sim.core.world import WorldState

logger = structlog.get_logger(__name__)

#: M1 支持动作白名单外的动作（build/demolish 等无引擎支撑）一律拒绝。
M1_SUPPORTED_ACTIONS = frozenset(
    {"move_to", "wait", "talk_to", "take", "give", "flee", "investigate", "attack"}
)

#: talk_to / take 等目标动作的目标最大距离（M1 简化：视觉半径内语义）。
_TARGET_MAX_DISTANCE = 12.0


@dataclass(frozen=True)
class GateVerdict:
    """闸门裁决。rejected=True 时 reason 是结构化原因（供重规划/观测）。"""

    accepted: bool
    reason: str = ""  # "ok" | "unsupported_action" | "missing_target" | ...

    @property
    def rejected(self) -> bool:
        return not self.accepted


def _target_visible(intent: Intent, state: WorldState, actor_id: str) -> bool:
    """目标在本 tick 状态里是否存在/可见（M1：目标实体存在即视为可见）。"""
    if intent.target_id is not None:
        return intent.target_id in state.entities
    if intent.target_pos is not None:
        x, y = intent.target_pos
        return x >= 0 and y >= 0  # M1 简化：坐标非负即合法（地图校验在寻路层）
    return False


class IntentGate:
    """无状态闸门（纯读）。所有裁决可重放、可测试。"""

    def validate(self, intent: Intent, state: WorldState, actor_id: str) -> GateVerdict:
        """规划时预检：schema 之后的语义层。"""
        if intent.action not in M1_SUPPORTED_ACTIONS:
            return GateVerdict(False, "unsupported_action")
        if not intent.reason.strip():
            return GateVerdict(False, "empty_reason")
        if intent.confidence < REPLAN_CONFIDENCE_THRESHOLD:
            return GateVerdict(False, "low_confidence")
        if intent.action in ("talk_to", "take", "give", "attack", "use") and (
            intent.target_id is None and intent.target_pos is None
        ):
            return GateVerdict(False, "missing_target")
        if intent.target_id is not None and intent.target_id not in state.entities:
            return GateVerdict(False, "unknown_target")
        if intent.target_pos is not None:
            x, y = intent.target_pos
            if not (0 <= x < 4096 and 0 <= y < 4096):
                return GateVerdict(False, "out_of_bounds")
        return GateVerdict(True, "ok")

    def revalidate_at_execution(
        self, intent: Intent, state: WorldState, actor_id: str, planned_tick: int
    ) -> GateVerdict:
        """执行 tick 二次校验：世界已变 → 过期 Intent 丢弃触发重规划。

        M1 检查两项：目标仍存在（可能已离开/消亡）+ 目标距离仍可达。
        """
        if intent.action in ("talk_to", "take", "give", "attack", "use"):
            if intent.target_id is not None and intent.target_id not in state.entities:
                return GateVerdict(False, "target_gone")
            if intent.target_id is not None:
                actor = state.entities.get(actor_id)
                target = state.entities.get(intent.target_id)
                if actor is not None and target is not None:
                    dx = target.pos[0] - actor.pos[0]
                    dy = target.pos[1] - actor.pos[1]
                    if (dx * dx + dy * dy) ** 0.5 > _TARGET_MAX_DISTANCE:
                        return GateVerdict(False, "target_out_of_range")
        # move_to：目标点不再可达（M1 简化为越界即过期）
        if intent.action == "move_to" and intent.target_pos is not None:
            x, y = intent.target_pos
            if not (0 <= x < 4096 and 0 <= y < 4096):
                return GateVerdict(False, "out_of_bounds")
        logger.debug(
            "intent.revalidated",
            actor=actor_id,
            action=intent.action,
            planned_tick=planned_tick,
            executed_tick=state.tick,
        )
        return GateVerdict(True, "ok")
