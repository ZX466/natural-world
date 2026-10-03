"""anchor 世界态物化包读写面 + 物化器 — `AnchorPackage`（M5-A10，批次 E 物化单）

设计稿 `docs/data/m5-anchor-materialization-preplan.md`（A3，预研稿即施工案）；
安规钉 `docs/security/m5-batch-e-security-preplan.md` **E-4/E-5/E-13**（codex S10）。

**为什么是「存档时一次物化」而不是读档时懒物化**（A3 §1.3）：快照会被淘汰
（留最近 8 份 + 每日首份）⇒ 懒物化会让老档随快照 GC **永久不可读档**。所以本模块的
写面在存档事务里固化一次，之后包自足、与快照生死解耦。

## 零迁移（与派单给的「0015 可用」不同，理由如下）

派单预留了 0015 号给「若需新列/新表」。实测：**表已经在了**——0011（M5-A4）已按 A3 §1.1
建好 ``anchor_packages``（含 `ck_anchor_packages_snapshot_pair`），模型与 create_all/
alembic 双路径一致性由 A4 的 8 钉钉死。本单**不需要任何新列/新表** ⇒ 不占号、不落空
迁移（空迁移是噪声，且会给未来 alembic 链塞一个无信息节点）。若将来确要加列（例如火势
物化基准点），随那一单加并配同款成对 CHECK（体例同 `0014 fires` 的 `ck_fires_end_pair`）。

## 包内清单（裁 34 已定：第 4 张「只有当前值」的表**不进包**）

| 成分 | 载体 | 备注 |
| --- | --- | --- |
| 锚点游标三元组 | `branch_id`/`tick`/`seq` | 与档面一致，读档校验用 |
| 快照指针 | `snapshot_seq`/`snapshot_tick` | **引用**（不复制 blob）；丢了退化为全前缀重放 |
| RNG 状态包 | `rng_state` | **本设计的核心**：anchor 时刻捕获（A3 §1.3） |
| agent 覆盖副本 | `agent_override` | 包自足，读档不 JOIN |
| 语料行值 | `corpus_blob` | **3 张**无事件源表的行值（gzip JSON） |
| 对账基线 | `state_hash` | 展开后 `WorldState.state_hash`（R-2 回归基线） |

**不进包的那一张**：批次 C 的权力态（无事件源 ⇒ 事件重放永远重建不出锚点时刻的值）。
S10 §2.3 裁决「不进包、读档后按未表态兜底 0」——理由是 D-10 下权力值**永不出站**，
进包等于给它造出第一个持久载体，而包（玩家档）将来极可能接诊断/出站面 ⇒ 攻击面由 0 变 1。
本模块用**构造性保证**落实它：:data:`CORPUS_TABLES` 是解码白名单，解码时未知表键**一律
丢弃** ⇒ 即使有人往 blob 里塞该表，读档路径也拿不到它（不靠"记得别写"，靠结构）。

## 应用次序 = 铁律（A3 §1.2，顺序不可换）

1. **展开**世界态（快照 payload + 事件窗口）；
2. **再套** ``agent_override``（快照里可能存着旧 override ⇒ 先套会被覆盖；它是玩家档的
   agent 身份覆盖，不参与 fold、不写事件，只在 resume 前生效一次）；
3. 再**灌** 3 张无事件源表的包内行值；
4. 最后 ``restore_rng_state(pkg.rng_state)``；
5. 然后才 resume 第一个 tick。

本模块**亲自按此序调用**四个钩子（:class:`MaterializationHooks`），并把实际执行序记进
:attr:`Materialization.steps` ⇒ 次序铁律本身可被钉子观测（而不是"约定"）。世界态展开与
override 的**语义实现**归 ws/决策层（钩子注入）——本模块只立序与 fail-closed 判据，
不越域重建 `WorldState`。

## fail-closed 五判据（**返回部分包 = 禁止**）

| 原因码 | 触发 | 依据 |
| --- | --- | --- |
| ``no_package`` | 该档没有包行（老档典型） | A3 §2「结构性不可救」 |
| ``rng_unavailable`` | ``rng_state`` 为 NULL/空串 | **禁止**用 `Branch.seed` 派生兜底
（seed 不含 PCG64 进度 ⇒ 抽签必然跳变，A2 已实测） |
| ``snapshot_missing`` | 无 ≤锚点 seq 的快照 **且** 全前缀事件不连续 | 重放起点不可得 ⇒
不得返回半展开世界 |
| ``event_gap`` | 有快照，但窗口 ``(snapshot_seq, anchor.seq]`` 内有洞 | 窗口折叠会跳过事件 ⇒
逐位性破 |

五判据都在**任何钩子被调用之前**判定 ⇒ 失败时零副作用（不套 override、不灌语料、不碰 RNG）。
语料那一条**不设**失配判据（包是权威 ⇒ 无「失配」可判；死码不用，A9 判例）。

## 火场（批次 D 增量）：**不为火扩格式**

火场生命周期表有事件源（``fire.ignited``/``fire.extinguished``）⇒ 属**可重放族** ⇒
物化时经 :meth:`sim.core.persistence.fire_store.FireStore.materialize_fires_replay` 从
「快照 + 事件窗口」重建，**不占包内任何一格**（S10 §2.5 采信 A9 偏差，A8「火场中间态
不入库」仍然成立）。E-13 因此判「不加火势基准列」：A9 的照妖镜已钉「快照 ↔ 重放逐位
相等」，再加列就是重复表达 = 未来谎言。

⚠️ **历史点读档不还原火场**：物化只产出**表行值**（火势中间态是纯运行态，每 tick 现抽），
机制面读档后**没有火对象**，只有"某坐标曾起火/已熄灭"的生命周期事实。
"""

