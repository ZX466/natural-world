"""玩家档（anchor）HTTP API — M5-K7 最小实现（anchors-api.md §4）+ M5-K3 D-9 当前指针。

**M5-CRUD（2026-09-30，裁 28-G Claude 域）**：读 + 写路径全量。
- GET 列表/current/单查（K7 最小实现，现读 `protected` **列**——S-4 切列完成，
  派生式退休，C1 单一真相源；`/current` 退化态回退 max(updated_at) 保底不 404，
  D-14）；每条落库项调 `register_anchor_id()` 注进 WS 分发块查表集。
- POST（§1.2）：仅 `name`（1..64）；同事务写新档 protected=true + 清其余
  （A2 进程锁 + A3 同事务，§6.1）；`updated_at` 只写一次；游标 = 世界当前
  tick + 当前活跃分支（D-16 默认 main）；无活跃 loop → 400 world-not-ready。
- PATCH（§1.3）：只改 name；不动 updated_at/protected；刷新 WS 标签。
- DELETE（§1.4）：409 判据**读列**；硬删；成功调 `unregister_anchor_id`
  （D-15/S-7 调用点）；不补位。
- F-6 注册侧 fail-closed（codex S2b §4.2）：name 过现行 `scan()`，命中 → 422
  `/errors/anchor-name-rejected`；不扩词表，只消费既有表。
- 404 走 ProblemDetail（`sim/api/errors.py` 全局换形，detail=机器码）。

**M5-A11（批次 E 收官件，2026-10-03）**：
- `create_item` **同事务写包**（A10 移交项）：玩家档一落库就把锚点时刻的世界态物化一次
  （快照指针 + 3 张无事件源表行值 + override + state_hash；RNG 见下）。**为什么必须同事务**：
  跨引擎就跨事务，档与包会分裂成「有档没包」的半态——而半包比没有包更坏（诊断说不可回退，
  玩家却以为能回退）。语料行值/快照引用用**同步面**（本模块是同步 Session），SQL 与
  `anchor_package.py` 的 async 面**同一份**（跨面一致性有钉）。
- **RNG 捕获是已知缺口**：`sim.core.rng_state.capture_rng_state` 需要 `RngRegistry` + 抽签
  cache + 流清单，而这三样**今天没有挂在 `app.state` 上**（app 只有 loop/store/tile_map）。
  ⇒ 存档拿不到 RNG 状态时 `rng_state=NULL`，该档在诊断面是 `rng_unavailable`
  （fail-closed，**禁止**用 `Branch.seed` 派生兜底）。待混沌流侧暴露 registry 后，
  `create_item(rng_state=...)` 一个参数即可接上，零改动数据面。
- `GET /api/anchors/{anchor_id}/materialization` 只读诊断路由（返回 `ready` + 原因码）：
  让产品显示「该档不可回退」而不是让人撞 500。**不可物化不是 HTTP 错误**（200 + ready=false）。
  ⚠️ 该路由**未进** `shared/openapi.json`（mock 是 gen-protocol 的唯一源，shared/ 非我域）
  ⇒ 前端类型面要等 kilo 登记（届时走 versioning §7 minor 流程）。

**⚠️ 上游阻塞缺陷（非本单引入，M5-A11 实测并回执）**：driver 跑起来时，**连发几次 POST
就会把 world.db 写锁长期占住** —— 同步写面提交时 `sqlite3.OperationalError: database is
locked`，且锁**持续存在**（第三条连接 `BEGIN IMMEDIATE` 同样拿不到）。复现：起 lifespan
（driver 在跑）后连发 5 次 POST，`201 / EXC / 201 / 201 / EXC`；把 `app.state.driver` 取消
后再连发 ⇒ 全 201、锁自由。**同样的抖动在 R-4 基线（不含包写）上就能复现**
（`201 / EXC / 201 / 201 / EXC`）⇒ 与物化包无关，是 async 驱动侧有写事务没有收口。
本单对此的处置只有两条，都不是「绕过」：
① 写事务 **writer-first**（语料/快照引用在只读会话先取）——这是 SQLite 唯一能吃到 busy
   重试的形态，也顺带缩短持锁窗口；
② 钉子层面对 driver 确定性（`test_m5_materialization_api.py` 的 `client` 夹具取消
   `app.state.driver`）——**不把上游缺陷藏进重试里**（有界重试治不了持久锁，只会拖长失败）。
根治在 `run_world_driver` / lifespan 侧（谁开的事务谁收口），归 Claude/kilo 面。
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from sim.api.ws import register_anchor_id, unregister_anchor_id
from sim.core.persistence.anchor_package import (
    collect_corpus_rows_sync,
    diagnose_anchor_materialization,
    encode_corpus_blob,
    latest_snapshot_ref_sync,
    write_anchor_package_sync,
)
from sim.core.persistence.models import PlayerAnchor
from sim.core.persistence.store import SqlEventStore
from sim.llm.prompts.banned_words import scan

router = APIRouter(prefix="/api/anchors", tags=["anchors"])


class AnchorListItem(BaseModel):
    """§1.1 列表项五键白名单（出戏边界：无 tick/seq/branch_id/agent_override）。

    description 逐字对齐 `shared/openapi.json` 快照的 `AnchorListItem`（#4 注入
    ProblemDetail/responses 时该 schema 仍由本文件 response_model 生成）。
    `model_config.json_schema_extra={"description": ""}` 是 K3 同款抑制开关
    （pydantic 无「不生成 description」开关）——openapi_ext 后处理按空串剥除。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"description": ""})

    id: str
    name: str
    #: 叙事化时间标签；construct 期 calendar 未就绪 → 空串（§6.7 定型，非 null）
    story_label: str = Field(description="叙事化时间标签，非 tick 数值")
    #: schema 声明 date-time 串（模型里是 epoch float → 此处序列化时转换）
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    #: §1.4 派生只读：末梢游标（updated_at 最大者）
    protected: bool


