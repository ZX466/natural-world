"""读档 = 分叉：事务与克隆（M5-D3-b，DESIGN §12；裁 6 (c) / 裁 10 (i) / R-1 / R-2）

读档流程（§12）：定位 anchor 的 `(branch_id, seq)` → **建新分支** → 旧分支标
`abandoned` → 世界继续。**不删除、不回退原世界线**（§19 禁止事项，C6）——本模块
只 INSERT 子分支行 + 改父分支 `status`；`events` / `entropy_log` / `snapshots` 一律不碰。

形态（`m5-fork-archive-preplan.md` §3.5，裁 6 (c) = async 引擎直写）：**一次事务**内

1. ``preflush()`` —— **P1 前置条件做成动作**：数据层看不到 driver 的 in-flight 批次，
   「投影追平到分叉点」只能由调用方以**必填**钩子声明并执行（漏传即不可分叉）；
2. 建子分支行（`forked_from_branch` / `forked_from_seq`）；
3. 六张有界表 ``INSERT … SELECT`` 换 ``branch_id`` 值（零 id 重映射）；
4. 两张语料表按分叉点**截断**克隆：自增 id **显式分配** + ``entry_id`` 重映射
   （裁 10 (i)）→ 治理指针（``superseded_by`` / ``source_knowledge_id`` /
   ``source_memory``）全部走临时映射表重写；
5. 证据引用改写：``evidence_branch_id`` 由 NULL（在本分支）→ 父分支（事件不克隆；
   0008-d 裁 4 封 C4 跨分支悬空）；
6. 父分支标 ``abandoned``（仅当仍 active；已弃分支可再分叉，不重复盖时间戳）。

**批次 C 权力态**（0013 / M5-A7）走有界表克隆（``npc_power`` 在 ``_BOUNDED_TABLES`` 内）：
子分支拿父分支**当前**权势值，逐字节。该表无事件源 ⇒ 它的值只能来自克隆/快照，
历史点读档（anchor 物化）拿不到——A3「不可重建」族第 4 张，由批次 E 物化单收口。

提交后（跨引擎，独立一步）：给了 ``vec_conn`` 就按**字节**重键拷贝 ``npc_memory_vec``
行（V4：vec 表为准 → **零 LLM 调用**；重新 embed 是红线禁）。

**分叉点只支持父分支头部**（fail-closed）：投影表的当前值 == 分叉点状态，**仅当父分支
在分叉点之后没有再推进**。历史点分叉（回昨天的存档）时 ``npc_memories`` /
``knowledge`` 的**治理列**与 ``relationships`` 的**累计值**已被父分支的「未来」改写，
而这三张表**没有事件源**（F2）⇒ 历史状态不可重建。修法需裁 7 的 ``*.written`` 事件或
anchor 世界态物化/快照展开（M5 均未落）——**不用「近似重置治理列」糊过去**。

**批次 E 物化单（M5-A10）：``kind`` 参数化 + 语料克隆源切包**（A3 §3.2）

``kind="head"``（现行，默认，行为**逐字不变**）= 读**当前档**：父分支已封存、语料按分叉点
截断克隆、权力态随有界表克隆。``kind="anchor"``（**历史点读档**）= 回退旧档：

- 分叉点**允许** ``fork_seq < head_seq``（历史点正是为此解锁的）；
- **必须**带 ``package``（物化器产物，缺包 ⇒ :class:`ForkError`，不静默近似）；
- 语料（``npc_memories`` / ``knowledge`` / ``relationships``）行值**以包为权威**，
  **无截断判据**（包是锚点时刻的全量行集）；id 仍显式分配 + ``entry_id`` 仍走确定性
  重映射 + R-2 指针重写照旧（治理完整性不因切包而放松）；
- 火场（``fires``，可重放族）行值取**包里的重放结果**，不是父分支当前行；
- 权力态**零克隆**（第 4 张无事件源表按 S10 §2.3 裁决**不进包** ⇒ 子分支该表零行 =
  「未表态兜底 0」，读档**不报错**）；
- 父分支**不封存**（保持 active，子线只是又一条并存线）——回退旧档不得封存玩家正在跑的
  世界线；当前行的移交归 R-4 施工单（0012 头注 + 双态钉已就位）。
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypedDict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sim.core.persistence.anchor_package import Materialization
from sim.core.persistence.vector import clone_branch_vectors

if TYPE_CHECKING:
    from sim.core.persistence.fire_store import FireRow

#: 分叉形态：``head`` = 读当前档（封存父、截断克隆）；``anchor`` = 历史点读档（父不封存、
#: 语料取包、权力态零克隆）。**禁止靠 ``fork_seq == head_seq`` 隐式区分**——那是本模块
#: 曾经（现在仍保留给 head 态）的 fail-closed 位置，不是形态判据。
ForkKind = Literal["head", "anchor"]

#: 权力态表名（批次 E：``kind="anchor"`` 时**跳过**克隆——S10 §2.3 裁决它不进包）。
_POWER_TABLE = "npc_power"

#: 重映射 `entry_id` 的命名空间（uuid5 派生 → 确定性，T2 逐位一致需要）。
ENTRY_ID_NAMESPACE: uuid.UUID = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

#: 六张有界表：换 `branch_id` 值即克隆（主键含 branch 或无内部指针）。
#: 列顺序无关紧要（显式列名），但**必须列全**——漏列即静默丢字段。
_BOUNDED_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "npc_profiles",
        (
            "id",
            "name",
            "species",
            "gender",
            "age",
            "occupation",
            "identity_anchor",
            "ocean_openness",
            "ocean_conscientiousness",
            "ocean_extraversion",
            "ocean_agreeableness",
            "ocean_neuroticism",
            "pad_pleasure",
            "pad_arousal",
            "pad_dominance",
            "emotion_updated_tick",
            "needs",
            "skills",
            "goals",
            "inventory",
            "knowledge_boundary",
            "lod",
            "created_at_tick",
            "updated_at_tick",
            "created_at",
        ),
    ),
    (
        "npc_health",
        (
            "npc_id",
            "category",
            "label",
            "severity",
            "active",
            "hidden",
            "descriptors",
            "trigger_conditions",
            "notes",
            "created_at_tick",
            "created_at",
        ),
    ),
    (
        "relationships",
        (
            "owner_id",
            "other_id",
            "trust",
            "affection",
            "fear",
            "debt",
            "face",
            "last_interaction",
            "created_at",
        ),
    ),
    (
        "matter_state",
        (
            "subject_id",
            "subject_kind",
            "material",
            "integrity",
            "quality",
            "decay_rate",
            "load_bearing",
            "supported_by",
            "is_rubble",
            "last_decay_tick",
            "updated_at_tick",
            "created_at",
        ),
    ),
    (
        "structures",
        (
            "structure_id",
            "tiles",
            "kind",
            "material",
            "phase",
            "load_bearing",
            "supported_by",
            "owner_id",
            "built_by",
            "built_at",
            "created_at",
        ),
    ),
    (
        "material_balances",
        ("ref", "material_id", "quantity", "updated_at_tick", "created_at"),
    ),
    (
        # 批次 C 权力态（0013 / M5-A7）：有界表，克隆 = 父分支当前值逐字节。
        # ⚠️ 本表**无事件源**（红线 A 不新增 kind）⇒ 子分支拿到的永远是父分支**当前**值，
        # 与「投影表当前值 == 分叉点状态」的前提同源（分叉点只支持父分支头部，fail-closed）。
        "npc_power",
        ("npc_id", "power_level", "updated_at_tick", "created_at"),
    ),
    (
        # 批次 D 火场生命周期（0014 / M5-A9）：有界表，克隆 = 父分支当前值逐字节。
        # 与 npc_power 不同：fires **有事件源**（fire.ignited/fire.extinguished）⇒ 它的
        # 当前值可被 fold 器逐位重建（物化靠「快照 + 事件窗口重放」，不需要快照指针列）。
        "fires",
        ("fire_id", "x", "y", "ignited_tick", "ended_tick", "end", "created_at"),
    ),
)

#: `npc_memories` 克隆列（`id` 显式分配、`branch_id`/`entry_id`/`superseded_by` 另处理）。
_MEMORY_COLUMNS: tuple[str, ...] = (
    "npc_id",
    "event_seq",
    "content",
    "source",
    "importance",
    "emotion_tag",
    "distortion",
    "embedding",
    "created_at_tick",
    "last_accessed_tick",
    "invalid_reason",
    "created_at",
)

#: `knowledge` 克隆列（`id` 显式分配；`branch_id`/指针/证据分支另处理）。
_KNOWLEDGE_COLUMNS: tuple[str, ...] = (
    "holder_id",
    "fact",
    "confidence",
    "source",
    "learned_at",
    "subject_npc_id",
    "subject_attr_id",
    "evidence_seq",
    "invalidated",
    "invalid_reason",
    "created_at",
)


class _MemoryClone(TypedDict):
    """`npc_memories` 克隆产出（内部）。"""

    cloned: int
    entry_id_map: dict[str, str]
    rowid_map: dict[int, int]
    superseded_rewritten: int
    superseded_cleared: int


class _KnowledgeClone(TypedDict):
    """`knowledge` 克隆产出（内部）。"""

    cloned: int
    id_map: dict[int, int]
    evidence_rewritten: int


class ForkError(RuntimeError):
    """分叉 fail-closed（分叉点非法 / 父分支不存在 / 指针悬空 / 完整性违规）。

    一律在事务内抛出 → 整批回滚，**不留半写**（无子分支行、无克隆行、父分支未封）。
    """


@dataclass(frozen=True)
class ForkResult:
    """分叉结果：给编排侧的事实清单（不含任何世界状态内容）。"""

    new_branch_id: str
    parent_branch_id: str
    forked_from_branch: str
    forked_from_seq: int
    forked_from_tick: int
    cloned_rows: Mapping[str, int] = field(default_factory=dict)
    #: 父 `entry_id` → 子 `entry_id`（裁 10 (i)，uuid5 确定性派生）。
    entry_id_map: Mapping[str, str] = field(default_factory=dict)
    #: 父 `knowledge.id` → 子 `knowledge.id`（自增 id 克隆后必变）。
    knowledge_id_map: Mapping[int, int] = field(default_factory=dict)
    #: 父 `npc_memories.id` → 子 `npc_memories.id`（= vec 重键用的 rowid 映射）。
    memory_rowid_map: Mapping[int, int] = field(default_factory=dict)
    #: `superseded_by` 重映射到子行的条数（R-2）。
    superseded_rewritten: int = 0
    #: `superseded_by` 因替换者在分叉点之后而置 NULL 的条数（R-2 的正常情形）。
    superseded_cleared: int = 0
    #: 证据引用改写到父分支的条数（0008-d 裁 4）。
    evidence_rewritten: int = 0
    vec_rows_copied: int = 0
    #: 未给 `vec_conn`（或 vec 行源缺失）→ 新分支召回降级为空，**不泄漏**，待补拷贝。
    vec_pending: bool = False
    #: RNG 状态包（`sim/core/rng_state.capture_rng_state` 的输出）——**原样落进子分支
    #: 行** `branches.rng_state`（0009，裁 27-B b2），与克隆同事务。
    rng_state: str | None = None
    #: 状态是否真落库了。`rng_state is None` ⇒ 该分支 `NULL`（未承接）+ warning，
    #: 此时为 ``False``（**不是**「已持久化」——避免把「没传」误读成「传了空的」）。
    rng_state_persisted: bool = False
    #: 分叉形态（``head`` / ``anchor``；批次 E 参数化，head 态语义不变）。
    kind: str = "head"
    #: 档的 agent 覆盖副本（批次 E：**包是权威**，原样透传给读档编排；head 态无包 ⇒ ``{}``）。
    agent_override: str = "{}"
    warnings: tuple[str, ...] = ()


def _as_int(value: object) -> int:
    """包内行的 id 列（JSON ⇒ ``object``）转 int；非法即 ``ValueError``（fail-closed）。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ForkError(f"包内行 id 必须是 int: {value!r}")
    return value