from __future__ import annotations

import base64
import gzip
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from sim.core.persistence.fire_store import FireRow, FireStore
from sim.core.persistence.store import SnapshotData, SqlEventStore, decompress_snapshot

#: 包内语料白名单：3 张**无事件源**表的行值（批次 C 的权力态按 S10 §2.3 裁决**不在此列**）。
#: 这是**构造性**边界——解码只认这张表，任何别的表键（含被硬塞进来的）一律丢弃。
CORPUS_TABLES: tuple[str, ...] = ("npc_memories", "knowledge", "relationships")

#: 每张语料表的确定性行序（无 `id` 的表按复合主键排）⇒ 同一世界态编出**同一份** blob。
_CORPUS_ORDER_BY: Mapping[str, str] = {
    "npc_memories": "id",
    "knowledge": "id",
    "relationships": "owner_id, other_id",
}

#: 包 upsert SQL（**async/sync 两个写面共用一份**；幂等覆盖见函数 doc）。
_PACKAGE_UPSERT_SQL = (
    "INSERT INTO anchor_packages"
    " (anchor_id, branch_id, tick, seq, snapshot_seq, snapshot_tick, rng_state,"
    "  agent_override, corpus_blob, state_hash, schema_version, created_at)"
    " VALUES (:aid, :bid, :tick, :seq, :sseq, :stick, :rng, :override, :blob, :hash, 1, :now)"
    " ON CONFLICT(anchor_id) DO UPDATE SET"
    "  branch_id = excluded.branch_id, tick = excluded.tick, seq = excluded.seq,"
    "  snapshot_seq = excluded.snapshot_seq, snapshot_tick = excluded.snapshot_tick,"
    "  rng_state = excluded.rng_state, agent_override = excluded.agent_override,"
    "  corpus_blob = excluded.corpus_blob, state_hash = excluded.state_hash"
)

#: blob 内层结构版本（外层还有 ``schema_version`` 列，A3 §1.1）。
_BLOB_SCHEMA_VERSION = 1

#: 二进制列（如记忆向量）在 JSON 里的带标签载体（无标签的裸串会被误当普通值）。
_BYTES_TAG = "__bytes_b64__"

#: 物化失败原因码（固定集，出站面只允许回这些码）。
MATERIALIZATION_REASONS: tuple[str, ...] = (
    "no_package",
    "rng_unavailable",
    "snapshot_missing",
    "event_gap",
    "corpus_mismatch",
)

