"""sim.agent.driver — 陈默 L2 决策驱动（批次 C：LLM 接进决策循环）。

管线（每决策轮）：assemble_prompt → LlmClient.complete → parse_intent →
IntentGate.validate（规划时预检）→ pending 队列 → 执行 tick
revalidate_at_execution（二次校验）→ MOVE 事件 + npc_monologue。

铁律落点：
- C1 闸门两道校验（LLM 永不直接改世界）——validate/revalidate 都是纯读；
- C4 唯一写路径——产出只有 move/monologue 事件，经 loop.enqueue 入流；
- 幻觉隔离——解析失败/闸门拒绝本轮零事件；
- 世界照常运转——LlmError/无 profile 降级跳过，不抛不阻塞。

成本治理：profile_provider 返回 None（无 active profile）时零调用；
调用由外层循环按节拍（默认 60s，CHENMO_DECIDE_SECONDS 可调）+ impulse
即时置位驱动；本模块不做计时（可测性：decide_once/execute_pending 纯同步步）。
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable

import structlog

from sim.agent.gate import IntentGate
from sim.agent.intent import Intent, parse_intent
from sim.core.tick import TickLoop
from sim.core.world import WorldState
from sim.llm.client import LlmClient, LlmError, ProfileSnapshot
from sim.llm.prompts.assembler import (
    InputSlice,
    MemorySlice,
    PlanSlice,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.identity import IdentityAnchor

logger = structlog.get_logger(__name__)

#: player_impulse 文本挂到 chenmo 决策的槽位（最近一条；None = 无新念头）
ImpulseText = str


class ChenmoDriver:
    """陈默 L2 决策驱动：异步决策 + 同步执行两段式（LLM 延迟天然无害，§8）。"""

    def __init__(
        self,
        anchor: IdentityAnchor,
        llm: LlmClient,
        profile_provider: Callable[[], ProfileSnapshot | None],
        perception_provider: Callable[[], str] | None = None,
    ) -> None:
        self._anchor = anchor
        self._llm = llm
        self._profile_provider = profile_provider
        # 批次 D6：实况感知投影供数（main.py 装配：chenmo 感知帧 → narrated()）。
        # None = 无感知面（测试/降级，[处境] 段省略——既有行为）。
        self._perception_provider = perception_provider
        self._gate = IntentGate()
        self._pending: deque[Intent] = deque()
        # impulse 置位（ws handler 在事件循环线程调，driver 循环也在事件循环——
        # 单线程语义本就安全；锁是防御性的，防将来跨线程调用）
        self._requested_lock = threading.Lock()
        self._requested = False
        self._last_impulse: ImpulseText | None = None

    # -- impulse 触发面（ws.py impulse handler 调用） -----------------------

    def request_decision(self, impulse_text: str | None = None) -> None:
        """置位下一轮决策（立即，不等节拍）；可携带玩家念头文本。"""
        with self._requested_lock:
            self._requested = True
            if impulse_text:
                self._last_impulse = impulse_text

    def take_requested(self) -> bool:
        """消费置位（一次）；driver 循环每拍调用。"""
        with self._requested_lock:
            if self._requested:
                self._requested = False
                return True
            return False

    def take_impulse(self) -> str | None:
        """取走最近念头文本（一次）；decide_once 的 [输入] 段供数。"""
        text = self._last_impulse
        self._last_impulse = None
        return text

    # -- 决策轮（async：调 LLM） -------------------------------------------

    async def decide_once(
        self,
        state: WorldState,
        tick: int,
        *,
        memory_entries: tuple[str, ...] = (),
        perception_text: str = "",
        interoception_text: str = "",
    ) -> bool:
        """一轮决策：prompt → LLM → 解析 → 闸门 → pending。True = 有意图入队。

        任何失败（无 profile / LlmError / 解析失败 / 闸门拒绝）→ False +
        结构化日志，**零事件**（世界照常运转；闸门拒绝时 pending 不动）。
        """
        profile = self._profile_provider()
        if profile is None:
            logger.debug("chenmo.no_profile", tick=tick)
            return False
        impulse = self.take_impulse()
        if perception_text == "" and self._perception_provider is not None:
            try:
                perception_text = self._perception_provider()
            except Exception as exc:  # 感知面故障不拖垮决策（降级空处境）
                logger.warning("chenmo.perception_failed", detail=str(exc))
                perception_text = ""
        prompt = assemble_prompt(
            anchor=self._anchor,
            memory=MemorySlice(entries=memory_entries),
            situation=SituationSlice(
                perception_text=perception_text, interoception_text=interoception_text
            ),
            plan=PlanSlice(),
            user_input=InputSlice(thought=impulse or ""),
            chain_id=f"chenmo-{tick}",
        )
        try:
            result = await self._llm.complete(profile, list(prompt.messages))
        except LlmError as exc:
            logger.warning("chenmo.llm_error", tick=tick, error_kind=exc.error_kind)
            return False
        try:
            intent = parse_intent(result.content)
        except Exception as exc:  # IntentParseError 及任何解析异常
            logger.warning("chenmo.parse_failed", tick=tick, detail=str(exc))
            return False
        verdict = self._gate.validate(intent, state, self._anchor.entity_id)
        if verdict.rejected:
            logger.info("chenmo.gate_rejected", tick=tick, reason=verdict.reason)
            return True  # 决策成立但被闸门拦下（幻觉隔离：不入 pending）
        self._pending.append(intent)
        return True

    # -- 执行段（同步：闸门二次校验 + 事件入流） -----------------------------

    def execute_pending(self, loop: TickLoop, *, pathfinder: object) -> int:
        """执行全部 pending：revalidate → MOVE（move_to）+ thought 独白。

        返回执行条数。寻路失败/目标过期 → 丢弃该条（重规划交给下一轮决策）。
        """
        executed = 0
        while self._pending:
            intent = self._pending.popleft()
            actor_id = self._anchor.entity_id
            verdict = self._gate.revalidate_at_execution(
                intent, loop.state, actor_id, planned_tick=loop.state.tick
            )
            if verdict.rejected:
                logger.info("chenmo.revalidate_rejected", reason=verdict.reason)
                continue
            if (
                intent.action == "move_to"
                and intent.target_pos is not None
                and not self._issue_move(loop, pathfinder, actor_id, intent.target_pos)
            ):
                # 寻路失败 → 意图不整条丢弃：落 thought 独白（心里想去，脚下去不了
                # —— 模型给的格子可能在屋顶/树墙内）。真实交付失败由下一轮重规划。
                logger.info("chenmo.move_unreachable_fallback", goal=str(intent.target_pos))
            from sim.core.events import npc_monologue_event

            loop.enqueue(
                npc_monologue_event(
                    tick=loop.state.tick + 1,
                    npc_id=actor_id,
                    form="thought",
                    content=intent.reason,
                )
            )
            executed += 1
        return executed

    @staticmethod
    def _issue_move(
        loop: TickLoop, pathfinder: object, actor_id: str, goal: tuple[int, int]
    ) -> bool:
        """move_to → issue_move（真寻路）；失败 False（fail-soft，独白仍出）。"""
        from sim.world.pathfinding import Pathfinder

        if not isinstance(pathfinder, Pathfinder):
            return False
        entity = loop.state.entities.get(actor_id)
        if entity is None:
            return False
        try:
            path = pathfinder.find(entity.pos, goal)
        except ValueError as exc:
            logger.info("chenmo.move_unreachable", goal=str(goal), detail=str(exc))
            return False
        try:
            loop.issue_move(actor_id, list(path))
        except ValueError as exc:
            logger.info("chenmo.move_failed", detail=str(exc))
            return False
        return True