def derive_child_entry_id(parent_entry_id: str, child_branch_id: str) -> str:
    """裁 10 (i)：`entry_id` 重映射 = ``uuid5(命名空间, "子分支:父 entry_id")``。

    **确定性**而非随机 uuid4：T2 要求「同一 anchor 载入两次 → 逐位一致」，随机 id 会让
    两次分叉的 `entry_id` 不同，破坏可比字段集（预研稿 §6.4 把 `(branch_id, entry_id)`
    当作语料的业务键）。命名空间带子分支 id ⇒ 同一父行克隆到不同分支得不同 id。
    """
    return uuid.uuid5(ENTRY_ID_NAMESPACE, f"{child_branch_id}:{parent_entry_id}").hex


def _truncation_sql(alias: str, seq_col: str, tick_col: str) -> str:
    """语料截断判据（预研稿 §3.6）：**两道**都过才克隆。

    - ``seq_col``：NULL = 推理/转述，无事件锚点 → 只看 tick；
    - ``tick_col``：写库时的 tick，防「事件尚未 flush 就被 clone」的纵深防御。

    有界表**不截断**：父分支在分叉点即被封存，其投影值 == 分叉点状态（前提 P1）。
    """
    return (
        f"({alias}.{seq_col} IS NULL OR {alias}.{seq_col} <= :fseq)"
        f" AND {alias}.{tick_col} <= :ftick"
    )


