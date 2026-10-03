"""M5-A10 T1 钉子 —— 批次 E 物化单（anchor_packages 读写面 + 物化器 + `kind` 参数化）

施工案 `docs/data/m5-anchor-materialization-preplan.md`（A3，预研稿即施工案）；
安规钉 `docs/security/m5-batch-e-security-preplan.md` **E-1..E-5 + E-13**（codex S10，
opencode 组 6 条）；G3 小单（A6 现状断言双态化）落在
`sim/tests/test_m5_anchors_branch_source.py::TestForkHandoverForm`。

**钉组一览**（本文件 N 例）：

- **包写面**：存档事务内一次物化（快照指针成对 / rng / override / state_hash / 幂等覆盖）、
  语料 blob 编解码**逐位**往返（含向量二进制列）、**确定性字节**（同输入同字节）。
- **包内容边界（构造性）**：解码白名单外键一律丢弃 ⇒ 「那第 4 张无事件源表」进不了包，
  也读不出来；**不为火扩格式**（包列集零火、包表清单零火）。
- **次序铁律**：展开 → 套 override → 灌语料 → restore_rng，四步各一次、顺序可观测。
- **fail-closed 五判据**：`no_package` / `rng_unavailable` / `snapshot_missing` /
  `event_gap` / `corpus_mismatch`，**失败时零钩子被调用**（不返回部分包）。
- **读档窗口**：快照必带 `max_seq=anchor.seq`（同 tick 多事件不倒挂）；退化全前缀重放；
  **`anchor.seq` 之后的事件对物化结果逐位零影响**（照妖镜体例）。
- **fires 可重放族整合**：火场经 `materialize_fires_replay` 重建（不进包）；
  `fork(kind="anchor")` 写进子分支的行 = 锚点时刻那批，父分支之后起的新火**不进子线**。
- **`kind` 参数化**：`head` 行为逐字不变（回归）；`anchor` 必须带包（缺则 `ForkError`）、
  游标逐项对齐、语料以包为权威、父分支**不封存**且可继续 append、权力态**零克隆**。
- **E 系 6 钉**（S10 归属）+ 白盒负钉（离线推进面零玩家档写入、包编解码零权力字面量）。

**判别力说明**：多数钉的强判据是「**父分支的『未来』不该渗进历史点子线**」——所以每条
关键钉都会在锚点之后**故意在父分支加东西**（新记忆/新关系/新火），子分支必须看不见。
"""

from __future__ import annotations

import ast
import gzip
import io
import json
import struct
import tokenize
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import npc_lod_change_event
from sim.core.flush import flush_rows
from sim.core.persistence.anchor_package import (
    CORPUS_TABLES,
    MATERIALIZATION_REASONS,
    AnchorMaterializationError,
    MaterializationHooks,
    collect_corpus_rows,
    decode_corpus_blob,
    diagnose_anchor_materialization,
    encode_corpus_blob,
    materialize_anchor,
    write_anchor_package,
)
from sim.core.persistence.database import init_database
from sim.core.persistence.fire_store import FireStore
from sim.core.persistence.fork import ForkError, fork_from_anchor
from sim.core.persistence.models import (
    AnchorPackage,
    Branch,
    Event,
    Fire,
    Knowledge,
    NpcMemory,
    NpcPower,
    PlayerAnchor,
    Relationship,
)
from sim.core.persistence.store import SnapshotData, SqlEventStore

PARENT = "main"
CHILD = "fork-anchor"
HEAD_CHILD = "fork-head"
ANCHOR_ID = "anchor-1"
RNG_BLOB = json.dumps({"materials": {"default": "state-packet"}})

#: 本单要扫的生产面（白盒负钉目标；E-1/E-4 的「对象」）。
PACKAGE_PY = Path(__file__).resolve().parents[1] / "core" / "persistence" / "anchor_package.py"
FORK_PY = Path(__file__).resolve().parents[1] / "core" / "persistence" / "fork.py"
#: 批次 E 离线推进面（Claude 域建设时新增；**不存在** ⇒ 记为「对象未落」，不假绿）。
DRILL_GLOBS: tuple[str, ...] = ("sim/world/offline*.py", "sim/core/offline*.py")
#: 仓库根 / alembic 版本目录（白盒钉专用：同步钉里做路径 IO）。
REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = Path(__file__).resolve().parents[1] / "core" / "persistence" / "alembic" / "versions"


# ---------------------------------------------------------------------------
# 夹具与小工具
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
async def world(session: AsyncSession):
    """一条世界线：分支 + 三张语料表各一行 + 权力态一行（事件由各钉自己推进）。"""
    session.add(Branch(id=PARENT, status="active", is_current=True))
    session.add(_memory("e-1"))
    session.add(_knowledge("他知道井在哪", evidence_seq=1))
    session.add(_relationship("chenmo", "xiaoman", trust=0.5))
    session.add(NpcPower(npc_id="chenmo", power_level=0.7, branch_id=PARENT))
    await session.commit()
    return session


async def _advance(store: SqlEventStore, ticks: Sequence[int]) -> None:
    rows, _entropy = flush_rows(
        [npc_lod_change_event(t, "chenmo", 1, 2, "walk", PARENT) for t in ticks]
    )
    await store.append(PARENT, rows)


def _memory(
    entry_id: str,
    *,
    branch_id: str = PARENT,
    content: str = "内容",
    event_seq: int = 1,
    created_at_tick: int = 0,
    superseded_by: str | None = None,
    embedding: bytes | None = None,
) -> NpcMemory:
    return NpcMemory(
        entry_id=entry_id,
        npc_id="chenmo",
        branch_id=branch_id,
        content=content,
        source="event",
        importance=0.5,
        created_at_tick=created_at_tick,
        event_seq=event_seq,
        superseded_by=superseded_by,
        embedding=embedding,
    )


def _knowledge(
    fact: str,
    *,
    branch_id: str = PARENT,
    evidence_seq: int | None = None,
    source_memory: str | None = None,
    source_knowledge_id: int | None = None,
) -> Knowledge:
    return Knowledge(
        holder_id="chenmo",
        fact=fact,
        confidence=0.6,
        source="witnessed" if evidence_seq is not None else "inferred",
        learned_at=0,
        branch_id=branch_id,
        evidence_seq=evidence_seq,
        source_memory=source_memory,
        source_knowledge_id=source_knowledge_id,
    )


def _relationship(
    owner: str,
    other: str,
    *,
    branch_id: str = PARENT,
    trust: float = 0.5,
) -> Relationship:
    return Relationship(owner_id=owner, other_id=other, trust=trust, branch_id=branch_id)


def _snap_blob(tick: int) -> bytes:
    """快照体 = **原始 JSON 字节**（``write_snapshot`` 自己做 gzip）。"""
    return json.dumps({"tick": tick, "entities": 3}).encode()


