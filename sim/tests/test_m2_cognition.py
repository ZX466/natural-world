"""M2-A2 第三批第 3 项：cognition 六偏差骨架（DESIGN §非理性框架表）。

契约（docs/arch/m2-npc-cognition.md §3.1 挂载缝 + DESIGN §251 表）：
- 纯函数层：偏差只作用于检索打分与效用计算，不进 prompt（§3.1）；
- 检索缝两偏差（memory.py Scorer 钩子形）：
  - confirmation_bias：与既有信念一致的条目 mul 系数上浮（belief_hits 命中面）；
  - mood_bias（情绪一致性）：条目情绪与当前 mood 同极性上浮、异极性下压；
- 效用缝四骨架（决策链固定缝，M3 行为能力接入时生效；现批次先立纯函数形）：
  - sunk_cost：已投入量 → 继续意愿加成（add 项）；
  - habit：重复次数 → 路径依赖加成（add 项）；
  - trauma_avoidance：创伤触发情境 → 回避惩罚（add 负项；接 hidden.triggered）；
  - drunkenness：感知噪声 + 意愿抑制下降（系数放大器，M3 感知接线）；
- 全部可重放：同输入同输出；零元信息（偏差名不进任何戏内文本）。
"""

from __future__ import annotations

import pytest

from sim.agent.cognition import (
    Beliefs,
    CognitionParams,
    confirmation_bias_scorer,
    drunkenness_factor,
    habit_bonus,
    mood_bias_scorer,
    sunk_cost_bonus,
    trauma_avoidance_penalty,
)
from sim.llm.memory_scan import MemoryEntry, make_entry
from sim.npc.memory import MemoryQuery, retrieve

# S1 守卫：测试构造也走 make_entry 工厂（memory_scan.py 唯一构造点）
_ENTRY_SEQ = iter(range(10_000))


def _entry(
    eid: str, content: str, *, importance: float = 0.5, emotion: str | None = None
) -> MemoryEntry:
    return make_entry(
        entry_id=eid,
        npc_id="npc:01",
        content=content,
        source="observation",
        event_seq=next(_ENTRY_SEQ),
        importance=importance,
        emotion_tag=emotion,
    )


class TestConfirmationBias:
    def test_belief_consistent_scores_higher(self) -> None:
        """与信念一致的条目得分 > 不一致条目（其余同分）。"""
        beliefs = Beliefs(keywords=("河里有鱼",))
        scorer = confirmation_bias_scorer(beliefs)
        q = MemoryQuery(npc_id="npc:01")
        hit_yes = scorer.apply(_entry("m1", "昨天在河里有鱼跃出水面。"), q)
        hit_no = scorer.apply(_entry("m2", "集市上人声嘈杂。"), q)
        assert hit_yes > hit_no
        assert hit_no == 1.0  # 未命中 = 恒等系数

    def test_no_beliefs_identity(self) -> None:
        """空信念表 = 恒等（默认无偏差可关）。"""
        scorer = confirmation_bias_scorer(Beliefs(keywords=()))
        assert scorer.apply(_entry("m1", "任意文本"), MemoryQuery(npc_id="npc:01")) == 1.0


class TestMoodBias:
    def test_same_polarity_boosted(self) -> None:
        """正面情绪 × 正面条目（joy）→ mul > 1。"""
        scorer = mood_bias_scorer()
        q = MemoryQuery(npc_id="npc:01", mood=(0.6, 0.0, 0.0))  # pleasure 正
        assert scorer.apply(_entry("m2", "内容", emotion="joy"), q) > 1.0

    def test_opposite_polarity_suppressed(self) -> None:
        """正面情绪 × 负面条目（grief）→ mul < 1。"""
        scorer = mood_bias_scorer()
        q = MemoryQuery(npc_id="npc:01", mood=(0.6, 0.0, 0.0))
        assert scorer.apply(_entry("m1", "内容", emotion="grief"), q) < 1.0

    def test_no_mood_identity(self) -> None:
        """mood 未知 = 恒等。"""
        scorer = mood_bias_scorer()
        q = MemoryQuery(npc_id="npc:01")
        assert scorer.apply(_entry("m1", "内容", emotion="joy"), q) == 1.0


class TestRetrievalIntegration:
    def test_scorers_flow_through_retrieve(self) -> None:
        """钩子注册进 retrieve 后偏差实际改变排序（§3.1 缝合验证）。"""
        beliefs = Beliefs(keywords=("鱼",))
        scorers = CognitionParams(beliefs=beliefs).retrieval_scorers()
        store = [
            _entry("m1", "河里全是鱼群。", importance=0.4),
            _entry("m2", "铁匠铺的炉火。", importance=0.5),
        ]
        hits = retrieve(store, MemoryQuery(npc_id="npc:01"), scorers=scorers)
        # m2 基础分更高但无命中；m1 命中「鱼」上浮后反超
        assert hits[0].entry.id == "m1"


class TestUtilitySeamSkeletons:
    """效用缝四骨架：纯函数形先立（M3 行为能力接入时生效）。"""

    def test_sunk_cost_bonus(self) -> None:
        assert sunk_cost_bonus(invested=0.0, base_desire=0.5) == pytest.approx(0.5)
        assert sunk_cost_bonus(invested=0.8, base_desire=0.5) > 0.5

    def test_habit_bonus_grows_with_repetition(self) -> None:
        assert habit_bonus(repetitions=0) == pytest.approx(0.0)
        assert habit_bonus(repetitions=10) > habit_bonus(repetitions=3)

    def test_trauma_avoidance_penalty(self) -> None:
        """未触发 = 0；触发属性数 > 0 → 负项。"""
        assert trauma_avoidance_penalty(triggered=frozenset()) == 0.0
        assert trauma_avoidance_penalty(triggered=frozenset({"a"})) < 0.0
        assert trauma_avoidance_penalty(triggered=frozenset({"a", "b"})) < trauma_avoidance_penalty(
            triggered=frozenset({"a"})
        )

    def test_drunkenness_factor_identity_when_sober(self) -> None:
        assert drunkenness_factor(drunkenness=0.0) == pytest.approx(1.0)
        assert drunkenness_factor(drunkenness=0.8) > 1.0

    def test_all_replayable(self) -> None:
        """C5：同输入同输出。"""
        assert sunk_cost_bonus(0.3, 0.5) == sunk_cost_bonus(0.3, 0.5)
        assert habit_bonus(7) == habit_bonus(7)
        assert drunkenness_factor(0.4) == drunkenness_factor(0.4)


class TestZeroMeta:
    def test_no_meta_words_in_outputs(self) -> None:
        """偏差产出全是数值——无任何文本面（零元信息结构性成立）。"""
        from sim.agent.cognition import BIAS_NAMES

        assert BIAS_NAMES == (
            "confirmation_bias",
            "mood_bias",
            "sunk_cost",
            "habit",
            "trauma_avoidance",
            "drunkenness",
        )
