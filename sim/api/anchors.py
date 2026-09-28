"""玩家档（anchor）HTTP API — M5-K7 最小实现（anchors-api.md §4）+ M5-K3 D-9 当前指针。

**本批次范围（K7 部署债 #1）**：只做读路径，替 ws.py `_ANCHOR_IDS` 内存替身
换成落库供数——`GET /api/anchors` 列表 + `GET /api/anchors/current` 当前游标
（M5-K3 / 裁 21-A D-9，**必须注册在路径参数路由之前**）+ `GET /api/anchors/{anchor_id}`
按 id 查，每条落库项调 `register_anchor_id()` 注进 WS 分发块的同步查表集
（连带登记 name/story_label 叙事标签，供 D-6 分叉告知帧组游标指针）。

**不在本批次（§5 清单余项，Claude 域）**：
- POST/PATCH/DELETE 三路由（含 `AnchorCreate`/`AnchorRename` 请求模型与 name 校验）；
- `sim/api/errors.py` ProblemDetail handler（§3.2 三层接法）；
- `player_anchors.protected` 新列迁移（现由 §1.4 派生公式在列表时算）。

因此 404 目前走 FastAPI 默认 `HTTPException`（`{"detail": ...}` 形），
**不是** ProblemDetail 四键形——待 #3/#4 落地后统一收编。

`protected` 派生（§1.4）：`NOT EXISTS(other.updated_at > 本档.updated_at)`
——末梢=updated_at 最大者。派生只读、不落库（POST 未实现时无写入路径，
等 POST 落库时 §1.4 要求改为「构造时计算写列」，届时只动本文件一处）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from sim.api.ws import register_anchor_id
from sim.core.persistence.models import PlayerAnchor

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


class AnchorStore:
    """PlayerAnchor 读路径（同步 SQL；settings.py ProfileStore 同口径）。

    只读：`list_items()` / `get_item()`。写路径（POST/PATCH/DELETE）归
    §5 清单 #2/#5，本批次不实现。
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
                s.query(PlayerAnchor).order_by(PlayerAnchor.updated_at).all()
            )
            s.expunge_all()
            return rows

    def _max_updated_at(self) -> float | None:
        with self._session_local() as s:
            return s.query(func.max(PlayerAnchor.updated_at)).scalar()

    def list_items(self) -> list[AnchorListItem]:
        rows = self._rows()
        newest = self._max_updated_at()
        return [
            AnchorListItem(
                id=row.id,
                name=row.name,
                story_label="",
                created_at=_iso(row.created_at),
                protected=newest is not None and row.updated_at >= newest,
            )
            for row in rows
        ]

    def current_item(self) -> AnchorListItem | None:
        """M5-K3 / 裁 21-A D-9：当前游标（末梢=updated_at 最大者）。

        同 `updated_at` 时按 `id` 降序兜底排序，保证多档同刻的返回**确定**（测试
        可复现）。`protected=True` 恒成立——它按定义就是末梢。
        """
        with self._session_local() as s:
            row: PlayerAnchor | None = (
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
                protected=True,
            )

    def get_item(self, anchor_id: str) -> AnchorListItem | None:
        with self._session_local() as s:
            row: PlayerAnchor | None = s.get(PlayerAnchor, anchor_id)
            if row is None:
                return None
            s.expunge(row)
            newest = self._max_updated_at()
            return AnchorListItem(
                id=row.id,
                name=row.name,
                story_label="",
                created_at=_iso(row.created_at),
                protected=newest is not None and row.updated_at >= newest,
            )


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
        raise HTTPException(status_code=404, detail="还没有存过档") from None
    return _item_payload(item)


@router.get("/{anchor_id}", response_model=AnchorListItem)
async def get_anchor(anchor_id: str) -> dict[str, Any]:
    """§4 按 id 查：404 时回 `{"detail"}`（ProblemDetail 收编见 §5 #3）。"""
    item = get_anchor_store().get_item(anchor_id)
    if item is None:
        raise HTTPException(status_code=404, detail="anchor 不存在") from None
    return _item_payload(item)