async def _write_package(
    session: AsyncSession,
    *,
    anchor_id: str = ANCHOR_ID,
    seq: int,
    tick: int,
    branch_id: str = PARENT,
    rng_state: str | None = RNG_BLOB,
    override: str = '{"npc":"chenmo"}',
    state_hash: str | None = "hash-1",
    snapshot: tuple[int, int] | None = None,
    corpus_blob: bytes | None = None,
) -> None:
    """走**生产写面**落包（存档路径同款调用序）。"""
    blob = (
        encode_corpus_blob(await collect_corpus_rows(session, branch_id))
        if corpus_blob is None
        else corpus_blob
    )
    await write_anchor_package(
        session,
        anchor_id=anchor_id,
        branch_id=branch_id,
        tick=tick,
        seq=seq,
        rng_state=rng_state,
        agent_override=override,
        corpus_blob=blob,
        state_hash=state_hash,
        snapshot=(
            None
            if snapshot is None
            else SnapshotData(branch_id=branch_id, seq=snapshot[0], tick=snapshot[1], data=b"{}")
        ),
    )
    await session.commit()


class _Recorder:
    """钩子记录器：记调用序 + 各步收到的实参（次序铁律的观测面）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.payload: Any = None
        self.window: Sequence[Mapping[str, Any]] = ()
        self.override: Any = None
        self.corpus: Any = None
        self.rng: str | None = None
        self.world: Any = None

    async def expand_world(self, payload, window):
        self.calls.append("expand_world")
        self.payload, self.window = payload, window
        self.world = {"payload": dict(payload), "window": len(window)}
        return self.world

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


async def _noop_preflush() -> None:
    return None


async def _head_and_tick(session: AsyncSession, branch_id: str = PARENT) -> tuple[int, int]:
    row = (
        await session.execute(
            select(func.max(Event.seq), func.max(Event.tick)).where(Event.branch_id == branch_id)
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


async def _row_count(
    session: AsyncSession, sql: str, params: Mapping[str, Any] | None = None
) -> int:
    return int((await session.execute(sa_text(sql), params or {})).scalar_one())


async def _child_rows(
    session: AsyncSession, table: str, columns: str, order: str, child: str = CHILD
) -> list[tuple[Any, ...]]:
    rows = (
        await session.execute(
            sa_text(f"SELECT {columns} FROM {table} WHERE branch_id = :cid ORDER BY {order}"),
            {"cid": child},
        )
    ).all()
    return [tuple(r) for r in rows]


async def _package_row(session: AsyncSession, anchor_id: str = ANCHOR_ID) -> AnchorPackage:
    return (
        await session.execute(select(AnchorPackage).where(AnchorPackage.anchor_id == anchor_id))
    ).scalar_one()


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _code_only(path: Path) -> str:
    """只留代码（去掉 docstring 与注释）——白盒负钉扫「实现」而不是「口径说明」。"""
    src = _src(path)
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


def _vec(row: Sequence[object]) -> bytes:
    """打包行里的向量列（比较用；float32 小端）。"""
    raw = row[0]
    assert isinstance(raw, (bytes, bytearray)), raw
    return bytes(raw)


def _float_blob(values: Sequence[float]) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


# ===========================================================================
# 1. 包写面（存档事务内一次物化）
# ===========================================================================


class TestPackageWriteFace:
    async def test_write_lands_every_column(self, world: AsyncSession) -> None:
        """写面逐字段落库（游标 / 快照指针 / rng / override / blob / state_hash / 版本）。

        判别力：漏列是这类写面最常见的病——某列不落 ⇒ 读档端拿到「看着有包、其实不完整」的
        半包，比没有包更坏。
        """
        await _write_package(world, seq=3, tick=3, snapshot=(1, 1))
        row = await _package_row(world)
        assert (row.anchor_id, row.branch_id, row.tick, row.seq) == (ANCHOR_ID, PARENT, 3, 3)
        assert (row.snapshot_seq, row.snapshot_tick) == (1, 1)
        assert row.rng_state == RNG_BLOB
        assert row.agent_override == '{"npc":"chenmo"}'
        assert row.state_hash == "hash-1"
        assert row.corpus_blob is not None
        assert row.schema_version == 1

    async def test_snapshot_pointer_pair_or_neither(self, world: AsyncSession) -> None:
        """快照指针**同有同无**：写面只产出两态（都有 / 都无），半对值被 0011 CHECK 拒。

        判别力：只写 seq 不写 tick 的实现会把「引用哪个快照」变成不可判定的悬空指针。
        """
        await _write_package(world, seq=3, tick=3, snapshot=None)
        assert (await _package_row(world)).snapshot_seq is None
        assert (await _package_row(world)).snapshot_tick is None
        await _write_package(world, anchor_id="anchor-snap", seq=3, tick=3, snapshot=(2, 2))
        row = await _package_row(world, "anchor-snap")
        assert (row.snapshot_seq, row.snapshot_tick) == (2, 2)

        with pytest.raises(IntegrityError, match="ck_anchor_packages_snapshot_pair"):
            await world.execute(
                sa_text(
                    "INSERT INTO anchor_packages"
                    " (anchor_id, branch_id, tick, seq, snapshot_seq, agent_override,"
                    "  schema_version, created_at)"
                    " VALUES ('anchor-bad', :b, 3, 3, 2, '{}', 1, 0.0)"
                ),
                {"b": PARENT},
            )
            await world.commit()
        await world.rollback()
        assert (
            await _row_count(
                world, "SELECT COUNT(*) FROM anchor_packages WHERE anchor_id = 'anchor-bad'"
            )
            == 0
        )

    async def test_write_is_idempotent_overwrite(self, world: AsyncSession) -> None:
        """同一 anchor 重复存档 ⇒ 覆盖为最新一版（不留半包、不报「已存在」）。

        判别力：存档按钮连点两次/改名重存是产品常态；第二次若撞唯一键，玩家会看到 500。
        """
        await _write_package(world, seq=2, tick=2, state_hash="hash-a")
        await _write_package(world, seq=3, tick=3, state_hash="hash-b")
        rows = await _row_count(world, "SELECT COUNT(*) FROM anchor_packages")
        row = await _package_row(world)
        assert rows == 1
        assert (row.seq, row.state_hash) == (3, "hash-b")

    async def test_write_does_not_touch_player_cursor(self, world: AsyncSession) -> None:
        """E-2（数据面半）：写包**零玩家档游标推进**——包是档的附属物，不是档本身。"""
        world.add(PlayerAnchor(id=ANCHOR_ID, name="档", branch_id=PARENT, tick=3, seq=3))
        await world.commit()
        before = (
            await world.execute(select(PlayerAnchor.tick, PlayerAnchor.seq, PlayerAnchor.name))
        ).one()
        await _write_package(world, seq=4, tick=4)
        after = (
            await world.execute(select(PlayerAnchor.tick, PlayerAnchor.seq, PlayerAnchor.name))
        ).one()
        assert tuple(before) == tuple(after), "写包顺手改了玩家档游标"

    async def test_events_not_swallowed_by_package_write(self, world: AsyncSession, store) -> None:
        """E-3（数据面半）：写包**不吞事件**——`events` 行数增量 == 推进 tick 数。"""
        await _advance(store, [1, 2, 3, 4])
        assert await _row_count(world, "SELECT COUNT(*) FROM events") == 4
        await _write_package(world, seq=4, tick=4)
        assert await _row_count(world, "SELECT COUNT(*) FROM events") == 4


# ===========================================================================
# 2. 语料 blob 编解码（逐位 + 确定性 + 构造性包边界）
# ===========================================================================


class TestCorpusCodec:
    def test_round_trip_is_bit_exact(self) -> None:
        """编解码**逐位**往返（含向量二进制列 + 空表 + 中文内容）。

        判别力：向量是 `LargeBinary`，JSON 直编会炸或静默变 base64 串——记忆内容对得上、
        向量对不上，召回质量悄悄掉一档。
        """
        rows = {
            "npc_memories": [
                {
                    "id": 1,
                    "entry_id": "e-1",
                    "content": "井在村东",
                    "embedding": _float_blob([1.0, 2.0]),
                    "importance": 0.5,
                },
                {"id": 2, "entry_id": "e-2", "content": "天要下雨", "embedding": None},
            ],
            "knowledge": [],
            "relationships": [
                {"owner_id": "a", "other_id": "b", "trust": 0.25, "created_at": 12.0}
            ],
        }
        out = decode_corpus_blob(encode_corpus_blob(rows))
        assert out == rows
        assert out["npc_memories"][0]["embedding"] == _float_blob([1.0, 2.0])

    def test_encoding_is_deterministic(self) -> None:
        """同输入 ⇒ 同字节（``mtime=0`` + ``sort_keys``）——R-2 对账/回归需要可比 blob。"""
        rows = {"npc_memories": [{"id": 2, "entry_id": "b"}, {"id": 1, "entry_id": "a"}]}
        assert encode_corpus_blob(rows) == encode_corpus_blob(dict(rows))

    def test_unknown_table_keys_are_dropped(self) -> None:
        """**构造性包边界**：解码只认白名单，硬塞进来的表键**一律丢弃**。

        这是 S10 §2.3 裁定的落地形态：权力态那张表即使被人手工塞进 blob，读档路径也拿不到
        它——不靠「记得别写」，靠结构。
        """
        blob = _blob_from({"npc_power": [{"npc_id": "chenmo", "power_level": 0.9}]})
        out = decode_corpus_blob(blob)
        assert "npc_power" not in out
        assert set(out) == set(CORPUS_TABLES)

    def test_encode_also_filters_allowlist(self) -> None:
        """编码侧同样过滤（调用方传了也写不进去）——白名单在编解码两侧都在。"""
        blob = encode_corpus_blob({"npc_power": [{"npc_id": "x"}], "knowledge": [{"id": 7}]})
        out = decode_corpus_blob(blob)
        assert set(out) == set(CORPUS_TABLES)
        assert out["knowledge"] == [{"id": 7}]

    def test_corrupt_blob_fails_closed(self) -> None:
        """坏 blob ⇒ `corpus_mismatch` fail-closed（不当成「空语料」糊过去）。"""
        with pytest.raises(AnchorMaterializationError) as exc:
            decode_corpus_blob(b"not-a-gzip")
        assert exc.value.reason == "corpus_mismatch"

    async def test_collect_rows_matches_decode(self, world: AsyncSession) -> None:
        """采集 → 编码 → 解码 恒等（读-编-解自洽，不丢列）。"""
        rows = await collect_corpus_rows(world, PARENT)
        assert decode_corpus_blob(encode_corpus_blob(rows)) == rows
        assert rows["relationships"][0]["owner_id"] == "chenmo"
        assert set(rows) == set(CORPUS_TABLES)

    async def test_collect_rows_are_branch_scoped(self, world: AsyncSession) -> None:
        """采集只取本分支行（别人的语料不进包——进包=跨分支越权读）。"""
        world.add(_memory("e-2", branch_id="other", content="别人的记忆"))
        world.add(_relationship("chenmo", "xiaoman", branch_id="other", trust=0.9))
        await world.commit()
        rows = await collect_corpus_rows(world, PARENT)
        assert [r["entry_id"] for r in rows["npc_memories"]] == ["e-1"]
        assert len(rows["relationships"]) == 1


def _blob_from(tables: Mapping[str, list[dict]]) -> bytes:
    """直接手搓 blob（绕过编码器的过滤，用来证明**解码侧**也拦）。"""
    body = json.dumps({"schema_version": 1, "tables": tables}, sort_keys=True).encode()
    return gzip.compress(body, mtime=0)


# ===========================================================================
# 3. 次序铁律（A3 §1.2：展开 → override → 语料 → RNG）
# ===========================================================================


class TestApplicationOrderIsLaw:
    async def test_order_is_expand_override_corpus_rng(self, world: AsyncSession, store) -> None:
        """四步顺序**逐项**断言，且各只调一次。

        判别力：顺序错了代码仍能跑（override 被快照覆盖、语料灌完又被 RNG 换掉都不报错），
        只有把序钉死才留得住。
        """
        await _advance(store, [1, 2])
        await store.write_snapshot(PARENT, tick=2, event_seq=2, blob=_snap_blob(2))
        await _write_package(world, seq=2, tick=2, snapshot=(2, 2))
        rec = _Recorder()
        result = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert rec.calls == ["expand_world", "apply_override", "load_corpus", "restore_rng"]
        assert result.steps == tuple(rec.calls)

    async def test_each_step_receives_its_argument(self, world: AsyncSession, store) -> None:
        """每步拿到的实参对得上：payload/窗口、override 映射、语料行值、RNG 串原样。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=3, tick=3, snapshot=(1, 1))
        rec = _Recorder()
        await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert rec.payload == {"tick": 1, "entities": 3}
        assert [int(e["seq"]) for e in rec.window] == [2, 3]
        assert rec.override == {"npc": "chenmo"}
        assert rec.corpus["npc_memories"][0]["entry_id"] == "e-1"
        assert rec.rng == RNG_BLOB

    async def test_override_applied_after_expansion(self, world: AsyncSession, store) -> None:
        """override 落在**展开之后**（快照里存着旧 override 时，先套会被覆盖）。"""
        await _advance(store, [1])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=1, tick=1, snapshot=(1, 1), override='{"npc":"替代"}')
        rec = _Recorder()
        result = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert result.world["override"] == {"npc": "替代"}
        assert rec.calls.index("apply_override") > rec.calls.index("expand_world")

    async def test_corpus_loaded_before_rng(self, world: AsyncSession, store) -> None:
        """语料灌入在 restore_rng **之前**（RNG 恢复是最后一环，之后才 resume）。"""
        await _advance(store, [1])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=1, tick=1, snapshot=(1, 1))
        rec = _Recorder()
        await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert rec.calls.index("load_corpus") < rec.calls.index("restore_rng")