#: 物化不可用的 ProblemDetail 机器码（**唯一真源**在本层）。
#: ⚠️ 出站登记在 ``sim/api/`` 侧（kilo 域）：本单只提供码，不动错误表/协议快照
#: （红线：``shared/protocol.ts`` 零 diff，gen-protocol 必须 EXIT 0）。
ANCHOR_MATERIALIZATION_MACHINE_CODE = "anchor-materialization-unavailable"


@dataclass(frozen=True)
class MaterializationPackage:
    """包行的只读投影（frozen；不把 ORM 实例带出 session 作用域）。"""

    anchor_id: str
    branch_id: str
    tick: int
    seq: int
    snapshot_seq: int | None
    snapshot_tick: int | None
    rng_state: str | None
    agent_override: str
    corpus_blob: bytes | None
    state_hash: str | None


class AnchorMaterializationError(RuntimeError):
    """锚点不可物化——fail-closed（**不是** ``ForkError``、不是静默降级）。

    :attr:`reason` 取 :data:`MATERIALIZATION_REASONS` 之一；出站面按它给玩家「该档不可
    回退」，而不是让人撞 500。
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        if reason not in MATERIALIZATION_REASONS:
            raise ValueError(f"未知物化原因码: {reason!r}（固定集 {MATERIALIZATION_REASONS}）")
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail

    @property
    def machine_code(self) -> str:
        """ProblemDetail 机器码（出站面登记用；本层是唯一真源）。"""
        return ANCHOR_MATERIALIZATION_MACHINE_CODE


# ---------------------------------------------------------------------------
# 语料 blob 编解码（gzip JSON；含向量等二进制列）
# ---------------------------------------------------------------------------


def _encode_value(value: Any) -> Any:
    if isinstance(value, bytes | bytearray | memoryview):
        return {_BYTES_TAG: base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, Mapping):
        return {str(k): _encode_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_encode_value(v) for v in value]
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if set(value) == {_BYTES_TAG}:
            return base64.b64decode(str(value[_BYTES_TAG]))
        return {str(k): _decode_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_value(v) for v in value]
    return value


def encode_corpus_blob(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> bytes:
    """把语料行值编成 blob（gzip JSON，**确定性**：同输入 ⇒ 同字节）。

    - **白名单过滤**：不在 :data:`CORPUS_TABLES` 的表键**不写入**（调用方传了也不会进包），
      正面落实 S10 §2.3 的包内容边界；
    - ``mtime=0`` + ``sort_keys`` ⇒ blob 字节可比（R-2 对账/回归需要）；
    - 二进制列走 ``{__bytes_b64__: ...}`` 带标签载体，解码还原为 ``bytes``。
    """
    body = {
        "schema_version": _BLOB_SCHEMA_VERSION,
        "tables": {
            table: _encode_value([dict(row) for row in tables.get(table, ())])
            for table in CORPUS_TABLES
        },
    }
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return gzip.compress(raw, mtime=0)


def decode_corpus_blob(blob: bytes | None) -> dict[str, list[dict[str, Any]]]:
    """解 blob → ``{表名: [行 dict, ...]}``；**未知表键一律丢弃**（构造性包边界）。

    - ``blob is None`` ⇒ 空语料（老档没包内语料时的合法态，由 ``no_package`` 那侧兜）；
    - blob 结构不认识 ⇒ **fail-closed 抛** :class:`AnchorMaterializationError`（损坏的包
      不能被当成"空语料"糊过去，否则读档会静默少灌三张表）。
    """
    if blob is None:
        return {}
    try:
        body = json.loads(gzip.decompress(blob))
        raw_tables = body["tables"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AnchorMaterializationError("corpus_mismatch", f"corpus_blob 不可解: {exc!r}") from exc
    if not isinstance(raw_tables, Mapping):
        raise AnchorMaterializationError("corpus_mismatch", "corpus_blob.tables 不是对象")
    out: dict[str, list[dict[str, Any]]] = {}
    for table in CORPUS_TABLES:
        rows = raw_tables.get(table, [])
        if not isinstance(rows, list):
            raise AnchorMaterializationError(
                "corpus_mismatch", f"corpus_blob[{table!r}] 不是行数组"
            )
        out[table] = [dict(_decode_value(row)) for row in rows]
    return out


def _corpus_select(table: str) -> str:
    """语料采集 SQL（**编解码两侧共用**的单真源；表名/排序列来自白名单常量）。"""
    return f"SELECT * FROM {table} WHERE branch_id = :bid ORDER BY {_CORPUS_ORDER_BY[table]}"


async def collect_corpus_rows(
    session: AsyncSession, branch_id: str
) -> dict[str, list[dict[str, Any]]]:
    """采一份分支当前的语料行值（存档时物化的**唯一**采集面，async 面）。

    用 ``SELECT *`` + 表主键排序：不维护列清单 ⇒ 既有克隆清单（``fork.py``）与包格式
    各改一处就会漂移；行序确定 ⇒ blob 字节可比。
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for table in CORPUS_TABLES:
        rows = (await session.execute(text(_corpus_select(table)), {"bid": branch_id})).mappings()
        out[table] = [dict(row) for row in rows]
    return out


