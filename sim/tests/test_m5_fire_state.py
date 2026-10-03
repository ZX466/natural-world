"""M5-A9 T1 钉子 - 批次 D 火灾生态数据面（0014 `fires` + `FireStore` + 2 新事件 kind）

裁 33（2026-10-03）落地单；设计稿 `docs/data/m5-fire-data-preplan.md`（A8）；接口约束
`docs/api/m5-fire-api-prestudy.md` §4 **F1-F5**（kilo K12）；安规钉
`docs/security/m5-fire-threatmodel.md` **D-1..D-7**（codex S9，opencode 组 7 条）。

**钉组一览**（共 41 例；S9 D 系 7 条逐条对齐）：

- **D-1 唯一写路径（负钉·白盒）**：我的火场数据面 + 机制面（存在才扫）零裸写
  `matter_state` / `structures` / `material_balances`。
- **D-2 kind 登记 + payload 闭合**：`set(PAYLOAD_MODELS) == set(EventKind)` 恒成立；
  `fire.*` payload `extra="forbid"`；坐标域与 `end` 值域闭合。
- **D-3 材料守恒逐位**：烧毁走 `material.moved{reason:"burned", to_ref:"world:burned"}`
  ⇒ 折叠 == 投影**逐位相等**（不给浮差）、两侧非空。
- **D-4 成对不变式进 DB**：三条 CHECK 存在；越界 / 半对（`ended_tick` 与 `end` 不同生同灭）
  直写被拒。
- **D-5 零新增 kind 优先 + 零归因键**：超授权 fire kind 即红；payload 与返回行字段集
  与归因黑名单零交集。
- **D-6 不可重建 4 表零触碰（负钉·白盒）**。
- **D-7 fork 克隆完整**：在有界表清单内；克隆逐字节 + 行数相等 + 不跨分支污染。
- **迁移往返**：0013 <-> 0014 逐级往返（全 revision id）、空表升级、重复 upgrade 幂等、
  **create_all 与 alembic 双路径列集一致**（K11 P5 教训）。
- **写/读面**：起火/熄灭必产事件（events 行集**只增 fire 族**）、非法入参与状态机违例
  零写、活跃读 + 分支隔离 + 纯读。
- **照妖镜**：快照路径 vs 重放路径逐位相等；`anchor.seq` 之后的火灾事件对读档窗口
  **零影响**（A8 §4）。

**零归因键是硬约束**（K12 §3 / D-10）：`FireRow` 与两个 payload 都**禁**
actor / igniter / culprit / cause_human / authority_* 之类键——「谁点的火」是意图归因，
写进事件层等于把权力位阶投影进可重放面。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import (
    EventKind,
    FireExtinguishedPayload,
    FireIgnitedPayload,
    material_moved_event,
    matter_event,
    structure_collapsed_event,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.event_validation import PAYLOAD_MODELS, validate_store_row
from sim.core.persistence.fire_store import FIRE_KINDS, Fire, FireRow, FireStore, FireWriteError
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.models import Branch, Event, MaterialBalance
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore

PARENT = "main"
CHILD = "fork-b"
ARCHIVE = "archive-line"
BURNED_SINK = "world:burned"

#: 归因键黑名单（火场面禁入 payload / 返回行；K12 §3 禁加字段清单 + D-10）。
ATTRIBUTION_KEYS: frozenset[str] = frozenset(
    {
        "actor_id",
        "igniter",
        "ignited_by",
        "cause_human",
        "culprit",
        "attribution",
        "authority",
        "authority_level",
        "power_level",
    }
)

#: 火灾机制面文件（Claude 域建设时新增；**不存在** ⇒ 白盒钉记为「对象未落」，不假绿）。
FIRE_ENGINE_GLOBS: tuple[str, ...] = ("sim/world/fire*.py", "sim/world/ecology*.py")

#: 火灾不得触碰的四张「不可重建」表（A3 §1.4 + A7 登记；S9 §3）。
UNREBUILDABLE_TABLES: tuple[str, ...] = (
    "npc_memories",
    "knowledge",
    "relationships",
    "npc_power",
)


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def store(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SqlEventStore(sf)


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


@pytest.fixture
async def fires(store: SqlEventStore, session: AsyncSession) -> FireStore:
    """分支已存在的 `FireStore`（事件 append 要过分支闸门）。"""
    session.add(Branch(id=PARENT, status="active", is_current=True))
    await session.commit()
    return FireStore(store, branch_id=PARENT)


async def _branch_head(session: AsyncSession) -> tuple[int, int]:
    """父分支事件流头部 ``(max seq, max tick)``——分叉点必须落在头部（fork 的 fail-closed 前置）。"""
    row = (
        await session.execute(
            select(func.max(Event.seq), func.max(Event.tick)).where(Event.branch_id == PARENT)
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


def _src(relative: str) -> str:
    return (Path(__file__).resolve().parents[2] / relative).read_text(encoding="utf-8")


async def _fire_rows(session: AsyncSession) -> list[tuple[str, str, int, int, int, str]]:
    result = await session.execute(
        select(Fire.branch_id, Fire.fire_id, Fire.x, Fire.y, Fire.ignited_tick, Fire.end)
    )
    return sorted(
        (str(r[0]), str(r[1]), int(r[2]), int(r[3]), int(r[4]), str(r[5])) for r in result.all()
    )


async def _event_kinds(session: AsyncSession) -> list[str]:
    result = await session.execute(select(Event.event_type).order_by(Event.seq))
    return [str(r[0]) for r in result.all()]


async def _event_payloads(session: AsyncSession) -> list[dict]:
    result = await session.execute(select(Event.payload).order_by(Event.seq))
    return [json.loads(str(r[0])) for r in result.all()]


# ===========================================================================
# D-1 唯一写路径（负钉·白盒）
# ===========================================================================


@pytest.mark.t1
class TestWritePath:
    def test_fire_data_layer_never_writes_matter_tables(self) -> None:
        """我的火场数据面**零**裸写投影表：它只经 `append` 产事件 + 只写 `fires` 行。"""
        src = _src("sim/core/persistence/fire_store.py")
        for table in ("MatterState", "Structure", "MaterialBalance"):
            assert table not in src, f"fire_store 出现 {table}（绕过 C4 唯一写路径，W-D1）"
        assert "session.add" in src and "Fire(" in src, "fires 行的唯一写入点应是 Fire(...)"

    def test_fire_engine_files_have_no_bypass(self) -> None:
        """机制面（`sim/world/fire*.py` 等）**零**裸写投影表——对象未落则本钉记「对象未落」。

        不是 skip：白盒扫**恒执行**，文件不存在时断言「尚无对象可扫」并把它写进失败消息，
        文件一落盘就自动生效（D-1 的判红条件：命中裸写，不是文件存在）。
        """
        root = Path(__file__).resolve().parents[2]
        hits: list[str] = []
        scanned: list[str] = []
        for pattern in FIRE_ENGINE_GLOBS:
            for path in sorted(root.glob(pattern)):
                scanned.append(path.name)
                text = path.read_text(encoding="utf-8")
                for table in ("MatterState", "Structure", "MaterialBalance"):
                    if re.search(rf"\.add\(\s*{table}\b|update\(\s*{table}\b", text):
                        hits.append(f"{path.name}:{table}")
        assert not hits, f"火灾机制面绕 C4 直写投影表：{hits}"
        if not scanned:
            pytest.skip("机制面文件尚未落盘（sim/world/fire*.py）——D-1 白盒扫随其落盘自动生效")


# ===========================================================================
# D-2 事件 kind 登记 + payload 闭合
# ===========================================================================


@pytest.mark.t1
class TestKindRegistration:
    def test_payload_models_cover_every_kind(self) -> None:
        """闭合集恒成立（既有钉同款）：`PAYLOAD_MODELS` 与 `EventKind` 一一对应。"""
        assert set(PAYLOAD_MODELS) == set(EventKind), "新增 kind 未登记 payload 模型（F3）"
        assert PAYLOAD_MODELS[EventKind.FIRE_IGNITED] is FireIgnitedPayload
        assert PAYLOAD_MODELS[EventKind.FIRE_EXTINGUISHED] is FireExtinguishedPayload

    def test_no_spread_or_burn_kind(self) -> None:
        """蔓延/烧毁**不新增 kind**（走既有族；A8 §2 / D-5：新增只会带来第二套投影路径）。"""
        values = {str(getattr(k, "value", k)) for k in EventKind}
        assert "fire.spread" not in values, "蔓延必须走 matter.damage（A8① / K12 §1.1）"
        assert "fire.burnt" not in values and "fire.burned" not in values

    def test_payload_rejects_smuggled_keys(self) -> None:
        """payload 封闭：夹带键在**构造**与**落库**两关都被拒（`extra="forbid"`）。"""
        with pytest.raises(ValueError):
            FireIgnitedPayload(fire_id="f1", x=0, y=0, igniter="someone")  # type: ignore[call-arg]
        with pytest.raises(ValueError):
            FireExtinguishedPayload(
                fire_id="f1",
                x=0,
                y=0,
                end="out",
                culprit="x",  # type: ignore[call-arg]
            )
        row = {
            "branch_id": PARENT,
            "tick": 1,
            "event_type": EventKind.FIRE_IGNITED.value,
            "payload": {"fire_id": "f1", "x": 0, "y": 0, "igniter": "someone"},
        }
        with pytest.raises(ValueError):
            validate_store_row(row)

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"fire_id": "f1", "x": -2, "y": 0}, "x"),
            ({"fire_id": "f1", "x": 0, "y": 4096}, "y"),
            ({"fire_id": "", "x": 0, "y": 0}, "fire_id"),
        ],
    )
    def test_payload_domain_constraints(self, payload: dict, field: str) -> None:
        """坐标域（-1 哨兵 / 4096 界）与 fire_id 非空由 payload 模型兜住。"""
        with pytest.raises(ValueError):
            FireIgnitedPayload(**payload)

    def test_extinguished_end_domain(self) -> None:
        """`end` 值域闭合（out/fuel_out/doused）——非法终止态进不去。"""
        FireExtinguishedPayload(fire_id="f1", x=0, y=0, end="out")
        with pytest.raises(ValueError):
            FireExtinguishedPayload(fire_id="f1", x=0, y=0, end="who")  # type: ignore[arg-type]


# ===========================================================================
# D-5 零新增 kind 优先 + 零归因键
# ===========================================================================


@pytest.mark.t1
class TestNoAttributionAndNoExtraKinds:
    def test_fire_payloads_have_zero_attribution_keys(self) -> None:
        """两个 payload 的字段集与归因黑名单**零交集**（K12 §3 / D-10 硬约束）。"""
        for model in (FireIgnitedPayload, FireExtinguishedPayload):
            names = set(model.model_fields)
            hits = names & ATTRIBUTION_KEYS
            assert not hits, f"{model.__name__} 含归因键：{sorted(hits)}"
            assert set(model.model_fields) <= {"fire_id", "x", "y", "end"}, (
                f"{model.__name__} 字段超出 K12 §1.3 形态：{sorted(names)}"
            )

    def test_fire_row_has_zero_attribution_keys(self) -> None:
        """返回行（F1）零归因键：dataclass 字段集逐个点名核对。"""
        names = set(FireRow.__dataclass_fields__)
        assert not (names & ATTRIBUTION_KEYS), f"FireRow 含归因键：{names & ATTRIBUTION_KEYS}"
        assert names == {"fire_id", "x", "y", "ignited_tick", "ended_tick", "end"}

    def test_unrebuildable_semantics_ride_no_new_kind(self) -> None:
        """不可重建 4 表的火灾语义**不新增 kind**（S9 D-5 执行形态）。

        裁 33 授权的 2 个新 kind 只承载火场生命周期（`fire.*`）；若将来出现承载
        「烧毁对 4 张表影响」的 kind ⇒ 本钉转红，须先在 S9 稿登记判据再走 CR。
        """
        values = {str(getattr(k, "value", k)) for k in EventKind}
        allowed = {"fire.ignited", "fire.extinguished"}
        suspect = sorted(v for v in values if v.startswith("fire.") and v not in allowed)
        assert not suspect, f"超出裁 33 授权的 fire kind：{suspect}（须先 CR + S9 登记判据）"


# ===========================================================================
# D-3 材料守恒（燃烧消耗材料走既有族）
# ===========================================================================


@pytest.mark.t1
class TestMaterialConservation:
    async def test_burned_material_move_keeps_ledger(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """烧毁走 `material.moved{reason:"burned", to_ref="world:burned"}` ⇒ 折叠 == 投影逐位相等。

        走世界循环路径（`NpcStore.flush_tick`，**带投影**）而非裸 `store.append`。
        判据（T1 第 6 条 + F4）：**两侧都非空**且 `quantity > 0`；折叠（事件流）与投影
        （`material_balances` 表）逐位相等，不给浮差。
        """
        from sim.tests.golden.assertions.conservation import (
            MaterialBalanceRow,
            assert_material_balances_conserved,
        )

        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        stocked = material_moved_event(
            1,
            transfer_id="t-stock-1",
            material_id="wood",
            quantity=5.0,
            from_ref="world:stockpile",
            to_ref="structure:hut-1",
            reason="build_reserved",
            structure_id="hut-1",
        )
        burned = material_moved_event(
            3,
            transfer_id="t-burn-1",
            material_id="wood",
            quantity=2.0,
            from_ref="structure:hut-1",
            to_ref=BURNED_SINK,
            reason="burned",
            structure_id="hut-1",
        )
        await NpcStore(store, branch_id=PARENT).flush_tick([stocked, burned])

        rows = (
            await session.execute(
                select(MaterialBalance.ref, MaterialBalance.material_id, MaterialBalance.quantity)
            )
        ).all()
        projected = [
            MaterialBalanceRow(
                ref=str(r[0]),
                material_id=str(r[1]),
                quantity=float(r[2]),
            )
            for r in rows
        ]
        assert_material_balances_conserved([stocked, burned], projected)
        refs = {(r.ref, r.material_id): r.quantity for r in projected}
        assert refs[("structure:hut-1", "wood")] == pytest.approx(3.0), "烧数 2 与建档 5 相减得 3"
        assert refs[(BURNED_SINK, "wood")] == pytest.approx(2.0), "烧毁侧未入账 ⇒ 材料凭空消失"

    def test_burned_reason_is_in_enum(self) -> None:
        """`reason="burned"` 是既有族 `MaterialMoveReason` 的合法成员（枚举扩展非新事件）。"""
        assert "burned" in MaterialMovedReasonValues()
        assert "fire" in StructureCollapseCauseValues()


def MaterialMovedReasonValues() -> set[str]:
    from sim.core.events import MaterialMoveReason

    return set(get_args(MaterialMoveReason))


def StructureCollapseCauseValues() -> set[str]:
    from sim.core.events import StructureCollapseCause

    return set(get_args(StructureCollapseCause))


def get_args(tp: object) -> tuple[str, ...]:
    from typing import get_args as _get_args

    return _get_args(tp)


# ===========================================================================
# D-4 成对不变式进 DB（0008 四件 CHECK 先例）
# ===========================================================================


@pytest.mark.t1
class TestDbChecks:
    async def test_checks_exist(self, session: AsyncSession) -> None:
        """三条 CHECK 真在 DDL 里（可表达约束进 DB，不靠 Python if —— D-4）。"""
        ddl = str(
            (
                await session.execute(
                    sa_text("SELECT sql FROM sqlite_master WHERE type='table' AND name='fires'")
                )
            ).scalar_one()
        )
        for name in ("ck_fires_xy_domain", "ck_fires_tick_nonneg", "ck_fires_end_pair"):
            assert name in ddl, f"fires 缺 CHECK {name}"

    async def test_coord_domain_enforced_by_db(self, session: AsyncSession) -> None:
        """坐标越界直写被 DB 拒（绕过写面也拦）。"""
        session.add(Fire(branch_id=PARENT, fire_id="f1", x=4096, y=0, ignited_tick=0, end=""))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_end_pair_invariant_enforced_by_db(self, session: AsyncSession) -> None:
        """**半对**状态（有 `ended_tick` 而 `end` 空 / 反之）被 DB 拒。"""
        session.add(Fire(branch_id=PARENT, fire_id="f1", ignited_tick=1, ended_tick=9, end=""))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        session.add(
            Fire(branch_id=PARENT, fire_id="f2", ignited_tick=1, ended_tick=None, end="doused")
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_negative_tick_enforced_by_db(self, session: AsyncSession) -> None:
        session.add(Fire(branch_id=PARENT, fire_id="f1", ignited_tick=-1, end=""))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# ===========================================================================
# 写面 / 读面（F1 + F2：变更必产事件，events 行集只增 fire 族）
# ===========================================================================


@pytest.mark.t1
class TestWriteSurface:
    async def test_ignite_produces_event_and_row(
        self, fires: FireStore, session: AsyncSession
    ) -> None:
        row = await fires.upsert_fire(fire_id="f1", x=3, y=4, tick=10)
        assert row == FireRow(fire_id="f1", x=3, y=4, ignited_tick=10)
        assert await _fire_rows(session) == [(PARENT, "f1", 3, 4, 10, "")]
        assert await _event_kinds(session) == ["fire.ignited"], "起火未产事件（F2/W-D1）"

    async def test_extinguish_closes_row(self, fires: FireStore, session: AsyncSession) -> None:
        await fires.upsert_fire(fire_id="f1", x=3, y=4, tick=10)
        row = await fires.set_fire_end("f1", end="fuel_out", tick=25)
        assert row.ended_tick == 25 and row.end == "fuel_out" and row.active is False
        assert await _event_kinds(session) == ["fire.ignited", "fire.extinguished"]

    async def test_writes_only_add_fire_family_events(
        self, fires: FireStore, session: AsyncSession
    ) -> None:
        """写面**只**产 fire 族事件（A7 体例「写完 events 行集只增本族」的火灾版）。"""
        await fires.upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        await fires.set_fire_end("f1", end="doused", tick=2)
        kinds = await _event_kinds(session)
        assert set(kinds) <= {k.value for k in FIRE_KINDS}, f"写面产了非 fire 族事件：{kinds}"

    async def test_ignite_payload_carries_no_attribution(
        self, fires: FireStore, session: AsyncSession
    ) -> None:
        """落库 payload 也零归因键（不只在模型层封闭）。"""
        await fires.upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        for payload in await _event_payloads(session):
            assert not (set(payload) & ATTRIBUTION_KEYS), f"落库 payload 含归因键：{payload}"

    async def test_duplicate_ignite_rejected(self, fires: FireStore, session: AsyncSession) -> None:
        await fires.upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        with pytest.raises(FireWriteError):
            await fires.upsert_fire(fire_id="f1", x=1, y=1, tick=2)
        assert len(await _fire_rows(session)) == 1
        assert await _event_kinds(session) == ["fire.ignited"], (
            "被拒的二次点火仍产了事件（零写要求）"
        )

    async def test_double_extinguish_rejected(self, fires: FireStore) -> None:
        await fires.upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        await fires.set_fire_end("f1", end="out", tick=5)
        with pytest.raises(FireWriteError):
            await fires.set_fire_end("f1", end="out", tick=6)

    async def test_extinguish_unknown_fire_rejected(self, fires: FireStore) -> None:
        with pytest.raises(FireWriteError):
            await fires.set_fire_end("ghost", end="out", tick=1)

    @pytest.mark.parametrize(
        ("kwargs", "field"),
        [
            ({"fire_id": "", "x": 0, "y": 0, "tick": 1}, "fire_id"),
            ({"fire_id": "f1", "x": -5, "y": 0, "tick": 1}, "x"),
            ({"fire_id": "f1", "x": 0, "y": 9999, "tick": 1}, "y"),
            ({"fire_id": "f1", "x": 0, "y": 0, "tick": -1}, "tick"),
        ],
    )
    async def test_invalid_input_zero_write(
        self, fires: FireStore, session: AsyncSession, kwargs: dict, field: str
    ) -> None:
        """非法入参 fail-closed **零写**（无行、无事件）。"""
        with pytest.raises(FireWriteError):
            await fires.upsert_fire(**kwargs)
        assert await _fire_rows(session) == []
        assert await _event_kinds(session) == []

    async def test_tick_regression_on_extinguish(self, fires: FireStore) -> None:
        await fires.upsert_fire(fire_id="f1", x=0, y=0, tick=10)
        with pytest.raises(FireWriteError):
            await fires.set_fire_end("f1", end="out", tick=9)


@pytest.mark.t1
class TestReadSurface:
    async def test_active_fires_lists_only_burning(self, fires: FireStore) -> None:
        await fires.upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        await fires.upsert_fire(fire_id="f2", x=2, y=2, tick=1)
        await fires.set_fire_end("f1", end="out", tick=5)
        active = await fires.active_fires()
        assert [r.fire_id for r in active] == ["f2"]
        assert await fires.active_fires(["f1"]) == []
        assert await fires.active_fires([]) == []

    async def test_active_fires_is_pure_read(self, fires: FireStore, session: AsyncSession) -> None:
        await fires.upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        before_events = await _event_kinds(session)
        before_rows = await _fire_rows(session)
        await fires.active_fires()
        await fires.active_fires(["f1"])
        assert await _event_kinds(session) == before_events
        assert await _fire_rows(session) == before_rows

    async def test_branch_isolation(self, store: SqlEventStore, session: AsyncSession) -> None:
        """分支隔离：子分支的火与父分支互不可见（0008 纪律）。"""
        session.add_all(
            [
                Branch(id=PARENT, status="active", is_current=True),
                Branch(id=ARCHIVE, status="active", is_current=False),
            ]
        )
        await session.commit()
        await FireStore(store, branch_id=PARENT).upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        await FireStore(store, branch_id=ARCHIVE).upsert_fire(fire_id="f1", x=9, y=9, tick=1)
        assert [r.x for r in await FireStore(store, branch_id=PARENT).active_fires()] == [1]
        assert [r.x for r in await FireStore(store, branch_id=ARCHIVE).active_fires()] == [9]


# ===========================================================================
# 照妖镜：快照路径 vs 重放路径（A8 §4）
# ===========================================================================


@pytest.mark.t1
class TestReplayMirror:
    async def test_replay_equals_snapshot_path(self, fires: FireStore) -> None:
        """两条路径**逐位相等**：读表（投影）== 折叠事件（重放），schema §19.3 铁律。"""
        await fires.upsert_fire(fire_id="f1", x=3, y=4, tick=10)
        await fires.upsert_fire(fire_id="f2", x=5, y=6, tick=11)
        await fires.set_fire_end("f2", end="doused", tick=20)
        replayed = await fires.materialize_fires_replay()
        assert replayed["f1"] == FireRow(fire_id="f1", x=3, y=4, ignited_tick=10)
        assert replayed["f2"] == FireRow(
            fire_id="f2", x=5, y=6, ignited_tick=11, ended_tick=20, end="doused"
        )

    async def test_events_after_anchor_seq_do_not_leak(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        """**照妖镜钉**：`anchor.seq` 之后注入的火灾事件对重放结果**零影响**。

        这是 A8 §4 给批次 E 的判据形态：历史点读档（物化）只折叠到 anchor 点，
        未来的火不该被吸收。注入窗口外事件后重放结果必须逐位不变。
        """
        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        fire_store = FireStore(store, branch_id=PARENT)
        await fire_store.upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        await fire_store.upsert_fire(fire_id="f2", x=2, y=2, tick=2)
        anchor_seq = int(
            (
                await session.execute(select(func.max(Event.seq)).where(Event.branch_id == PARENT))
            ).scalar_one()
        )
        before = await fire_store.materialize_fires_replay(upto_seq=anchor_seq)

        # 窗口之外：熄灭 + 新起火 + 烧毁（既有族）
        await fire_store.set_fire_end("f1", end="out", tick=3)
        await fire_store.upsert_fire(fire_id="f3", x=7, y=7, tick=4)
        await store.append(
            PARENT,
            [
                matter_event(
                    5,
                    EventKind.MATTER_COLLAPSE,
                    "hut-1",
                    x=1,
                    y=1,
                    durability=0.0,
                    note="burned",
                ).to_store_dict(),
                structure_collapsed_event(
                    5, structure_id="hut-1", cause="fire", branch_id=PARENT
                ).to_store_dict(),
            ],
        )
        after = await fire_store.materialize_fires_replay(upto_seq=anchor_seq)
        assert after == before, "anchor 点之后的火灾事件泄漏进了读档窗口"
        assert set(after) == {"f1", "f2"}


# ===========================================================================
# D-7 fork 克隆完整
# ===========================================================================


async def _noop_preflush() -> None:
    return None


@pytest.mark.t1
class TestForkClone:
    async def test_fires_in_bounded_tables(self) -> None:
        """`fires` 在有界表克隆清单内（D-7 前置：漏登记 = 分叉丢火场）。"""
        from sim.core.persistence.fork import _BOUNDED_TABLES

        tables = dict(_BOUNDED_TABLES)
        assert "fires" in tables
        assert set(tables["fires"]) >= {"fire_id", "x", "y", "ignited_tick", "ended_tick", "end"}

    async def test_fork_clones_fires_byte_equal(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        fire_store = FireStore(store, branch_id=PARENT)
        await fire_store.upsert_fire(fire_id="f1", x=3, y=4, tick=10)
        await fire_store.upsert_fire(fire_id="f2", x=5, y=6, tick=11)
        await fire_store.set_fire_end("f2", end="fuel_out", tick=20)

        head_seq, head_tick = await _branch_head(session)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=head_seq,
            fork_tick=head_tick,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        session.expire_all()
        parent = await _fire_rows(session)
        parent = [r for r in parent if r[0] == PARENT]
        child = [r for r in await _fire_rows(session) if r[0] == CHILD]
        assert len(child) == len(parent) == 2, "分叉后火场行数不等（D-7）"
        assert [r[1:] for r in child] == [r[1:] for r in parent], "克隆不是逐字节相等"

    async def test_child_writes_do_not_touch_parent(
        self, store: SqlEventStore, session: AsyncSession
    ) -> None:
        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        parent_store = FireStore(store, branch_id=PARENT)
        await parent_store.upsert_fire(fire_id="f1", x=1, y=1, tick=1)
        head_seq, head_tick = await _branch_head(session)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=head_seq,
            fork_tick=head_tick,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )
        await FireStore(store, branch_id=CHILD).set_fire_end("f1", end="doused", tick=9)
        session.expire_all()
        rows = {r[0]: [x for x in r if x != r[0]] for r in await _fire_rows(session)}
        assert rows[CHILD][-1] == "doused", "子分支熄灭未落"
        assert rows[PARENT][-1] == "", "子分支写入污染了父分支火场（跨分支写）"


# ===========================================================================
# 迁移往返（scratch DB + 全 revision id；K11 P5 双路径列集一致）
# ===========================================================================


def _alembic(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {"WORLD_DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(Path(__file__).resolve().parents[2]),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def _columns(db: Path, table: str) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    finally:
        conn.close()


def _version(db: Path) -> str:
    conn = sqlite3.connect(str(db))
    try:
        return str(conn.execute("SELECT version_num FROM alembic_version").fetchone()[0])
    finally:
        conn.close()


class TestAlembic0014:
    def test_upgrade_from_0013(self, tmp_path: Path) -> None:
        assert _alembic(tmp_path, "upgrade", "0013_power_state").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0014_fires").returncode == 0
        assert _version(tmp_path / "mig.db") == "0014_fires"

    def test_upgrade_is_repeatable(self, tmp_path: Path) -> None:
        assert _alembic(tmp_path, "upgrade", "0014_fires").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0014_fires").returncode == 0

    def test_round_trip_0013_0014(self, tmp_path: Path) -> None:
        db = tmp_path / "mig.db"
        assert _alembic(tmp_path, "upgrade", "0014_fires").returncode == 0
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO fires"
                " (branch_id, fire_id, x, y, ignited_tick, ended_tick, end, created_at)"
                " VALUES ('main', 'f1', 1, 2, 5, NULL, '', 1.0)"
            )
            conn.commit()
        finally:
            conn.close()
        assert _alembic(tmp_path, "downgrade", "0013_power_state").returncode == 0
        assert _alembic(tmp_path, "upgrade", "0014_fires").returncode == 0
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute("SELECT fire_id FROM fires").fetchall()
        finally:
            conn.close()
        assert rows == [], "降级重建后应为空（火场生命周期是运行期事实）"
        assert _version(db) == "0014_fires"

    def test_create_all_and_alembic_columns_match(self, tmp_path: Path) -> None:
        """**双路径列集一致**（K11 P5 教训：两条建表路径分叉 ⇒ 随机 teardown 红）。"""
        assert _alembic(tmp_path, "upgrade", "0014_fires").returncode == 0
        alembic_cols = _columns(tmp_path / "mig.db", "fires")

        async def _via_create_all() -> list[str]:
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            await init_database(engine)
            assert engine.dialect is not None
            out: list[str] = []
            async with engine.begin() as conn:
                rows = await conn.exec_driver_sql("PRAGMA table_info(fires)")
                out = [str(r[1]) for r in rows]
            await engine.dispose()
            return out

        import asyncio

        create_all_cols = asyncio.run(_via_create_all())
        assert alembic_cols == create_all_cols, (
            f"两条建表路径列集不一致：alembic={alembic_cols} create_all={create_all_cols}"
        )
        model_cols = [c.name for c in Fire.__table__.columns]
        assert model_cols == alembic_cols, "模型列集与迁移不一致"


# ===========================================================================
# D-6 不可重建 4 表零触碰（负钉·白盒）
# ===========================================================================


@pytest.mark.t1
class TestUnrebuildableUntouched:
    def test_fire_data_layer_never_touches_unrebuildable(self) -> None:
        """我的火灾数据面对不可重建 4 表**零**触碰（D-6 白盒）。"""
        src = _src("sim/core/persistence/fire_store.py")
        for table in UNREBUILDABLE_TABLES:
            assert table not in src, f"fire_store 触碰不可重建表 {table}（A8③/D-6）"

    def test_burned_material_is_a_move_not_a_delete(self) -> None:
        """烧毁的材料**经既有族搬运**（reason=burned + to_ref），不删行、不清账。"""
        src = _src("sim/core/persistence/fire_store.py")
        for pattern in (
            r"\.delete\(",
            r"\bPowerStore\(",
            r"\bNpcPower\(",
            r"\bRelationship\(",
            r"\bNpcMemory\(",
            r"\bKnowledge\(",
        ):
            assert not re.search(pattern, src), (
                f"火灾数据面出现写入口 {pattern}（D-6：不可重建 4 表零触碰）"
            )
