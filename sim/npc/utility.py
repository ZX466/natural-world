"""sim.npc.utility — L1 效用 AI（M2-A1 §2；兼 LLM 断线兜底）。

打分模型对齐 pi bench 原型（test_bench_l1_utility._L1Load.tick_vectorized）：
全 NPC 需求矩阵 (n_npc, n_needs) numpy 一次算完，禁止逐 NPC Python 循环
（红线 L1_UTILITY_TICK_LIMIT_MS=6.0 / 单 NPC 0.12ms，thresholds.py）。

效用(action | npc) = Σ w_i * value_i * gain(action, need_i)   # 需求加权和
                     + habit_bonus(action)                     # 习惯（§3，M2 占位常量）
候选集 = 日程档 + needs 阈值补救 + 计划队列剩余（本模块产出打分；候选集由 runtime 注入）。

L1 决策不走 IntentGate（闸门审 LLM 输出；效用函数是确定性代码，§2.2）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.npc.actions import ACTION_WHITELIST
from sim.npc.model import NpcProfileData

#: 动作固定序（向量化列序；确定性契约——不随 set 迭代序漂移）
ACTION_ORDER: tuple[str, ...] = tuple(
    a for a in ("move", "work", "eat", "rest", "wander", "request_chat") if a in ACTION_WHITELIST
)

N_ACTIONS = len(ACTION_ORDER)

#: 每动作对每需求的满足增益（内容常量·占位值：eat 治饥饿、rest 恢复精力…）
#: 行=NEED_ORDER 序，列=ACTION_ORDER 序（move/work/eat/rest/wander/request_chat）。
NEED_ORDER: tuple[str, ...] = ("hunger", "energy", "social")
_GAIN = np.array(
    [
        [0.0, 0.0, 0.9, 0.1, 0.0, 0.0],  # hunger: eat 治饥饿
        [0.0, 0.0, 0.1, 0.9, 0.2, 0.0],  # energy: rest 恢复精力
        [0.0, 0.2, 0.0, 0.0, 0.3, 0.8],  # social: work/wander/chat
    ],
    dtype=np.float32,
)  # (n_needs, n_actions)

#: 习惯加成占位（§3 六偏差之一；M2 常量，M4 意愿系统接管）
HABIT_BONUS = 0.05

#: OCEAN→动作的温和偏置（外向者爱交谈等；占位系数）
_EXTRAVERSION_CHAT_BIAS = 0.3


@dataclass(frozen=True)
class UtilityDecision:
    """单个 NPC 的 L1 决策（§2.1 输出；target M2 留空串）。"""

    npc_id: str
    action: str
    target: str = ""
    scores: dict[str, float] = None  # type: ignore[assignment]  # action → 分数（审计进 NPC_ACT.params）


class UtilityModel:
    """L1 效用模型：持有动作增益矩阵与可选噪声种子（C5：seed 进构造，不隐式取全局）。"""

    def __init__(self, n_npc: int, seed: int = 0) -> None:
        if n_npc <= 0:
            msg = f"n_npc 必须为正: {n_npc}"
            raise ValueError(msg)
        self.n_npc = n_npc
        self.seed = seed
        self.action_index = {a: i for i, a in enumerate(ACTION_ORDER)}

    def _needs_matrix(self, profiles: list[NpcProfileData]) -> np.ndarray:
        """needs 元组 → (n_npc, n_needs) float32 矩阵（value 列）。"""
        rows = np.zeros((len(profiles), len(NEED_ORDER)), dtype=np.float32)
        for i, p in enumerate(profiles):
            for n in p.needs:
                if n.name in self._need_col:
                    rows[i, self._need_col[n.name]] = np.float32(n.value)
        return rows

    @property
    def _need_col(self) -> dict[str, int]:
        return {name: i for i, name in enumerate(NEED_ORDER)}

    def _weights_matrix(self, profiles: list[NpcProfileData]) -> np.ndarray:
        """needs 权重 → (n_npc, n_needs) float32 矩阵。"""
        rows = np.ones((len(profiles), len(NEED_ORDER)), dtype=np.float32)
        for i, p in enumerate(profiles):
            for n in p.needs:
                if n.name in self._need_col:
                    rows[i, self._need_col[n.name]] = np.float32(n.weight)
        return rows


def utility_scores_matrix(profiles: list[NpcProfileData], model: UtilityModel) -> np.ndarray:
    """50 NPC 全量打分：需求加权和 + 外向偏置 → (n_npc, n_actions) float32。

    向量化实现（与 bench 原型同构：矩阵乘法一次算完）。
    """
    needs = model._needs_matrix(profiles)  # (n, 3)
    weights = model._weights_matrix(profiles)  # (n, 3)
    # 加权紧迫度 × 满足增益：(n,3)·(n,3) → (n,3) @ (3,n_actions)
    urgency = needs * weights
    scores = urgency @ _GAIN  # (n, n_actions)

    # 外向偏置：OCEAN 外向分（0-100 → 0-1）加到 request_chat 列
    chat_col = model.action_index["request_chat"]
    extrav = np.array([p.ocean[2] / 100.0 for p in profiles], dtype=np.float32).reshape(-1, 1)
    scores[:, chat_col] = scores[:, chat_col] + np.float32(_EXTRAVERSION_CHAT_BIAS) * extrav[:, 0]

    # 习惯加成占位：常数列偏置（M4 前均匀；避免全零打分并列）
    scores += np.float32(HABIT_BONUS)
    return scores


def evaluate_batch(profiles: list[NpcProfileData], model: UtilityModel) -> list[UtilityDecision]:
    """批量评估 → 每 NPC 一个 UtilityDecision（argmax；scores 全量随行供审计）。"""
    scores = utility_scores_matrix(profiles, model)
    best = scores.argmax(axis=1)
    return [
        UtilityDecision(
            npc_id=p.npc_id,
            action=ACTION_ORDER[int(best[i])],
            target="",
            scores={a: float(scores[i, j]) for j, a in enumerate(ACTION_ORDER)},
        )
        for i, p in enumerate(profiles)
    ]
