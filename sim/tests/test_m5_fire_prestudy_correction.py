"""火灾现行契约与历史订正守卫（裁 35-1）。

现行 WS 文档集中记录两 kind、matter.damage/parent_seq 蔓延机制及旧三 kind 顺序；
完整预研稿留在 Git。保留原有订正优先级、决策链和代码事实断言，防止旧方案复活。
"""

from __future__ import annotations

import re
from pathlib import Path

from sim.core.events import EventKind
from sim.core.persistence.event_validation import PAYLOAD_MODELS

CONTRACT_DOC = Path(__file__).resolve().parents[2] / "docs" / "api" / "ws-protocol.md"

#: 施工采信的 2 kind（opencode 数据面裁定 + 裁 35-1 采认）。
SETTLED_KINDS = ("fire.ignited", "fire.extinguished")

#: 2-kind 案的核心：蔓延**不独立成事件**，因果走既有族的 `parent_seq` 谱系。
SETTLED_SPREAD_MECHANISM = ("matter.damage", "parent_seq")


def _text() -> str:
    return CONTRACT_DOC.read_text(encoding="utf-8")


def _fire_kinds() -> list[str]:
    return [
        member.value for name, member in EventKind.__members__.items() if name.startswith("FIRE_")
    ]


def test_prestudy_has_correction_block() -> None:
    """现行契约的订正必须声明优先级，避免与历史三 kind 顺序混淆。"""
    text = _text()
    assert "⚠ 施工订正" in text, "K12 稿缺「⚠ 施工订正」块"
    assert "以本段为准" in text or "本段优先于下方原文" in text, (
        "订正块未声明优先级（读者会以为两段并列）"
    )


def test_correction_block_names_settled_decision() -> None:
    """订正块须点名 2 kind 与蔓延的谱系机制（订正不能只写「已修正」）。"""
    text = _text()
    for kind in SETTLED_KINDS:
        assert kind in text, f"订正块未点名已落地的 kind：{kind}"
    for token in SETTLED_SPREAD_MECHANISM:
        assert token in text, f"订正块未写蔓延机制 {token}（matter.damage / parent_seq 谱系）"
    assert "fire.spread" in text, "应保留 `fire.spread` 字样（历史决策链不删原文）"


def test_code_facts_match_correction() -> None:
    """代码事实与订正一致：`fire.*` 恰为 2 项、都已登记 payload 模型。"""
    kinds = _fire_kinds()
    assert sorted(kinds) == sorted(SETTLED_KINDS), (
        f"fire.* kind 集与订正不一致：{kinds}"
        "（若 opencode 加回了 fire.spread，先更新 K12 稿订正块）"
    )
    unregistered = [kind for kind in kinds if kind not in PAYLOAD_MODELS]
    assert unregistered == [], f"fire kind 未登记 payload 模型：{unregistered}"


def test_prestudy_keeps_original_decision_chain() -> None:
    """现行记录仍保留历史三 kind 顺序，完整过程可从 Git 回查。"""
    text = _text()
    assert re.search(r"fire\.ignited.*fire\.spread.*fire\.extinguished", text), (
        "3-kind 期表述被删掉了——订正要「保留原文 + 加订正块」，不是抹掉历史"
    )
