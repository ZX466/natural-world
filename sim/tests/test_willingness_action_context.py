"""意愿独白必须**按动作**分口径；街巷句库必须够宽。

根因（2026-11-02 实测，见 `.orca/memory.md` §1g）：
1. `will.py::willingness_expression` **不收 `action` 参数**，36 句全是「不想干活」
   口径 ⇒ 人 `rest` 却配「这活儿讨价还价也没人听」、`request_chat` 却配
   「不想干就走开走开」。A 修后 band>0 的残留正是 `rest band2` 10,298 次
   + `request_chat band1` 212 次，全在错配。
2. `dialogue.py::_REGISTER_TEMPLATES["粗"]` **只有 2 句**，而生产语域恒为「粗」
   （`SpeechContext(平民, in_circle=False)`）⇒ 50 人一整天不同台词总数 = 2。

口径：
- `action` 缺省 `""` ⇒ 走通用池 + 旧选取键（既有行为**逐位不变**，旧钉子全绿）；
- 给定动作**且有专属池** ⇒ 用专属池，选取键 `(npc_name, action)`；
- **无专属池**（`move`/`build`）⇒ **池与选取键一起回落**——只回落池会静默换句；
- 每池 ≥12 句（与通用池同宽；rest 是真实库绝对主力 87,864 次，窄池=更复读）；
- 词面纪律不变：仍是自我怀疑族，禁被操纵/外部命令源（T4 band 词表同源）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1

#: 与 `test_m4_willingness.py` 同源的出戏禁词表（不许因扩池放宽）。
FORBIDDEN = ("谁在指使", "谁指使", "被指使", "有人让我", "命令我", "被控制", "被操纵")

#: 生产上真正会走到 band≥1 的动作（A 修后实测：rest / request_chat 为主）。
ACTIONS = ("rest", "eat", "work", "wander", "request_chat")


def _verdict(band: int):
    from sim.agent.will import WillingnessVerdict

    return WillingnessVerdict(score={1: 0.35, 2: 0.6, 3: 0.9}[band], band=band)


def _expr(band: int, action: str, name: str = "陈默"):
    from sim.agent.will import willingness_expression

    return willingness_expression(_verdict(band), npc_name=name, action=action)


class TestActionSpecificPools:
    @pytest.mark.parametrize("band", [1, 2, 3])
    def test_every_action_has_its_own_pool(self, band: int) -> None:
        """每个生产动作×档位都必须有专属池，且**不得比通用池窄**。

        阈值 **12** 与既有契约 `test_m4d18_believable.test_every_band_has_twelve_lines`
        同口径（通用池每档 12 句）。专属池窄于 12 就是**开了条更复读的路**：
        真实库 `npc.act` 实测 rest **87,864 次**是绝对主力（wander 30,994 /
        move 18,993 / work 6,988 / request_chat 3,124 / eat 237），
        池子一窄，主力动作的独白比它替换掉的通用池更单调，本末倒置。
        """
        from sim.agent.will import _ACTION_TEMPLATES

        missing = []
        for action in ACTIONS:
            pool = _ACTION_TEMPLATES.get(action, {}).get(band)
            if pool is None or len(pool) < 12:
                missing.append((action, band, 0 if pool is None else len(pool)))
        assert not missing, f"动作×档位专属池不足 12 句：{missing}"

    @pytest.mark.parametrize("action", ACTIONS)
    @pytest.mark.parametrize("band", [1, 2, 3])
    def test_pool_yields_eight_distinct_in_one_screen(self, action: str, band: int) -> None:
        """20 人同屏同动作同档：distinct ≥8（与通用池既有契约同口径）。"""
        from sim.agent.will import _ACTION_TEMPLATES, _pick_index

        pool = _ACTION_TEMPLATES[action][band]
        picks = {pool[_pick_index(f"villager_{i:02d}:{action}", len(pool))] for i in range(1, 21)}
        assert len(picks) >= 8, f"{action} band{band} 20 人同屏只 {len(picks)} 句"

    def test_pools_have_no_internal_duplicates(self) -> None:
        """扩池不得靠复制凑数（否则 distinct 数是假的）。"""
        from sim.agent.will import _ACTION_TEMPLATES

        for action, bands in _ACTION_TEMPLATES.items():
            for band, pool in bands.items():
                assert len(set(pool)) == len(pool), f"{action} band{band} 池内有重复句"

    def test_rest_and_work_never_share_text(self) -> None:
        """核心缺陷：`rest` 不能配**劳作抱怨**口径，`work` 也不能配歇息口径。

        注意「活儿」本身不算越界——「眼皮直打架，心里却还在盘算着活儿」正是
        歇息时的合理措辞。真正越界的是**劳作抱怨族**（讨价还价/打怵/干砸）。
        """
        from sim.agent.will import _ACTION_TEMPLATES

        work_complaint = ("讨价还价", "打怵", "干砸", "撂下", "干活的是我")
        # 「歇会儿」在 work 池里是**拖延**（band 2 本义）；「缓过来」在 band 3 是
        # 「走开缓缓再回来干」——两者都合法。真正错配的是把 work 写成**睡下去**。
        rest_action = ("躺下", "睡")
        for band in (1, 2, 3):
            rest_pool = _ACTION_TEMPLATES["rest"][band]
            work_pool = _ACTION_TEMPLATES["work"][band]
            assert not (set(rest_pool) & set(work_pool)), f"band {band}: rest 与 work 共用句子"
            for text in rest_pool:
                for word in work_complaint:
                    assert word not in text, f"rest 池混入劳作抱怨口径 {word!r}：{text!r}"
            for text in work_pool:
                for word in rest_action:
                    assert word not in text, f"work 池混入休息动作口径 {word!r}：{text!r}"

    def test_expression_uses_the_action_pool(self) -> None:
        """同一 NPC 同一档位，换动作必须换句子（旧实现恒同句）。"""
        from sim.agent.will import _ACTION_TEMPLATES

        for band in (1, 2, 3):
            rest = _expr(band, "rest")
            work = _expr(band, "work")
            assert rest is not None and work is not None
            assert rest.monologue != work.monologue
            assert rest.monologue in _ACTION_TEMPLATES["rest"][band]
            assert work.monologue in _ACTION_TEMPLATES["work"][band]

    def test_unknown_action_falls_back_to_generic_pool(self) -> None:
        """没专属池的动作回落通用池（不静默丢弃表现面）。"""
        from sim.agent.will import _TEMPLATES

        expr = _expr(2, "build")
        assert expr is not None
        assert expr.monologue in _TEMPLATES[2]

    def test_default_action_keeps_legacy_behaviour(self) -> None:
        """`action=""`（缺省）必须与旧实现逐位一致——旧钉子不红。"""
        from sim.agent.will import _TEMPLATES, willingness_expression

        verdict = _verdict(2)
        legacy = willingness_expression(verdict, npc_name="陈默")
        explicit = willingness_expression(verdict, npc_name="陈默", action="")
        assert legacy == explicit
        assert legacy is not None and legacy.monologue in _TEMPLATES[2]

    @pytest.mark.parametrize("action", ["move", "build"])
    @pytest.mark.parametrize("band", [1, 2, 3])
    def test_poolless_action_is_bit_identical_to_legacy(self, action: str, band: int) -> None:
        """**回落也必须逐位一致**：`move`/`build` 没有专属池 ⇒ 通用池 + 旧选取键。

        修前首个版本这里有个真错：池回落了，但选取键仍用 `(npc, action)` ⇒
        `move`/`build` 的独白**静默换句**（同人同档，修前一句、修后另一句）。
        这不是「无专属池 ⇒ 行为不变」，而是没声明的行为变更。钉死：
        无专属池时必须连**选取键**一起回落（键 = `npc_name`）。
        """
        from sim.agent.will import _ACTION_TEMPLATES, _TEMPLATES, willingness_expression

        assert action not in _ACTION_TEMPLATES, f"{action} 现在有专属池了，本条钉子该改写"
        verdict = _verdict(band)
        legacy = willingness_expression(verdict, npc_name="villager_07")
        with_action = willingness_expression(verdict, npc_name="villager_07", action=action)
        assert legacy == with_action
        assert with_action is not None and with_action.monologue in _TEMPLATES[band]


class TestDeterminismAndDiscipline:
    @pytest.mark.parametrize("action", ACTIONS)
    @pytest.mark.parametrize("band", [1, 2, 3])
    def test_same_input_same_output(self, action: str, band: int) -> None:
        """C5：同 (npc, action, band) ⇒ 同句。"""
        assert _expr(band, action) == _expr(band, action)

    def test_action_key_does_not_leak_into_text(self) -> None:
        """动作名是选取键，不是文本内容（同 `npc_name` 的既有纪律）。"""
        for action in ACTIONS:
            for band in (1, 2, 3):
                expr = _expr(band, action, name="villager_07")
                assert expr is not None
                assert action not in expr.monologue
                assert "villager_07" not in expr.monologue

    def test_all_action_templates_are_self_doubt(self) -> None:
        """扩池不得放宽词面纪律（全池逐句扫禁词 + 自我怀疑族）。"""
        from sim.agent.will import _ACTION_TEMPLATES, _TEMPLATES

        pools = [p for bands in _ACTION_TEMPLATES.values() for p in bands.values()]
        pools.extend(_TEMPLATES.values())
        for pool in pools:
            for text in pool:
                for word in FORBIDDEN:
                    assert word not in text, f"词面越界 {word!r}: {text!r}"

    def test_no_scores_in_action_text(self) -> None:
        from sim.agent.will import _ACTION_TEMPLATES

        for _action, bands in _ACTION_TEMPLATES.items():
            for band, pool in bands.items():
                for text in pool:
                    assert f"{0.35 + band * 0.25:.2f}" not in text


class TestChatterPoolWidth:
    """街巷句库：生产语域「粗」只有 2 句 ⇒ 50 人一整天只有 2 种台词。"""

    def test_coarse_register_has_at_least_eight_lines(self) -> None:
        from sim.agent.dialogue import _REGISTER_TEMPLATES

        assert len(_REGISTER_TEMPLATES["粗"]) >= 8

    def test_polite_and_daily_registers_widened(self) -> None:
        from sim.agent.dialogue import _REGISTER_TEMPLATES

        assert len(_REGISTER_TEMPLATES["文雅"]) >= 6
        assert len(_REGISTER_TEMPLATES["日常"]) >= 5  # 原 5 句，不得缩水

    def test_every_line_keeps_the_listener_placeholder(self) -> None:
        from sim.agent.dialogue import _REGISTER_TEMPLATES

        for register, pool in _REGISTER_TEMPLATES.items():
            for text in pool:
                assert "{listener}" in text, f"{register} 池句子缺 {{listener}}：{text!r}"

    def test_every_line_passes_banned_scan(self) -> None:
        from sim.agent.dialogue import _REGISTER_TEMPLATES
        from sim.llm.prompts.banned_words import scan

        for register, pool in _REGISTER_TEMPLATES.items():
            for text in pool:
                filled = text.format(listener="赵铁")
                assert not scan(filled).hits, f"{register} 池句子过不了 banned 面：{filled!r}"

    def test_register_lines_are_distinct(self) -> None:
        from sim.agent.dialogue import _REGISTER_TEMPLATES

        for register, pool in _REGISTER_TEMPLATES.items():
            assert len(set(pool)) == len(pool), f"{register} 池有重复句"


class TestRuntimePassesAction:
    """执行面：runtime 必须把本拍动作传给 `willingness_expression`。"""

    def test_monologue_matches_the_acted_action(self) -> None:
        from sim.agent.will import WillingnessVerdict
        from sim.core.events import EventKind
        from sim.npc.model import Need, NpcProfileData
        from sim.npc.runtime import NpcRuntime
        from sim.npc.utility import UtilityModel

        runtime = NpcRuntime(
            profiles={
                "villager_07": NpcProfileData(
                    npc_id="villager_07",
                    name="周仓",
                    lod=1,
                    needs=(Need(name="hunger", value=0.9, weight=1.0),),
                )
            },
            utility=UtilityModel(n_npc=1),
            willingness=WillingnessVerdict(score=0.6, band=2),
        )
        events = runtime.tick(10)
        act = next(e for e in events if e.event_type is EventKind.NPC_ACT)
        action = str(act.payload["action"])
        voice = next(
            e
            for e in events
            if e.event_type is EventKind.NPC_MONOLOGUE and e.payload.get("form") == "thought"
        )
        from sim.agent.will import _ACTION_TEMPLATES, _TEMPLATES

        expected_pool = _ACTION_TEMPLATES.get(action, {}).get(2, _TEMPLATES[2])
        assert voice.payload["content"] in expected_pool, (
            f"独白不属于本拍动作 {action!r} 的池：{voice.payload['content']!r}"
        )
