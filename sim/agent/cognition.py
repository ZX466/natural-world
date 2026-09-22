"""sim.agent.cognition — 非理性框架：六偏差纯函数层（M2-A2 第三批；DESIGN §非理性框架）。

架构定位（m2-npc-cognition.md §3.1/§3.2）：
- **偏差只作用于检索打分与效用计算，不进 prompt**——LLM 不感知偏差参数，
  「像人」由代码层施加，prompt 装配保持纯净；
- 检索缝两偏差以 `sim/npc/memory.py` 的 `Scorer` 钩子形注册（`RetrievalScorers`/
  `retrieve(..., scorers=...)`）；效用缝四偏差为纯函数骨架，M3 行为能力接入时
  挂进决策链固定缝；
- 纯函数、可重放（C5）；全部产出数值，偏差名/参数零元信息（铁律 1）。

M2 内容常量：系数占位值（0.5 上浮 / 0.5 下压 / 投入与重复的线性量级），
调参基准走观测 breakdown（MemoryHit.breakdown），M3 用 7 日自转数据回填。
"""

from __future__ import annotations

from dataclasses import dataclass

from sim.llm.memory_scan import MemoryEntry
from sim.npc.memory import MemoryQuery, Scorer

#: 六偏差名（戏外观测/诊断标签；绝不进戏内文本/prompt——零元信息）。
BIAS_NAMES: tuple[str, ...] = (
    "confirmation_bias",
    "mood_bias",
    "sunk_cost",
    "habit",
    "trauma_avoidance",
    "drunkenness",
)

#: 确认偏误：信念关键词命中时的乘法上浮系数。
CONFIRMATION_BOOST: float = 1.5
#: 情绪一致性：同极性上浮 / 异极性下压系数。
MOOD_CONGRUENT_BOOST: float = 1.3
MOOD_INCONGRUENT_PENALTY: float = 0.7
#: 条目 emotion_tag → 情绪极性（pleasure 正负向）。None=中性不偏。
EMOTION_VALENCE: dict[str, int] = {
    "joy": 1,
    "hope": 1,
    "pride": 1,
    "gratitude": 1,
    "grief": -1,
    "fear": -1,
    "anger": -1,
    "shame": -1,
    "disgust": -1,
}
#: 沉没成本：每单位已投入对继续意愿的加成（0..1 线性）。
SUNK_COST_WEIGHT: float = 0.3
#: 习惯：路径依赖加成 = HABIT_WEIGHT × ln(1+重复次数)（边际递减）。
HABIT_WEIGHT: float = 0.2
#: 创伤应激：每个触发中属性的回避惩罚（add 负项）。
TRAUMA_PENALTY_PER_ATTR: float = 0.5
#: 醉酒：感知噪声/意愿抑制的放大系数（清醒=1.0 恒等）。
DRUNKENNESS_NOISE_MAX: float = 2.0


# ---------------------------------------------------------------------------
# 检索缝（memory.py Scorer 钩子；mode="mul"）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Beliefs:
    """一个 NPC 的既有信念关键词表（M2 关键词子串命中；M3 接信念存储）。

    frozen 值对象；keywords 为空 = 无信念 = 恒等系数（偏差可整体关闭）。
    """

    keywords: tuple[str, ...] = ()


def confirmation_bias_scorer(beliefs: Beliefs) -> Scorer:
    """确认偏误钩子：条目内容命中任一信念关键词 → ×CONFIRMATION_BOOST。

    纯函数闭包（beliefs frozen）；未命中 = 1.0 恒等（DESIGN：一致条目权重上浮）。
    """

    def fn(entry: MemoryEntry, query: MemoryQuery) -> float:
        _ = query  # 上下文命中面在 M3 扩展（query.context 关键词抽取）
        if not beliefs.keywords:
            return 1.0
        return CONFIRMATION_BOOST if any(k in entry.content for k in beliefs.keywords) else 1.0

    return Scorer(name=BIAS_NAMES[0], fn=fn, mode="mul")


def mood_bias_scorer() -> Scorer:
    """情绪一致性钩子：query.mood 与条目 emotion_tag 极性同向 → 上浮，反向 → 下压。

    mood.pleasure（PAD 第一维）>0 正向、<0 负向；条目无极性标签 = 1.0 恒等。
    """

    def fn(entry: MemoryEntry, query: MemoryQuery) -> float:
        if query.mood is None or entry.emotion_tag is None:
            return 1.0
        valence = EMOTION_VALENCE.get(entry.emotion_tag, 0)
        if valence == 0:
            return 1.0
        mood_valence = 1 if query.mood[0] > 0 else (-1 if query.mood[0] < 0 else 0)
        if mood_valence == 0:
            return 1.0
        return MOOD_CONGRUENT_BOOST if valence == mood_valence else MOOD_INCONGRUENT_PENALTY

    return Scorer(name=BIAS_NAMES[1], fn=fn, mode="mul")


@dataclass(frozen=True)
class CognitionParams:
    """偏差装配参数：检索缝一次注册（retrieval_scorers 供 retrieve 调用方）。"""

    beliefs: Beliefs = Beliefs()

    def retrieval_scorers(self) -> tuple[Scorer, ...]:
        """检索缝钩子序列（顺序固定，C5：先确认偏误后情绪一致性）。"""
        return (confirmation_bias_scorer(self.beliefs), mood_bias_scorer())


# ---------------------------------------------------------------------------
# 效用缝骨架（M3 行为能力接入决策链时生效；现批次纯函数形先立）
# ---------------------------------------------------------------------------


def sunk_cost_bonus(invested: float, base_desire: float) -> float:
    """沉没成本：已投入量（0..1 归一）→ 继续意愿 = base_desire + 投入加成。

    「因为已经投入而继续错下去」——加成与投入线性同增，永不回落。
    """
    return base_desire + max(0.0, invested) * SUNK_COST_WEIGHT


def habit_bonus(repetitions: int) -> float:
    """习惯：重复次数 → 路径依赖加成（ln(1+n) 边际递减；0 次 = 0）。"""
    import math

    if repetitions <= 0:
        return 0.0
    return HABIT_WEIGHT * math.log1p(repetitions)


def trauma_avoidance_penalty(triggered: frozenset[str]) -> float:
    """创伤应激：触发中属性数 → 回避惩罚（add 负项；绕过理性评估）。"""
    return -TRAUMA_PENALTY_PER_ATTR * len(triggered)


def drunkenness_factor(drunkenness: float) -> float:
    """醉酒：感知噪声/意愿抑制下降的放大系数（清醒 1.0 恒等；0..1 → 1..MAX）。

    M3 接线：乘进感知噪声幅度与意愿阈值折减；此处只定系数形。
    """
    d = min(1.0, max(0.0, drunkenness))
    return 1.0 + (DRUNKENNESS_NOISE_MAX - 1.0) * d


__all__ = [
    "BIAS_NAMES",
    "Beliefs",
    "CognitionParams",
    "confirmation_bias_scorer",
    "drunkenness_factor",
    "habit_bonus",
    "mood_bias_scorer",
    "sunk_cost_bonus",
    "trauma_avoidance_penalty",
]