async def _scalar_int(session: AsyncSession, sql: str, params: Mapping[str, object]) -> int:
    return int((await session.execute(text(sql), params)).scalar_one())


async def fork_from_anchor(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    parent_branch_id: str,
    fork_seq: int,
    fork_tick: int,
    preflush: Callable[[], Awaitable[None]],
    new_branch_id: str | None = None,
    vec_conn: sqlite3.Connection | None = None,
    rng_state: str | None = None,
    warn: Callable[[str], None] | None = None,
    kind: ForkKind = "head",
    package: Materialization | None = None,
) -> ForkResult:
    """从 ``(parent_branch_id, fork_seq, fork_tick)`` 分叉出新分支（§12 读档 = 分叉）。

    Args:
        session_factory: 异步 session 工厂（**直写**，裁 6 (c)：不过 store 类、
            不触 S1 —— 克隆是既有合规行的字节复制，不产生新内容）。
        parent_branch_id: 父分支（anchor 所在世界线；可已是 abandoned——再分叉合法）。
        fork_seq: 分叉点事件 seq（该分支内解释）；**必须等于父分支头部**。
        fork_tick: 分叉点 tick（语料截断判据之一）。
        preflush: **必填**钩子，fork 第一步执行（P1：冲掉父分支 in-flight 批次，使投影
            追平到分叉点）。数据层看不到 driver 的缓冲，故做成动作而非断言。
        new_branch_id: 新分支 id；缺省 ``uuid4().hex``。
        vec_conn: 已加载 sqlite-vec 的**同步**连接（同一 DB 文件）。给出则提交后按字节
            重键拷贝 vec 行；不给 → ``vec_pending=True``（召回降级，不泄漏）。
        rng_state: RNG 状态包（`sim.core.rng_state.capture_rng_state` 的输出）。
            **原样落进子分支行** `branches.rng_state`（0009，裁 27-B b2），与克隆
            **同事务** ⇒ 分支自带状态、可连续分叉。缺省 ``None`` ⇒ 该列留 NULL +
            发 warning（漏传 = 读档接缝跳变风险）。
        kind: 分叉形态（批次 E，M5-A10）。``"head"``（默认，**现行行为逐字不变**）：
            读当前档 ⇒ 必须 ``fork_seq == 父分支头部``、父分支封存、语料按分叉点截断克隆。
            ``"anchor"``：**历史点读档** ⇒ ``package`` 必填（缺则 :class:`ForkError`），
            语料行值取包、``fires`` 取包里的重放结果、权力态零克隆、父分支**不封存**。
        package: 物化器产物（``kind="anchor"`` 必填；``kind="head"`` 给了则**拒绝**
            ——「传了包却被静默忽略」等于无声降级）。游标三元组必须与分叉参数逐项相符。
        warn: 警告收集回调（缺省并入返回值 ``warnings``）。

    Returns:
        ``ForkResult``：克隆行数、id 映射、R-2 重写/清零计数、vec 状态。

    Raises:
        ForkError: 分叉点不在头部 / 越界 / tick 不自洽 / 父分支不存在 / 治理指针悬空
            （一律整批回滚，无半写）。
    """
    child_id = new_branch_id or uuid.uuid4().hex
    collected: list[str] = []

    def _warn(msg: str) -> None:
        collected.append(msg)
        if warn is not None:
            warn(msg)

    # ---- P1：投影追平（动作，不是断言）----
    await preflush()

    async with session_factory() as session, session.begin():
        parent_status = (
            await session.execute(
                text("SELECT status FROM branches WHERE id = :pid"),
                {"pid": parent_branch_id},
            )
        ).scalar_one_or_none()
        if parent_status is None:
            raise ForkError(f"父分支不存在: {parent_branch_id!r}")
        child_exists = (
            await session.execute(text("SELECT 1 FROM branches WHERE id = :cid"), {"cid": child_id})
        ).scalar_one_or_none()
        if child_exists is not None:
            raise ForkError(f"子分支已存在: {child_id!r}（分支 id 不可复用）")

        head_seq, head_tick = (
            await session.execute(
                text(
                    "SELECT COALESCE(MAX(seq), 0), COALESCE(MAX(tick), 0) FROM events"
                    " WHERE branch_id = :pid"
                ),
                {"pid": parent_branch_id},
            )
        ).one()
        if fork_seq > head_seq:
            raise ForkError(
                f"分叉点越界: seq={fork_seq} > 父分支头部 seq={head_seq}"
                f"（分支 {parent_branch_id!r}）"
            )
        if kind == "anchor":
            # 历史点读档：游标必须**逐项**对上物化包，否则「拿 A 档的世界态分叉 B 点」。
            if package is None:
                raise ForkError(
                    f"kind='anchor' 必须带物化包: 分叉点 seq={fork_seq}（分支 "
                    f"{parent_branch_id!r}）。历史点分叉的语料/关系没有事件源，包是"
                    "唯一权威——缺包就 fail-closed，不用近似重置治理列糊"
                )
            if (
                package.branch_id != parent_branch_id
                or int(package.seq) != fork_seq
                or int(package.tick) != fork_tick
            ):
                raise ForkError(
                    "物化包游标与分叉参数不符: "
                    f"包=({package.branch_id!r}, tick={package.tick}, seq={package.seq}) "
                    f"分叉=({parent_branch_id!r}, tick={fork_tick}, seq={fork_seq})"
                )
            if rng_state is not None and rng_state != package.rng_state:
                raise ForkError(
                    "rng_state 与包内 rng_state 不一致：锚点时刻的随机流状态以**包**为权威"
                    "（分支列是当前值、每次 fork 覆写，读时取会重掷混沌，A2 §3 修正 2）"
                )
        else:
            if package is not None:
                raise ForkError(
                    "kind='head' 不接受物化包：读当前档的语料走截断克隆；"
                    "传了包却被静默忽略 = 无声降级"
                )
            if fork_seq < head_seq:
                raise ForkError(
                    f"分叉点不在父分支头部: seq={fork_seq} < head={head_seq}"
                    f"（分支 {parent_branch_id!r}）。历史点分叉需要语料/关系的事件源"
                    "（裁 7 的 *.written）或 anchor 世界态物化路径（kind='anchor'）——"
                    "投影表当前值 ≠ 分叉点状态，故 fail-closed（不用近似重置治理列糊）"
                )
            if fork_tick < head_tick:
                raise ForkError(
                    f"分叉点 tick={fork_tick} < 分支头部 tick={head_tick}（锚点数据不自洽）"
                )
        if kind == "anchor" and fork_tick > head_tick:
            raise ForkError(
                f"分叉点 tick={fork_tick} > 分支头部 tick={head_tick}（锚点数据不自洽："
                "分叉点不可能比父分支头部还晚）"
            )

        # 锚点时刻的随机流状态以**包**为权威（A3 §1.3）：分支列是当前值、每次 fork 覆写。
        effective_rng = rng_state if kind == "head" or package is None else package.rng_state
        await session.execute(
            text(
                "INSERT INTO branches"
                " (id, forked_from_branch, forked_from_seq, status, rng_state, created_at)"
                " VALUES (:cid, :pid, :fseq, 'active', :rng, :now)"
            ),
            {
                "cid": child_id,
                "pid": parent_branch_id,
                "fseq": fork_seq,
                "rng": effective_rng,
                "now": time.time(),
            },
        )
        if effective_rng is None:
            _warn(
                f"未提供 rng_state：新分支 {child_id!r} 的随机流将从头开始"
                "（读档接缝跳变风险；预研稿 §6.3）。落库形态 = branches.rng_state"
                "（0009，裁 27-B b2），状态包由 sim/core/rng_state.py 生成。"
            )

        cloned: dict[str, int] = {}
        for table, columns in _BOUNDED_TABLES:
            if kind == "anchor" and table == _POWER_TABLE:
                # 批次 E 裁决：权力态**不进包** ⇒ 历史点读档不克隆（子分支该表零行 =
                # 「未表态兜底 0」，读档不报错）。克隆父分支当前值等于拿未来糊过去。
                continue
            if kind == "anchor" and table == "fires":
                # 火场是**可重放族**：取包里的重放结果，不是父分支当前行。
                assert package is not None
                cloned[table] = await _clone_fires_from_rows(
                    session, list(package.fires.values()), child_id
                )
                continue
            if kind == "anchor" and table == "relationships":
                continue  # 语料块按包写（累计值属锚点时刻，不是父分支当前值）
            cloned[table] = await _clone_bounded(
                session, table, columns, parent_branch_id, child_id
            )

        corpus = None if package is None else dict(package.corpus)
        mem = await _clone_memories(
            session,
            parent_branch_id=parent_branch_id,
            child_id=child_id,
            fork_seq=fork_seq,
            fork_tick=fork_tick,
            rows=None if corpus is None else list(corpus.get("npc_memories", ())),
        )
        cloned["npc_memories"] = int(mem["cloned"])
        know = await _clone_knowledge(
            session,
            parent_branch_id=parent_branch_id,
            child_id=child_id,
            fork_seq=fork_seq,
            fork_tick=fork_tick,
            rows=None if corpus is None else list(corpus.get("knowledge", ())),
        )
        cloned["knowledge"] = int(know["cloned"])
        if corpus is not None:
            # 语料第三张：包是权威（父分支的「未来」不该渗进历史点子线）。
            cloned["relationships"] = await _clone_relationships_from_rows(
                session, list(corpus.get("relationships", ())), child_id
            )

        # 父分支封存**只对 head 态**：回退旧档不得封存玩家正在跑的世界线（批次 E）。
        if parent_status == "active" and kind == "head":
            await session.execute(
                text(
                    "UPDATE branches SET status = 'abandoned', abandoned_at = :now"
                    " WHERE id = :pid AND status = 'active'"
                ),
                {"pid": parent_branch_id, "now": time.time()},
            )

        await session.execute(text("DROP TABLE IF EXISTS fork_mem"))
        await session.execute(text("DROP TABLE IF EXISTS fork_know"))

    rowid_map: dict[int, int] = mem["rowid_map"]
    vec_copied = 0
    vec_pending = False
    if vec_conn is not None:
        vec_copied = clone_branch_vectors(vec_conn, rowid_map)
        if vec_copied != len(rowid_map):
            vec_pending = True
            _warn(
                f"vec 行拷贝不齐: 期望 {len(rowid_map)} 实得 {vec_copied}"
                "（新分支向量召回可能不全；不泄漏，补拷贝即可）"
            )
    else:
        vec_pending = True
        _warn(
            f"未提供 vec_conn：{len(rowid_map)} 条子分支记忆的向量未重键拷贝，"
            "该分支向量召回降级为空（不泄漏）；用 clone_branch_vectors 补齐。"
        )

    return ForkResult(
        new_branch_id=child_id,
        parent_branch_id=parent_branch_id,
        forked_from_branch=parent_branch_id,
        forked_from_seq=fork_seq,
        forked_from_tick=fork_tick,
        cloned_rows=cloned,
        entry_id_map=mem["entry_id_map"],
        knowledge_id_map=know["id_map"],
        memory_rowid_map=rowid_map,
        superseded_rewritten=mem["superseded_rewritten"],
        superseded_cleared=mem["superseded_cleared"],
        evidence_rewritten=know["evidence_rewritten"],
        vec_rows_copied=vec_copied,
        vec_pending=vec_pending,
        rng_state=effective_rng,
        rng_state_persisted=effective_rng is not None,
        kind=kind,
        agent_override="{}" if package is None else json.dumps(package.agent_override),
        warnings=tuple(collected),
    )