# ===========================================================================
# 4. fail-closed 五判据（失败 ⇒ 零钩子被调用，不返回部分包）
# ===========================================================================


class TestFailClosedReasons:
    async def test_no_package(self, world: AsyncSession, store) -> None:
        """老档没包 ⇒ `no_package`，且**零钩子被调用**。"""
        rec = _Recorder()
        with pytest.raises(AnchorMaterializationError) as exc:
            await materialize_anchor(store, anchor_id="ghost", hooks=rec.hooks())
        assert exc.value.reason == "no_package"
        assert rec.calls == []

    async def test_rng_null_is_unavailable(self, world: AsyncSession, store) -> None:
        """`rng_state` NULL ⇒ `rng_unavailable`（**禁止** seed 派生兜底）。"""
        await _advance(store, [1])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=1, tick=1, snapshot=(1, 1), rng_state=None)
        rec = _Recorder()
        with pytest.raises(AnchorMaterializationError) as exc:
            await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert exc.value.reason == "rng_unavailable"
        assert rec.calls == []

    async def test_rng_blank_counts_as_unavailable(self, world: AsyncSession, store) -> None:
        """空串/纯空白同样算「不可得」——空包不是有效包。"""
        await _advance(store, [1])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=1, tick=1, snapshot=(1, 1), rng_state="   ")
        with pytest.raises(AnchorMaterializationError) as exc:
            await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        assert exc.value.reason == "rng_unavailable"

    async def test_snapshot_missing_when_prefix_has_hole(self, world: AsyncSession, store) -> None:
        """无快照 + 全前缀有洞 ⇒ `snapshot_missing`（重放起点不可得）。"""
        await _advance(store, [1, 2, 3])
        await _write_package(world, seq=3, tick=3, snapshot=None)
        await world.execute(
            sa_text("DELETE FROM events WHERE branch_id = :b AND seq = 2"), {"b": PARENT}
        )
        await world.commit()
        rec = _Recorder()
        with pytest.raises(AnchorMaterializationError) as exc:
            await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert exc.value.reason == "snapshot_missing"
        assert rec.calls == []

    async def test_event_gap_inside_window(self, world: AsyncSession, store) -> None:
        """有快照但窗口内有洞 ⇒ `event_gap`（窗口折叠会跳事件 ⇒ 逐位性破）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=3, tick=3, snapshot=(1, 1))
        await world.execute(
            sa_text("DELETE FROM events WHERE branch_id = :b AND seq = 2"), {"b": PARENT}
        )
        await world.commit()
        with pytest.raises(AnchorMaterializationError) as exc:
            await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        assert exc.value.reason == "event_gap"

    async def test_two_failures_are_distinguished(self, world: AsyncSession, store) -> None:
        """两判据**互斥且可分辨**：同一条「有洞」，有快照报 `event_gap`、
        无快照报 `snapshot_missing`。"""
        await _advance(store, [1, 2, 3])
        await world.execute(
            sa_text("DELETE FROM events WHERE branch_id = :b AND seq = 2"), {"b": PARENT}
        )
        await world.commit()
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, anchor_id="with-snap", seq=3, tick=3, snapshot=(1, 1))
        await _write_package(world, anchor_id="no-snap", seq=3, tick=3, snapshot=None)
        with pytest.raises(AnchorMaterializationError) as gap:
            await materialize_anchor(store, anchor_id="with-snap", hooks=_Recorder().hooks())
        # 第二段：把快照行删掉（模拟快照已 GC）⇒ 退化路径的判据换成 `snapshot_missing`。
        # 口径注：物化取「库内 ≤锚点 seq 的最新快照」，**不以包内指针为准**（指针只是存档
        # 时刻的记录；快照被 GC 时就该退化为全前缀重放，A3 §1.1）。
        await world.execute(sa_text("DELETE FROM snapshots WHERE branch_id = :b"), {"b": PARENT})
        await world.commit()
        with pytest.raises(AnchorMaterializationError) as missing:
            await materialize_anchor(store, anchor_id="no-snap", hooks=_Recorder().hooks())
        assert (gap.value.reason, missing.value.reason) == ("event_gap", "snapshot_missing")

    async def test_corpus_mismatch_is_in_reason_set(self) -> None:
        """原因码固定集包含五个（出站面只允许回这些码）。"""
        assert MATERIALIZATION_REASONS == (
            "no_package",
            "rng_unavailable",
            "snapshot_missing",
            "event_gap",
            "corpus_mismatch",
        )

    async def test_unknown_reason_code_rejected(self) -> None:
        """自造原因码直接拒（原因码是契约，不是自由文本）。"""
        with pytest.raises(ValueError, match="未知物化原因码"):
            AnchorMaterializationError("because_i_said_so")

    async def test_diagnose_never_raises(self, world: AsyncSession, store) -> None:
        """诊断面**不抛异常**：不可物化的档要说得出原因，而不是让玩家撞 500。"""
        diag = await diagnose_anchor_materialization(store, "ghost")
        assert (diag.ready, diag.reason) == (False, "no_package")

    async def test_diagnose_ready_reports_snapshot_ref(self, world: AsyncSession, store) -> None:
        """就绪档给出快照引用（产品据此显示「可回退」）。"""
        await _advance(store, [1, 2])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=2, tick=2, snapshot=(1, 1))
        diag = await diagnose_anchor_materialization(store, ANCHOR_ID)
        assert diag.ready is True
        assert diag.reason is None
        assert diag.snapshot_seq == 1

    async def test_diagnose_does_not_write(self, world: AsyncSession, store) -> None:
        """诊断面**零写入**（纯读面；产品轮询它也不该污染库）。"""
        await _advance(store, [1])
        await _write_package(world, seq=1, tick=1, snapshot=None)
        before = await _row_count(world, "SELECT COUNT(*) FROM anchor_packages")
        await diagnose_anchor_materialization(store, ANCHOR_ID)
        assert await _row_count(world, "SELECT COUNT(*) FROM anchor_packages") == before


# ===========================================================================
# 5. 读档窗口（快照 seq 上界 / 退化重放 / 照妖镜）
# ===========================================================================


class TestReplayWindow:
    async def test_snapshot_respects_anchor_seq_bound(self, world: AsyncSession, store) -> None:
        """同 tick 两个快照时，物化必须取 ``seq <= anchor.seq`` 的那个（窗口不倒挂）。

        判别力：只按 tick 选会挑到 seq 已越过锚点的快照 ⇒ 窗口倒挂、`seq=2` 的事件被跳过，
        而结果是「看着能读档」的半世界。
        """
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=3, event_seq=1, blob=_snap_blob(1))
        await store.write_snapshot(PARENT, tick=3, event_seq=3, blob=_snap_blob(3))
        await _write_package(world, seq=2, tick=3, snapshot=(1, 1))
        rec = _Recorder()
        result = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert result.snapshot_seq == 1
        assert rec.payload == {"tick": 1, "entities": 3}

    async def test_full_prefix_replay_fallback(self, world: AsyncSession, store) -> None:
        """无快照 + 事件连续 ⇒ 退化为**全前缀重放**（重放起点 0，窗口 = 全部事件）。

        判别力：快照被 GC 是常态（留最近 8 份 + 每日首份）；退化路径必须给出与快照路径
        逐位相同的世界态，否则「老档不可读」就变成了「老档读出来是另一个世界」。
        """
        await _advance(store, [1, 2, 3])
        await _write_package(world, seq=3, tick=3, snapshot=None)
        rec = _Recorder()
        result = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert result.replay_from_seq == 0
        assert result.payload == {}
        assert [int(e["seq"]) for e in result.window] == [1, 2, 3]

    async def test_post_anchor_events_are_invisible(self, world: AsyncSession, store) -> None:
        """照妖镜：`anchor.seq` 之后注入任意事件 ⇒ 物化结果**逐位不变**。"""
        await _advance(store, [1, 2])
        await store.write_snapshot(PARENT, tick=2, event_seq=2, blob=_snap_blob(2))
        await _write_package(world, seq=2, tick=2, snapshot=(2, 2))
        before = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        await _advance(store, [3, 4])
        await FireStore(store, branch_id=PARENT).upsert_fire(fire_id="f-late", x=7, y=7, tick=3)
        after = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        assert after.window == before.window
        assert after.payload == before.payload
        assert after.fires == before.fires
        assert after.corpus == before.corpus

    async def test_state_hash_is_passed_through(self, world: AsyncSession, store) -> None:
        """``state_hash`` 原样透出（R-2 对账/回归基线，不在读档端重算）。"""
        await _advance(store, [1])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=1, tick=1, snapshot=(1, 1), state_hash="hash-42")
        result = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        assert result.state_hash == "hash-42"

    async def test_override_blank_falls_back_to_empty(self, world: AsyncSession, store) -> None:
        """坏/空 override ⇒ 空覆盖（**不改身份**，fail-safe 而不是 fail-closed）。"""
        await _advance(store, [1])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        await _write_package(world, seq=1, tick=1, snapshot=(1, 1), override="")
        rec = _Recorder()
        result = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=rec.hooks())
        assert rec.override == {}
        assert result.agent_override == {}


# ===========================================================================
# 6. fires 可重放族整合（批次 D 增量；**不为火扩格式**）
# ===========================================================================


class TestFireReplayFamilyIntegration:
    async def test_fires_rebuilt_by_replay(self, world: AsyncSession, store) -> None:
        """火场 = `materialize_fires_replay(upto_seq=锚点 seq)` 的**逐位**结果（可重放族）。

        口径注：锚点是**事件 seq**（不是 tick）——`fire.*` 事件与 lod 事件共享 seq 序列。
        """
        await _advance(store, [1, 2])
        fires = FireStore(store, branch_id=PARENT)
        await fires.upsert_fire(fire_id="f-1", x=3, y=4, tick=1)
        await fires.upsert_fire(fire_id="f-2", x=5, y=6, tick=2)
        head_seq, head_tick = await _head_and_tick(world)
        await store.write_snapshot(
            PARENT, tick=head_tick, event_seq=head_seq, blob=_snap_blob(head_tick)
        )
        await _write_package(world, seq=head_seq, tick=head_tick, snapshot=(head_seq, head_tick))
        result = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        expected = await fires.materialize_fires_replay(upto_seq=head_seq)
        assert result.fires == expected
        assert sorted(result.fires) == ["f-1", "f-2"]

    async def test_fire_after_anchor_is_invisible(self, world: AsyncSession, store) -> None:
        """锚点之后起火/熄火 ⇒ 对物化结果**零影响**（A8 §4 照妖镜体例）。"""
        await _advance(store, [1, 2])
        fires = FireStore(store, branch_id=PARENT)
        await fires.upsert_fire(fire_id="f-1", x=3, y=4, tick=1)
        head_seq, head_tick = await _head_and_tick(world)
        await store.write_snapshot(
            PARENT, tick=head_tick, event_seq=head_seq, blob=_snap_blob(head_tick)
        )
        await _write_package(world, seq=head_seq, tick=head_tick, snapshot=(head_seq, head_tick))
        before = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        await fires.upsert_fire(fire_id="f-late", x=9, y=9, tick=3)
        await fires.set_fire_end(fire_id="f-1", tick=4, end="out")
        after = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        assert after.fires == before.fires

    async def test_package_carries_no_fire_column(self) -> None:
        """E-13：**不为火扩格式**——`AnchorPackage` 列集零火相关列（火不进包）。"""
        columns = {c.name for c in AnchorPackage.__table__.columns}
        assert not {c for c in columns if "fire" in c or "ignit" in c or "flame" in c}
        assert "corpus_blob" in columns

    async def test_fire_is_not_a_corpus_table(self) -> None:
        """火场不在语料白名单内（它可重放，不需要行值快照）。"""
        assert "fires" not in CORPUS_TABLES
        assert CORPUS_TABLES == ("npc_memories", "knowledge", "relationships")

    async def test_materializer_emits_no_mechanism_fire_object(self) -> None:
        """「历史点读档**不还原火场**」落码：产出只有表行值，无机制面火对象。

        判别力：白盒扫物化器零机制面火类引用（只有 `FireRow` 这类数据面行）。
        """
        code = _code_only(PACKAGE_PY)
        assert "FireStore" in code  # 数据面重放器允许
        assert "sim.world" not in code  # 机制面零引用
        assert "WorldState" not in code  # 世界态重建归 ws 层（钩子注入）


# ===========================================================================
# 7. `kind` 参数化 + 语料克隆源切包（fork）
# ===========================================================================


async def _anchor_package(
    store: SqlEventStore,
    session: AsyncSession,
    *,
    seq: int,
    tick: int,
    snapshot: tuple[int, int] | None,
    anchor_id: str = ANCHOR_ID,
) -> Any:
    await _write_package(session, anchor_id=anchor_id, seq=seq, tick=tick, snapshot=snapshot)
    return await materialize_anchor(store, anchor_id=anchor_id, hooks=_Recorder().hooks())


class TestForkKindParameterization:
    async def test_anchor_kind_requires_package(self, world: AsyncSession, store) -> None:
        """历史点读档**必须**带包（缺包 ⇒ `ForkError`，不静默走截断克隆）。

        判别力：没有包就退化成 head 语义 = 拿父分支的「未来」糊过去，正是本单要根治的病。
        """
        await _advance(store, [1, 2, 3])
        with pytest.raises(ForkError, match="必须带物化包"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=2,
                fork_tick=2,
                preflush=_noop_preflush,
                new_branch_id=CHILD,
                kind="anchor",
            )
        assert (
            await _row_count(world, "SELECT COUNT(*) FROM branches WHERE id = :c", {"c": CHILD})
            == 0
        )

    async def test_head_kind_rejects_package(self, world: AsyncSession, store) -> None:
        """`kind="head"` 给了包 ⇒ 拒绝（传了却被静默忽略 = 无声降级）。"""
        await _advance(store, [1])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        with pytest.raises(ForkError, match="不接受物化包"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=1,
                fork_tick=1,
                preflush=_noop_preflush,
                new_branch_id=HEAD_CHILD,
                kind="head",
                package=package,
            )

    async def test_package_cursor_must_match(self, world: AsyncSession, store) -> None:
        """包的游标必须与分叉参数**逐项**相符（拿 A 档的世界态分叉 B 点 = 串档）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        with pytest.raises(ForkError, match="游标与分叉参数不符"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=2,
                fork_tick=2,
                preflush=_noop_preflush,
                new_branch_id=CHILD,
                kind="anchor",
                package=package,
            )

    async def test_anchor_kind_allows_history_point(self, world: AsyncSession, store) -> None:
        """`kind="anchor"` 解锁 `fork_seq < head_seq`（历史点读档本就是为此而生）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        assert result.forked_from_seq == 1
        assert result.kind == "anchor"

    async def test_anchor_kind_still_rejects_overrun(self, world: AsyncSession, store) -> None:
        """分叉点越界（`fork_seq > head`）在 anchor 态**仍然拒**（包也救不了越界）。"""
        await _advance(store, [1, 2])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        with pytest.raises(ForkError, match="分叉点越界"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=9,
                fork_tick=9,
                preflush=_noop_preflush,
                new_branch_id=CHILD,
                kind="anchor",
                package=package,
            )

    async def test_anchor_kind_rejects_tick_after_head(self, world: AsyncSession, store) -> None:
        """`fork_tick > head_tick` 拒（锚点数据不自洽：分叉点不可能比父头部还晚）。"""
        await _advance(store, [1, 2])
        await store.write_snapshot(PARENT, tick=2, event_seq=2, blob=_snap_blob(2))
        package = await _anchor_package(store, world, seq=2, tick=2, snapshot=(2, 2))
        with pytest.raises(ForkError, match="tick"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=2,
                fork_tick=7,
                preflush=_noop_preflush,
                new_branch_id=CHILD,
                kind="anchor",
                package=package,
            )

    async def test_head_kind_behavior_unchanged(self, world: AsyncSession, store) -> None:
        """回归：`kind="head"`（默认）行为**逐字不变**——父封存、语料截断克隆、权力态随克隆。"""
        await _advance(store, [1])
        world.add(_memory("e-late", content="分叉点之后写的", event_seq=9))
        await world.commit()
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=HEAD_CHILD,
        )
        assert result.kind == "head"
        status = (
            await world.execute(sa_text("SELECT status FROM branches WHERE id = :p"), {"p": PARENT})
        ).scalar_one()
        assert str(status) == "abandoned", "head 态必须封存父分支（现行行为不得变）"
        assert (
            await _row_count(
                world, "SELECT COUNT(*) FROM npc_memories WHERE branch_id = :c", {"c": HEAD_CHILD}
            )
            == 1
        )
        assert (
            await _row_count(
                world, "SELECT COUNT(*) FROM npc_power WHERE branch_id = :c", {"c": HEAD_CHILD}
            )
            == 1
        )

    async def test_anchor_kind_parent_not_sealed(self, world: AsyncSession, store) -> None:
        """历史点读档**不封存父分支**（回退旧档不得封存玩家正在跑的世界线）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        status = (
            await world.execute(sa_text("SELECT status FROM branches WHERE id = :p"), {"p": PARENT})
        ).scalar_one()
        assert str(status) == "active"

    async def test_anchor_kind_parent_still_appendable(self, world: AsyncSession, store) -> None:
        """分叉后父分支**照写不误**（分叉不回溯污染：父分支的时间线继续走）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        await _advance(store, [4])
        assert (
            await _row_count(
                world,
                "SELECT COUNT(*) FROM events WHERE branch_id = :p AND tick = 4",
                {"p": PARENT},
            )
            == 1
        )

    async def test_anchor_kind_rng_comes_from_package(self, world: AsyncSession, store) -> None:
        """子分支的 RNG 状态取**包**（分支列是当前值、每次 fork 覆写 ⇒ 读时取会重掷混沌）。"""
        await _advance(store, [1, 2])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        assert result.rng_state == RNG_BLOB
        assert result.rng_state_persisted is True
        stored = (
            await world.execute(
                sa_text("SELECT rng_state FROM branches WHERE id = :c"), {"c": CHILD}
            )
        ).scalar_one()
        assert str(stored) == RNG_BLOB

    async def test_anchor_kind_rejects_conflicting_rng(self, world: AsyncSession, store) -> None:
        """显式传入的 rng 与包内不一致 ⇒ 拒（锚点时刻的状态只有一个真源）。"""
        await _advance(store, [1, 2])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        with pytest.raises(ForkError, match="rng_state 与包内"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=1,
                fork_tick=1,
                preflush=_noop_preflush,
                new_branch_id=CHILD,
                kind="anchor",
                package=package,
                rng_state='{"materials":{"default":"别的"}}',
            )

    async def test_anchor_kind_passes_agent_override(self, world: AsyncSession, store) -> None:
        """`agent_override` **透传**（包是权威，读档不 JOIN 档面）。"""
        await _advance(store, [1, 2])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        assert json.loads(result.agent_override) == {"npc": "chenmo"}


class TestForkCorpusFromPackage:
    async def test_memories_come_from_package(self, world: AsyncSession, store) -> None:
        """语料行值以**包**为权威：锚点之后在父分支写的记忆**不进子线**。

        判别力：若实现仍从父分支表截断克隆，这条会看到 `e-late`（父分支当前值）。
        """
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        world.add(_memory("e-late", content="锚点之后写的"))
        await world.execute(
            sa_text("UPDATE relationships SET trust = 0.99 WHERE branch_id = :p"), {"p": PARENT}
        )
        await world.commit()
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        entries = await _child_rows(world, "npc_memories", "entry_id, content", "entry_id")
        assert entries == [(result.entry_id_map["e-1"], "内容")]

    async def test_relationships_come_from_package(self, world: AsyncSession, store) -> None:
        """`relationships` 取包内累计值（父分支的「未来」不许渗进历史点子线）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        await world.execute(
            sa_text("UPDATE relationships SET trust = 0.99 WHERE branch_id = :p"), {"p": PARENT}
        )
        await world.commit()
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        rows = await _child_rows(world, "relationships", "owner_id, other_id, trust", "owner_id")
        assert rows == [("chenmo", "xiaoman", 0.5)]

    async def test_knowledge_comes_from_package(self, world: AsyncSession, store) -> None:
        """`knowledge` 取包内行值（锚点后学的不进子线）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        world.add(_knowledge("锚点之后才知道的事"))
        await world.commit()
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        facts = await _child_rows(world, "knowledge", "fact", "fact")
        assert facts == [("他知道井在哪",)]

    async def test_entry_id_remap_is_deterministic(self, world: AsyncSession, store) -> None:
        """包路径下 ``entry_id`` 仍**确定性**重映射（同一父行 + 同一子分支 ⇒ 同一 entry）。"""
        from sim.core.persistence.fork import derive_child_entry_id

        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        assert result.entry_id_map == {"e-1": derive_child_entry_id("e-1", CHILD)}

    async def test_superseded_pointer_remapped(self, world: AsyncSession, store) -> None:
        """R-2：包路径下 ``superseded_by`` 仍重映射到子行（治理完整性不因切包放松）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        world.add(_memory("e-2", superseded_by="e-1"))
        await world.commit()
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        rows = await _child_rows(world, "npc_memories", "entry_id, superseded_by", "entry_id")
        mapping = dict(rows)
        # 子行的 entry_id 是重映射后的 uuid5 ⇒ 用映射表反查（父 entry 不该出现在子行）
        assert set(mapping) == set(result.entry_id_map.values())
        assert mapping[result.entry_id_map["e-2"]] == result.entry_id_map["e-1"]
        assert result.superseded_rewritten == 1

    async def test_dangling_superseded_is_cleared_not_kept(
        self, world: AsyncSession, store
    ) -> None:
        """包内 ``superseded_by`` 指向的替换者不在包内 ⇒ 子行落 NULL（不留悬空指针）。

        构造法：手搓 blob（把治理指针改成不存在的 entry），**不改父表**——这样钉的才是
        「包内自相矛盾」这条真实读档路径。
        """
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        rows = await collect_corpus_rows(world, PARENT)
        rows["npc_memories"][0]["superseded_by"] = "e-ghost"
        await _write_package(
            world, seq=1, tick=1, snapshot=(1, 1), corpus_blob=encode_corpus_blob(rows)
        )
        package = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        rows = await _child_rows(world, "npc_memories", "entry_id, superseded_by", "entry_id")
        assert set(dict(rows)) == set(result.entry_id_map.values())
        assert set(dict(rows).values()) == {None}
        assert result.superseded_cleared == 1

    async def test_knowledge_source_memory_pointer_remapped(
        self, world: AsyncSession, store
    ) -> None:
        """包路径下 ``knowledge.source_memory`` 仍重映射到子 entry（悬空即整批拒绝）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        world.add(_knowledge("听人说的", source_memory="e-1"))
        await world.commit()
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        rows = await _child_rows(world, "knowledge", "fact, source_memory", "fact")
        assert dict(rows)["听人说的"] == result.entry_id_map["e-1"]

    async def test_dangling_source_memory_rejects_fork(self, world: AsyncSession, store) -> None:
        """包内 ``source_memory`` 悬空 ⇒ **整批拒绝**（宁可不读档，不留治理断链）。"""
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        rows = await collect_corpus_rows(world, PARENT)
        rows["knowledge"][0]["source_memory"] = "e-ghost"  # 悬空指针（人肉构造）
        await _write_package(
            world, seq=1, tick=1, snapshot=(1, 1), corpus_blob=encode_corpus_blob(rows)
        )
        package = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        with pytest.raises(ForkError, match="悬空"):
            await fork_from_anchor(
                store.session_factory,
                parent_branch_id=PARENT,
                fork_seq=1,
                fork_tick=1,
                preflush=_noop_preflush,
                new_branch_id=CHILD,
                kind="anchor",
                package=package,
            )
        assert (
            await _row_count(world, "SELECT COUNT(*) FROM branches WHERE id = :c", {"c": CHILD})
            == 0
        )


class TestForkFireRowsFromMaterialization:
    async def test_fire_rows_equal_replay_result(self, world: AsyncSession, store) -> None:
        """`fork(kind="anchor")` 写的火场行 = 物化重放结果（逐位）。

        判别力：若仍从父分支当前行克隆，锚点之后熄灭的火会带着「已熄灭」进子线。
        """
        await _advance(store, [1, 2, 3])
        fires = FireStore(store, branch_id=PARENT)
        await fires.upsert_fire(fire_id="f-1", x=3, y=4, tick=1)
        anchor_seq, anchor_tick = await _head_and_tick(world)
        await store.write_snapshot(
            PARENT, tick=anchor_tick, event_seq=anchor_seq, blob=_snap_blob(anchor_tick)
        )
        package = await _anchor_package(
            store, world, seq=anchor_seq, tick=anchor_tick, snapshot=(anchor_seq, anchor_tick)
        )
        await fires.set_fire_end(fire_id="f-1", tick=3, end="out")
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=anchor_seq,
            fork_tick=anchor_tick,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        rows = await _child_rows(world, "fires", "fire_id, ended_tick, `end`", "fire_id")
        assert rows == [("f-1", None, "")]

    async def test_fire_started_after_anchor_absent_in_child(
        self, world: AsyncSession, store
    ) -> None:
        """锚点之后才起的火**不进子线**（父分支的「未来」不许渗进历史点子线）。"""
        await _advance(store, [1, 2, 3])
        fires = FireStore(store, branch_id=PARENT)
        await fires.upsert_fire(fire_id="f-old", x=1, y=1, tick=1)
        anchor_seq, anchor_tick = await _head_and_tick(world)
        await store.write_snapshot(
            PARENT, tick=anchor_tick, event_seq=anchor_seq, blob=_snap_blob(anchor_tick)
        )
        package = await _anchor_package(
            store, world, seq=anchor_seq, tick=anchor_tick, snapshot=(anchor_seq, anchor_tick)
        )
        await fires.upsert_fire(fire_id="f-new", x=8, y=8, tick=3)
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=anchor_seq,
            fork_tick=anchor_tick,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        rows = await _child_rows(world, "fires", "fire_id", "fire_id")
        assert rows == [("f-old",)]

    async def test_child_fire_rows_are_bit_equal_to_parent_snapshot_rows(
        self, world: AsyncSession, store
    ) -> None:
        """端到端逐位：子分支火场行 == 锚点时刻的投影行（快照 ↔ 重放同源的端到端证据）。"""
        await _advance(store, [1, 2, 3])
        fires = FireStore(store, branch_id=PARENT)
        await fires.upsert_fire(fire_id="f-1", x=11, y=12, tick=1)
        await fires.set_fire_end(fire_id="f-1", tick=2, end="doused")
        head_seq, head_tick = await _head_and_tick(world)
        await store.write_snapshot(
            PARENT, tick=head_tick, event_seq=head_seq, blob=_snap_blob(head_tick)
        )
        package = await _anchor_package(
            store, world, seq=head_seq, tick=head_tick, snapshot=(head_seq, head_tick)
        )
        assert package.fires["f-1"].ended_tick == 2
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=head_seq,
            fork_tick=head_tick,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        rows = await _child_rows(
            world, "fires", "fire_id, x, y, ignited_tick, ended_tick, `end`", "fire_id"
        )
        assert rows == [("f-1", 11, 12, 1, 2, "doused")]

    async def test_fire_table_row_count_matches(self, world: AsyncSession, store) -> None:
        """克隆计数如实反映写入行数（不谎报「克隆了 N 条」）。"""
        await _advance(store, [1, 2])
        fires = FireStore(store, branch_id=PARENT)
        await fires.upsert_fire(fire_id="f-1", x=1, y=1, tick=1)
        await fires.upsert_fire(fire_id="f-2", x=2, y=2, tick=1)
        head_seq, head_tick = await _head_and_tick(world)
        await store.write_snapshot(
            PARENT, tick=head_tick, event_seq=head_seq, blob=_snap_blob(head_tick)
        )
        package = await _anchor_package(
            store, world, seq=head_seq, tick=head_tick, snapshot=(head_seq, head_tick)
        )
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=head_seq,
            fork_tick=head_tick,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        assert result.cloned_rows["fires"] == 2

    async def test_head_kind_still_clones_fires_from_parent(
        self, world: AsyncSession, store
    ) -> None:
        """回归：head 态火场仍走有界表克隆（当前值即分叉点状态）。"""
        await _advance(store, [1])
        await FireStore(store, branch_id=PARENT).upsert_fire(fire_id="f-1", x=1, y=1, tick=1)
        head_seq, head_tick = await _head_and_tick(world)
        result = await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=head_seq,
            fork_tick=head_tick,
            preflush=_noop_preflush,
            new_branch_id=HEAD_CHILD,
        )
        assert result.cloned_rows["fires"] == 1


# ===========================================================================
# 8. S10 E 系 6 钉 + 白盒负钉
# ===========================================================================


class TestSecurityNailsESeries:
    def test_e1_offline_surface_never_writes_player_anchor(self) -> None:
        """**E-1（数据面半·白盒）**：离线推进面零玩家档写入。

        判别力：离线推进代码**存在才扫**（本单时点尚未落盘 ⇒ 记「对象未落」不假绿）；
        本单两个物化面（物化器 + 分叉）恒扫。
        """
        surfaces = [PACKAGE_PY, FORK_PY]
        roots = REPO_ROOT
        for pattern in DRILL_GLOBS:
            surfaces.extend(sorted(roots.glob(pattern)))
        assert len(surfaces) >= 2
        for path in surfaces:
            code = _code_only(path)
            assert "PlayerAnchor(" not in code, f"{path.name} 构造了玩家档行（E-1）"
            assert "insert(PlayerAnchor" not in code, f"{path.name} 插了玩家档行（E-1）"
            assert "update(PlayerAnchor" not in code, f"{path.name} 改了玩家档行（E-1）"

    async def test_e2_cursor_frozen_after_world_progress(self, world: AsyncSession, store) -> None:
        """**E-2（正向）**：世界推进后玩家档游标**逐字段不变**。"""
        world.add(PlayerAnchor(id=ANCHOR_ID, name="档", branch_id=PARENT, tick=2, seq=2))
        await world.commit()
        before = (
            await world.execute(
                select(
                    PlayerAnchor.branch_id,
                    PlayerAnchor.tick,
                    PlayerAnchor.seq,
                    PlayerAnchor.name,
                    PlayerAnchor.protected,
                )
            )
        ).one()
        await _advance(store, [3, 4, 5])
        await _write_package(world, seq=5, tick=5, snapshot=None)
        after = (
            await world.execute(
                select(
                    PlayerAnchor.branch_id,
                    PlayerAnchor.tick,
                    PlayerAnchor.seq,
                    PlayerAnchor.name,
                    PlayerAnchor.protected,
                )
            )
        ).one()
        assert tuple(before) == tuple(after)

    async def test_e3_events_not_dropped(self, world: AsyncSession, store) -> None:
        """**E-3**：推进 3 tick ⇒ `events` 恰好 +3（同事务同批，一条不丢）。"""
        await _advance(store, [1, 2, 3])
        assert (
            await _row_count(
                world, "SELECT COUNT(*) FROM events WHERE branch_id = :p", {"p": PARENT}
            )
            == 3
        )

    async def test_e4_package_carries_no_power_state(self, world: AsyncSession, store) -> None:
        """**E-4（负钉·白盒 + 行为）**：包编解码器零权力键字面量，且硬塞也进不来/读不出。"""
        code = _code_only(PACKAGE_PY)
        assert "npc_power" not in code
        assert "power_level" not in code
        await _advance(store, [1])
        await _write_package(world, seq=1, tick=1, snapshot=None)
        package = await materialize_anchor(store, anchor_id=ANCHOR_ID, hooks=_Recorder().hooks())
        assert set(package.corpus) == set(CORPUS_TABLES)

    async def test_e5_anchor_load_leaves_power_fallback_zero(
        self, world: AsyncSession, store
    ) -> None:
        """**E-5**：历史点读档后权力表按「未表态兜底 0」处理，**且不报错**。

        判别力：子分支该表**零行**（不是父分支当前值 0.7），且读档全程无异常。
        """
        await _advance(store, [1, 2, 3])
        await store.write_snapshot(PARENT, tick=1, event_seq=1, blob=_snap_blob(1))
        package = await _anchor_package(store, world, seq=1, tick=1, snapshot=(1, 1))
        await fork_from_anchor(
            store.session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            preflush=_noop_preflush,
            new_branch_id=CHILD,
            kind="anchor",
            package=package,
        )
        assert (
            await _row_count(
                world, "SELECT COUNT(*) FROM npc_power WHERE branch_id = :c", {"c": CHILD}
            )
            == 0
        )
        assert (
            await _row_count(
                world, "SELECT COUNT(*) FROM npc_power WHERE branch_id = :p", {"p": PARENT}
            )
            == 1
        )

    async def test_e13_no_fire_baseline_column_added(self, world: AsyncSession) -> None:
        """**E-13**：火势物化基准点**不加列**（快照 + 事件窗口重放已能逐位重建）。"""
        fire_columns = {c.name for c in Fire.__table__.columns}
        assert fire_columns == {
            "branch_id",
            "fire_id",
            "x",
            "y",
            "ignited_tick",
            "ended_tick",
            "end",
            "created_at",
        }

    def test_e13_no_new_migration_for_package(self) -> None:
        """E-13 侧注：包表已在 0011 落 ⇒ 本单**零新迁移**（空迁移是噪声）。"""
        versions = VERSIONS_DIR
        assert not (versions / "0015_*.py").exists(), "批次 E 不该新增迁移（表已在 0011）"
        assert (versions / "0011_anchor_packages.py").exists()

    async def test_machine_code_declared_here_only(self) -> None:
        """ProblemDetail 机器码**唯一真源在本层**，出站登记不在本单（协议零漂移）。"""
        from sim.core.persistence.anchor_package import ANCHOR_MATERIALIZATION_MACHINE_CODE

        assert ANCHOR_MATERIALIZATION_MACHINE_CODE == "anchor-materialization-unavailable"
        assert "AnchorMaterializationError" not in _code_only(FORK_PY), (
            "fork.py 不该物化失败原因码（那是本层的契约，出站面才转 ProblemDetail）"
        )
