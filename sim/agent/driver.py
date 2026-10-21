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
from typing import Any

import structlog

from sim.agent.gate import IntentGate
from sim.agent.intent import Intent, parse_intent
from sim.agent.targets import nearby_actor_names, resolve_actor_target, resolve_good_target
from sim.core.events import WorldEvent
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
from sim.npc.speech_register import SpeechContext

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
        display_name_of: Callable[[str], str | None] | None = None,
        economy_provider: Callable[[], tuple[Any, int]] | None = None,
        build_runtime_provider: Callable[[], Any] | None = None,
        combat_provider: Callable[[], tuple[Any, int]] | None = None,
        entropy_provider: Callable[[str, int], WorldEvent] | None = None,
        speech_context_provider: Callable[[str | None], SpeechContext] | None = None,
    ) -> None:
        self._anchor = anchor
        self._llm = llm
        self._profile_provider = profile_provider
        # 批次 D6：实况感知投影供数（main.py 装配：chenmo 感知帧 → narrated()）。
        # None = 无感知面（测试/降级，[处境] 段省略——既有行为）。
        self._perception_provider = perception_provider
        # 批次 E1：戏内名映射注入（entity_id → 戏内名；分层红线：agent 域禁
        # import sim.api，名字映射由 main.py 装配传入 _display_names.get）。
        self._display_name_of = display_name_of or (lambda _eid: None)
        # 批次 E3：经济面注入（() -> (CoinLedger, world_seed)）；None = 无买卖面。
        self._economy = economy_provider
        # 批次 E4：施工面注入（() -> BuildRuntime）；None = 无建造面。
        self._build = build_runtime_provider
        # 批次 E6：战斗面注入（() -> (CombatLedger, world_seed)）；None = 无攻击面。
        self._combat = combat_provider
        self._entropy_provider = entropy_provider
        self._speech_context_of = speech_context_provider
        self._gate = IntentGate()
        self._pending: deque[Intent] = deque()
        self._chat_lines: dict[int, str] = {}
        # 批次 E6 战斗尺（§9）：attack 命中 → 进战斗尺 60 tick；过期即退出。
        # None = 不在战斗尺；issue_combat_scale 发既有 combat.scale_change 事件。
        self._combat_until_tick: int | None = None
        self._exchange: Any = None
        self._combat_target: str | None = None
        self._combat_tick_last = 0
        self._combat_visual_index = 0
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
        landmarks_text: str = "",
    ) -> bool:
        """一轮决策：prompt → LLM → 解析 → 闸门 → pending。

        无 profile / LlmError / 解析失败返回 False；正常解析的决策轮返回 True。
        闸门拒绝只记结构化日志，不入 pending、不产事件，沿既有节拍等待下一轮。
        """
        profile = self._profile_provider()
        if profile is None:
            logger.debug("chenmo.no_profile", tick=tick)
            return False
        impulse = self.take_impulse()
        if self._exchange is not None:
            perception_text += "\n正在交手，可进攻、防御、拉开、瞄准要害、逃跑或喊话。"
        if perception_text == "" and self._perception_provider is not None:
            try:
                perception_text = self._perception_provider()
            except Exception as exc:  # 感知面故障不拖垮决策（降级空处境）
                logger.warning("chenmo.perception_failed", detail=str(exc))
                perception_text = ""
        display_names = {
            entity_id: name
            for entity_id in state.entities
            if (name := self._display_name_of(entity_id))
        }
        people = nearby_actor_names(
            state, display_names=display_names, actor_id=self._anchor.entity_id
        )
        people_text = f"你认得这些人：{'、'.join(people)}。" if people else ""
        prompt = assemble_prompt(
            anchor=self._anchor,
            memory=MemorySlice(entries=memory_entries),
            situation=SituationSlice(
                perception_text=perception_text,
                interoception_text=interoception_text,
                landmarks_text="\n".join(text for text in (landmarks_text, people_text) if text),
            ),
            plan=PlanSlice(),
            user_input=InputSlice(thought=impulse or ""),
            chain_id=f"chenmo-{tick}",
            speech_context=self._speech_context_of(None) if self._speech_context_of else None,
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
        if intent.target_id is not None:
            resolved = (
                resolve_good_target(intent.target_id)
                if intent.action in ("buy", "sell")
                else resolve_actor_target(
                    intent.target_id,
                    state,
                    display_names=display_names,
                    actor_id=self._anchor.entity_id,
                )
            )
            if resolved is not None:
                intent = intent.model_copy(update={"target_id": resolved})
            # 未解析的原文仍送既有 gate，不把幻觉/重名改成可执行目标。
        verdict = self._gate.validate(intent, state, self._anchor.entity_id)
        if verdict.rejected:
            if intent.action in ("buy", "sell"):
                logger.info(
                    "chenmo.trade_rejected",
                    tick=tick,
                    action=intent.action,
                    target_id=intent.target_id,
                    reason=verdict.reason,
                )
            logger.info(
                "chenmo.gate_rejected",
                tick=tick,
                reason=verdict.reason,
                action=intent.action,
                target_id=intent.target_id,
                reason_len=len(intent.reason),
            )
            return True  # 决策成立但被闸门拦下（幻觉隔离：不入 pending）
        if intent.action == "talk_to" and intent.target_id is not None:
            self._chat_lines[id(intent)] = await self._dialogue_line(
                profile, intent.target_id, intent.reason, tick
            )
        self._pending.append(intent)
        return True

    async def _dialogue_line(
        self, profile: ProfileSnapshot, target_id: str, context: str, tick: int
    ) -> str:
        from sim.agent.dialogue import template_line
        from sim.llm.prompts.assembler import (
            InputSlice,
            MemorySlice,
            PlanSlice,
            SituationSlice,
            assemble_prompt,
        )

        name = self._display_name_of(target_id) or "眼前的人"
        context_register = self._speech_context_of(target_id) if self._speech_context_of else None
        fallback = template_line(
            self._anchor.entity_id, name, tick, speech_context=context_register
        )
        prompt = assemble_prompt(
            anchor=self._anchor,
            memory=MemorySlice(),
            situation=SituationSlice(),
            plan=PlanSlice(),
            user_input=InputSlice(
                dialogue=(
                    f"你正与{name}当面交谈。对话缘由：{context}。"
                    "请只写一句自然、简短的戏内对白，不要解释，不要JSON。"
                )
            ),
            chain_id=f"chat-{tick}-{target_id}",
            speech_context=context_register,
        )
        try:
            result = await self._llm.complete(
                profile, list(prompt.messages), max_tokens_override=64
            )
        except (LlmError, TypeError):
            return fallback
        # T4 泄漏修复(2026-10-11):复读剥离判梯先行(≤2 可映射命中→改写),
        # 改不动再走既有硬拒(退模板池)——不绕任何既有钉。
        from sim.agent.dialogue import sanitize_provider_line

        return sanitize_provider_line(result.content) or fallback

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
                self._chat_lines.pop(id(intent), None)
                if intent.action in ("buy", "sell"):
                    logger.info(
                        "chenmo.trade_rejected",
                        tick=loop.state.tick,
                        action=intent.action,
                        target_id=intent.target_id,
                        reason=verdict.reason,
                    )
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
            elif intent.action == "talk_to" and intent.target_id is not None:
                self._issue_talk(loop, pathfinder, actor_id, intent)
            elif intent.action == "investigate" and intent.target_pos is not None:
                self._issue_investigate(loop, pathfinder, actor_id, intent.target_pos)
            elif intent.action in ("buy", "sell") and intent.target_id is not None:
                if self._economy is not None:
                    self._issue_trade(loop, intent)
            elif intent.action == "build" and intent.target_pos is not None:
                if self._build is not None and self._economy is not None:
                    self._issue_build(loop, actor_id, intent)
            elif intent.action == "attack" and intent.target_id is not None:
                if self._combat is not None:
                    if self._exchange is not None:
                        self._exchange.prefetch(intent.params.get("posture", "attack"))
                    else:
                        self._issue_attack(loop, actor_id, intent)
            elif intent.action == "flee" and intent.target_id is not None:
                self._issue_flee(loop, pathfinder, actor_id, intent.target_id)
            from sim.core.events import npc_monologue_event

            # 批次 E（review M3）：buy/sell/build/attack 的 handler 已出**结果**
            # 独白（买了/没买成/伤了/杀了）——尾部 reason（动机）独白对这四类
            # 不重发（一意图两条 thought 是面板噪声）；其余动作 reason 即独白。
            if intent.action not in ("buy", "sell", "build", "attack"):
                loop.enqueue(
                    npc_monologue_event(
                        tick=loop.state.tick + 1,
                        npc_id=actor_id,
                        form="thought",
                        content=intent.reason,
                    )
                )
            executed += 1
        # 战斗尺过期退出（E6：意图队列清空后检查——窗口过完恢复原倍率）。
        if self._combat_until_tick is not None and loop.state.tick >= self._combat_until_tick:
            self.reset_combat()
            loop.issue_combat_scale(False)
        return executed

    def reset_combat(self) -> None:
        self._combat_visual_index = 0
        self._combat_until_tick = None
        self._exchange = None
        self._combat_target = None
        self._pending.clear()
        self._chat_lines.clear()

    def combat_tick(self, loop: TickLoop, *, pathfinder: object) -> None:
        """同步交换单元，不等 LLM；边界预取，迟到的姿态顺延下一单元。"""
        if self._exchange is None:
            return
        actor_id = self._anchor.entity_id
        target = self._combat_target
        if actor_id not in loop.state.entities or target not in loop.state.entities:
            self.reset_combat()
            loop.issue_combat_scale(False)
            return
        tick = loop.state.tick
        if self._combat_until_tick is not None and tick >= self._combat_until_tick:
            self.reset_combat()
            loop.issue_combat_scale(False)
            return
        elapsed = tick - self._combat_tick_last
        if elapsed <= 0:
            return
        boundary = self._exchange.elapsed + elapsed >= 10
        self._exchange.advance(elapsed)
        self._combat_tick_last = tick
        if not boundary:
            return
        self.request_decision()
        posture = self._exchange.active_posture
        loop.pending_combat_visuals.append((self._combat_visual_index, actor_id, posture))
        self._combat_visual_index += 1
        from sim.agent.intent import Intent
        from sim.core.events import npc_monologue_event

        if posture in ("attack", "aim"):
            self._issue_attack(
                loop,
                actor_id,
                Intent(
                    action="attack",
                    target_id=target,
                    params={"posture": posture},
                    reason="护住自己。",
                ),
            )
        elif posture in ("withdraw", "flee"):
            self._issue_flee(loop, pathfinder, actor_id, target)
            if posture == "flee":
                self.reset_combat()
                loop.issue_combat_scale(False)
                return
        elif posture == "shout":
            loop.enqueue(
                npc_monologue_event(
                    tick=tick, npc_id=actor_id, form="bubble", content="乡亲们，快来帮忙！"
                )
            )
        else:
            loop.enqueue(
                npc_monologue_event(
                    tick=tick, npc_id=actor_id, form="thought", content="护住要害，等他露出破绽。"
                )
            )
        # 对手仍在近身，下一招由同一结算/熵入口完成。
        if target in loop.state.entities and actor_id in loop.state.entities:
            self._issue_attack(
                loop, target, Intent(action="attack", target_id=actor_id, reason="挡住这一招。")
            )

    def _issue_talk(
        self, loop: TickLoop, pathfinder: object, actor_id: str, intent: Intent
    ) -> None:
        """talk_to：走向目标（寻路可达才发 MOVE）+ npc.chat 事件（批次 E1）。

        台词走模板池（C5 确定性）；对方听得见 → chat 是外在可观察面。
        """
        from sim.agent.dialogue import template_line
        from sim.core.events import npc_chat_event

        state = loop.state
        target_id = intent.target_id
        if target_id is None:  # pyright 收窄（调用分支已保证非 None）
            return
        target = state.entities.get(target_id)
        actor = state.entities.get(actor_id)
        if target is None or actor is None:
            return
        # 走向目标：曼哈顿 > 2 格才需要 MOVE（贴脸直接说）
        dx, dy = target.pos[0] - actor.pos[0], target.pos[1] - actor.pos[1]
        if abs(dx) + abs(dy) > 2:
            from sim.world.pathfinding import Pathfinder

            if isinstance(pathfinder, Pathfinder):
                try:
                    path = pathfinder.find(actor.pos, target.pos)
                    loop.issue_move(actor_id, list(path))
                except ValueError:
                    pass  # 不可达：原地喊话（fail-soft，聊天仍发生）
        listener_name = self._display_name_of(target_id) or "眼前的人"
        line = self._chat_lines.pop(id(intent), None)
        if line is None:
            context = self._speech_context_of(target_id) if self._speech_context_of else None
            line = template_line(actor_id, listener_name, state.tick, speech_context=context)
        loop.enqueue(npc_chat_event(tick=state.tick, npc_id=actor_id, to_id=target_id, line=line))

    def _issue_trade(self, loop: TickLoop, intent: Intent) -> None:
        """buy/sell：查价 → 余额判定 → coin.grant 事件 + 独白结果（E3 最小面）。

        target_id 存货名（herb/salve/meal）。买不起=零 grant + 叙事独白
        （fail-soft：买不起是戏内常态，不是错误）。铜钱数额是戏内事实可出站。
        """
        from sim.core.events import coin_grant_event, npc_monologue_event
        from sim.world.economy import _GOOD_INDEX, buy_price

        good = _GOOD_INDEX.get(intent.target_id or "")
        if good is None:
            logger.info(
                "chenmo.trade_rejected",
                tick=loop.state.tick,
                action=intent.action,
                target_id=intent.target_id,
                reason="unknown_good",
            )
            return
        if self._economy is None:
            return
        actor_id = self._anchor.entity_id
        ledger, seed = self._economy()
        tick = loop.state.tick
        price = buy_price(good.id, tick=tick, seed=seed)
        if intent.action == "buy":
            ok = ledger.apply_grant(actor_id, -price, tick=tick)
            if ok:
                loop.enqueue(
                    coin_grant_event(
                        tick=tick, owner_id=actor_id, delta=-price, note=f"buy:{good.id}"
                    )
                )
                content = f"这剂{good.name}花了{price}文，值。"
            else:
                content = f"摸遍全身也凑不齐这{price}文，{good.name}先记着吧。"
        else:  # sell：E3 简化——卖=凭手艺挣工钱口径（无库存面），得半价
            earned = max(1, price // 2)
            ledger.apply_grant(actor_id, earned, tick=tick)
            loop.enqueue(
                coin_grant_event(tick=tick, owner_id=actor_id, delta=earned, note=f"sell:{good.id}")
            )
            content = f"出手一批{good.name}，进账{earned}文。"
        loop.enqueue(
            npc_monologue_event(tick=tick + 1, npc_id=actor_id, form="thought", content=content)
        )

    def _issue_build(self, loop: TickLoop, actor_id: str, intent: Intent) -> None:
        """L2 与 NPC 共用到站/资金/退款判据和结构事件翻译。"""
        from sim.core.events import npc_act_event
        from sim.npc.build_action import build_action_events
        from sim.world.economy import CoinLedger

        assert self._build is not None
        build_runtime = self._build()
        pos = intent.target_pos
        assert pos is not None
        assert self._economy is not None
        ledger, _seed = self._economy()
        assert isinstance(ledger, CoinLedger)
        tick = loop.state.tick
        loop.enqueue(
            npc_act_event(tick, actor_id, "build", params={"x": str(pos[0]), "y": str(pos[1])})
        )
        for event in build_action_events(
            loop.state,
            actor_id,
            pos,
            tick=tick,
            runtime=build_runtime,
            ledger=ledger,
            form="thought",
        ):
            loop.enqueue(event)

    def _issue_attack(self, loop: TickLoop, actor_id: str, intent: Intent) -> None:
        """attack：确定性结算 → hp 账本 → 死亡走 npc.death（E6 最小面）。

        hp/伤害数值零出戏（独白只有叙事）；命中后呼救是外在可观察 bubble。
        """
        from sim.agent.combat_exec import (
            CombatLedger,
            entropy_roll,
            help_line,
            needs_critical_entropy,
        )
        from sim.core.events import npc_death_event, npc_monologue_event

        if self._combat is None:  # 调用分支已保证（pyright 收窄）
            return
        ledger, seed = self._combat()
        target = intent.target_id
        actor = loop.state.entities.get(actor_id)
        victim = loop.state.entities.get(target or "")
        if target is None or actor is None or victim is None:
            return  # 目标不在场（闸门 revalidate 也会拦——双保险）
        if abs(actor.pos[0] - victim.pos[0]) + abs(actor.pos[1] - victim.pos[1]) > 2:
            return  # 够不着：不扣血、不抽熵、不切战斗时间尺
        tick = loop.state.tick
        if self._exchange is None:
            from sim.agent.combat_exec import CombatExchange

            self._exchange = CombatExchange()
            self._combat_target = target
            self._combat_tick_last = tick
            self.request_decision()
        roll = None
        if self._entropy_provider is not None and needs_critical_entropy(
            actor_id, target, tick=tick, seed=seed
        ):
            event = self._entropy_provider("combat.critical", tick)
            loop.enqueue(event)
            roll = entropy_roll(str(event.payload["material"]))
        if isinstance(ledger, CombatLedger):
            scale = 1.25 if intent.params.get("posture") == "aim" else 1.0
            if target == self._anchor.entity_id and self._exchange.active_posture == "defend":
                scale *= 0.5
            out = ledger.apply_attack(
                actor_id, target, tick=tick, seed=seed, entropy_roll=roll, damage_scale=scale
            )
        elif roll is None:
            out = ledger.apply_attack(actor_id, target, tick=tick, seed=seed)
        else:
            out = ledger.apply_attack(actor_id, target, tick=tick, seed=seed, entropy_roll=roll)
        target_name = self._display_name_of(target) or target
        attacker_name = self._display_name_of(actor_id) or actor_id
        if out.outcome == "kill":
            loop.enqueue(npc_death_event(tick=tick, entity_id=target))
            loop.enqueue(
                npc_monologue_event(
                    tick=tick + 1,
                    npc_id=actor_id,
                    form="thought",
                    content=f"看着{target_name}倒下去，我的手一直在抖。",
                )
            )
        elif out.outcome == "miss":
            loop.enqueue(
                npc_monologue_event(
                    tick=tick + 1,
                    npc_id=actor_id,
                    form="thought",
                    content=f"这一下挥空了，{target_name}躲开了。",
                )
            )
        else:
            loop.enqueue(
                npc_monologue_event(
                    tick=tick + 1,
                    npc_id=actor_id,
                    form="thought",
                    content=f"我伤了{target_name}，他退了半步。",
                )
            )
            # 呼救：被袭者 bubble（广播面——路人都听得见）
            loop.enqueue(
                npc_monologue_event(
                    tick=tick + 1,
                    npc_id=target,
                    form="bubble",
                    content=help_line(attacker_name, tick=tick),
                )
            )
        if target not in loop.state.entities or self._anchor.entity_id not in loop.state.entities:
            self.reset_combat()
            loop.issue_combat_scale(False)
        elif self._combat_until_tick is None:
            self._combat_until_tick = tick + 60
            loop.issue_combat_scale(True)

    def _issue_flee(
        self, loop: TickLoop, pathfinder: object, actor_id: str, threat_id: str
    ) -> None:
        """flee：背离威胁 4 格反向寻路（不可达=原地——fail-soft）。"""
        from sim.world.pathfinding import Pathfinder

        if not isinstance(pathfinder, Pathfinder):
            return
        actor = loop.state.entities.get(actor_id)
        threat = loop.state.entities.get(threat_id)
        if actor is None or threat is None:
            return
        dx = 4 if actor.pos[0] >= threat.pos[0] else -4
        dy = 4 if actor.pos[1] >= threat.pos[1] else -4
        goal = (max(0, actor.pos[0] + dx), max(0, actor.pos[1] + dy))
        try:
            path = pathfinder.find(actor.pos, goal)
            loop.issue_move(actor_id, list(path))
        except ValueError:
            pass  # 不可达：原地（独白仍出）

    def _issue_investigate(
        self, loop: TickLoop, pathfinder: object, actor_id: str, target_pos: tuple[int, int]
    ) -> None:
        """investigate：走过去看一眼（位移即落地；观察产物由感知层接管）。"""
        from sim.world.pathfinding import Pathfinder

        if not isinstance(pathfinder, Pathfinder):
            return
        actor = loop.state.entities.get(actor_id)
        if actor is None:
            return
        try:
            path = pathfinder.find(actor.pos, target_pos)
            loop.issue_move(actor_id, list(path))
        except ValueError:
            pass  # 不可达：原地张望（独白仍出——fail-soft 同 move_to 口径）

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
