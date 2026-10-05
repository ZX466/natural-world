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
NPC_STORE_PY = REPO_ROOT / "sim" / "core" / "persistence" / "npc_store.py"

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
        """登记要写明**实现现状**（退役版「要求而非现状」钉）。

        落点 a 落地后，§24 现状段必须写明「同步投影删行**已实现**」并给出处
        （handler/投影函数名）——读者不会再把契约误当未实现，也不会误信未实现。
        """
        section = SCHEMA_MD.read_text(encoding="utf-8").split("## 24. ", 1)[1]
        assert "已实现" in section or "已落地" in section, (
            "§24 现状段未随落点 a 落地更新（仍停在「要求而非现状」口径）"
        )
        assert "_apply_npc_death" in section and "_project_npc_death" in section, (
            "§24 现状段未给两侧实现出处（状态层 handler + 投影删行函数）"
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

    def test_death_kind_registered_and_profiles_named(self) -> None:
        """落点 a 已落（退役版「现状钉」）：死亡 kind 在默认总线，且 §24 现状段已更新。"""
        kind = _death_kind()
        assert kind is not None, "死亡类 kind 未注册（落点 a 回退？）"
        text = SCHEMA_MD.read_text(encoding="utf-8")
        # 现状段必须从「今天无载体」更新为「已落地=同步投影删行」的口径
        assert "同步投影删" in text or "同步删" in text, "§24 现状段未更新（仍是「落地前」口径）"


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


# ===========================================================================
# npc_health 组（M6-A5）：活体状态机**也要**删；物质账本**保留**
# ===========================================================================


def _health_deletion_landed() -> bool:
    """锁信号：`_project_npc_death` **函数体内**出现 `NpcHealth`。

    用 ast 取函数真身 + tokenize 剥注释/字符串后再找（与 A1 锁信号同手法的理由）：
    注释或头注里先写表名**不算落地**（文档先行的假解锁是本仓已吃过的坑——A3 fog），
    锁必须打在代码体上。
    """
    import ast
    import io
    import tokenize

    src = NPC_STORE_PY.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:  # pragma: no cover - 源码坏了就让这组 skip，不误报红
        return False
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
            and n.name == "_project_npc_death"
        ),
        None,
    )
    if fn is None:
        return False
    seg = ast.get_source_segment(src, fn) or ""
    code = "\n".join(
        tok.string
        for tok in tokenize.generate_tokens(io.StringIO(seg).readline)
        if tok.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    return "NpcHealth" in code


requires_health_deletion = pytest.mark.skipif(
    not _health_deletion_landed(),
    reason="npc_health 对称删除未落：`_project_npc_death` 尚不碰 NpcHealth（落地后自动解锁）",
)
requires_no_health_deletion = pytest.mark.skipif(
    _health_deletion_landed(),
    reason="npc_health 对称删除已落：残留已被正向钉接管，反向钉退役",
)

_CATEGORY = "disease"


async def _seed_npc_with_health(
    session: AsyncSession, *, npc_id: str, branch_id: str = PARENT, hidden: bool = True
) -> None:
    """种一个「有花名册行 + 有隐藏属性行」的 NPC（活体状态机的两面）。"""
    from sim.core.persistence.models import NpcHealth

    session.add(NpcProfile(id=npc_id, name=f"npc-{npc_id}", branch_id=branch_id, lod=1))
    session.add(
        NpcHealth(
            npc_id=npc_id,
            branch_id=branch_id,
            category=_CATEGORY,
            label="secret",
            hidden=hidden,
            active=True,
        )
    )


async def _health_ids(session: AsyncSession, branch_id: str, npc_id: str) -> set[str]:
    from sim.core.persistence.models import NpcHealth

    rows = await session.execute(
        select(NpcHealth.label).where(NpcHealth.branch_id == branch_id, NpcHealth.npc_id == npc_id)
    )
    return {str(r[0]) for r in rows.all()}


# ---------------------------------------------------------------------------
# A 组：登记节（今天即绿，确定性）
# ---------------------------------------------------------------------------


class TestSchemaLivingVsLedgerBoundary:
    """§24.4「活体状态机删、物质账本留」必须登记在案（不许只在对话里说过）。"""

    def _section_24_4(self) -> str:
        src = SCHEMA_MD.read_text(encoding="utf-8")
        m = re.search(r"^### 24\.4 .*?(?=^#{2,3} |\Z)", src, re.M | re.S)
        assert m is not None, "schema.md 缺 §24.4（主体删行边界登记段）"
        return m.group(0)

    def test_section_24_4_exists(self) -> None:
        self._section_24_4()

    def test_registration_names_four_tables_with_verdicts(self) -> None:
        """四张表都要点名，且每张都要有明确判决（`npc_health` 删、`matter_state` 留）。"""
        sec = self._section_24_4()
        for table in ("npc_profiles", "npc_health", "matter_state", "material_balances"):
            assert table in sec, f"§24.4 未点名 {table}（漏一张就会长出同类残留）"
        assert "**删**" in sec, "§24.4 未写「删」的判决"
        assert "**保留**" in sec, "§24.4 未写「保留」的判决（matter_state 是登记不是漏删）"

    def test_registration_states_the_ledger_justification(self) -> None:
        """保留物质账本必须给出**理由**（否则后人会当成漏删来「修」）。"""
        sec = self._section_24_4()
        assert "T1" in sec, "§24.4 的物质保留理由必须点名 T1 材料守恒"
        assert "materialize_hidden" in sec, "§24.4 必须记录装配反向事实（只查 npc_health 不 JOIN）"

    def test_npc_health_is_a_bounded_table(self) -> None:
        """机制钉：`npc_health` 在有界表清单里 ⇒ 随 fork 整表克隆 ⇒ 死者行会被带进子分支。

        这是「必须删」的根因（不是洁癖）：克隆源里留着，就等于给死亡开了复活后门。
        """
        from sim.core.persistence.fork import _BOUNDED_TABLES

        tables = {table for table, _cols in _BOUNDED_TABLES}
        assert "npc_health" in tables


# ---------------------------------------------------------------------------
# 反向钉：钉住**落地前**的残留（今天即绿；对称删除落地即自动退役）
# ---------------------------------------------------------------------------


@requires_no_health_deletion
class TestHealthResidueToday:
    @pytest.mark.t1
    async def test_death_leaves_health_row_and_assembly_keeps_dead_npc(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """**今天的残留**（这正是本组钉子的存在理由，落地后本钉退役）：

        1) `npc_profiles` 行已删（§24.1 兑现）；
        2) `npc_health` 行**还在**；
        3) `materialize_hidden()` **仍装配死者的隐藏属性**（它只查 npc_health，不 JOIN
           npc_profiles）⇒ agent 决策输入里仍有死人。
        """
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        await _seed_npc_with_health(session, npc_id="doomed")
        await session.commit()

        await NpcStore(store, branch_id=PARENT).flush_tick([_death_event(1, "doomed")])

        assert await _ids(session, PARENT) == set(), "前提不成立：npc_profiles 行没删"
        assert await _health_ids(session, PARENT, "doomed") == {"secret"}, "今天不该已删健康行"
        hidden = await NpcStore(store, branch_id=PARENT).materialize_hidden()
        assert "doomed" in hidden, "今天 materialize_hidden 应仍返回死者（残留的装配面证据）"


# ---------------------------------------------------------------------------
# B 组：npc_health 对称删除落地即转绿（skip-locked）
# ---------------------------------------------------------------------------


@requires_health_deletion
class TestDeathProjectsHealthDeletion:
    async def test_projection_deletes_npc_health_row(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """对称删除：`npc_health` 行随死亡**同事务**删除（活体状态机两面一起删）。"""
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        await _seed_npc_with_health(session, npc_id="doomed")
        await session.commit()

        await NpcStore(store, branch_id=PARENT).flush_tick([_death_event(1, "doomed")])
        assert await _health_ids(session, PARENT, "doomed") == set(), "死亡已投影但健康行仍在"

    async def test_projection_is_idempotent_when_health_row_absent(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """幂等：健康行不存在时重复投影**不抛**（DELETE 命中零行不是错误）。"""
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        npc_store = NpcStore(store, branch_id=PARENT)
        await npc_store.flush_tick([_death_event(1, "ghost")])
        await npc_store.flush_tick([_death_event(2, "ghost")])

    async def test_materialize_hidden_excludes_dead_npc(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """**装配反向钉**：死者不再出现在 `materialize_hidden()` 的装配结果里。

        这条独立于「行删没删」——即便有人未来改走读侧过滤，这条也照样绿；
        反之，若只加 JOIN 过滤而不删行，fork 克隆那条仍会红（两处一起钉，避免单点修法）。
        """
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        await _seed_npc_with_health(session, npc_id="doomed")
        await _seed_npc_with_health(session, npc_id="alive-1")
        await session.commit()

        npc_store = NpcStore(store, branch_id=PARENT)
        hidden = await npc_store.materialize_hidden()
        assert "doomed" in hidden, "前提不成立：死者本该先在装配结果里（否则本钉无判别力）"

        await npc_store.flush_tick([_death_event(1, "doomed")])
        hidden = await npc_store.materialize_hidden()
        assert "doomed" not in hidden, "死者仍在 agent 决策输入的隐藏属性里"
        assert "alive-1" in hidden, "投影误伤活人（删除不按主体？)"

    async def test_fork_does_not_clone_dead_health_row(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """fork 克隆钉：死者的 `npc_health` 行不得被整表克隆进读档子分支。"""
        from sim.core.persistence.fork import fork_from_anchor
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        await _seed_npc_with_health(session, npc_id="alive-1")
        await _seed_npc_with_health(session, npc_id="dead-1")
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
        assert await _health_ids(session, CHILD, "dead-1") == set(), "死者健康行被克隆进子分支"
        assert await _health_ids(session, CHILD, "alive-1") == {"secret"}, "子分支丢了活人的健康行"

    async def test_health_deletion_is_scoped_to_branch_and_npc(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """双键口径：只删「本分支的这个 NPC」，不误删同名 id 的他分支行、也不误删本分支他人。"""
        from sim.core.persistence.npc_store import NpcStore

        session.add(Branch(id=PARENT, status="active", is_current=True))
        session.add(Branch(id=CHILD, status="active", is_current=False))
        await _seed_npc_with_health(session, npc_id="doomed", branch_id=PARENT)
        await _seed_npc_with_health(session, npc_id="doomed", branch_id=CHILD)
        await _seed_npc_with_health(session, npc_id="bystander", branch_id=PARENT)
        await session.commit()

        await NpcStore(store, branch_id=PARENT).flush_tick([_death_event(1, "doomed")])
        assert await _health_ids(session, PARENT, "doomed") == set(), "本分支死者行未删"
        assert await _health_ids(session, PARENT, "bystander") == {"secret"}, "误删了旁人"
        assert await _health_ids(session, CHILD, "doomed") == {"secret"}, (
            "跨分支误删（未按 branch_id 限定）"
        )
