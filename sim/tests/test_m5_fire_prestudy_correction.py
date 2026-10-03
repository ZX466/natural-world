"""K12 预研稿订正的**同步钉**（M5-K15 / 裁 35-1：3-kind 案 → opencode 2-kind 案）

**为什么需要钉**：K12 稿是**预研案**（当时据 W-D1 字面推出「新增 `fire.spread`」），
而施工按 opencode 数据面论证改成 **2 kind**（蔓延走既有 `matter.damage` + `parent_seq` 谱系）。
订正以「保留原文 + 加 ⚠ 订正块」的方式落在稿子里——**原文必须保留**（决策链的一部分），
但**冲突处必须有一句「以本段为准」**。人一懒就会只读原文表，于是需要一个机器门禁：

- **本文件锁三件事**：①稿内有「⚠ 施工订正」块；②块内点名 2 kind 与 `parent_seq` 谱系；
  ③代码事实与订正一致（`EventKind` 现恰为 `FIRE_IGNITED` / `FIRE_EXTINGUISHED` 两项，
  且蔓延确实**没有**独立 kind）。
- ③ 是关键：**若将来 opencode 又加回 `fire.spread`**，本钉立即红，强制更新口径文本
  （免得文档与实现悄悄分叉）。
"""

from __future__ import annotations

import re
from pathlib import Path

from sim.core.events import EventKind
from sim.core.persistence.event_validation import PAYLOAD_MODELS

PRESTUDY = Path(__file__).resolve().parents[2] / "docs" / "api" / "m5-fire-api-prestudy.md"

#: 施工采信的 2 kind（opencode 数据面裁定 + 裁 35-1 采认）。
SETTLED_KINDS = ("fire.ignited", "fire.extinguished")

#: 2-kind 案的核心：蔓延**不独立成事件**，因果走既有族的 `parent_seq` 谱系。
SETTLED_SPREAD_MECHANISM = ("matter.damage", "parent_seq")


def _text() -> str:
    return PRESTUDY.read_text(encoding="utf-8")


def _fire_kinds() -> list[str]:
    return [
        member.value for name, member in EventKind.__members__.items() if name.startswith("FIRE_")
    ]


def test_prestudy_has_correction_block() -> None:
    """稿内必须有「⚠ 施工订正」块，且明写「以本段为准」——否则后人会只读原文 3-kind 表。"""
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
    """原文 3-kind 表述**必须仍在**（决策链的一部分；将来复核「为何 spread 不独立」要用）。"""
    text = _text()
    assert re.search(r"fire\.ignited.*fire\.spread.*fire\.extinguished", text), (
        "3-kind 期表述被删掉了——订正要「保留原文 + 加订正块」，不是抹掉历史"
    )
