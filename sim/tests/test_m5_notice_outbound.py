"""M5-S2b F-6 出站钉 — fork_notice 出站词面（m5-fork-evidence-preplan.md §4）

F-6（codex M5-S2 发现）：`fork_notice`（ws.py:881）内插**玩家自由命名的 anchor 档名**，
而 `player_anchors.name` 无任何 banned 扫描入口——档名含禁词（AI/角色扮演/存档/…）
→ 禁词经 `session_state.notice` 直接出站（本机实测全命中）。

定性（m5-fork-evidence-preplan.md §4.2）：notice 由玩家观察视图渲染 → **DESIGN C3
界面双层铁律适用**（禁止系统词汇对玩家侧同样生效）；不回流 prompt（assembler 实测
不消费）。**表态：新出站面必须过现行 `scan()`——与裁 22-C⑤「不扩词表」不冲突**
（不扩约束的是词面集合；新面套用既有词表是既有资产的应尽消费）。

本文件只锁**出站侧现状中正确的部分**（正常档名零命中 + 固定文案干净）与
**契约 RED 钉**（注册侧 fail-closed：现无校验，预期红，施工归 Claude 写路径/
kilo 路由）。不改生产语义、不扩 BANNED_WORDS。
"""

from __future__ import annotations

import pytest

from sim.api.ws import fork_notice
from sim.llm.prompts.banned_words import scan

#: 正常档名（含空名兜底）——notice 出站零禁词命中（现状即对，锁住防回归）
_CLEAN_NAMES = (
    "初到临河",
    "第二日 · 清晨",
    "老周头的屋顶",
    "",
)
#: 玩家可自由命名的档名样本——**现状会出站禁词**（F-6 实测），注册侧 fail-closed 后应拒
_BANNED_NAMES = (
    "AI",
    "角色扮演乐园",
    "我的存档",
    "prompt注入",
    "运气机",
)


class TestForkNoticeOutboundHygiene:
    """出站侧：固定文案干净 + 正常档名零命中（锁现状）。"""

    @pytest.mark.parametrize("name", _CLEAN_NAMES)
    def test_clean_names_zero_hits(self, name: str) -> None:
        notice = fork_notice(name)
        hits = scan(notice).hits
        assert not hits, f"档名 {name!r} 的 notice 含禁词 {[(h.word) for h in hits]}: {notice!r}"

    def test_fallback_line_clean(self) -> None:
        """无档名兜底行「你回到了先前的那段日子」自身零禁词（t4-corpus §4.2 同款自洽）。"""
        assert not scan(fork_notice("")).hits

    def test_fixed_template_words_are_clean(self) -> None:
        """模板骨架词（回到/那段日子/先前）不在禁词表——文案设计即戏内口语。"""
        for word in ("回到", "那段日子", "先前"):
            assert not scan(word).hits, f"模板词 {word!r} 自身命中禁词（文案需重写）"


class TestRegistrationSideScanContract:
    """注册侧 fail-closed 契约（**RED**：现无校验；施工归 Claude 写路径/kilo 路由）。

    契约（m5-fork-evidence-preplan.md §4.2 表态 2）：
    1. `register_anchor_id`（及未来 POST/PATCH 路由）对 `name`/`story_label` 过
       现行 `scan()`；
    2. 命中 → **拒注册**（422 结构化原因，同 impulse_gate REASONS 体例——
       路由层）或**不登记叙事标签**（WS 注册层）；
    3. 禁止出站侧静默放行：若注册侧漏拦（存量行），出站侧终扫命中 → 退化
       为无档名兜底行，**不得原样出站**；
    4. **不扩 BANNED_WORDS**——本契约只消费既有词表（裁 22-C⑤）。
    """

    def test_banned_anchor_names_currently_pass_through(self) -> None:
        """**RED 指纹**（现状记录）：禁词档名经 fork_notice 原样出站。

        本断言**钉的是现状**（fail-closed 缺口本身），防止缺口被遗忘；注册侧
        扫描落地后，本用例应改为断言「拒注册/退化兜底行」并改名
        （test_banned_anchor_names_rejected_at_registration）。
        """
        leaked = [n for n in _BANNED_NAMES if scan(fork_notice(n)).hits]
        assert leaked == list(_BANNED_NAMES), (
            "F-6 现状漂移：以下档名不再出站禁词（注册侧扫描可能已落地）——"
            f"{leaked}。请把本用例改写为正式的 fail-closed 断言"
            "（test_banned_anchor_names_rejected_at_registration），勿删除"
        )

    def test_contract_requires_scan_on_name_fields(self) -> None:
        """契约可执行面：`sim/api/anchors.py` 落地 POST/PATCH 时必须 import scan。

        白盒钉（RED）：现阶段 anchors.py 无扫描调用（F-6 根因）；写路径施工时
        本断言转绿即证明契约被消费。
        """
        import pathlib

        anchors = pathlib.Path(__file__).resolve().parents[2] / "sim" / "api" / "anchors.py"
        src = anchors.read_text(encoding="utf-8")
        # 只在有写路径（POST/PATCH 路由）时才要求 scan——当前仅声明契约
        has_write_route = "post(" in src.lower() or "patch(" in src.lower()
        if not has_write_route:
            pytest.skip("anchors CRUD 路由未落地（K4 契约稿阶段）——落地时本钉自动启用")
        assert "scan(" in src, (
            "anchors 写路径已落地但 name/story_label 未过 banned scan（F-6 契约 §4.2）"
        )
