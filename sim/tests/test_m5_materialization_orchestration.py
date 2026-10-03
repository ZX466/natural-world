"""M5-A11 编排链钉 —— `diagnose → materialize → fork(kind="anchor")` + hooks 注入缝

施工单：批次 E 出站编排（收官件）。被测面 = `sim/core/persistence/fork_orchestration.py`；
数据面钉在 `test_m5_materialization_package.py`（A10）。

**钉组一览**（本文件 N 例）：

- **全链正例**：注入 hooks 后一次调用走完 diagnose → materialize → fork(anchor) → 登记；
  钩子**次序铁律**逐项断言；子分支语料/火场以**包**为权威。
- **fail-closed 前置**：包缺 / rng 不可得 / 事件有洞 ⇒ `AnchorLoadUnavailable` 且
  **零副作用**（不建子分支行、钩子零调用、父分支不动）——「诊断先于分叉」的可观测证据。
- **hooks 缺省行为**：不给 `hooks` ⇒ 现行 head 分叉**逐字不变**；走物化链但未注册语义
  实现 ⇒ `hooks_unavailable` fail-closed（**不假装能展开世界态**）。
- **缝的性质**：模块级注册/取用/复位成对；`AnchorLoadUnavailable` 是 `RuntimeError` ⇒
  上层 `except Exception → load_failed` 降级体例自然接管（**不新增消息类型**）。
- **游标一致性**：包游标与 anchor 行不符 ⇒ `ForkError`（判据唯一处在 `fork.py`，编排层
  不重复实现）。
- **白盒**：编排层零 `sim.world` / `sim.npc` / `WorldState` 引用（不越域重建世界态）。
"""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import npc_lod_change_event
from sim.core.flush import flush_rows
from sim.core.persistence.anchor_package import (
    MATERIALIZATION_REASONS,
    MaterializationHooks,
    collect_corpus_rows,
    diagnose_anchor_materialization,
    encode_corpus_blob,
    write_anchor_package,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.fire_store import FireStore
from sim.core.persistence.fork import ForkError
from sim.core.persistence.fork_orchestration import (
    HOOKS_UNAVAILABLE,
    AnchorLoadUnavailable,
    OrchestrationError,
    get_materialization_hooks,
    orchestrate_load_anchor,
    orchestrate_materialized_load_anchor,
    set_materialization_hooks,
    unavailable_hooks,
)
from sim.core.persistence.models import Branch, Knowledge, NpcMemory, Relationship
from sim.core.persistence.store import SnapshotData, SqlEventStore

PARENT = "main"
CHILD = "fork-anchor"
ANCHOR_ID = "anchor-1"
RNG_BLOB = '{"registry":{"world_seed":42}}'
ORCH_PY = Path(__file__).resolve().parents[1] / "core" / "persistence" / "fork_orchestration.py"


# ---------------------------------------------------------------------------
# 夹具与工具
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def store(engine):
    return SqlEventStore(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))


@pytest.fixture(autouse=True)
def _reset_hooks():
    """每例前后都复位成 fail-closed 缺省桩（模块级注册是进程态，不能漏）。"""
    set_materialization_hooks(None)
    yield
    set_materialization_hooks(None)


