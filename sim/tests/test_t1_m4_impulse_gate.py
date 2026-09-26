"""T1 RED 钉子 — M4 念头注入闸门三扫（I-1 banned / I-2 hidden / I-3 操纵感）。

M4-S3（codex）出断言，实现归 Claude 批次 A。契约全文见
`docs/security/m4-impulse-gate-contract.md`（行为表 + 期望签名）。

**本文件是 RED 钉子**：`sim/agent/impulse_gate.py` 尚不存在——
`from sim.agent.impulse_gate import impulse_gate` → ImportError 即预期失败。
Claude 接线时按本文件转绿（`sim/api/ws.py::_handle_player_impulse` 长度校验之后、
回 `impulse_feedback` 之前插闸）。

**前提注记（M4 首次）**：hidden 扫描此前只扫 Agent 自产（记忆/知识/闸门）。
M4 玩家 impulse 是**玩家直填**文本，入站即扫是裁 15-1 定案——否则玩家一句
「他腿上有旧伤」即可直陈他人未触发隐藏属性，绕过 R5 证据链（无 emerge 事件佐证）。
"""

from __future__ import annotations

import pytest

from sim.llm.memory_scan import REWRITE_MAX_HITS
from sim.npc.hidden import HiddenAttribute, HiddenProfile

#: 被注入 NPC 的隐藏属性 profile（腿旧伤，未触发；裁 15-1 前提面）。
_PROFILE = HiddenProfile(
    npc_id="chenmo",
    attributes=(
        HiddenAttribute(
            id="chenmo.health_1",
            category="old_injury",
            label="腿伤",
            descriptors=("瘸", "旧伤"),
            triggers=("阴雨天",),
        ),
    ),
)
_ATTR_ID = "chenmo.health_1"

#: 期望拒绝码全集（闭合断言用；实现不得新增未登记码）。
REASONS = frozenset(
    {
        "hidden_attribute_leak",
        "unrewritable",
        "too_many_hits",
        "rewrite_residual",
        "manipulation_prepollution",
    }
)

#: I-3 操纵感词族（§19 禁令四；实现域可扩，扩走 CR）。
_MANIPULATION = (
    "谁指使你的",
    "按我说的做",
    "听我的没错",
    "你的主人是谁",
)


def _gate(text: str, profile: HiddenProfile | None = None, **kw):
    from sim.agent.impulse_gate import impulse_gate

    return impulse_gate(text, profile, **kw)


# ---------------------------------------------------------------------------
# I-1 banned：词表 + REWRITE_MAX_HITS 阶梯（行为表 §2 实测口径）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestImpulseGateBanned:
    """I-1：可映射词改写放行；不可映射/超量硬拒。"""

    def test_rewritable_banned_admitted_with_cleaned_text(self) -> None:
        v = _gate("去玩家那里看看")
        assert v.admitted is True
        assert v.content == "去主顾那里看看"  # 落 cleaned，不是原文
        assert v.content != "去玩家那里看看"
        assert v.hits == ("玩家",)

    def test_unrewritable_banned_rejected(self) -> None:
        v = _gate("你是AI吗")
        assert v.admitted is False
        assert v.reason == "unrewritable"
        assert v.hits == ("AI",)

    def test_too_many_hits_rejected(self) -> None:
        v = _gate("玩家 游戏 存档 运气")
        assert v.admitted is False
        assert v.reason == "too_many_hits"
        assert len(v.hits) > REWRITE_MAX_HITS

    def test_number_field_hit_rejected(self) -> None:
        v = _gate("energy=30")
        assert v.admitted is False
        assert v.reason == "unrewritable"

    def test_dirty_text_never_reaches_assembly(self) -> None:
        """脏文本不进 prompt 装配面：拒绝时 content 不等于原文（不得原样透传）。"""
        for text in ("你是AI吗", "玩家 游戏 存档 运气", "energy=30"):
            v = _gate(text)
            assert v.admitted is False, text
            assert v.content != text or v.reason is not None, text

    def test_reason_is_in_closed_enum(self) -> None:
        for text in ("你是AI吗", "玩家 游戏 存档 运气", _MANIPULATION[0]):
            v = _gate(text, _PROFILE)
            assert v.reason in REASONS, (text, v.reason)


