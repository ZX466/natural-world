"""SQLAlchemy 2.0 async ORM 模型 — M0 表

对齐 docs/data/schema.md + m0-core.md §8 EventStore Protocol。
M3 表（npc_memories / relationships / knowledge）暂不建。
"""

from __future__ import annotations

import time

from sqlalchemy import (
    Boolean,
    Float,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


class TimestampMixin:
    """公共时间戳字段。"""

    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: time.time())


class Branch(TimestampMixin, Base):
    """世界线分支 — §6 Branch + §12 双轨存档。"""

    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    forked_from_branch: Mapped[str | None] = mapped_column(String, nullable=True)
    forked_from_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    abandoned_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("idx_branches_status", "status"),)


class Event(TimestampMixin, Base):
    """事件日志 — append-only 世界档。§6 WorldEvent + §4 C4。"""

    __tablename__ = "events"

    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    witnesses: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    entropy_ref: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("branch_id", "seq"),
        Index("idx_events_branch_tick", "branch_id", "tick"),
        Index("idx_events_actor", "branch_id", "actor_id"),
        Index("idx_events_type", "branch_id", "event_type"),
    )


class Snapshot(TimestampMixin, Base):
    """快照 — gzip 压缩的全量状态。§12 双轨存档。

    seq 语义（codex 必须项 #3 修正）：等于快照点当前事件流的 events 最大 seq，
    不是 snapshots 表内自增。读档时 `start_seq = snapshot.seq` 可直接衔接
    `events.seq > start_seq`，保证重放窗口不错位。
    """

    __tablename__ = "snapshots"

    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_cold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        PrimaryKeyConstraint("branch_id", "seq"),
        Index("idx_snapshots_branch_tick", "branch_id", "tick"),
        Index("idx_snapshots_cold", "is_cold"),
    )


class PlayerAnchor(TimestampMixin, Base):
    """玩家档 — 游标 + agent_override。§6 PlayerAnchor。"""

    __tablename__ = "player_anchors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_override: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: time.time())

    __table_args__ = (Index("idx_anchors_branch", "branch_id"),)


class EntropyLog(TimestampMixin, Base):
    """熵日志 — 开发模式。§11 混合熵。"""

    __tablename__ = "entropy_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("idx_entropy_branch_tick", "branch_id", "tick"),)


class LLMProfile(TimestampMixin, Base):
    """LLM 配置档案 — §15 成本治理。"""

    __tablename__ = "llm_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    api_key_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
