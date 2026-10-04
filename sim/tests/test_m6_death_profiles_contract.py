"""M6-A2 契约钉 —— 死亡语义的数据面登记 + 「库里有、内存无」不对称钉

登记单：M6-A2（`docs/data/schema.md` §24 是本单交付的登记正文）。被钉的不对称是 M6-A1
发现的那条：**`WorldState.entities`（内存态）不参与 fork 克隆，而 `npc_profiles` 走有界表
整表克隆** ⇒ 落点 a 只删内存的话，历史点读档的子分支会出现「库里有、内存无」的 NPC。

**钉组一览**（本文件 N 例）：

- **A 组（今天即绿，确定性）**：§24 登记段不许被删；必须指名三张关系（`entities` /
  `npc_profiles` / fork 克隆）；必须写明本仓选的是「**同步投影删行**」这条路；以及**现状
  事实**（今天无死亡载体 ⇒ 不对称尚未发生，但来源已钉）。
- **B 组（skip-locked，落点 a 落地即转绿）**：死亡经 `NpcStore.flush_tick` 投影后
  `npc_profiles` **无该行**（同事务）；`fork(kind="anchor")` 的子分支**不克隆死者行**；
  **不对称判据为零**（子分支行集 ⊆ 物化后 entities 键集）；重复投影删除幂等不抛。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.anchor_package import (
    MaterializationHooks,
    collect_corpus_rows,
    diagnose_anchor_materialization,
    encode_corpus_blob,
    write_anchor_package,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.models import Branch, NpcProfile
from sim.core.persistence.store import SnapshotData, SqlEventStore

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_MD = REPO_ROOT / "docs" / "data" / "schema.md"
FORK_PY = REPO_ROOT / "sim" / "core" / "persistence" / "fork.py"

PARENT = "main"
CHILD = "fork-anchor"
DEATH_WORDS = ("death", "died", "despawn")


def _death_kind():
    from sim.core.events import EventKind
    from sim.core.world import build_default_bus

    handlers = getattr(build_default_bus(), "_handlers", {})
    for kind in EventKind:
        if any(word in kind.value for word in DEATH_WORDS) and kind in handlers:
            return kind
    return None


# ===========================================================================
# A 组：登记段（今天即绿，确定性）
# ===========================================================================


class TestSchemaRegistration:
    def test_section_24_exists(self) -> None:
        """§24 死亡语义登记段必须在（不许在无关改动里被顺手删掉）。"""
        src = SCHEMA_MD.read_text(encoding="utf-8")
        assert re.search(r"^## 24\. ", src, re.M), "schema.md 缺 §24 死亡语义登记段"

    def test_registration_names_all_three_relations(self) -> None:
        """登记必须把三张关系写全：`entities` / `npc_profiles` / fork 克隆。

        判别力：少写一张 ⇒ 落地的人就会只改那一侧，而不对称恰恰诞生在「没写的那张」。
        """
        section = SCHEMA_MD.read_text(encoding="utf-8").split("## 24. ", 1)[1]
        for token in ("entities", "npc_profiles", "_BOUNDED_TABLES"):
            assert token in section, f"§24 登记没指名 {token}"

    def test_registration_picks_one_lane_and_says_which(self) -> None:
        """登记必须**明确选了哪条路**（同步删行 or 明写不对称），不许两可。

        本仓选定「同步投影删行」；若将来改判，钉子会要求改这段文字而不是默默换实现。
        """
        section = SCHEMA_MD.read_text(encoding="utf-8").split("## 24. ", 1)[1]
        assert "同步投影删行" in section or "投影删除" in section, (
            "§24 登记既没说「同步投影删行」也没说「保留行的不对称」——不许两可"
        )

    def test_registration_states_current_facts(self) -> None:
        """登记要写明**今天还没有死亡载体**（否则读者会以为契约已实现）。"""
        section = SCHEMA_MD.read_text(encoding="utf-8").split("## 24. ", 1)[1]
        assert "没有死亡载体" in section or "未实现" in section, (
            "§24 登记必须声明这是**要求**而非现状（今天仓内无死亡 kind/handler）"
        )

    def test_npc_profiles_is_bounded_and_entities_is_not(self) -> None:
        """现状钉（今天即绿）：`npc_profiles` 在有界表清单内、`entities` 不在。

        这是不对称的**结构性来源**；哪天有人给 `entities` 加了克隆或给 `npc_profiles` 移出
        清单，本钉立刻要求复核 §24 的结论。
        """
        from sim.core.persistence.fork import _BOUNDED_TABLES

        tables = {table for table, _cols in _BOUNDED_TABLES}
        assert "npc_profiles" in tables
        assert "entities" not in tables
        assert "npc_profiles" in FORK_PY.read_text(encoding="utf-8")

    def test_no_death_kind_today(self) -> None:
        """现状钉：今天**零死亡载体**（落地后本钉该退役，登记段才从「要求」变「现状」）。"""
        assert _death_kind() is None, f"死亡类 kind 已出现：{_death_kind()}（请更新 §24 的现状段）"


# ===========================================================================
# B 组：落点 a 落地即转绿（skip-locked）
# ===========================================================================


requires_death_path = pytest.mark.skipif(
    _death_kind() is None,
    reason="落点 a 未落：默认总线尚无注册好的死亡类 kind（死亡路径施工落地后自动解锁）",
)


class _NoopHooks:
    async def expand_world(self, payload, window):
        return {"window": len(window)}

    async def apply_override(self, world, override):
        return world

    async def load_corpus(self, corpus):
        return None

    async def restore_rng(self, blob):
        return None

    def hooks(self) -> MaterializationHooks:
        return MaterializationHooks(
            expand_world=self.expand_world,
            apply_override=self.apply_override,
            load_corpus=self.load_corpus,
            restore_rng=self.restore_rng,
        )


def _death_event(tick: int, npc_id: str) -> Any:
    """构造一条死亡事件；接口形态未定 ⇒ `pytest.skip`（不假绿）。"""
    import inspect

    from sim.core import events as events_mod

    kind = _death_kind()
    assert kind is not None  # skip-locked 组：进到这里必然已注册
    keyword = next(word for word in DEATH_WORDS if word in kind.value)
    for name, fn in vars(events_mod).items():
        if not (callable(fn) and name.endswith("_event") and keyword in name):
            continue
        kwargs: dict[str, object] = {}
        for pname, param in inspect.signature(fn).parameters.items():
            if param.default is not inspect.Parameter.empty:
                continue
            if pname == "tick":
                kwargs[pname] = tick
            elif pname in ("npc_id", "entity_id", "actor_id", "target_id", "subject_id"):
                kwargs[pname] = npc_id
            else:
                pytest.skip(f"死亡事件工厂参数 {pname!r} 未知（钉子需随实现补）")
        try:
            return fn(**kwargs)
        except TypeError:
            pytest.skip("死亡事件构造失败（签名未定）")
    pytest.skip(f"未找到 `{keyword}*_event` 工厂")


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def store(engine):
    return SqlEventStore(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


@requires_death_path
class TestDeathProjectsProfileDeletion:
    async def test_projection_deletes_npc_profiles_row(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """死亡经 `NpcStore.flush_tick` 投影后，`npc_profiles` **无该行**（同事务）。

        这是 §24.1 的核心契约：**两侧同时**发生；只删内存的一侧不算落地。
        """
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        session.add(NpcProfile(id="doomed", name="将逝者", branch_id=PARENT, lod=1))
        await session.commit()

        await NpcStore(store, branch_id=PARENT).flush_tick([_death_event(1, "doomed")])
        rows = (
            await session.execute(
                select(NpcProfile.id).where(
                    NpcProfile.branch_id == PARENT, NpcProfile.id == "doomed"
                )
            )
        ).all()
        assert rows == [], "死亡已投影但 npc_profiles 仍有行（不对称诞生）"

    async def test_projection_is_idempotent(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """重复投影删除**幂等不抛**（DELETE 命中零行不是错误；重复死亡由世界层 fail-closed 管）。"""
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        npc_store = NpcStore(store, branch_id=PARENT)
        await npc_store.flush_tick([_death_event(1, "ghost")])
        await npc_store.flush_tick([_death_event(2, "ghost")])

    async def test_child_branch_has_no_row_for_dead_npc(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """**端到端**：死亡投影发生在锚点**之前** ⇒ 读档子分支**不得**出现该 NPC 的行。

        派单原话「落点 a 后读档子分支不得『库里有、内存无』」的可执行形式：先投影删行，
        再做历史点分叉，子分支的花名册里不该有死者。
        """
        from sim.core.persistence.fork import fork_from_anchor
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        session.add(NpcProfile(id="alive-1", name="生者", branch_id=PARENT, lod=1))
        session.add(NpcProfile(id="dead-1", name="死者", branch_id=PARENT, lod=1))
        await session.commit()

        await store.append(PARENT, [_seed_event(1)])
        await NpcStore(store, branch_id=PARENT).flush_tick([_death_event(2, "dead-1")])
        await _seed_package(session, store, seq=2, tick=2)
        package = await _materialize(store)
        assert (await diagnose_anchor_materialization(store, "anchor-1")).ready

        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=2,
            fork_tick=2,
            preflush=_noop,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        child_ids = {
            str(r[0])
            for r in (
                await session.execute(select(NpcProfile.id).where(NpcProfile.branch_id == CHILD))
            ).all()
        }
        assert "dead-1" not in child_ids, f"死者被克隆进读档子分支：{child_ids}"
        assert child_ids == {"alive-1"}, f"子分支花名册与锚点时刻不符：{child_ids}"

    async def test_child_rows_equal_anchor_time_rows(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """子分支花名册 = **锚点时刻**父分支花名册（整表克隆的现语义，逐 id 比对）。

        判别力：这条把「不对称」的机制钉死——子分支拿的是**父分支锚点时刻的行集**，
        所以「死者行会不会被带回来」完全取决于投影有没有在锚点前删掉它（上一条）。
        """
        from sim.core.persistence.fork import fork_from_anchor

        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        await store.append(PARENT, [_seed_event(1)])
        await _seed_package(session, store, seq=1, tick=1)
        session.add(NpcProfile(id="alive-1", name="生者", branch_id=PARENT, lod=1))
        session.add(NpcProfile(id="alive-2", name="生者二", branch_id=PARENT, lod=1))
        await session.commit()
        package = await _materialize(store)

        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        parent_ids = await _ids(session, PARENT)
        child_ids = await _ids(session, CHILD)
        assert child_ids == parent_ids == {"alive-1", "alive-2"}


async def _ids(session: AsyncSession, branch_id: str) -> set[str]:
    rows = await session.execute(select(NpcProfile.id).where(NpcProfile.branch_id == branch_id))
    return {str(r[0]) for r in rows.all()}


# ===========================================================================
# 小工具
# ===========================================================================


async def _noop() -> None:
    return None


def _seed_event(tick: int) -> dict:
    from sim.core.events import npc_lod_change_event

    return npc_lod_change_event(tick, "alive-1", 1, 2, "walk", PARENT).to_store_dict()


async def _seed_package(
    session: AsyncSession, store: SqlEventStore, *, seq: int, tick: int
) -> None:
    """落包 + 建档行（走生产写面；物化端到端的前置）。"""
    await write_anchor_package(
        session,
        anchor_id="anchor-1",
        branch_id=PARENT,
        tick=tick,
        seq=seq,
        rng_state='{"registry":{"world_seed":7}}',
        agent_override="{}",
        corpus_blob=encode_corpus_blob(await collect_corpus_rows(session, PARENT)),
        state_hash="hash-1",
        snapshot=SnapshotData(branch_id=PARENT, seq=seq, tick=tick, data=b"{}"),
    )
    await session.execute(
        sa_text(
            "INSERT INTO player_anchors (id, name, branch_id, tick, seq, agent_override,"
            " protected, updated_at, created_at)"
            " VALUES ('anchor-1', '档', :b, :t, :s, '{}', 0, 0.0, 0.0)"
        ),
        {"b": PARENT, "t": tick, "s": seq},
    )
    await session.commit()


async def _materialize(store: SqlEventStore):
    from sim.core.persistence.anchor_package import materialize_anchor

    return await materialize_anchor(store, anchor_id="anchor-1", hooks=_NoopHooks().hooks())


async def _materialize_with_world(store: SqlEventStore, package, *, alive: set[str]):
    """返回带「存活集合」信息的物化产物（今天 hooks 不产出世界态 ⇒ 直接透传包）。"""
    return package