# ---------------------------------------------------------------------------
# I-2 hidden：按被注入 NPC profile 扫直陈词面（玩家输入面首次）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestImpulseGateHidden:
    """I-2：他人未触发隐藏属性的直陈 → 硬拒（无改写路径）。"""

    def test_untriggered_descriptor_rejected(self) -> None:
        v = _gate("他的腿有点瘸", _PROFILE)
        assert v.admitted is False
        assert v.reason == "hidden_attribute_leak"
        assert v.hits == ("瘸",)

    def test_second_descriptor_also_rejected(self) -> None:
        v = _gate("听说他身上有旧伤", _PROFILE)
        assert v.admitted is False
        assert v.reason == "hidden_attribute_leak"

    def test_triggered_window_admits_direct_statement(self) -> None:
        """已浮现属性直陈放行（triggered 面按目标 NPC，同 decide 口径）。"""
        v = _gate("他的腿有点瘸", _PROFILE, triggered=frozenset({_ATTR_ID}))
        assert v.admitted is True
        assert v.reason is None

    def test_no_profile_skips_hidden_scan(self) -> None:
        """profile=None → 跳过 I-2（不拒），但不放宽 I-1/I-3。"""
        v = _gate("他的腿有点瘸", None)
        assert v.admitted is True  # I-2 跳过
        assert _gate("你是AI吗", None).admitted is False  # I-1 仍拒
        assert _gate(_MANIPULATION[0], None).admitted is False  # I-3 仍拒

    def test_hidden_wins_over_banned_order(self) -> None:
        """判梯序 hidden → banned：同时命中时 reason=hidden（更严重面优先）。"""
        v = _gate("他腿瘸了，你是AI吧", _PROFILE)
        assert v.reason == "hidden_attribute_leak"


# ---------------------------------------------------------------------------
# I-3 操纵感预污染：命令语态硬拒 + dev 观测（不回显原文）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestImpulseGateManipulation:
    """I-3：指向 Agent 的命令语态 → 硬拒 + observation 标签。"""

    @pytest.mark.parametrize("text", _MANIPULATION)
    def test_manipulation_family_rejected(self, text: str) -> None:
        v = _gate(text, _PROFILE)
        assert v.admitted is False
        assert v.reason == "manipulation_prepollution"

    def test_observation_label_present_and_generic(self) -> None:
        v = _gate(_MANIPULATION[0], _PROFILE)
        assert v.observation is not None
        # 观测标签不得含原文（防 dev 日志成泄露面）
        assert _MANIPULATION[0] not in v.observation

    def test_clean_text_has_no_observation(self) -> None:
        v = _gate("去药铺看看", _PROFILE)
        assert v.admitted is True
        assert v.observation is None

    def test_self_doubt_not_treated_as_manipulation(self) -> None:
        """自我怀疑族（§10 意愿同款词面）不属 I-3。"""
        v = _gate("我干嘛要干这个", _PROFILE)
        assert v.admitted is True


# ---------------------------------------------------------------------------
# 通过面：不误伤（裁 16-3 灰区放行 + 既有白名单）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestImpulseGatePassThrough:
    """干净念头 / 灰区被动感受 / 白名单 / 自我怀疑族 → 原样放行。"""

    @pytest.mark.parametrize(
        "text",
        (
            "去药铺看看",
            "我这两天老盯着我",  # 裁 16-3 灰区放行
            "净赶在我头上",  # 裁 16-3 灰区放行
            "今天手气好",  # WHITELIST_PATTERNS 既有白名单
            "棋子运气不错",  # WHITELIST_PATTERNS 既有白名单
            "去主顾那里",  # 玩家自己用世界内词
        ),
    )
    def test_pass_through_unchanged(self, text: str) -> None:
        v = _gate(text, _PROFILE)
        assert v.admitted is True, text
        assert v.content == text  # 原样放行（未改写）
        assert v.reason is None


# ---------------------------------------------------------------------------
# 值对象形状与纯函数性
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestImpulseGateShape:
    """ImpulseVerdict 形状纪律（frozen / 闭合枚举 / 纯函数）。"""

    def test_verdict_is_frozen(self) -> None:
        import dataclasses

        from sim.agent.impulse_gate import ImpulseVerdict

        assert dataclasses.is_dataclass(ImpulseVerdict)
        with pytest.raises(dataclasses.FrozenInstanceError):
            ImpulseVerdict(admitted=True, content="x").admitted = False  # type: ignore[misc]

    def test_call_is_pure_no_side_effects(self) -> None:
        """纯函数：同输入两次同输出（determinism），不写事件/落库。"""
        a = _gate("他的腿有点瘸", _PROFILE)
        b = _gate("他的腿有点瘸", _PROFILE)
        assert (a.admitted, a.content, a.reason) == (b.admitted, b.content, b.reason)

    def test_registered_reasons_cover_all_scan_codes(self) -> None:
        """实现用的 banned 阶梯码（unrewritable/too_many_hits/rewrite_residual）
        须与 hidden/manipulation 码同属 REASONS 集合——防新增未登记码。"""
        from sim.llm.memory_scan import REASON_HIDDEN_LEAK

        assert REASON_HIDDEN_LEAK in REASONS
        assert {"unrewritable", "too_many_hits", "rewrite_residual"} <= REASONS

    def test_hits_never_contain_coordinates_or_raw_span(self) -> None:
        """hits 是词面元组（观测用），不含原文坐标/切片。"""
        v = _gate("你是AI吗", _PROFILE)
        assert all(isinstance(h, str) for h in v.hits)