def collect_corpus_rows_sync(session: Session, branch_id: str) -> dict[str, list[dict[str, Any]]]:
    """同步面（``sim/api/anchors.py`` 的 ``create_item`` 同事务写包走这条）。

    与 :func:`collect_corpus_rows` **同一份 SQL**（:func:`_corpus_select`）⇒ 两个面不会
    漂移；跨面一致性由钉子（`test_m5_materialization_api.py`）钉住。
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for table in CORPUS_TABLES:
        rows = session.execute(text(_corpus_select(table)), {"bid": branch_id}).mappings()
        out[table] = [dict(row) for row in rows]
    return out


# ---------------------------------------------------------------------------
# 包写面（存档事务内一次物化；不进 tick 热路径）
# ---------------------------------------------------------------------------


async def load_package(session: AsyncSession, anchor_id: str) -> MaterializationPackage | None:
    """取包行（``None`` ⇒ 该档不可物化，判据码 ``no_package``）。"""
    row = (
        (
            await session.execute(
                text("SELECT * FROM anchor_packages WHERE anchor_id = :aid"),
                {"aid": anchor_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return MaterializationPackage(
        anchor_id=str(row["anchor_id"]),
        branch_id=str(row["branch_id"]),
        tick=int(row["tick"]),
        seq=int(row["seq"]),
        snapshot_seq=None if row["snapshot_seq"] is None else int(row["snapshot_seq"]),
        snapshot_tick=None if row["snapshot_tick"] is None else int(row["snapshot_tick"]),
        rng_state=None if row["rng_state"] is None else str(row["rng_state"]),
        agent_override=str(row["agent_override"]),
        corpus_blob=None if row["corpus_blob"] is None else bytes(row["corpus_blob"]),
        state_hash=None if row["state_hash"] is None else str(row["state_hash"]),
    )


async def write_anchor_package(
    session: AsyncSession,
    *,
    anchor_id: str,
    branch_id: str,
    tick: int,
    seq: int,
    rng_state: str | None,
    agent_override: str,
    corpus_blob: bytes | None,
    state_hash: str | None = None,
    snapshot: SnapshotData | None = None,
) -> None:
    """在**存档事务里**固化包行（一次；A3 §4.1「不进 tick 热路径」）。

    - 快照指针**引用** ``snapshots`` 行（``snapshot_seq``/``snapshot_tick``），零 blob 复制；
      快照被 GC 时读档退化为全前缀重放（语料/rng 仍在包内）。两列**同有同无**，半对值由
      0011 的 ``ck_anchor_packages_snapshot_pair`` 挡（fail-closed）。
    - ``rng_state`` 传 ``None`` 是**合法**（该档就是不可物化），但**禁止**改传 seed 派生值
      ——那会让回退旧档**重掷混沌**（A2 已实测）。
    - ``agent_override`` 原样落库（包自足，读档不 JOIN 档面）。
    - 幂等：同一 ``anchor_id`` 重复存档 ⇒ 覆盖为最新（``ON CONFLICT``），不留半包。
    """
    await session.execute(
        text(_PACKAGE_UPSERT_SQL),
        _package_upsert_params(
            anchor_id=anchor_id,
            branch_id=branch_id,
            tick=tick,
            seq=seq,
            rng_state=rng_state,
            agent_override=agent_override,
            corpus_blob=corpus_blob,
            state_hash=state_hash,
            snapshot=None if snapshot is None else (int(snapshot.seq), int(snapshot.tick)),
        ),
    )


def _package_upsert_params(
    *,
    anchor_id: str,
    branch_id: str,
    tick: int,
    seq: int,
    rng_state: str | None,
    agent_override: str,
    corpus_blob: bytes | None,
    state_hash: str | None,
    snapshot: tuple[int, int] | None,
) -> dict[str, Any]:
    """包 upsert 的绑定参数（**async/sync 两个写面的单真源**）。"""
    return {
        "aid": anchor_id,
        "bid": branch_id,
        "tick": tick,
        "seq": seq,
        "sseq": None if snapshot is None else snapshot[0],
        "stick": None if snapshot is None else snapshot[1],
        "rng": rng_state,
        "override": agent_override,
        "blob": corpus_blob,
        "hash": state_hash,
        "now": time.time(),
    }


def write_anchor_package_sync(
    session: Session,
    *,
    anchor_id: str,
    branch_id: str,
    tick: int,
    seq: int,
    rng_state: str | None,
    agent_override: str,
    corpus_blob: bytes | None,
    state_hash: str | None = None,
    snapshot: tuple[int, int] | None = None,
) -> None:
    """同步写面（存档 CRUD 的**同事务**位置：`sim/api/anchors.py::create_item`）。

    与 :func:`write_anchor_package` 共用 SQL 与参数构造 ⇒ 两面不可能写出不同的包。
    同步面存在的**唯一**理由：玩家档落库是同步事务（``threading.Lock`` + 同步 Session），
    包必须与「写档行 + 清其余 protected」**同事务**，跨引擎就跨事务了。
    """
    session.execute(
        text(_PACKAGE_UPSERT_SQL),
        _package_upsert_params(
            anchor_id=anchor_id,
            branch_id=branch_id,
            tick=tick,
            seq=seq,
            rng_state=rng_state,
            agent_override=agent_override,
            corpus_blob=corpus_blob,
            state_hash=state_hash,
            snapshot=snapshot,
        ),
    )


def latest_snapshot_ref_sync(
    session: Session, branch_id: str, upto_seq: int
) -> tuple[int, int] | None:
    """同步取「库内 ≤锚点 seq 的最新快照」引用 ``(seq, tick)``（无则 ``None``）。

    与 :meth:`SqlEventStore.latest_snapshot` 的 ``max_seq`` 判据同口径（A2 收紧：只按
    tick 选会挑到 seq 已越过锚点的快照 ⇒ 窗口倒挂）。**只取引用，不复制 blob**。
    跨面一致性由钉子钉住（同一库上与 async 面逐位相等）。
    """
    row = session.execute(
        text(
            "SELECT seq, tick FROM snapshots"
            " WHERE branch_id = :bid AND seq <= :useq"
            " ORDER BY seq DESC LIMIT 1"
        ),
        {"bid": branch_id, "useq": upto_seq},
    ).first()
    return None if row is None else (int(row[0]), int(row[1]))


# ---------------------------------------------------------------------------
# 物化器（次序铁律的执行者）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaterializationHooks:
    """读档编排的四个钩子（**语义归 ws/决策层，顺序归本层**）。

    全部要求 **awaitable**（读档在 async 路径上）；调用方用闭包包住同步实现即可。
    """

    #: 展开世界态：快照 payload（无快照时为 ``{}``）+ 窗口事件（``(snapshot_seq, seq]``）。
    expand_world: Callable[[Mapping[str, Any], Sequence[Mapping[str, Any]]], Awaitable[Any]]
    #: 套 agent 覆盖副本（必须**在展开之后**）。
    apply_override: Callable[[Any, Mapping[str, Any]], Awaitable[Any]]
    #: 灌语料行值（``{表名: 行 dict}``；写进子分支是调用方的活儿）。
    load_corpus: Callable[[Mapping[str, Sequence[Mapping[str, Any]]]], Awaitable[Any]]
    #: 恢复 RNG（必须**最后**）。
    restore_rng: Callable[[str], Awaitable[Any]]


@dataclass(frozen=True)
class Materialization:
    """物化产物（给编排层的事实清单）。"""

    anchor_id: str
    branch_id: str
    tick: int
    seq: int
    snapshot_seq: int | None
    snapshot_tick: int | None
    #: 重放起点（含）——退化路径下是 ``0``（全前缀重放）。
    replay_from_seq: int
    payload: Mapping[str, Any]
    window: tuple[Mapping[str, Any], ...]
    #: 锚点时刻的火场生命周期（可重放族，经 ``materialize_fires_replay`` 重建；非机制面火对象）。
    fires: Mapping[str, FireRow]
    #: 钩子展开出的世界态（类型归调用方；本层只透传）。
    world: Any
    #: 语料行值（3 张无事件源表；**按构造**不含权力态那张）。
    corpus: Mapping[str, list[dict[str, Any]]]
    rng_state: str
    agent_override: Mapping[str, Any]
    state_hash: str | None
    #: 实际执行序（次序铁律的观测面，钉子断言它）。
    steps: tuple[str, ...]


@dataclass(frozen=True)
class MaterializationDiagnosis:
    """只读诊断面（产品据此显示「该档不可回退」，而不是让人撞 500）。"""

    anchor_id: str
    ready: bool
    reason: str | None = None
    snapshot_seq: int | None = None
    steps: tuple[str, ...] = field(default=())


async def _count_range(
    session: AsyncSession, branch_id: str, lo: int, hi: int
) -> tuple[int, int, int]:
    row = (
        await session.execute(
            text(
                "SELECT COUNT(*), COALESCE(MIN(seq), 0), COALESCE(MAX(seq), 0) FROM events"
                " WHERE branch_id = :bid AND seq >= :lo AND seq <= :hi"
            ),
            {"bid": branch_id, "lo": lo, "hi": hi},
        )
    ).one()
    return int(row[0]), int(row[1]), int(row[2])


async def _resolve_replay_start(
    session: AsyncSession, branch_id: str, *, seq: int, snapshot: SnapshotData | None
) -> int:
    """判定重放起点；不可得 ⇒ 抛 fail-closed（判据见模块 docstring）。

    - 有快照 ⇒ 窗口 ``(snap.seq, seq]`` 必须**逐 seq 连续**（`COUNT == hi-lo` 且
      ``MIN == lo+1``），否则 ``event_gap``；返回 ``snap.seq``；
    - 无快照 ⇒ 退化为全前缀重放 ``[1, seq]``，必须 ``COUNT == MAX`` 且 ``MIN == 1``
      （无洞），否则 ``snapshot_missing``；返回 ``0``。
    """
    if snapshot is not None:
        lo = int(snapshot.seq)
        if seq <= lo:
            return lo
        count, min_seq, _max = await _count_range(session, branch_id, lo + 1, seq)
        if count != seq - lo or min_seq != lo + 1:
            raise AnchorMaterializationError(
                "event_gap",
                f"快照 seq={lo} 与锚点 seq={seq} 之间有洞（行数 {count} 应为 {seq - lo}）",
            )
        return lo
    if seq <= 0:
        return 0
    count, min_seq, max_seq = await _count_range(session, branch_id, 1, seq)
    if count != max_seq or min_seq != 1:
        raise AnchorMaterializationError(
            "snapshot_missing",
            f"无 ≤锚点的快照且全前缀不连续（COUNT={count} MIN={min_seq} MAX={max_seq}）",
        )
    return 0


async def _resolve_package(
    store: SqlEventStore, session: AsyncSession, anchor_id: str
) -> tuple[MaterializationPackage, SnapshotData | None, int]:
    """取包 + 快照指针 + 重放起点；三条 fail-closed 判据在此（**零副作用**）。"""
    package = await load_package(session, anchor_id)
    if package is None:
        raise AnchorMaterializationError("no_package", f"该档没有物化包: {anchor_id!r}")
    if not (package.rng_state or "").strip():
        raise AnchorMaterializationError(
            "rng_unavailable", f"包内 rng_state 不可得: {anchor_id!r}（禁止用 seed 派生兜底）"
        )
    snapshot = await store.latest_snapshot(
        package.branch_id, package.tick, max_seq=int(package.seq)
    )
    replay_from = await _resolve_replay_start(
        session, package.branch_id, seq=int(package.seq), snapshot=snapshot
    )
    return package, snapshot, replay_from


async def diagnose_anchor_materialization(
    store: SqlEventStore, anchor_id: str
) -> MaterializationDiagnosis:
    """只读诊断面：**不抛异常**、不写库（老档「不可回退」要能说出来）。"""
    async with store.session_factory() as session:
        try:
            _pkg, snapshot, _start = await _resolve_package(store, session, anchor_id)
        except AnchorMaterializationError as exc:
            return MaterializationDiagnosis(anchor_id=anchor_id, ready=False, reason=exc.reason)
        return MaterializationDiagnosis(
            anchor_id=anchor_id,
            ready=True,
            reason=None,
            snapshot_seq=None if snapshot is None else int(snapshot.seq),
            steps=(),
        )


async def materialize_anchor(
    store: SqlEventStore,
    *,
    anchor_id: str,
    hooks: MaterializationHooks,
) -> Materialization:
    """把一个档物化成「该锚点时刻的世界态」——**次序铁律的唯一执行点**。

    执行序（A3 §1.2，不可换）：``expand_world`` → ``apply_override`` → ``load_corpus``
    → ``restore_rng``。任何一步之前的判据失败 ⇒ **零钩子被调用**（不返回部分包）。

    - 快照选择**必须**带 ``max_seq=anchor.seq``（同 tick 多事件时，只按 tick 选会挑到
      seq 已越过锚点的快照 ⇒ 窗口倒挂、事件被跳过；A2 已钉该判据）。
    - 火场经 :meth:`FireStore.materialize_fires_replay` 重建（可重放族，**不进包**）；
      锚点 seq 之后的 ``fire.*`` 事件对本结果**零影响**（A8 §4 照妖镜判据）。
    - 语料按**包**为准（包是权威）：解 blob 得到的行值就是读档要灌的行值。
    """
    async with store.session_factory() as session:
        package, snapshot, replay_from = await _resolve_package(store, session, anchor_id)
        seq = int(package.seq)
        window = tuple(await store.read_range(package.branch_id, replay_from + 1, seq))
        payload: Mapping[str, Any] = {} if snapshot is None else decompress_snapshot(snapshot)
        fires = await FireStore(store, branch_id=package.branch_id).materialize_fires_replay(
            upto_seq=seq
        )
        override = _load_override(package.agent_override)

    steps: list[str] = []
    world = await hooks.expand_world(payload, window)
    steps.append("expand_world")
    world = await hooks.apply_override(world, override)
    steps.append("apply_override")
    corpus = decode_corpus_blob(package.corpus_blob)
    await hooks.load_corpus(corpus)
    steps.append("load_corpus")
    await hooks.restore_rng(str(package.rng_state))
    steps.append("restore_rng")

    return Materialization(
        anchor_id=anchor_id,
        branch_id=str(package.branch_id),
        tick=int(package.tick),
        seq=seq,
        snapshot_seq=None if snapshot is None else int(snapshot.seq),
        snapshot_tick=None if snapshot is None else int(snapshot.tick),
        replay_from_seq=replay_from,
        payload=payload,
        window=window,
        fires=fires,
        world=world,
        corpus=corpus,
        rng_state=str(package.rng_state),
        agent_override=override,
        state_hash=package.state_hash,
        steps=tuple(steps),
    )


def _load_override(raw: object) -> Mapping[str, Any]:
    """包内 ``agent_override``（TEXT JSON）→ 映射；空/坏值 ⇒ 空覆盖（**不改身份**）。"""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except ValueError:
        return {}
    return loaded if isinstance(loaded, Mapping) else {}
