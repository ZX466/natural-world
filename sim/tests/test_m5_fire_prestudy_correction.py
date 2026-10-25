"""M5 火灾事件 kind 钉子（2026-10-25 文档大整理后只留代码事实）。

历史预研稿 `docs/api/m5-fire-api-prestudy.md` 已删除，可从 git 历史找回。
保留下来的不变量：`fire.*` 恰为 2 项，且都已登记 payload 模型。
若将来加回 `fire.spread`，本钉立即红，强制先更新设计口径。
"""

from __future__ import annotations

from sim.core.events import EventKind
from sim.core.persistence.event_validation import PAYLOAD_MODELS

#: 施工采信的 2 kind（opencode 数据面裁定 + 裁 35-1 采认）。
SETTLED_KINDS = ("fire.ignited", "fire.extinguished")


def _fire_kinds() -> list[str]:
    return [
        member.value for name, member in EventKind.__members__.items() if name.startswith("FIRE_")
    ]


def test_code_facts_match_settled_two_kind_design() -> None:
    """`fire.*` 恰为 2 项、都已登记 payload 模型；蔓延走既有 `matter.damage` 谱系。"""
    kinds = _fire_kinds()
    assert sorted(kinds) == sorted(SETTLED_KINDS), (
        f"fire.* kind 集与 2-kind 设计不一致：{kinds}"
        "（若加回 fire.spread，先更新设计口径，别只改测试）"
    )
    unregistered = [kind for kind in kinds if kind not in PAYLOAD_MODELS]
    assert unregistered == [], f"fire kind 未登记 payload 模型：{unregistered}"
