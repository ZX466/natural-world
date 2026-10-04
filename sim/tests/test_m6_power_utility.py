"""批次 C 机制面验收钉 — 权力→utility 传导（裁 34 口径；P10 红线的消费兑现）。

四条判据：
- **向量化接线**（P10 红线）：权力是效用矩阵的额外列偏置——同 profile 集合
  power=None 与 power=全 0 打分**逐位相等**（零值权力=无偏置，管线不漂移）；
- **POWER_MAX_BIAS≤0.2**（裁 34-2）：偏置上界由常量钉死；|power|=1 时社交列
  偏置恰 0.2；
- **生存列零触碰**（eat/rest 不受权力影响——饿不死权力低）；
- **flip 上界**（一箭双雕：性能 flip≤0.25 = 安规「被操纵感」——动作分布熵
  不许坍缩，与 codex 红线 C 共用口径）。
"""

from __future__ import annotations

import numpy as np

from sim.npc.model import Need, NpcProfileData
from sim.npc.utility import POWER_MAX_BIAS, UtilityModel, evaluate_batch, utility_scores_matrix


def _profile(npc_id: str, hunger: float = 0.5) -> NpcProfileData:
    return NpcProfileData(
        npc_id=npc_id,
        name=npc_id,
        lod=1,
        needs=(Need(name="hunger", value=hunger, weight=1.0),),
        ocean=(50.0, 50.0, 50.0, 50.0, 50.0),
    )


class TestPowerBiasWiring:
    def test_power_none_and_zero_are_bitwise_identical(self) -> None:
        """power=None 与 power=全 0 ⇒ 打分**逐位相等**（零值权力=零偏置，不漂移）。"""
        profiles = [_profile(f"npc{i}") for i in range(5)]
        model = UtilityModel(n_npc=5)
        none_scores = utility_scores_matrix(profiles, model, power=None)
        zero_scores = utility_scores_matrix(profiles, model, power=[0.0] * 5)
        assert np.array_equal(none_scores, zero_scores), "零值权力改了打分（偏置不是 0）"

    def test_bias_is_exactly_power_times_max(self) -> None:
        """偏置 = power × POWER_MAX_BIAS（|power|=1 ⇒ 恰 0.2；-1 ⇒ -0.2）。"""
        profiles = [_profile("npc0"), _profile("npc1")]
        model = UtilityModel(n_npc=2)
        base = utility_scores_matrix(profiles, model, power=None)
        full = utility_scores_matrix(profiles, model, power=[1.0, -1.0])
        for action in ("request_chat", "wander"):
            col = model.action_index[action]
            assert np.isclose(
                float(full[0, col] - base[0, col]), POWER_MAX_BIAS, atol=1e-6
            ), f"{action} 列偏置 ≠ +{POWER_MAX_BIAS}：{full[0, col] - base[0, col]}"
            assert np.isclose(
                float(full[1, col] - base[1, col]), -POWER_MAX_BIAS, atol=1e-6
            ), f"{action} 列偏置 ≠ -{POWER_MAX_BIAS}"

    def test_survival_columns_untouched(self) -> None:
        """生存列（eat/rest）零偏置——权力不改变生存紧迫度语义。"""
        profiles = [_profile("npc0")]
        model = UtilityModel(n_npc=1)
        base = utility_scores_matrix(profiles, model, power=None)
        full = utility_scores_matrix(profiles, model, power=[1.0])
        for action in ("eat", "rest"):
            col = model.action_index[action]
            assert np.isclose(
                float(full[0, col] - base[0, col]), 0.0, atol=1e-7
            ), f"{action} 列被权力动了（饿不死权力低的语义破了）"

    def test_power_clamped_to_dimension(self) -> None:
        """越界 power 值截到 [-1,1]（快照外值不混入打分——A7 量纲口径）。"""
        profiles = [_profile("npc0")]
        model = UtilityModel(n_npc=1)
        clamped = utility_scores_matrix(profiles, model, power=[99.0])
        at_one = utility_scores_matrix(profiles, model, power=[1.0])
        assert np.array_equal(clamped, at_one), "越界 power 未被截断"

    def test_length_mismatch_fails_closed(self) -> None:
        """power 与 profiles 数不一致 ⇒ ValueError（fail-closed，不静默截断）。"""
        profiles = [_profile("npc0"), _profile("npc1")]
        model = UtilityModel(n_npc=2)
        try:
            utility_scores_matrix(profiles, model, power=[1.0])
        except ValueError:
            return
        raise AssertionError("长度不一致竟未抛")

    def test_flip_bounded_by_bias_constant(self) -> None:
        """flip ≤ 0.25 翻正式（pi M6-P5 定标扫参裁决：POWER_MAX_BIAS 0.2→0.18）。

        定标记录（seed=42 同夹具）：bias 0.20→flip 0.260 / **0.18→0.240**（余量
        4%）/ 0.15→0.200——取「满足守卫的最松值」0.18（权力被感知=机制意图，
        过度收紧=无感；0.15 已备下档）。**advisory 界 0.5 就此翻正式 0.25**；
        常数钉同步 ==0.18（定标轮唯一旋钮，勿偷调）。
        熵守卫（红线 C）不得跨口径引用——须在 L1 bench 真实分布另建基线
        （P5 口径警告：本夹具体熵 0.68-0.88 与 P10 合成面 2.52/2.41 不同口径）。
        """
        rng = np.random.default_rng(42)
        profiles = [
            _profile(f"npc{i}", hunger=float(rng.uniform(0.1, 0.9))) for i in range(50)
        ]
        model = UtilityModel(n_npc=50, seed=7)
        base = evaluate_batch(profiles, model, power=None)
        full = evaluate_batch(profiles, model, power=[1.0] * 50)
        flips = sum(1 for a, b in zip(base, full, strict=True) if a.action != b.action)
        ratio = flips / len(base)
        # 正式界（pi P5 扫参：0.18 ⇒ 实测 0.240 ≤ 0.25）
        assert ratio <= 0.25, f"flip={ratio:.2f} > 0.25（被操纵感前兆——红线 C 同源）"
        # 硬判据：偏置上界由常量保证（机制旋钮，定标轮唯一调法是改 POWER_MAX_BIAS）
        assert POWER_MAX_BIAS == 0.18, "POWER_MAX_BIAS 被改（须随定标轮同 CR，勿偷调）"
