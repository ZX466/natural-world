"""修复验证:聊天决策面节流——冷却期内 request_chat 压出候选(治 733 万空转)。

实况实测(main@fdfa898,4.9 游戏日):npc.act 837 万行,其中 request_chat
733 万(88%),同 tick 同 npc 最多 175 连发;开口转化仅 0.06%(4469/733万)。
根因=开口冷却(chat_last)只挡**事件**,不挡**决策**——村民每 10 tick 又选
chat 又写 npc.act,库无限膨胀→第三天卡死。

修复:runtime.tick 加 chat_suppressed(逐人冷却内=True)→ evaluate_batch
压掉该 npc 的 request_chat 列,argmax 落回其他动作。
"""

from dataclasses import replace

import numpy as np

from sim.npc.model import NpcProfileData
from sim.npc.utility import UtilityModel, evaluate_batch, utility_scores_matrix


def _profile(npc_id: str = "villager_01") -> NpcProfileData:
    return NpcProfileData(npc_id=npc_id, name="赵铁柱")


def _social_max(p: NpcProfileData) -> NpcProfileData:
    """social 需求顶格（chat 增益最大——无抑制时必选 chat 的夹具）。"""
    return replace(p, needs=tuple(replace(n, value=0.95) for n in p.needs))


def test_evaluate_batch_suppresses_chat_column():
    """社交顶格+外向满值时,无抑制必选 chat;有抑制必不选 chat。"""
    model = UtilityModel(n_npc=1, seed=42)
    p = _profile()
    # 外向拉满→chat 列有额外偏置;social 需求顶格→chat 增益最大
    social_max = _social_max(p)
    assert evaluate_batch([social_max], model)[0].action == "request_chat"
    suppressed = evaluate_batch([social_max], model, suppress_chat=(True,))
    assert suppressed[0].action != "request_chat"


def test_suppress_chat_keeps_scores_audit_clean():
    """被压列的审计分仍随行(不代表真实效用——params 面只作展示)。"""
    model = UtilityModel(n_npc=1, seed=42)
    scores = utility_scores_matrix([_profile()], model, suppress_chat=(True,))
    assert scores.shape == (1, len(model.action_index))


def test_suppression_is_per_npc():
    """抑制按人独立:(True, False) → 只有第一个被压。"""
    model = UtilityModel(n_npc=2, seed=42)
    a, b = _profile("villager_01"), _profile("villager_02")
    social = [_social_max(p) for p in (a, b)]
    out = evaluate_batch(social, model, suppress_chat=(True, False))
    assert out[0].action != "request_chat"
    assert out[1].action == "request_chat"


def test_no_suppression_bitwise_identical():
    """suppress_chat=None ⇒ 打分逐位同旧(零回归钉)。"""
    model = UtilityModel(n_npc=3, seed=42)
    profiles = [_profile(f"villager_{i:02d}") for i in (1, 2, 3)]
    old = utility_scores_matrix(profiles, model)
    new = utility_scores_matrix(profiles, model, suppress_chat=None)
    assert np.array_equal(old, new)