class AnchorCreate(BaseModel):
    """§1.2 请求体：仅 name（1..64，与 ProfileCreate 同口径）。

    `extra="forbid"` 拒绝越权字段（tick/branch_id 等服务端定，客户端不参与游标）。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"description": ""})

    name: str = Field(min_length=1, max_length=64)


class AnchorRename(BaseModel):
    """§1.3 请求体：仅 name 必填非可空（全量替换语义；不复用 ProfileUpdate）。"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"description": ""})

    name: str = Field(min_length=1, max_length=64)


class AnchorMaterializationStatus(BaseModel):
    """§2 只读诊断面响应（批次 E）：该档**能不能回退**，以及不能的原因码。

    形状固定 `{anchor_id, ready, reason}`：
    - `ready=false` 时 `reason` ∈ `anchor_package.MATERIALIZATION_REASONS`（固定集）；
    - `reason=None` ⇔ `ready=true`（**互斥**，不出现「ready 但带原因」的骗人组合）；
    - **不含任何世界状态内容**（不返 seq/tick/branch_id/包内行值）——与本模块其余响应
      同款出戏边界。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"description": ""})

    anchor_id: str
    ready: bool
    reason: str | None = None


#: 写路径进程锁（§6.1 A2：同步临界区互斥；单 worker 部署匹配——写方法是同步 SQL，
#: 在事件循环线程内执行，threading.Lock 足够且避免 asyncio.Lock 的同步/异步混用问题）。
_anchor_write_lock = threading.Lock()


def _assert_name_clean(name: str) -> None:
    """F-6 注册侧 fail-closed：name 过现行 scan()，命中即拒（不扩词表）。

    422 形由全局 handler 兜底为 ProblemDetail；此处抛 HTTPException 携机器码。
    """
    result = scan(name)
    if not result.ok:
        words = "、".join(sorted({h.word for h in result.hits}))
        raise HTTPException(
            status_code=422,
            detail=f"/errors/anchor-name-rejected|{name!r} 含不可用词汇：{words}",
        ) from None


class AnchorStore:
    """PlayerAnchor 读写路径（同步 SQL；settings.py ProfileStore 同口径）。

    protected 单一真相源 = **列**（C1 切列完成，派生式退休）。
    退化态（全表无 protected 行）是合法态（C3 删末梢不补位）。
    """

    def __init__(self, db_url: str = "sqlite:///world.db", create_tables: bool = True) -> None:
        self._engine = create_engine(db_url)
        if create_tables:
            from sim.core.persistence.models import Base

            Base.metadata.create_all(self._engine)
        self._session_local: sessionmaker[Session] = sessionmaker(self._engine)

    def session(self) -> Session:
        return self._session_local()

    def _rows(self) -> list[PlayerAnchor]:
        with self._session_local() as s:
            rows: list[PlayerAnchor] = list(
                s.query(PlayerAnchor)
                .order_by(PlayerAnchor.updated_at.desc(), PlayerAnchor.id.desc())
                .all()
            )
            s.expunge_all()
            return rows

    def _max_updated_at(self) -> float | None:
        """D-14 保底判据（退化态 /current 用）；非 protected 判据（C1 已切列）。"""
        with self._session_local() as s:
            return s.query(func.max(PlayerAnchor.updated_at)).scalar()

    def list_items(self) -> list[AnchorListItem]:
        """§1.1 列表：protected 直接读列（S-4 切列，C1 单一真相源）。"""
        rows = self._rows()
        return [
            AnchorListItem(
                id=row.id,
                name=row.name,
                story_label="",
                created_at=_iso(row.created_at),
                protected=bool(row.protected),
            )
            for row in rows
        ]

    def current_item(self) -> AnchorListItem | None:
        """M5-K3 / 裁 21-A D-9 + D-14：当前游标（protected 列优先）。

        正常态：protected=true 的行（≤1，C3）；同刻多行按 id 降序兜底（与 0010
        回填同口径）。退化态（无 protected 行，删末梢不补位）：回退 max(updated_at)
        保底**不 404**，protected=false（语义=「没有受保护的末梢」，D-14）。
        """
        with self._session_local() as s:
            row: PlayerAnchor | None = (
                s.query(PlayerAnchor)
                .filter(PlayerAnchor.protected.is_(True))
                .order_by(PlayerAnchor.updated_at.desc(), PlayerAnchor.id.desc())
                .first()
            )
            degraded = row is None
            if degraded:
                row = (
                    s.query(PlayerAnchor)
                    .order_by(PlayerAnchor.updated_at.desc(), PlayerAnchor.id.desc())
                    .first()
                )
            if row is None:
                return None
            s.expunge(row)
            return AnchorListItem(
                id=row.id,
                name=row.name,
                story_label="",
                created_at=_iso(row.created_at),
                protected=not degraded,
            )

    def get_item(self, anchor_id: str) -> AnchorListItem | None:
        """按 id 查：protected 读列（S-4 切列）。"""
        with self._session_local() as s:
            row: PlayerAnchor | None = s.get(PlayerAnchor, anchor_id)
            if row is None:
                return None
            s.expunge(row)
            return AnchorListItem(
                id=row.id,
                name=row.name,
                story_label="",
                created_at=_iso(row.created_at),
                protected=bool(row.protected),
            )

    # ---- 写路径（A2 进程锁串行；每方法一个 session = A3 同事务）----

    def create_item(
        self,
        name: str,
        *,
        branch_id: str,
        tick: int,
        seq: int,
        rng_state: str | None = None,
        state_hash: str | None = None,
    ) -> AnchorListItem:
        """§1.2 POST：同事务写新档 protected=true + 清其余（§6.1 A3）**+ 写物化包**。

        updated_at 只写一次（INSERT default；此处显式赋值一次，后续永不改）。
        游标 (branch_id, tick, seq) 由路由层从世界态取（客户端不参与，D-16）。

        物化包（M5-A11）：**同一个 session、同一个 commit** 里写（档 + 包 + 清位）⇒ 不存在
        「有档没包」的半态。包内容 = 快照指针（引用，不复制 blob）+ 3 张无事件源表行值
        + `agent_override` 副本 + `state_hash` 对账基线。
        - `rng_state` 缺省 `None` ⇒ 该档诊断为 `rng_unavailable`（fail-closed；**禁止**
          seed 派生兜底，见模块注的已知缺口）。
        - `state_hash` 缺省 `None` ⇒ 可空列，R-2 对账基线待接入。

        ⚠️ **writer-first 纪律**：语料/快照引用在**只读会话**里先取（见下方注释），写事务
        随后才开嗓——SQLite 的「读后升级为写」不重试，与 driver 的 in-flight flush 相撞就是
        硬 `database is locked`（实测连发两次 POST 必现）。
        """
        # 语料行值 / 快照引用**先在只读会话里取**（下面写事务因此以写语句开嗓）。
        # 纪律：SQLite 下「先读后写」的事务在升级为写者时**不重试**（busy handler 只对
        # 开局就写的事务生效）⇒ 撞上 driver 的 in-flight flush 就直接 SQLITE_BUSY。写面
        # 必须是 writer-first，这也是本方法原有形态（autoflush 先落 INSERT）。
        with self._session_local() as read_s:
            corpus_blob = encode_corpus_blob(collect_corpus_rows_sync(read_s, branch_id))
            snapshot_ref = latest_snapshot_ref_sync(read_s, branch_id, seq)

        with _anchor_write_lock, self._session_local() as s:
            anchor_id = uuid.uuid4().hex[:12]
            now = time.time()
            row = PlayerAnchor(
                id=anchor_id,
                name=name,
                branch_id=branch_id,
                tick=tick,
                seq=seq,
                agent_override="{}",
                protected=True,
                updated_at=now,
            )
            s.add(row)
            # 同事务清旧末梢（A3：两写一事务，SQLite 写串行兜底）
            s.query(PlayerAnchor).filter(PlayerAnchor.id != anchor_id).update(
                {PlayerAnchor.protected: False}
            )
            # 同事务写物化包（A11）：语料行值/快照引用已在只读会话取好（writer-first，见上）。
            write_anchor_package_sync(
                s,
                anchor_id=anchor_id,
                branch_id=branch_id,
                tick=tick,
                seq=seq,
                rng_state=rng_state,
                agent_override=row.agent_override,
                corpus_blob=corpus_blob,
                state_hash=state_hash,
                snapshot=snapshot_ref,
            )
            s.commit()
            return AnchorListItem(
                id=row.id,
                name=row.name,
                story_label="",
                created_at=_iso(row.created_at),
                protected=True,
            )

    def rename_item(self, anchor_id: str, name: str) -> AnchorListItem | None:
        """§1.3 PATCH：只改 name；**不动** updated_at/protected（硬约束）。

        返回 None = 不存在（404 判定归路由层）。
        """
        with _anchor_write_lock, self._session_local() as s:
            row: PlayerAnchor | None = s.get(PlayerAnchor, anchor_id)
            if row is None:
                return None
            row.name = name
            s.commit()
            return AnchorListItem(
                id=row.id,
                name=row.name,
                story_label="",
                created_at=_iso(row.created_at),
                protected=bool(row.protected),
            )

    def delete_item(self, anchor_id: str) -> str | None:
        """§1.4 DELETE：409 判据**读列**；硬删；返回 None=不存在 / "protected"=409 / "ok"=删成。

        不补位（删末梢后 protected=0 是合法退化态，C3）。
        """
        with _anchor_write_lock, self._session_local() as s:
            row: PlayerAnchor | None = s.get(PlayerAnchor, anchor_id)
            if row is None:
                return None
            if row.protected:
                return "protected"
            s.delete(row)
            s.commit()
            return "ok"


def _current_branch_id_or_400() -> str:
    """当前分支真源读入口（同步侧）：零行/歧义 ⇒ 400 world-not-ready（R-4.1-S）。

    fail-closed：查不到当前行**不猜**（禁 'main' 兜底——记档指向错误世界线
    比拒绝更坏，R-4.1）。detail 与无活跃 loop 同码不同文（0 行=「无当前世界线」，
    歧义不可能——部分唯一索引保证至多一个当前）。
    """
    from sqlalchemy import text

    store = get_anchor_store()
    with store._session_local() as s:
        row = s.execute(
            text("SELECT id FROM branches WHERE is_current = 1 LIMIT 1")
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail="/errors/world-not-ready: 无当前世界线（branches.is_current 全 0；"
            "世界尚未开线或读档交接未完成）",
        ) from None
    return str(row)


def get_current_seq() -> int:
    """当前活跃分支 events 表最大 seq（POST 游标用；无事件 → 0）。

    分支真源 = ``store.current_branch_id()``（R-4.1，branches.is_current 列；
    A4/K9「同改警告」执行处之一）。同步轻查询走 anchor store 的 engine
    （同一 world.db；不进驱动热路径）。
    """
    from sqlalchemy import text

    store = get_anchor_store()
    with store._session_local() as s:
        row = s.execute(
            text(
                "SELECT COALESCE(MAX(e.seq), 0) FROM events e"
                " JOIN branches b ON b.id = e.branch_id"
                " WHERE b.is_current = 1"
            )
        ).scalar()
    return int(row or 0)


def _iso(epoch: float) -> str:
    """epoch float → UTC ISO-8601 `...Z`（schema `format: date-time` 口径）。"""
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_anchor_store: AnchorStore | None = None


def get_anchor_store() -> AnchorStore:
    global _anchor_store
    if _anchor_store is None:
        _anchor_store = AnchorStore()
    return _anchor_store


def _item_payload(item: AnchorListItem) -> dict[str, Any]:
    """注册 + 序列化（路由共用的落库→WS 查表集供数点）。

    M5-K3：`register_anchor_id` 连带登记**叙事标签**（name + story_label）——
    `load_anchor` 成功路径的 D-6 分叉告知帧靠它组游标指针（零原始数值）。
    """
    register_anchor_id(item.id, item.name, item.story_label)
    return item.model_dump()


@router.get("", response_model=list[AnchorListItem])
async def list_anchors() -> list[dict[str, Any]]:
    """§1 GET /api/anchors：空库 → 200 + []（非 404）。

    每条落库项注 id 进 ws.py 同步查表集（部署债 #1）——`load_anchor` 的
    存在性判定由此供数，不再靠进程内 `_ANCHOR_IDS` 手填。
    """
    return [_item_payload(item) for item in get_anchor_store().list_items()]


@router.get("/current", response_model=AnchorListItem)
async def current_anchor() -> dict[str, Any]:
    """M5-K3 / 裁 21-A D-9：当前所在游标（戏外 meta shell 只读面，零原始数值）。

    **声明顺序铁律**（本路由唯一高风险点）：必须注册在 `/{anchor_id}` **之前**——
    FastAPI 按声明顺序匹配，路径参数路由若在前会把 `"current"` 当 anchor_id 吃掉
    并回 404。钉子：`TestCurrentAnchorRoute`（实跑 200 + 白盒顺序双钉）。

    空库 → 404（"还没有存过档"）：与列表路由的 200+[] 是两回事——列表问"有什么"，
    当前指针问"你在哪"，没有档就是没有答案。字段同 `AnchorListItem` 五键。
    """
    item = get_anchor_store().current_item()
    if item is None:
        raise HTTPException(status_code=404, detail="/errors/anchor-not-found") from None
    return _item_payload(item)


@router.post("", response_model=AnchorListItem, status_code=201)
async def create_anchor(payload: AnchorCreate, request: Request) -> dict[str, Any]:
    """§1.2 POST 新建游标（裁 28-G S-2/S-5/S-8）。

    世界未就绪（无活跃 loop）→ 400 world-not-ready（判据=app.state.loop，§1.5 ③）。
    游标：branch=当前活跃分支（D-16 默认 main）、tick=世界当前 tick、seq=当前
    分支 events 最大 seq（客户端不参与游标）。name 过 F-6 fail-closed 扫描。
    """
    loop = getattr(request.app.state, "loop", None)
    if loop is None:
        raise HTTPException(status_code=400, detail="/errors/world-not-ready") from None
    _assert_name_clean(payload.name)  # R-9：先世界就绪(400)后词表(422)，错误序对齐契约表
    tick = loop.state.tick
    seq = get_current_seq()
    # 分支真源 = branches.is_current（R-4.1；A4/K9「同改警告」执行处之二）。
    # 零行（无当前行/歧义库全 0）⇒ fail-closed 400 world-not-ready（R-4.1-S 裁定：
    # 不用 409/503，0 行与歧义同码、detail 区分）；禁 'main' 字面量兜底。
    branch_id = _current_branch_id_or_400()
    # 物化包的两个可空成分（M5-A11）：state_hash 取世界态现值（R-2 对账基线）；
    # rng_state 缺省 None —— app.state 上还没有 registry+抽签 cache（模块注的已知缺口），
    # 该档因此在诊断面是 `rng_unavailable`，**不猜、不用 seed 派生**。
    item = get_anchor_store().create_item(
        payload.name,
        branch_id=branch_id,
        tick=tick,
        seq=seq,
        rng_state=_rng_state_or_none(request),
        state_hash=_world_state_hash(loop),
    )
    return _item_payload(item)


def _rng_state_or_none(request: Request) -> str | None:
    """锚点时刻的 RNG 状态包；混沌流侧未暴露 registry ⇒ ``None``（fail-closed）。

    上层把 `app.state.rng_capture` 挂成「零参可调用、返回 capture_rng_state 的 JSON 串」
    即可接上（混沌流域），本模块零改动。
    """
    capture = getattr(request.app.state, "rng_capture", None)
    if capture is None:
        return None
    blob = capture()
    return blob if isinstance(blob, str) and blob.strip() else None


def _world_state_hash(loop: Any) -> str | None:
    """`WorldState.state_hash`（R-2 对账基线）；拿不到就 ``None``（可空列）。"""
    state = getattr(loop, "state", None)
    hasher = getattr(state, "state_hash", None)
    if hasher is None:
        return None
    try:
        value = hasher() if callable(hasher) else hasher
    except Exception:  # 对账基线不值得让存档失败
        return None
    return value if isinstance(value, str) else None


@router.patch("/{anchor_id}", response_model=AnchorListItem)
async def rename_anchor(anchor_id: str, payload: AnchorRename) -> dict[str, Any]:
    """§1.3 PATCH 重命名（S-2/S-6）：只改 name；成功刷新 WS 标签（register 幂等覆盖）。"""
    _assert_name_clean(payload.name)
    item = get_anchor_store().rename_item(anchor_id, payload.name)
    if item is None:
        raise HTTPException(status_code=404, detail="/errors/anchor-not-found") from None
    register_anchor_id(item.id, item.name, item.story_label)  # 幂等覆盖标签
    return _item_payload(item)


@router.delete("/{anchor_id}", status_code=204)
async def delete_anchor(anchor_id: str) -> Response:
    """§1.4 DELETE（S-6）：409 读列判定；硬删；成功摘除 WS 注册表（D-15/S-7 调用点）。"""
    outcome = get_anchor_store().delete_item(anchor_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="/errors/anchor-not-found") from None
    if outcome == "protected":
        raise HTTPException(status_code=409, detail="/errors/anchor-protected") from None
    unregister_anchor_id(anchor_id)  # S-7 调用点（契约 §1.5 V.3）
    return Response(status_code=204)


@router.get("/{anchor_id}", response_model=AnchorListItem)
async def get_anchor(anchor_id: str) -> dict[str, Any]:
    """§4 按 id 查：404 时回 `{"detail"}`（ProblemDetail 收编见 §5 #3）。"""
    item = get_anchor_store().get_item(anchor_id)
    if item is None:
        raise HTTPException(status_code=404, detail="/errors/anchor-not-found") from None
    return _item_payload(item)