async def _clone_fires_from_rows(
    session: AsyncSession, rows: Sequence[FireRow], child_id: str
) -> int:
    """火场生命周期：按**物化重放结果**写子分支行（可重放族 ⇒ 不从父分支当前行克隆）。

    判别力：父分支在锚点之后又起的新火**不得**进子线（那正是「投影表当前值 ≠ 分叉点
    状态」的病）。写的只是生命周期事实，火势中间态不入库（A8 §1.2）。
    """
    if not rows:
        return 0
    await session.execute(
        text(
            "INSERT INTO fires"
            " (branch_id, fire_id, x, y, ignited_tick, ended_tick, `end`, created_at)"
            " VALUES (:cid, :fid, :x, :y, :itick, :etick, :end, :now)"
        ),
        [
            {
                "cid": child_id,
                "fid": row.fire_id,
                "x": row.x,
                "y": row.y,
                "itick": row.ignited_tick,
                "etick": row.ended_tick,
                "end": row.end,
                "now": time.time(),
            }
            for row in rows
        ],
    )
    return await _scalar_int(
        session, "SELECT COUNT(*) FROM fires WHERE branch_id = :cid", {"cid": child_id}
    )


async def _clone_relationships_from_rows(
    session: AsyncSession, rows: Sequence[Mapping[str, object]], child_id: str
) -> int:
    """``relationships``：按**包内行值**写子分支（``branch_id`` 换成子分支，余列逐字节）。

    复合主键 ``(branch_id, owner_id, other_id)`` ⇒ 无 id 重映射；累计值（trust/affection/
    fear/debt/face）原样落包内值 ⇒ 不被父分支的「未来」改写（A3 §1.4 路径 A）。
    """
    if not rows:
        return 0
    columns = [name for name in rows[0] if name != "branch_id"]
    cols = ", ".join(columns)
    marks = ", ".join(f":{name}" for name in columns)
    await session.execute(
        text(f"INSERT INTO relationships (branch_id, {cols}) VALUES (:cid, {marks})"),
        [{name: row.get(name) for name in columns} | {"cid": child_id} for row in rows],
    )
    return await _scalar_int(
        session,
        "SELECT COUNT(*) FROM relationships WHERE branch_id = :cid",
        {"cid": child_id},
    )


