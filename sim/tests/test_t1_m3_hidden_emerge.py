"""T1 RED 钉子 ③— E1 浮现事件 + R5 证据链判定缝（M3-S3，m3-evidence-chain.md §3/§4）。

**RED 状态（本文件按 M3-S3 任务书零实现提交，预期失败即验收）**：

- 实现归 Claude 批次 B（`sim/npc/propagation.py` 的 retell() + E1 事件消费已随
  A2 第六批开工）；本文件是它的验收契约。
- 现状（2026-09-24 实测留痕）：`EventKind.NPC_HIDDEN_EMERGE` 不存在、
  `HiddenEmergePayload` 不存在、`sim/npc/evidence.py` 不存在 →
  `judge_third_party_hidden` / `EvidenceVerdict` 均不可导入。
- 裁 8 已裁：E1 采（attr_ids=新进窗口 delta，witnesses 感知层装配）；
  knowledge 五列采进 B3（opencode 合并评审后实施）——故 §5 told 形以
  **独立的 teller 知识行参数**断言（不依赖 B3 列落地）。

**X4 修订留痕（CR 已裁，裁 8）**：m3-preplan §3 X4 原文「attr ids 永不入 events」
在 R5 证据链下修订为——**descriptors/label/triggered 全量集合仍永不入事件**；
`npc.hidden_emerge` 仅承载「新进触发窗口」的 **attr_id 清单**（戏外主键
``f"{npc_id}.health_{row.id}"``，非直陈词面；与 npc_id/matter_id 同戏外审计纪律）。

契约锁定（m3-evidence-chain.md §3/§4/§8）：

A. **事件形状**：`EventKind.NPC_HIDDEN_EMERGE = "npc.hidden_emerge"` +
   `HiddenEmergePayload`（extra=forbid：npc_id + attr_ids，无第三键）+
   `PAYLOAD_MODELS` 登记（行级校验可拒绝夹带）；
B. **delta 语义**：attr_ids = 本 tick **新进窗口**（triggered_now - triggered_prev），
   合并一条；窗口抖动=每 tick 发全量是事件流噪声污染）；
C. **witnesses 装配**：感知层产出 = 该 tick 感知帧含主体的观察者；**嗅觉不计数**
   （narrate_smell 无来源归属——闻到 ≠ 目击，m3-preplan §5.11/self-unknown §2）；
D. **三路判定**（judge_third_party_hidden → EvidenceVerdict）：
   witnessed 需 emerge 事件（tick/witnesses/attr_id 三要素齐）→ 0.9；
   told 沿链衰减 0.9×0.6、下限 0.1 断链、链断 deny；inferred 一律拒；
E. **结构化拒绝**：拒绝 = `EvidenceVerdict(admitted=False, confidence=0.0,
   reason=...)`（不含 LLM 原文/词面，与闸门拒绝原因同纪律）。

失败指纹（实现前运行，26/26 RED；pyright 同报 10 个 missing-symbol）：
- `AttributeError: type object 'EventKind' has no attribute 'NPC_HIDDEN_EMERGE'`（kind 未注册）；
- `ImportError: cannot import name 'HiddenEmergePayload'/'hidden_emerge_event' from sim.core.events`
  （payload 模型 / 工厂未建，delta 装配入口同用工厂）；
- `ModuleNotFoundError: No module named 'sim.npc.evidence'`（judge_third_party_hidden /
  witnesses_of_emerge 未实现）；
- 二阶拒绝（stage-2 RED）：`test_store_row_rejects_smuggled_payload_key` /
  `test_store_row_rejects_forged_witnesses` 现在撞的是「未登记 payload 模型」
  而非「payload 校验失败」/「witnesses」——**同异常类型、不同原因串**，故以
  `"payload 校验失败" in msg` / `match="witnesses"` 锁指纹；kind 注册后这两条
  必须转为按正确原因拒绝（制造「红灯会被错误实现满足」的假象不可能）。

实现归属：Claude（批次 B4/B5，E1 消费已随 propagation.py 开工）。
CI：test_t1_m3_* 前缀随 `-m "not bench"` 全量跑（m3-plan §6 钉子清单口径）。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import EventKind
from sim.core.persistence.database import init_database
from sim.core.persistence.event_validation import EventValidationError, validate_store_row
from sim.core.persistence.store import SqlEventStore

ATTR_A = "chenmo.health_1"  # 戏外主键（npc_id.health_{row.id} 同构）
ATTR_B = "chenmo.health_2"


def _emerge_row(
    npc_id: str,
    attr_ids: tuple[str, ...],
    *,
    tick: int,
    witnesses: list[str] | None = None,
    smuggled: str | None = None,
) -> dict:
    """helpers：npc.hidden_emerge store 行（to_store_dict 形状）。"""
    payload: dict = {"npc_id": npc_id, "attr_ids": list(attr_ids)}
    if smuggled is not None:
        payload[smuggled] = "x"
    return {
        "tick": tick,
        "event_type": "npc.hidden_emerge",
        "payload": payload,
        "witnesses": list(witnesses or []),
    }


# ---------------------------------------------------------------------------
# A. 事件形状（裁 8 E1：kind 注册 + extra=forbid payload + 行级登记）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestE1EventShape:
    """E1 事件形状契约（RED：种类/payload/登记均未落）。"""

    def test_kind_registered(self) -> None:
        assert EventKind.NPC_HIDDEN_EMERGE == "npc.hidden_emerge"

    def test_payload_model_forbids_extra(self) -> None:
        from sim.core.events import HiddenEmergePayload

        with pytest.raises(ValidationError):
            HiddenEmergePayload(npc_id="chenmo", attr_ids=(ATTR_A,), descriptors=("旧伤",))

    def test_payload_accepts_attr_id_tuple(self) -> None:
        from sim.core.events import HiddenEmergePayload

        p = HiddenEmergePayload(npc_id="chenmo", attr_ids=(ATTR_A, ATTR_B))
        assert list(p.attr_ids) == [ATTR_A, ATTR_B]

    def test_payload_requires_npc_id(self) -> None:
        from sim.core.events import HiddenEmergePayload

        with pytest.raises(ValidationError):
            HiddenEmergePayload(attr_ids=(ATTR_A,))

    def test_store_row_registered_in_payload_models(self) -> None:
        """PAYLOAD_MODELS 登记 → 行级校验可拒夹带键（新 kind 纪律同现有）。"""
        validate_store_row(_emerge_row("chenmo", (ATTR_A,), tick=7, witnesses=["b"]))

    @pytest.mark.parametrize("smuggled", ["descriptors", "label", "triggered", "x"])
    def test_store_row_rejects_smuggled_payload_key(self, smuggled: str) -> None:
        """X4 修订红线：descriptor/label/triggered 词面永远进不了 E1 事件。

        RED 语义（二阶拒绝）：**先**断言 kind 已注册（`PAYLOAD_MODELS` 命中），
        **再**断言夹带键被拒。未实现时 `validate_store_row` 抛的是
        「未登记 payload 模型」而非「payload 校验失败」——两者都是
        EventValidationError，但原因串不同；不区分则红灯失去指纹意义。
        """
        row = _emerge_row("chenmo", (ATTR_A,), tick=7, smuggled=smuggled)
        with pytest.raises(EventValidationError) as exc_info:
            validate_store_row(row)
        msg = str(exc_info.value)
        assert "payload 校验失败" in msg, f"拒绝原因非 payload 夹带（未实现的指纹）：{msg}"

    def test_store_row_rejects_forged_witnesses(self) -> None:
        """stage-2 RED：kind 注册后 witnesses 仍须 list[str]。

        未实现时先撞「未登记 payload 模型」（同为 EventValidationError）→ match
        失败即 RED；实现后必须因 witnesses 类型被拒（`_validate_witnesses`）。
        """
        row = _emerge_row("chenmo", (ATTR_A,), tick=7, witnesses="b")  # type: ignore[arg-type]  # 钉住：str 不是 list
        with pytest.raises(EventValidationError, match="witnesses"):
            validate_store_row(row)

    def test_factory_rejects_non_tuple_attr_ids(self) -> None:
        from sim.core.events import hidden_emerge_event

        with pytest.raises(ValidationError):
            hidden_emerge_event(tick=1, npc_id="chenmo", attr_ids="not-a-tuple")


# ---------------------------------------------------------------------------
# B. delta 语义（仅新进窗口；无变化不发）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestE1DeltaSemantics:
    """attr_ids = triggered_now - triggered_prev；无 delta 不发事件。"""

    def _evaluate(self, *, profile, context_text: str, state: dict[str, frozenset[str]]) -> list:
        """tick 第 0 步：重估 → 产 emerge 事件列表（契约入口，实现后生效）。"""
        from sim.npc.contract import HiddenState

        prev = state["chenmo"]
        now = HiddenState(profile=profile, triggered=prev).evaluate(context_text).triggered
        state["chenmo"] = now
        delta = now - prev
        if not delta:
            return []
        from sim.core.events import hidden_emerge_event

        return [hidden_emerge_event(tick=state["_tick"], npc_id="chenmo", attr_ids=tuple(delta))]

    def test_delta_only_newly_triggered(self) -> None:
        from sim.npc.hidden import HiddenAttribute, HiddenProfile

        profile = HiddenProfile(
            npc_id="chenmo",
            attributes=(
                HiddenAttribute(
                    id=ATTR_A,
                    category="disease",
                    label="咳疾",
                    descriptors=("咳嗽",),
                    triggers=("阴雨天",),
                ),
                HiddenAttribute(
                    id=ATTR_B,
                    category="trauma",
                    label="怕水",
                    descriptors=("怕水",),
                    triggers=("河边",),
                ),
            ),
        )
        state = {"chenmo": frozenset(), "_tick": 1}
        events = self._evaluate(profile=profile, context_text="阴雨天，檐角滴雨。", state=state)
        assert len(events) == 1
        assert list(events[0].payload["attr_ids"]) == [ATTR_A]
        # 窗口内已有 A，再触发 B：只发 B（不是全量 [A, B]）
        events = self._evaluate(profile=profile, context_text="阴雨天，河边刮风。", state=state)
        assert len(events) == 1
        assert list(events[0].payload["attr_ids"]) == [ATTR_B]

    def test_no_change_no_event(self) -> None:
        from sim.npc.hidden import HiddenAttribute, HiddenProfile

        profile = HiddenProfile(
            npc_id="chenmo",
            attributes=(
                HiddenAttribute(
                    id=ATTR_A,
                    category="disease",
                    label="咳疾",
                    descriptors=("咳嗽",),
                    triggers=("阴雨天",),
                ),
            ),
        )
        state = {"chenmo": frozenset(), "_tick": 1}
        assert len(self._evaluate(profile=profile, context_text="阴雨天。", state=state)) == 1
        # 同窗口内再求值（无新增）→ 不发
        assert (
            self._evaluate(profile=profile, context_text="阴雨天，还是阴雨天。", state=state) == []
        )


# ---------------------------------------------------------------------------
# C. witnesses 装配（感知层产出；嗅觉不计数）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestE1WitnessAssembly:
    """witnesses = 该 tick 感知帧含主体的观察者；嗅觉通道不计入（闻到 ≠ 目击）。"""

    def test_witness_source_seam_exists(self) -> None:
        """装配入口存在（实现后由感知层接线；契约以可导入为最低验收）。"""
        import sim.npc.evidence as evidence

        assert hasattr(evidence, "witnesses_of_emerge")

    def test_smell_channel_not_counted(self) -> None:
        """嗅觉观测不得产生 witnesses 契约物（narrate_smell 无来源归属）。"""
        import sim.npc.evidence as evidence

        frames = {
            "b": _Frame(observations=[("smell", "chenmo", 0.9)]),
            "a": _Frame(observations=[("vision", "chenmo", 0.8)]),
        }
        got = evidence.witnesses_of_emerge(frames, subject="chenmo")
        assert "a" in got
        assert "b" not in got

    @pytest.fixture
    async def engine(self):
        eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        await init_database(eng)
        yield eng
        await eng.dispose()

    @pytest.fixture
    def store(self, engine):
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        return SqlEventStore(sf)

    async def test_emerge_event_persists_with_witnesses(self, store) -> None:
        """落库往返：E1 事件带 witnesses 进 events 表（读回 witnesses 不变形）。"""
        from sim.core.events import hidden_emerge_event

        ev = hidden_emerge_event(
            tick=3,
            npc_id="chenmo",
            attr_ids=(ATTR_A,),
            witnesses=["a", "b"],
        )
        await store.append("main", [ev.to_store_dict()])
        rows = await store.read_range("main", 1, 1)
        assert len(rows) == 1
        assert rows[0]["event_type"] == "npc.hidden_emerge"
        assert rows[0]["witnesses"] == ["a", "b"]
        assert list(rows[0]["payload"]["attr_ids"]) == [ATTR_A]


# ---------------------------------------------------------------------------
# D. 三路判定（judge_third_party_hidden → EvidenceVerdict）
# ---------------------------------------------------------------------------


def _teller_row(
    *,
    confidence: float = 0.9,
    invalidated: bool = False,
    subject_npc_id: str | None = "chenmo",
    subject_attr_id: str | None = ATTR_A,
) -> dict:
    """teller 的 knowledge 行（B3 五列形的最小戏外dict；invalidated=治理列非空）。"""
    return {
        "confidence": confidence,
        "subject_npc_id": subject_npc_id,
        "subject_attr_id": subject_attr_id,
        "invalidated": invalidated,
    }


@pytest.mark.t1
class TestEvidenceChainVerdict:
    """R5 三路判定（§8 钉子 1-6；RED：evidence 模块未实现）。"""

    def _judge(self, **kw) -> object:
        from sim.npc.evidence import judge_third_party_hidden

        return judge_third_party_hidden(**kw)

    def _as(self, v) -> tuple[object, object, str]:
        # 戏外读取 verdict 三字段（RED 期 EvidenceVerdict 未定义，鸭子类型取）。
        return (
            getattr(v, "admitted", None),
            getattr(v, "confidence", None),
            getattr(v, "reason", ""),
        )

    # ---- witnessed（§8-1/§8-2）----

    def test_witnessed_admitted(self) -> None:
        events = [_emerge_row("chenmo", (ATTR_A,), tick=10, witnesses=["b"])]
        ok, conf, reason = self._as(
            self._judge(
                source="witnessed",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=events,
                observed_tick=10,
            )
        )
        assert ok is True
        assert conf == pytest.approx(0.9)
        assert reason == "ok_witnessed"

    @pytest.mark.parametrize(
        ("observed_tick", "witnesses"),
        [
            (11, ["b"]),  # tick 不对 → deny
            (10, ["c"]),  # holder 不在 witnesses → deny
        ],
    )
    def test_witnessed_denied_on_mismatch(self, observed_tick: int, witnesses: list[str]) -> None:
        events = [_emerge_row("chenmo", (ATTR_A,), tick=10, witnesses=witnesses)]
        ok, conf, _ = self._as(
            self._judge(
                source="witnessed",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=events,
                observed_tick=observed_tick,
            )
        )
        assert ok is False
        assert conf == 0.0

    def test_witnessed_denied_without_emerge_event(self) -> None:
        ok, _, _ = self._as(
            self._judge(
                source="witnessed",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=[],
                observed_tick=10,
            )
        )
        assert ok is False

    # ---- told（§8-3/§8-4）----

    def test_told_admitted_with_decay(self) -> None:
        ok, conf, reason = self._as(
            self._judge(
                source="told",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=[],
                teller_knowledge=_teller_row(confidence=0.9),
            )
        )
        assert ok is True
        assert conf == pytest.approx(0.9 * 0.6)
        assert reason == "ok_told"

    def test_told_denied_when_teller_row_invalidated(self) -> None:
        ok, _, _ = self._as(
            self._judge(
                source="told",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=[],
                teller_knowledge=_teller_row(invalidated=True),
            )
        )
        assert ok is False

    def test_told_denied_below_floor(self) -> None:
        ok, _, _ = self._as(
            self._judge(
                source="told",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=[],
                teller_knowledge=_teller_row(confidence=0.2),  # 0.2×0.6=0.12 ok; 见下
            )
        )
        # 0.2×0.6 = 0.12 ≥ 0.1 → 仍准入；再一跳 0.072 < 0.1 应拒
        assert ok is True

        low, _, _ = self._as(
            self._judge(
                source="told",
                holder_id="c",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=[],
                teller_knowledge=_teller_row(confidence=0.12),
            )
        )
        assert low is False

    def test_told_denied_without_teller_row(self) -> None:
        ok, _, _ = self._as(
            self._judge(
                source="told",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=[],
                teller_knowledge=None,
            )
        )
        assert ok is False

    # ---- inferred（§8-6：写死无例外）----

    def test_inferred_always_denied(self) -> None:
        ok, _, _ = self._as(
            self._judge(
                source="inferred",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=[],
            )
        )
        assert ok is False

    # ---- 自我披露（§2 特例：teller == subject 作链根，无需 emerge）----

    def test_self_disclosure_is_chain_root(self) -> None:
        ok, conf, _ = self._as(
            self._judge(
                source="told",
                holder_id="b",
                subject_id="chenmo",
                attr_id=ATTR_A,
                events=[],
                teller_knowledge=_teller_row(
                    confidence=0.9, subject_npc_id="chenmo", subject_attr_id=ATTR_A
                ),
                teller_is_subject=True,
            )
        )
        assert ok is True
        assert conf == pytest.approx(0.9)  # 链根不衰减


# ---------------------------------------------------------------------------
# 本地最小观测替身（witnesses 装配断言用；不引入感知域依赖）
# ---------------------------------------------------------------------------


class _Frame:
    def __init__(self, observations: list[tuple[str, str, float]]) -> None:
        self.observations = observations
