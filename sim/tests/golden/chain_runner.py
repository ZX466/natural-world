"""M4-D3 续接差事执行器——把 ErrandChain 跑成 ErrandOutcome（T5 完成率素材）。

链路（与 M1 _run_errand 同构，步进版）：
  每步：parse_intent（脚本 LLM 原文）→ IntentGate.validate（消费**当前状态**）
  → 末步 action ∈ expected_actions 判定。
步间状态续接（裁 17-3 的「多决策」语义）：move_to 步走 `bus.apply(MOVE)`
（§19 铁律：状态只经 apply(event) 改）——第 N 步闸门校验看到的是前 N-1 步
落地后的世界（跨决策状态存活的可测面）。
fixture 优先：零 LLM、零网络；C5：同种子同链逐位可重放。
"""
from __future__ import annotations

from dataclasses import dataclass

from sim.agent.gate import IntentGate
from sim.agent.intent import parse_intent
from sim.core.events import move_event
from sim.core.world import TickContext, WorldState, build_default_bus
from sim.tests.fixtures.errands import ERRAND_CHAINS, ErrandChain
from sim.tests.golden.assertions.errands_rate import ErrandOutcome


@dataclass(frozen=True)
class ChainRunResult:
    """一条链的执行结果（全步判定明细供诊断）。"""

    chain_id: str
    passed: bool
    reason: str  # "" = 通过；"gate:<step>:<reason>" / "action:<step>:<act>" / "parse:<step>"


def run_chain(
    chain: ErrandChain,
    state: WorldState,
    *,
    start_tick: int = 0,
    actor_entity_id: str = "",
) -> ChainRunResult:
    """逐步执行续接差事（MOVE 经 apply 落地；状态以值传递续接）。"""
    gate = IntentGate()
    bus = build_default_bus()
    ctx = TickContext()
    cur = state
    for i, reply in enumerate(chain.steps):
        # @actor 占位替换：fixture 与世界实体 id 解耦（执行器注入真实 id）
        reply_i = reply.replace('"@actor"', f'"{actor_entity_id or chain.actor_id}"')
        try:
            intent = parse_intent(reply_i)
        except Exception as exc:
            return ChainRunResult(chain.chain_id, False, f"parse:{i}:{exc}")
        verdict = gate.validate(intent, cur, actor_entity_id or chain.actor_id)
        if not verdict.accepted:
            return ChainRunResult(chain.chain_id, False, f"gate:{i}:{verdict.reason}")
        # 步间状态续接：move_to 经 apply(MOVE) 真落地（§19 唯一写路径）
        if intent.action == "move_to" and intent.target_pos is not None:
            entity = cur.entities.get(actor_entity_id or chain.actor_id)
            if entity is not None:
                ev = move_event(
                    tick=cur.tick + 1,  # 事件 tick 单调约束（≤ state.tick+1）
                    actor_id=actor_entity_id or chain.actor_id,
                    start=entity.pos,
                    goal=intent.target_pos,
                    path=(entity.pos, intent.target_pos),
                    branch_id="golden",
                )
                cur = bus.apply(cur, ev, ctx).state
        # 末步动作集判定
        if i == len(chain.steps) - 1 and intent.action not in chain.expected_actions:
            return ChainRunResult(chain.chain_id, False, f"action:{i}:{intent.action}")
    return ChainRunResult(chain.chain_id, True, "")


def run_all_chains(
    state: WorldState, *, actor_entity_map: dict[str, str] | None = None
) -> list[ErrandOutcome]:
    """全链跑完 → ErrandOutcome 列表（喂 errands_rate.measure_baseline）。

    actor_entity_map：chain.actor_id → state.entities 真实实体 id（链 fixture
    的 actor 语义名与 harness 实体 e00N 解耦；缺省取 state 首个实体）。
    """
    if actor_entity_map is None:
        first_entity = next(iter(state.entities), "")
        actor_entity_map = {c.actor_id: first_entity for c in ERRAND_CHAINS}
    outcomes: list[ErrandOutcome] = []
    for chain in ERRAND_CHAINS:
        actor_id = actor_entity_map.get(chain.actor_id, chain.actor_id)
        r = run_chain(chain, state, actor_entity_id=actor_id)
        outcomes.append(ErrandOutcome(case_id=r.chain_id, passed=r.passed, reason=r.reason))
    return outcomes