async def _clone_bounded(
    session: AsyncSession,
    table: str,
    columns: Sequence[str],
    parent_branch_id: str,
    child_id: str,
) -> int:
    """有界表克隆：``INSERT … SELECT`` 把 ``branch_id`` 换成子分支（零 id 重映射）。"""
    cols = ", ".join(columns)
    selects = ", ".join(f"p.{c}" for c in columns)
    await session.execute(
        text(
            f"INSERT INTO {table} (branch_id, {cols})"
            f" SELECT :cid, {selects} FROM {table} p WHERE p.branch_id = :pid"
        ),
        {"cid": child_id, "pid": parent_branch_id},
    )
    return await _scalar_int(
        session,
        f"SELECT COUNT(*) FROM {table} WHERE branch_id = :cid",
        {"cid": child_id},
    )


async def _next_id(session: AsyncSession, table: str) -> int:
    return await _scalar_int(session, f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}", {})


async def _clone_memories(
    session: AsyncSession,
    *,
    parent_branch_id: str,
    child_id: str,
    fork_seq: int,
    fork_tick: int,
    rows: Sequence[Mapping[str, object]] | None = None,
) -> _MemoryClone:
    """`npc_memories` 克隆 + 显式分配 id + `entry_id` 重映射 + R-2 指针重映射。

    ``rows`` 给定（**包路径**，``kind="anchor"``）⇒ 行集来自物化包（锚点时刻的全量行值，
    **无截断判据**：包是权威）；给 ``None``（head 路径）⇒ 从父分支表按分叉点截断克隆。
    两条路的 id 分配 / entry_id 派生 / R-2 重写**同源**，切包不放松治理完整性。
    """
    if rows is None:
        where = _truncation_sql("p", "event_seq", "created_at_tick")
        params: dict[str, object] = {
            "pid": parent_branch_id,
            "fseq": fork_seq,
            "ftick": fork_tick,
        }
        parent_rows: Sequence[Sequence[object]] = (
            await session.execute(
                text(
                    f"SELECT id, entry_id, superseded_by FROM npc_memories p"
                    f" WHERE p.branch_id = :pid AND {where} ORDER BY p.id"
                ),
                params,
            )
        ).all()
        blob_rows: Sequence[Mapping[str, object]] = ()
    else:
        where = ""
        params = {"pid": parent_branch_id}
        parent_rows = [
            (_as_int(row.get("id")), str(row.get("entry_id")), row.get("superseded_by"))
            for row in rows
        ]
        blob_rows = rows

    entry_id_map = {
        str(eid): derive_child_entry_id(str(eid), child_id) for _rid, eid, _sb in parent_rows
    }
    base_id = await _next_id(session, "npc_memories")
    # 临时映射表：父 id → 子 id（vec 重键）+ 父 entry → 子 entry（治理指针重写）。
    await session.execute(
        text(
            "CREATE TEMP TABLE fork_mem"
            " (src_id INTEGER PRIMARY KEY, dst_id INTEGER NOT NULL,"
            "  src_entry TEXT NOT NULL, dst_entry TEXT NOT NULL)"
        )
    )
    if parent_rows:
        await session.execute(
            text(
                "INSERT INTO fork_mem (src_id, dst_id, src_entry, dst_entry)"
                " VALUES (:sid, :did, :sent, :dent)"
            ),
            [
                {
                    "sid": int(rid),
                    "did": base_id + i,
                    "sent": str(eid),
                    "dent": entry_id_map[str(eid)],
                }
                for i, (rid, eid, _sb) in enumerate(parent_rows)
            ],
        )

        cols = ", ".join(_MEMORY_COLUMNS)
        if blob_rows:
            # 包路径：逐行写（值取包内行，id/entry_id/branch_id 由本函数决定）。
            marks = ", ".join(f":{c}" for c in _MEMORY_COLUMNS)
            await session.execute(
                text(
                    "INSERT INTO npc_memories"
                    f" (id, branch_id, entry_id, superseded_by, {cols})"
                    f" VALUES (:did, :cid, :dent, :sb, {marks})"
                ),
                [
                    {
                        "did": base_id + i,
                        "cid": child_id,
                        "dent": entry_id_map[str(eid)],
                        "sb": _sb,
                        **{c: row.get(c) for c in _MEMORY_COLUMNS},
                    }
                    for i, (row, (_rid, eid, _sb)) in enumerate(
                        zip(blob_rows, parent_rows, strict=True)
                    )
                ],
            )
        else:
            selects = ", ".join(f"p.{c}" for c in _MEMORY_COLUMNS)
            await session.execute(
                text(
                    "INSERT INTO npc_memories"
                    f" (id, branch_id, entry_id, superseded_by, {cols})"
                    f" SELECT k.dst_id, :cid, k.dst_entry, p.superseded_by, {selects}"
                    " FROM npc_memories p JOIN fork_mem k ON k.src_id = p.id"
                    f" WHERE p.branch_id = :pid AND {where}"
                ),
                {**params, "cid": child_id},
            )

        # R-2：指针重映射到子行；替换者未随克隆进入子分支（含「写在分叉点之后」）
        # → 落 NULL（该分支时间线里它确实还没被取代），**绝不留下悬空指针**。
        before = await _scalar_int(
            session,
            "SELECT COUNT(*) FROM npc_memories"
            " WHERE branch_id = :cid AND superseded_by IS NOT NULL",
            {"cid": child_id},
        )
        await session.execute(
            text(
                "UPDATE npc_memories SET superseded_by = ("
                "  SELECT k.dst_entry FROM fork_mem k WHERE k.src_entry = superseded_by"
                ") WHERE branch_id = :cid AND superseded_by IS NOT NULL"
            ),
            {"cid": child_id},
        )
        after = await _scalar_int(
            session,
            "SELECT COUNT(*) FROM npc_memories"
            " WHERE branch_id = :cid AND superseded_by IS NOT NULL",
            {"cid": child_id},
        )
        expected = _targeted_count(parent_rows, entry_id_map)
        if after != expected:
            raise ForkError(
                f"superseded_by 重映射结果与预期不符: 实际 {after} 预期 {expected}（R-2）"
            )
    else:
        before = 0
        after = 0

    rowid_map = {int(rid): base_id + i for i, (rid, _e, _s) in enumerate(parent_rows)}
    return {
        "cloned": len(parent_rows),
        "entry_id_map": entry_id_map,
        "rowid_map": rowid_map,
        "superseded_rewritten": after,
        "superseded_cleared": before - after,
    }