@router.get("/{anchor_id}/materialization", response_model=AnchorMaterializationStatus)
async def anchor_materialization(anchor_id: str, request: Request) -> dict[str, Any]:
    """M5-A11 只读诊断面：该档能不能回退（A3 §2「产品显示不可回退，而不是让人撞 500」）。

    - **不可物化不是 HTTP 错误**：一律 200 + `ready=false` + 原因码（`no_package` /
      `rng_unavailable` / `snapshot_missing` / `event_gap` / `corpus_mismatch`）；
    - anchor 不存在才 404（`/errors/anchor-not-found`，与其余读路由同码）；
    - 无世界（app.state.store 缺位 ⇒ 没有事件库）⇒ 400 `world-not-ready`（fail-closed，
      **不新建引擎去猜**哪个库才是真的）；
    - 路径两段 vs `/{anchor_id}` 一段 ⇒ 无遮蔽顺序风险（仍按就近声明放最后）。
    """
    if get_anchor_store().get_item(anchor_id) is None:
        raise HTTPException(status_code=404, detail="/errors/anchor-not-found") from None
    store = getattr(request.app.state, "store", None)
    if not isinstance(store, SqlEventStore):
        raise HTTPException(status_code=400, detail="/errors/world-not-ready") from None
    diagnosis = await diagnose_anchor_materialization(store, anchor_id)
    return {
        "anchor_id": anchor_id,
        "ready": bool(diagnosis.ready),
        "reason": diagnosis.reason,
    }