class _Recorder:
    """hooks 替身：记调用序与实参（次序铁律的观测面；语义是「什么都不真做」）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.payload: Any = None
        self.window: Sequence[Mapping[str, Any]] = ()
        self.override: Any = None
        self.corpus: Any = None
        self.rng: str | None = None

    async def expand_world(self, payload, window):
        self.calls.append("expand_world")
        self.payload, self.window = payload, window
        return {"expanded": len(window)}

    async def apply_override(self, world, override):
        self.calls.append("apply_override")
        self.override = override
        return {**world, "override": dict(override)}

    async def load_corpus(self, corpus):
        self.calls.append("load_corpus")
        self.corpus = {k: [dict(r) for r in rows] for k, rows in corpus.items()}
        return

    async def restore_rng(self, blob):
        self.calls.append("restore_rng")
        self.rng = blob
        return

    def hooks(self) -> MaterializationHooks:
        return MaterializationHooks(
            expand_world=self.expand_world,
            apply_override=self.apply_override,
            load_corpus=self.load_corpus,
            restore_rng=self.restore_rng,
        )


def _snap_blob(tick: int) -> bytes:
    """快照体 = **原始 JSON 字节**（``write_snapshot`` 自己做 gzip）。"""
    import json

    return json.dumps({"tick": tick, "entities": 1}).encode()


async def _noop_preflush() -> None:
    return None


async def _advance(store: SqlEventStore, ticks: Sequence[int]) -> None:
    rows, _entropy = flush_rows(
        [npc_lod_change_event(t, "chenmo", 1, 2, "walk", PARENT) for t in ticks]
    )
    await store.append(PARENT, rows)


async def _seed_package(
    session: AsyncSession,
    store: SqlEventStore,
    *,
    anchor_id: str = ANCHOR_ID,
    seq: int | None = None,
    tick: int | None = None,
    rng_state: str | None = RNG_BLOB,
    write_snapshot: bool = True,
    snapshot_seq: int | None = None,
    snapshot_tick: int | None = None,
    before_package: Callable[[], Awaitable[None]] | None = None,
) -> tuple[int, int]:
    """建世界线 + 落包（走生产写面）；返回包游标 ``(seq, tick)``。"""
    if (await session.execute(sa_text("SELECT COUNT(*) FROM branches"))).scalar_one() == 0:
        session.add(Branch(id=PARENT, status="active", is_current=True))
        session.add(
            NpcMemory(
                entry_id="e-1",
                npc_id="chenmo",
                branch_id=PARENT,
                content="内容",
                source="event",
                importance=0.5,
                created_at_tick=0,
                event_seq=1,
            )
        )
        session.add(
            Knowledge(
                holder_id="chenmo",
                fact="井在村东",
                confidence=0.5,
                source="inferred",
                learned_at=0,
                branch_id=PARENT,
            )
        )
        session.add(
            Relationship(owner_id="chenmo", other_id="xiaoman", trust=0.5, branch_id=PARENT)
        )
        await session.commit()
    await _advance(store, [1, 2, 3])
    if before_package is not None:
        await before_package()  # 锚点之前的世界推进（起火等），包与快照都含它
    head = (
        await session.execute(
            sa_text(
                "SELECT COALESCE(MAX(seq),0), COALESCE(MAX(tick),0) FROM events"
                " WHERE branch_id = :b"
            ),
            {"b": PARENT},
        )
    ).one()
    anchor_seq = int(head[0]) if seq is None else seq
    anchor_tick = int(head[1]) if tick is None else tick
    snap_seq = None
    snap_tick = anchor_tick
    if write_snapshot:
        snap_seq = anchor_seq if snapshot_seq is None else snapshot_seq
        snap_tick = anchor_tick if snapshot_tick is None else snapshot_tick
        await store.write_snapshot(
            PARENT, tick=snap_tick, event_seq=snap_seq, blob=_snap_blob(snap_tick)
        )
    await write_anchor_package(
        session,
        anchor_id=anchor_id,
        branch_id=PARENT,
        tick=anchor_tick,
        seq=anchor_seq,
        rng_state=rng_state,
        agent_override='{"npc":"chenmo"}',
        corpus_blob=encode_corpus_blob(await collect_corpus_rows(session, PARENT)),
        state_hash="hash-1",
        snapshot=(
            None
            if snap_seq is None
            else SnapshotData(branch_id=PARENT, seq=snap_seq, tick=snap_tick, data=b"{}")
        ),
    )
    await session.execute(
        sa_text(
            "INSERT INTO player_anchors (id, name, branch_id, tick, seq, agent_override,"
            " protected, updated_at, created_at) VALUES (:aid, '档', :b, :t, :s, '{}', 0, 0.0, 0.0)"
        ),
        {"aid": anchor_id, "b": PARENT, "t": anchor_tick, "s": anchor_seq},
    )
    await session.commit()
    return anchor_seq, anchor_tick


@pytest.fixture
async def session(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        yield s


async def _branches(session: AsyncSession) -> list[str]:
    rows = (await session.execute(sa_text("SELECT id FROM branches ORDER BY id"))).all()
    return [str(r[0]) for r in rows]


async def _child_memories(session: AsyncSession, child: str = CHILD) -> list[tuple[Any, ...]]:
    rows = (
        await session.execute(
            sa_text("SELECT content FROM npc_memories WHERE branch_id = :c ORDER BY id"),
            {"c": child},
        )
    ).all()
    return [tuple(r) for r in rows]


# ===========================================================================
# 1. 全链正例
# ===========================================================================


class TestMaterializedChain:
    async def test_chain_forks_with_anchor_kind(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """全链一次调用走完 diagnose → materialize → fork(anchor) → 登记。

        判别力：fork 的 `kind` 必须真的是 `"anchor"`（不是 head）——head 会封存父分支、
        从父表截断克隆语料，正是本单要根治的病。
        """
        await _seed_package(session, store)
        rec = _Recorder()
        registered: list[str] = []
        result, materialization = await orchestrate_materialized_load_anchor(
            store.session_factory,
            anchor_id=ANCHOR_ID,
            flush_in_flight=_noop_preflush,
            hooks=rec.hooks(),
            register_child=registered.append,
            new_branch_id=CHILD,
        )
        assert result.kind == "anchor"
        assert result.new_branch_id == CHILD
        assert CHILD in await _branches(session)
        assert registered == [CHILD]
        assert materialization.seq == result.forked_from_seq

    async def test_chain_runs_hooks_in_law_order(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """钩子次序 = A3 §1.2 铁律：展开 → override → 语料 → restore_rng（编排链不许换序）。"""
        await _seed_package(session, store)
        rec = _Recorder()
        _result, materialization = await orchestrate_materialized_load_anchor(
            store.session_factory,
            anchor_id=ANCHOR_ID,
            flush_in_flight=_noop_preflush,
            hooks=rec.hooks(),
            new_branch_id=CHILD,
        )
        assert rec.calls == ["expand_world", "apply_override", "load_corpus", "restore_rng"]
        assert materialization.steps == tuple(rec.calls)
        assert rec.rng == RNG_BLOB
        assert rec.override == {"npc": "chenmo"}

    async def test_child_corpus_comes_from_package(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """子分支语料以**包**为权威：锚点之后父分支新增的记忆不进子线。"""
        anchor_seq, anchor_tick = await _seed_package(session, store)
        session.add(
            NpcMemory(
                entry_id="e-late",
                npc_id="chenmo",
                branch_id=PARENT,
                content="锚点之后",
                source="event",
                importance=0.5,
                created_at_tick=0,
                event_seq=99,
            )
        )
        await session.commit()
        await orchestrate_materialized_load_anchor(
            store.session_factory,
            anchor_id=ANCHOR_ID,
            flush_in_flight=_noop_preflush,
            hooks=_Recorder().hooks(),
            new_branch_id=CHILD,
        )
        rows = await _child_memories(session)
        assert [str(r[0]) for r in rows] == ["内容"]
        assert (anchor_seq, anchor_tick) == (await _head(store, session))

    async def test_child_fires_come_from_replay(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """火场以**物化重放**为准（可重放族不进包）：锚点之后起的新火不进子线。"""
        fires = FireStore(store, branch_id=PARENT)

        async def _ignite_old() -> None:
            await fires.upsert_fire(fire_id="f-old", x=1, y=2, tick=4)

        await _seed_package(session, store, before_package=_ignite_old)
        await fires.upsert_fire(fire_id="f-new", x=8, y=9, tick=5)
        result, _m = await orchestrate_materialized_load_anchor(
            store.session_factory,
            anchor_id=ANCHOR_ID,
            flush_in_flight=_noop_preflush,
            hooks=_Recorder().hooks(),
            new_branch_id=CHILD,
        )
        rows = (
            await session.execute(
                sa_text("SELECT fire_id FROM fires WHERE branch_id = :c ORDER BY fire_id"),
                {"c": CHILD},
            )
        ).all()
        assert [str(r[0]) for r in rows] == ["f-old"]
        assert result.cloned_rows.get("fires") == 1

    async def test_parent_not_sealed_by_anchor_load(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """历史点读档**不封存父分支**（回退旧档不动玩家正在跑的线；R-4 交接只归 head）。"""
        await _seed_package(session, store)
        await orchestrate_materialized_load_anchor(
            store.session_factory,
            anchor_id=ANCHOR_ID,
            flush_in_flight=_noop_preflush,
            hooks=_Recorder().hooks(),
            new_branch_id=CHILD,
        )
        status = (
            await session.execute(
                sa_text("SELECT status FROM branches WHERE id = :b"), {"b": PARENT}
            )
        ).scalar_one()
        assert str(status) == "active"


async def _head(store: SqlEventStore, session: AsyncSession) -> tuple[int, int]:
    row = (
        await session.execute(
            sa_text(
                "SELECT COALESCE(MAX(seq),0), COALESCE(MAX(tick),0) FROM events"
                " WHERE branch_id = :b"
            ),
            {"b": PARENT},
        )
    ).one()
    return int(row[0]), int(row[1])


# ===========================================================================
# 2. fail-closed 前置（诊断先于分叉 ⇒ 零副作用）
# ===========================================================================


class TestChainFailClosed:
    async def test_no_package_blocks_before_fork(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """老档无包 ⇒ `no_package`，且**不建子分支行**（诊断先于分叉的可观测证据）。"""
        session.add(Branch(id=PARENT, status="active", is_current=True))
        await session.commit()
        await _advance(store, [1, 2])
        await session.execute(
            sa_text(
                "INSERT INTO player_anchors (id, name, branch_id, tick, seq, agent_override,"
                " protected, updated_at, created_at)"
                " VALUES (:aid, '档', :b, 2, 2, '{}', 0, 0.0, 0.0)"
            ),
            {"aid": ANCHOR_ID, "b": PARENT},
        )
        await session.commit()
        rec = _Recorder()
        with pytest.raises(AnchorLoadUnavailable) as exc:
            await orchestrate_materialized_load_anchor(
                store.session_factory,
                anchor_id=ANCHOR_ID,
                flush_in_flight=_noop_preflush,
                hooks=rec.hooks(),
                new_branch_id=CHILD,
            )
        assert exc.value.reason == "no_package"
        assert await _branches(session) == [PARENT]
        assert rec.calls == []

    async def test_rng_unavailable_blocks_before_fork(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """包内 RNG 不可得 ⇒ `rng_unavailable`，零副作用（**不用 seed 派生兜底**）。"""
        await _seed_package(session, store, rng_state=None)
        rec = _Recorder()
        with pytest.raises(AnchorLoadUnavailable) as exc:
            await orchestrate_materialized_load_anchor(
                store.session_factory,
                anchor_id=ANCHOR_ID,
                flush_in_flight=_noop_preflush,
                hooks=rec.hooks(),
                new_branch_id=CHILD,
            )
        assert exc.value.reason == "rng_unavailable"
        assert await _branches(session) == [PARENT]
        assert rec.calls == []

    async def test_event_gap_blocks_before_fork(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """事件有洞 ⇒ `event_gap`，零副作用。

        构造：快照停在 seq=1（窗口 `(1, 3]`），再挖掉 seq=2 ⇒ 窗口有洞 ⇒ 逐位性破，
        必须在**分叉之前**就被拒。
        """
        await _seed_package(session, store, snapshot_seq=1, snapshot_tick=1)
        await session.execute(
            sa_text("DELETE FROM events WHERE branch_id = :b AND seq = 2"), {"b": PARENT}
        )
        await session.commit()
        with pytest.raises(AnchorLoadUnavailable) as exc:
            await orchestrate_materialized_load_anchor(
                store.session_factory,
                anchor_id=ANCHOR_ID,
                flush_in_flight=_noop_preflush,
                hooks=_Recorder().hooks(),
                new_branch_id=CHILD,
            )
        assert exc.value.reason == "event_gap"
        assert await _branches(session) == [PARENT]

    async def test_reason_codes_come_from_the_fixed_set(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """编排层透出的原因码 ∈ 物化五判据 +  ``hooks_unavailable``（出口只有一个集合）。"""
        await _seed_package(session, store, rng_state=None)
        with pytest.raises(AnchorLoadUnavailable) as rng_exc:
            await orchestrate_materialized_load_anchor(
                store.session_factory,
                anchor_id=ANCHOR_ID,
                flush_in_flight=_noop_preflush,
                hooks=_Recorder().hooks(),
                new_branch_id=CHILD,
            )
        assert rng_exc.value.reason in set(MATERIALIZATION_REASONS) | {HOOKS_UNAVAILABLE}

    async def test_package_cursor_mismatch_is_rejected(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """包游标与 anchor 行不符 ⇒ `ForkError`（判据唯一处在 fork.py），且不建子分支。"""
        await _seed_package(session, store)
        await session.execute(sa_text("UPDATE player_anchors SET seq = seq - 1"), {})
        await session.commit()
        with pytest.raises(ForkError, match="游标与分叉参数不符"):
            await orchestrate_materialized_load_anchor(
                store.session_factory,
                anchor_id=ANCHOR_ID,
                flush_in_flight=_noop_preflush,
                hooks=_Recorder().hooks(),
                new_branch_id=CHILD,
            )
        assert await _branches(session) == [PARENT]

    async def test_unavailable_is_catchable_as_runtime_error(self) -> None:
        """`AnchorLoadUnavailable` 是 `RuntimeError` ⇒ 上层 `except Exception` 降级体例
        （`main.py::_drain_loads` 的 ``load_failed``）自然接管，**不新增消息类型**。"""
        assert issubclass(AnchorLoadUnavailable, OrchestrationError)
        assert issubclass(AnchorLoadUnavailable, RuntimeError)


# ===========================================================================
# 3. hooks 缺省行为与注入缝
# ===========================================================================


class TestHooksSeam:
    @pytest.mark.parametrize(
        "step", ["expand_world", "apply_override", "load_corpus", "restore_rng"]
    )
    async def test_each_step_fails_closed_on_its_own(
        self, session: AsyncSession, store: SqlEventStore, step: str
    ) -> None:
        """**每一步**单独缺位都要 fail-closed（不是只有第一步会拦）。

        判别力：只钉「四步全缺」的话，把某一步改成静默空实现照样全绿——链会带着半展开的
        世界态继续往下走，最后 resume 出一个错的档。本钉逐 step 注入「只有这一步是桩」。
        """
        await _seed_package(session, store)
        rec = _Recorder()
        real = rec.hooks()
        stub = unavailable_hooks()
        hooks = MaterializationHooks(
            **{
                name: (getattr(stub, name) if name == step else getattr(real, name))
                for name in ("expand_world", "apply_override", "load_corpus", "restore_rng")
            }
        )
        with pytest.raises(AnchorLoadUnavailable) as exc:
            await orchestrate_materialized_load_anchor(
                store.session_factory,
                anchor_id=ANCHOR_ID,
                flush_in_flight=_noop_preflush,
                hooks=hooks,
                new_branch_id=CHILD,
            )
        assert exc.value.reason == HOOKS_UNAVAILABLE
        assert step in exc.value.detail or "物化钩子" in exc.value.detail
        assert await _branches(session) == [PARENT]
        # 该步之前的允许跑、之后的不许跑（次序铁律在缺位时也不许越过去）
        order = ["expand_world", "apply_override", "load_corpus", "restore_rng"]
        assert rec.calls == order[: order.index(step)]

    async def test_default_hooks_fail_closed(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """未注入语义实现 ⇒ `hooks_unavailable`（**不假装能展开世界态**），零副作用。"""
        await _seed_package(session, store)
        with pytest.raises(AnchorLoadUnavailable) as exc:
            await orchestrate_materialized_load_anchor(
                store.session_factory,
                anchor_id=ANCHOR_ID,
                flush_in_flight=_noop_preflush,
                new_branch_id=CHILD,
            )
        assert exc.value.reason == HOOKS_UNAVAILABLE
        assert await _branches(session) == [PARENT]

    async def test_registered_hooks_are_used_by_default(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """模块级注册缝：注册后不传 `hooks` 参数也走真实链（生产注入路径）。"""
        await _seed_package(session, store)
        rec = _Recorder()
        set_materialization_hooks(rec.hooks())
        result, _m = await orchestrate_materialized_load_anchor(
            store.session_factory,
            anchor_id=ANCHOR_ID,
            flush_in_flight=_noop_preflush,
            new_branch_id=CHILD,
        )
        assert result.kind == "anchor"
        assert rec.calls == ["expand_world", "apply_override", "load_corpus", "restore_rng"]

    def test_seam_roundtrip_and_reset(self) -> None:
        """注册/取用/复位成对；复位后回到 fail-closed 缺省桩。"""
        rec = _Recorder()
        assert isinstance(get_materialization_hooks(), MaterializationHooks)
        hooks = rec.hooks()
        set_materialization_hooks(hooks)
        assert get_materialization_hooks() is hooks
        set_materialization_hooks(None)
        assert get_materialization_hooks() is not hooks

    async def test_legacy_path_without_hooks_is_head_fork(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """`hooks` 不给 ⇒ 现行 head 分叉**逐字不变**（kind=head，父封存）。"""
        await _seed_package(session, store)
        result = await orchestrate_load_anchor(
            store.session_factory,
            anchor_id=ANCHOR_ID,
            flush_in_flight=_noop_preflush,
        )
        assert result.kind == "head"
        status = (
            await session.execute(
                sa_text("SELECT status FROM branches WHERE id = :b"), {"b": PARENT}
            )
        ).scalar_one()
        assert str(status) == "abandoned"

    async def test_legacy_path_still_refuses_history_point(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """回归：head 路径对历史点仍 fail-closed（不会被物化链的加入而放松）。"""
        await _seed_package(session, store)
        await session.execute(sa_text("UPDATE player_anchors SET seq = 1, tick = 1"), {})
        await session.commit()
        with pytest.raises(ForkError, match="分叉点不在父分支头部"):
            await orchestrate_load_anchor(
                store.session_factory,
                anchor_id=ANCHOR_ID,
                flush_in_flight=_noop_preflush,
            )

    async def test_dispatch_uses_chain_when_hooks_given(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """`orchestrate_load_anchor(hooks=…)` 分派到物化链（单一入口，不两套语义）。"""
        await _seed_package(session, store)
        registered: list[str] = []
        result = await orchestrate_load_anchor(
            store.session_factory,
            anchor_id=ANCHOR_ID,
            flush_in_flight=_noop_preflush,
            hooks=_Recorder().hooks(),
            register_child=registered.append,
        )
        assert result.kind == "anchor"
        assert registered == [result.new_branch_id]
        assert set(await _branches(session)) == {PARENT, result.new_branch_id}


# ===========================================================================
# 4. 白盒：编排层不越域重建世界态
# ===========================================================================


def _code_only(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    skip: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            skip.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            skip.add(tok.start[0])
    return "\n".join(line for n, line in enumerate(src.splitlines(), 1) if n not in skip)


class TestOrchestrationWhitebox:
    def test_no_world_or_npc_layer_imports(self) -> None:
        """编排层零 `sim.world` / `sim.npc` / `WorldState` 引用（语义归注入方）。"""
        code = _code_only(ORCH_PY)
        assert "sim.world" not in code
        assert "sim.npc" not in code
        assert "WorldState" not in code

    def test_pending_injection_checklist_is_documented(self) -> None:
        """待注入清单必须落在模块 docstring（不然下一个人得从头考古）。"""
        doc = ORCH_PY.read_text(encoding="utf-8")
        for step in ("expand_world", "apply_override", "load_corpus", "restore_rng"):
            assert step in doc, f"模块注缺 {step} 的归属说明"

    async def test_diagnosis_is_read_only(
        self, session: AsyncSession, store: SqlEventStore
    ) -> None:
        """诊断纯读：调用前后包行数与事件行数不变（产品轮询它也不该污染库）。"""
        await _seed_package(session, store)

        async def _count(table: str) -> int:
            return int(
                (await session.execute(sa_text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()
            )

        before = (await _count("anchor_packages"), await _count("events"))
        await diagnose_anchor_materialization(store, ANCHOR_ID)
        assert (await _count("anchor_packages"), await _count("events")) == before