def _targeted_count(
    parent_rows: Sequence[Sequence[object]], entry_id_map: Mapping[str, str]
) -> int:
    """有多少条 `superseded_by` 能重映射到子行（其余将被置 NULL）——SQL 侧结果的期望值。"""
    return sum(1 for _r, _e, sb in parent_rows if sb is not None and str(sb) in entry_id_map)


async def _clone_knowledge(
    session: AsyncSession,
    *,
    parent_branch_id: str,
    child_id: str,
    fork_seq: int,
    fork_tick: int,
    rows: Sequence[Mapping[str, object]] | None = None,
) -> _KnowledgeClone:
    """`knowledge` 克隆 + 显式分配 id + told 链/源记忆指针重写 + 证据分支改写。

    ``rows`` 给定（**包路径**，``kind="anchor"``）⇒ 行集来自物化包；``None``（head 路径）
    ⇒ 父分支表按分叉点截断克隆。指针悬空一律**整批拒绝**（两条路同款）。
    """
    if rows is None:
        where = _truncation_sql("p", "evidence_seq", "learned_at")
        params: dict[str, object] = {
            "pid": parent_branch_id,
            "fseq": fork_seq,
            "ftick": fork_tick,
        }
        parent_rows = (
            await session.execute(
                text(
                    f"SELECT id FROM knowledge p WHERE p.branch_id = :pid AND {where} ORDER BY p.id"
                ),
                params,
            )
        ).all()
        blob_rows: Sequence[Mapping[str, object]] = ()
    else:
        where = ""
        params = {"pid": parent_branch_id}
        parent_rows = [(_as_int(row.get("id")),) for row in rows]
        blob_rows = rows
    if not parent_rows:
        return {"cloned": 0, "id_map": {}, "evidence_rewritten": 0}

    base_id = await _next_id(session, "knowledge")
    await session.execute(
        text("CREATE TEMP TABLE fork_know (src_id INTEGER PRIMARY KEY, dst_id INTEGER NOT NULL)")
    )
    await session.execute(
        text("INSERT INTO fork_know (src_id, dst_id) VALUES (:sid, :did)"),
        [{"sid": int(row[0]), "did": base_id + i} for i, row in enumerate(parent_rows)],
    )

    cols = ", ".join(_KNOWLEDGE_COLUMNS)
    if blob_rows:
        marks = ", ".join(f":{c}" for c in _KNOWLEDGE_COLUMNS)
        await session.execute(
            text(
                "INSERT INTO knowledge"
                f" (id, branch_id, source_knowledge_id, source_memory, evidence_branch_id, {cols})"
                f" VALUES (:did, :cid, :skid, :smem, :ebid, {marks})"
            ),
            [
                {
                    "did": base_id + i,
                    "cid": child_id,
                    "skid": row.get("source_knowledge_id"),
                    "smem": row.get("source_memory"),
                    "ebid": (
                        parent_branch_id
                        if row.get("evidence_seq") is not None
                        and row.get("evidence_branch_id") is None
                        else row.get("evidence_branch_id")
                    ),
                    **{c: row.get(c) for c in _KNOWLEDGE_COLUMNS},
                }
                for i, row in enumerate(blob_rows)
            ],
        )
    else:
        selects = ", ".join(f"p.{c}" for c in _KNOWLEDGE_COLUMNS)
        await session.execute(
            text(
                "INSERT INTO knowledge"
                f" (id, branch_id, source_knowledge_id, source_memory, evidence_branch_id, {cols})"
                " SELECT k.dst_id, :cid, p.source_knowledge_id, p.source_memory,"
                "   CASE WHEN p.evidence_seq IS NOT NULL AND p.evidence_branch_id IS NULL"
                "        THEN :pid ELSE p.evidence_branch_id END,"
                f"  {selects}"
                " FROM knowledge p JOIN fork_know k ON k.src_id = p.id"
                f" WHERE p.branch_id = :pid AND {where}"
            ),
            {**params, "cid": child_id},
        )

    # told 链指针：teller 不在克隆集（被截断或本就是悬空）= 完整性违规 → 整批拒绝
    dangling = await _scalar_int(
        session,
        "SELECT COUNT(*) FROM knowledge c WHERE c.branch_id = :cid"
        " AND c.source_knowledge_id IS NOT NULL"
        " AND c.source_knowledge_id NOT IN (SELECT src_id FROM fork_know)",
        {"cid": child_id},
    )
    if dangling:
        raise ForkError(
            f"knowledge.source_knowledge_id 悬空 {dangling} 条（teller 不在克隆集内）"
            " → 拒绝分叉（宁可不分，也不留治理断链）"
        )
    await session.execute(
        text(
            "UPDATE knowledge SET source_knowledge_id = ("
            "  SELECT n2.id FROM knowledge n2"
            "  JOIN fork_know k ON k.src_id = knowledge.source_knowledge_id"
            "  WHERE n2.id = k.dst_id"
            ") WHERE branch_id = :cid AND source_knowledge_id IS NOT NULL"
        ),
        {"cid": child_id},
    )

    # 源记忆指针：同法（entry_id 映射在 fork_mem 里，事务末才 DROP）
    dangling_mem = await _scalar_int(
        session,
        "SELECT COUNT(*) FROM knowledge c WHERE c.branch_id = :cid"
        " AND c.source_memory IS NOT NULL"
        " AND c.source_memory NOT IN (SELECT src_entry FROM fork_mem)",
        {"cid": child_id},
    )
    if dangling_mem:
        raise ForkError(
            f"knowledge.source_memory 悬空 {dangling_mem} 条（源记忆不在克隆集内）→ 拒绝分叉"
        )
    await session.execute(
        text(
            "UPDATE knowledge SET source_memory = ("
            "  SELECT k.dst_entry FROM fork_mem k WHERE k.src_entry = source_memory"
            ") WHERE branch_id = :cid AND source_memory IS NOT NULL"
        ),
        {"cid": child_id},
    )

    evidence_rewritten = await _scalar_int(
        session,
        "SELECT COUNT(*) FROM knowledge WHERE branch_id = :cid"
        " AND evidence_branch_id = :pid AND evidence_seq IS NOT NULL",
        {"cid": child_id, "pid": parent_branch_id},
    )
    id_map = {int(row[0]): base_id + i for i, row in enumerate(parent_rows)}
    return {
        "cloned": len(parent_rows),
        "id_map": id_map,
        "evidence_rewritten": evidence_rewritten,
    }
