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
    """熵日志 — 开发模式。§11 混合熵 + §4 C5 熵注入审计。

    event_seq（codex 终审记账项，0002 迁移加入）：关联触发本次熵注入的
    events.seq —— M1 由 Claude 接 EntropyMixer 时回填，用于事件-熵对账。
    """

    __tablename__ = "entropy_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    event_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_entropy_branch_tick", "branch_id", "tick"),
        Index("idx_entropy_event", "branch_id", "event_seq"),
    )


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


# ---------------------------------------------------------------------------
# M3 预留表（0002 迁移先建空表+索引，M3 填业务）
# 对齐 docs/data/schema.md §5/§6/§7/§8
# ---------------------------------------------------------------------------


class NpcMemory(TimestampMixin, Base):
    """NPC 记忆 — schema.md §5。§6 MemoryEntry：第一人称叙事记忆。M3 启用。"""

    __tablename__ = "npc_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    npc_id: Mapped[str] = mapped_column(String, nullable=False)
    event_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = 推理/转述
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    emotion_tag: Mapped[str | None] = mapped_column(String, nullable=True)
    distortion: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # M3 填
    created_at_tick: Mapped[int] = mapped_column(Integer, nullable=False)
    last_accessed_tick: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_memories_npc", "npc_id", "branch_id"),
        Index("idx_memories_importance", "npc_id", "importance"),
        Index("idx_memories_event", "branch_id", "event_seq"),
    )


class Relationship(TimestampMixin, Base):
    """NPC 有向不对称关系 — schema.md §7。双向存储（A→B、B→A 各一行）。"""

    __tablename__ = "relationships"

    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    other_id: Mapped[str] = mapped_column(String, nullable=False)
    trust: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    affection: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fear: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    debt: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    face: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_interaction: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("branch_id", "owner_id", "other_id"),
        Index("idx_rel_owner", "branch_id", "owner_id"),
        Index("idx_rel_other", "branch_id", "other_id"),
    )


class Knowledge(TimestampMixin, Base):
    """NPC 事实性知识 — schema.md §8。带可信度与来源。"""

    __tablename__ = "knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    holder_id: Mapped[str] = mapped_column(String, nullable=False)
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    source: Mapped[str] = mapped_column(String, nullable=False)  # witnessed/told/inferred
    learned_at: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("idx_knowledge_holder", "branch_id", "holder_id"),
        Index("idx_knowledge_source", "branch_id", "source"),
    )
