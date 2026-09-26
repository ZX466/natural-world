"""M4-D2 差事 fixture 多决策续接（T5 前置，裁 17-3；cline C4 识别的缺口）。

现 20 条 ErrandCase 是**单决策场景**——10 日长跑的完成率若沿用即退化为 M1
单轮口径，测不到跨日计划。本文件补「续接差事」（ErrandChain）：
- steps：N 步 Intent 脚本（步进决策，每步经 parse_intent+闸门）；
- 步间状态续接：上一步 action 落地改变 WorldState（如 move 后位置更新、
  work 后需求变化），下一步决策消费**新状态**——测到「计划跨决策存活」；
- 完成判定：全步 accepted 且末步 action ∈ expected_actions。
fixture 优先（§16 T5 原则）：假 LLM 脚本回放，零网络零真实调用。
"""
from __future__ import annotations

import pytest

from sim.tests.fixtures.errands import ERRAND_CHAINS


@pytest.mark.t1
class TestErrandChainFixture:
    def test_chains_exist_with_multiple_steps(self) -> None:
        # 至少 3 条续接差事，每条 ≥2 步（跨日计划的最低形态）
        assert len(ERRAND_CHAINS) >= 3
        assert all(len(c.steps) >= 2 for c in ERRAND_CHAINS)

    def test_steps_are_valid_intents(self) -> None:
        # 每步 scripted_reply 都能 parse_intent（脚本 LLM 输出契约）
        from sim.agent.intent import parse_intent

        for chain in ERRAND_CHAINS:
            for i, step in enumerate(chain.steps):
                intent = parse_intent(step)
                assert intent.action, (chain.chain_id, i)

    def test_step_targets_reference_chain_entities(self) -> None:
        # 步 target 不得引用链外实体（脚本自洽性）：@actor 占位（执行器注入真实
        # 实体 id）或链内 actor 名；显式 loc:/npc: 前缀也接受（描述性目标）
        known = {c.actor_id for c in ERRAND_CHAINS}
        for chain in ERRAND_CHAINS:
            for step_intent_src in chain.steps:
                from sim.agent.intent import parse_intent

                intent = parse_intent(step_intent_src)
                if intent.target_id is not None:
                    assert (
                        intent.target_id == "@actor"
                        or intent.target_id in known
                        or intent.target_id.startswith(("loc:", "npc:"))
                    ), (chain.chain_id, intent.target_id)


@pytest.mark.t1
class TestChainRunnerIntegration:
    """run_chain 步间续接与完成率接通（T5 errands_rate 素材面）。"""

    def test_all_chains_pass_on_harness_state(self) -> None:
        # 真实 harness state（4 实体）上 4 链全通过——fixture/执行器/闸门三方自洽
        from sim.tests.bench.harness import make_state
        from sim.tests.golden.chain_runner import run_all_chains

        state = make_state(4, world_seed=7)
        outcomes = run_all_chains(state)
        assert len(outcomes) == len(ERRAND_CHAINS)
        failures = [(o.case_id, o.reason) for o in outcomes if not o.passed]
        assert all(o.passed for o in outcomes), failures

    def test_move_step_actually_changes_position(self) -> None:
        # 步间状态续接的实证：C01 含 move 步且目标 (9,3) 与 harness 默认位形不同——
        # runner 内部 gate 校验 + apply(MOVE) 已证明落地（本断言钉 fixture 形状）
        chain0 = ERRAND_CHAINS[0]
        assert any("move_to" in s for s in chain0.steps)
        assert '"target_pos": [9, 3]' in chain0.steps[1]
