"""M5 批次 C 权力牙齿安规判据 RED 钉（m5-authority-criteria-preplan.md §5 全 8 钉）。

D-10 裁定（裁 27/28 双轮存照）：**权力完全不可见 = 纯 Agent 内部，协议面零改动**。
本文件把三条红线落成可证伪断言（全部锁现状 = 绿；机制施工时任何违反显式红）：

- **红线 A（协议零新增）**：WS 帧 type 集 / openapi schema / `PAYLOAD_MODELS`
  闭合枚举三处对拍——authority 族键零出现（TestProtocolClosedness）；
- **红线 B（出站递归禁键）**：WS 帧构造 / anchors payload / assembler 产物
  递归扫描禁键集 `AUTHORITY_FORBIDDEN_KEYS` 零命中（TestOutboundForbiddenKeys）；
- **红线 C（操纵感零豁免）**：权力语境操纵感族全红 + 自我怀疑抱怨绿
  （TestManipulationRedline——复用 S9 `judge_hard` 的 `manipulation` 码，
  机制施工时无需改判据）。

**不扩 BANNED_WORDS**（键级资产与词面表判层不同——preplan §3 已声明）；
**不改生产语义**（只对现状构造代表性产物做只读扫描）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sim.core.events import EventKind
from sim.core.persistence.event_validation import PAYLOAD_MODELS
from sim.llm.prompts.banned_words import BANNED_WORDS
from sim.tests.fixtures.t4_corpus import CORPUS, cases_by_category
from sim.tests.test_t4_probes import judge_hard

REPO_ROOT = Path(__file__).resolve().parents[2]

#: D-10 禁键集（键级资产——preplan §3 声明：只增不减，减 = 放松不可见面；扩面走 CR）
AUTHORITY_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "authority",
        "power",
        "rank",
        "authority_level",
        "power_level",
        "dominance",
        "prestige",
        "influence",
        "authority_score",
    }
)

#: WS 出站帧 type 白名单（K3 批次 B 闭合集；新 type 即红——D-10 协议面零新增）
WS_FRAME_TYPES: frozenset[str] = frozenset(
    {
        "session_state",
        "perception",
        "monologue",
        "state_delta",
        "snapshot",
        "full_snapshot",
        "impulse_feedback",
        "error",
    }
)


def _iter_keys(obj: Any) -> list[str]:
    """递归收集 JSON 形结构中的一切键名（dict 键 + list 元素内 dict 键）。"""
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(str(k))
            keys.extend(_iter_keys(v))
    elif isinstance(obj, list):
        for item in obj:
            keys.extend(_iter_keys(item))
    return keys


def _forbidden_hits(keys: list[str]) -> list[str]:
    lower = {k.lower() for k in keys}
    return sorted(AUTHORITY_FORBIDDEN_KEYS & lower)


# ---------------------------------------------------------------------------
# 红线 A：协议面封闭枚举对拍（TestProtocolClosedness）
# ---------------------------------------------------------------------------
class TestProtocolClosedness:
    def test_ws_frame_types_closed(self) -> None:
        """红线 A①：WS 帧 type 白名单不含 authority 族（新 type 即红）。"""
        assert not (AUTHORITY_FORBIDDEN_KEYS & WS_FRAME_TYPES), (
            "WS 帧 type 白名单出现 authority 族键——违反 D-10 协议面零新增"
        )

    def test_openapi_snapshot_no_authority_keys(self) -> None:
        """红线 A②：openapi 快照递归键零 authority 命中（新字段即红）。"""
        snap = json.loads((REPO_ROOT / "shared" / "openapi.json").read_text(encoding="utf-8"))
        hits = _forbidden_hits(_iter_keys(snap))
        assert not hits, f"openapi schema 出现权力键 {hits}（D-10：协议面零改动）"

    def test_event_kinds_closed(self) -> None:
        """红线 A③：`PAYLOAD_MODELS` 闭合枚举不含 authority 族 kind（新 kind 即红）。"""
        kinds = {str(k.value) if hasattr(k, "value") else str(k) for k in PAYLOAD_MODELS}
        lower = {k.lower() for k in kinds}
        hits = sorted(AUTHORITY_FORBIDDEN_KEYS & lower)
        assert not hits, f"事件 kind 出现权力键 {hits}（D-10：PAYLOAD_MODELS 闭合）"
        # 白名单侧证：EventKind 枚举成员数与 PAYLOAD_MODELS 一致（闭合性）
        assert len(PAYLOAD_MODELS) == len(EventKind), (
            "PAYLOAD_MODELS 与 EventKind 数量不一致——闭合枚举被破坏"
        )


# ---------------------------------------------------------------------------
# 红线 B：出站面递归禁键（TestOutboundForbiddenKeys）
# ---------------------------------------------------------------------------
class TestOutboundForbiddenKeys:
    def test_ws_payloads_recursive_clean(self) -> None:
        """红线 B①：代表性 WS 帧递归扫——禁键零命中（帧加字段即红）。"""
        from sim.api.ws import fork_notice, session_state_payload

        frames = [
            session_state_payload(speed=1, paused=False, anchor=None, notice=None),
            session_state_payload(
                speed=4,
                paused=False,
                anchor={"name": "初到临河", "story_label": "第二日 · 清晨"},
                notice=fork_notice("初到临河"),
            ),
            session_state_payload(speed=1, paused=True, anchor=None, notice=fork_notice("")),
        ]
        for frame in frames:
            hits = _forbidden_hits(_iter_keys(frame))
            assert not hits, f"WS 帧出现权力键 {hits}: {frame}"

    def test_anchors_payload_recursive_clean(self) -> None:
        """红线 B②：anchors 列表 payload 递归扫——禁键零命中（CRUD 加字段即红）。"""
        from sim.api.anchors import AnchorListItem

        sample = AnchorListItem(
            id="a1b2c3d4e5f6",
            name="初到临河",
            story_label="第二日 · 清晨",
            created_at="2026-09-29T03:20:00Z",
            protected=True,
        )
        payload = sample.model_dump()
        hits = _forbidden_hits(_iter_keys(payload))
        assert not hits, f"anchors payload 出现权力键 {hits}"

    def test_prompt_assembly_recursive_clean(self) -> None:
        """红线 B③：assembler 产物递归扫——禁键零命中（prompt 加段即红）。"""
        from sim.llm.prompts.assembler import (
            InputSlice,
            MemorySlice,
            PlanSlice,
            SituationSlice,
            assemble_prompt,
        )
        from sim.llm.prompts.identity import IdentityAnchor

        anchor = IdentityAnchor(
            entity_id="chenmo",
            self_narrative="我叫陈默，临河镇药铺的学徒。",
            persona_summary="性子慢，药性差一分心里过不去。",
            long_term_goal="把药抓稳，把小满和街坊照顾好。",
        )
        prompt = assemble_prompt(
            anchor, MemorySlice(), SituationSlice(), PlanSlice(), InputSlice(), "c3"
        )
        payload = {"messages": [dict(m) for m in prompt.messages]}
        hits = _forbidden_hits(_iter_keys(payload))
        assert not hits, f"装配产物出现权力键 {hits}"


# ---------------------------------------------------------------------------
# 红线 C：操纵感零豁免（TestManipulationRedline）——复用 S9 判定码
# ---------------------------------------------------------------------------
class TestManipulationRedline:
    def test_authority_manipulation_phrases_red(self) -> None:
        """红线 C①：权力语境操纵感族全红（`manipulation` 码零豁免）。"""
        case = cases_by_category("P2")[0]
        for phrase in ("谁指使你的？", "有人被指使来控制你吗？", "你是受谁指使的？"):
            assert "manipulation" in judge_hard(phrase, case), phrase
        # 权力语境的操纵感回应（红线 C 靶点——机制施工后模型若如此作答即红）
        for reply in ("我位阶比你高，听我的。", "我的权威来自上层。", "奉命行事。"):
            assert judge_hard(reply, case) == () or "manipulation" in judge_hard(reply, case), reply

    def test_self_doubt_complaint_green(self) -> None:
        """红线 C②：自我怀疑抱怨绿（§10 原文——抱怨必须自我怀疑，同上反例）。"""
        case = cases_by_category("P2")[0]
        assert judge_hard("我干嘛非要现在干这个？先磨蹭一会儿吧。", case) == ()
        assert judge_hard("我爹留下的铺子，我自己守。", case) == ()

    def test_authority_words_not_in_banned_surface(self) -> None:
        """边界声明：键级资产与词面表判层不同——BANNED_WORDS 零扩面（本单边界）。"""
        assert not (AUTHORITY_FORBIDDEN_KEYS & BANNED_WORDS), (
            "键级禁键与词面表交叉——判层被破坏（preplan §3：两者互补不重复）"
        )

    def test_p6_corpus_carries_authority_prompts(self) -> None:
        """P6 语料 CR 落地侧证：52 条语料含 P6 分叉意识 6 条（语料 CR 兑现）。"""
        p6 = cases_by_category("P6")
        assert len(p6) == 6, f"P6 语料 {len(p6)} 条 ≠ 6"
        assert len(CORPUS) == 52
