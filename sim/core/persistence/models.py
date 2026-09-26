"""SQLAlchemy 2.0 async ORM 模型 — M0 表

对齐 docs/data/schema.md + m0-core.md §8 EventStore Protocol。
M3 表（npc_memories / relationships / knowledge）暂不建。
"""

from __future__ import annotations

import time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    """NPC 记忆 — schema.md §5 + memory-scan.md §4 治理列。§6 MemoryEntry。

    治理列（0003 迁移加入）：
    - entry_id：MemoryEntry.id 的稳定字符串句柄（uuid hex），供 supersede 关联；
    - source：reason/dialogue/event/interoception（写入来源）；
    - superseded_by：指向替代条目 entry_id；NULL = 有效（retrieval 过滤）；
    - invalid_reason：'banned_word' / 'manual_review'。
    append-only 纪律：supersede 只 UPDATE 这两个治理列，永不改 content（S5）。
    """

    __tablename__ = "npc_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String, nullable=False)  # MemoryEntry.id（uuid hex）
    npc_id: Mapped[str] = mapped_column(String, nullable=False)
    event_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = 推理/转述
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="event")
    importance: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    emotion_tag: Mapped[str | None] = mapped_column(String, nullable=True)
    distortion: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # M3 填
    created_at_tick: Mapped[int] = mapped_column(Integer, nullable=False)
    last_accessed_tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    invalid_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("idx_memories_npc", "npc_id", "branch_id"),
        Index("idx_memories_importance", "npc_id", "importance"),
        Index("idx_memories_event", "branch_id", "event_seq"),
        Index("idx_memories_entry", "entry_id", unique=True),
        Index("idx_memories_visible", "npc_id", "branch_id", "superseded_by"),
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
    """NPC 事实性知识 — schema.md §8。带可信度与来源。

    M3-D4（0005 迁移，裁 10 全采 B3 提案）补两组列：
    - **证据链派生键**（codex m3-evidence-chain §5）：`subject_npc_id` /
      `subject_attr_id`（他人属性知识的主体与属性主键；自身事实两列同 NULL）/
      `evidence_seq`（witnessed 锚定的 emerge 事件 seq，经 M2-D3 ``seq_by_index``
      投影缝回填）/ `source_knowledge_id`（told 链上行 id = 级联递归索引起点）；
    - **治理列**（§6 终裁「继承失效、不继承替代」）：`source_memory`（派生源
      记忆 entry_id）/ `invalidated`（独立失效位——knowledge 无「替代行」语义，
      故不复用 ``superseded_by``）/ `invalid_reason`（结构化原因串，不含 LLM 原文）。
    """

    __tablename__ = "knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    holder_id: Mapped[str] = mapped_column(String, nullable=False)
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    source: Mapped[str] = mapped_column(String, nullable=False)  # witnessed/told/inferred
    learned_at: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    # ---- 证据链派生键（m3-evidence-chain §5）----
    subject_npc_id: Mapped[str | None] = mapped_column(String, nullable=True)
    subject_attr_id: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_knowledge_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ---- 治理列（R1/S5：继承失效、不继承替代）----
    source_memory: Mapped[str | None] = mapped_column(String, nullable=True)
    invalidated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invalid_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        CheckConstraint("source IN ('witnessed', 'told', 'inferred')", name="ck_knowledge_source"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_knowledge_confidence"),
        CheckConstraint(
            "(subject_npc_id IS NULL) = (subject_attr_id IS NULL)",
            name="ck_knowledge_subject_pair",
        ),
        Index("idx_knowledge_holder", "branch_id", "holder_id"),
        Index("idx_knowledge_source", "branch_id", "source"),
        Index("idx_knowledge_source_memory", "branch_id", "source_memory"),
        Index("idx_knowledge_source_kid", "branch_id", "source_knowledge_id"),
        Index("idx_knowledge_subject", "branch_id", "subject_npc_id", "subject_attr_id"),
    )


# ---------------------------------------------------------------------------
# M2 表（0004 迁移：NPC 完整属性 + 物质熵增状态）
# 对齐 DESIGN.md §13（NPC 完整属性）+ §11（物质熵增）+ §14（结构 integrity）
# + docs/data/schema.md §9/§12/§13 + codex docs/security/self-unknown.md §6。
#
# 范围说明（M2-D1）：健康档以外的完整属性用宽表 npc_profiles 承载；健康档
# （疾病/旧伤/成瘾/残疾 + 创伤应激）独立成 npc_health，为「自我未知」隐藏
# 标注留 hidden / descriptors / trigger_conditions 三列——字段映射对齐 codex
# sim/npc/hidden.py 的 HiddenAttribute（id/category/label/descriptors/triggers）。
# 物质熵增以 matter_state 表持久化（可重放），熵增过程本身走 events 流的
# tile_changed / matter.* 事件（事件模型见 docs/data/schema.md §13）。
# 注意：npc_memory_vec 是 sqlite-vec 虚拟表，仍锁 M3（vector.py），不在 0004 范围。
# ---------------------------------------------------------------------------


class NpcProfile(TimestampMixin, Base):
    """NPC 完整属性宽表（DESIGN §13；M2）。健康档见 NpcHealth。

    OCEAN 人格与 PAD 情绪为数值列（对齐 §6 契约 + prompt 装配需要）；
    需求/技能/目标/物品/知识边界是低频变动集合，JSON 文本承载避免表爆炸。

    字段域（DESIGN §13）：身份 / 需求（带权重）/ OCEAN / PAD / 技能树 / 目标 /
    物品 / 知识边界（语言判定用识字率与行话）。关系 / 记忆 / 知识分别落
    relationships / npc_memories / knowledge。
    """

    __tablename__ = "npc_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # NPC entity_id
    branch_id: Mapped[str] = mapped_column(String, nullable=False)

    # ---- 身份（DESIGN §13 身份）----
    name: Mapped[str] = mapped_column(String, nullable=False)
    species: Mapped[str] = mapped_column(String, nullable=False, default="human")
    gender: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    age: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occupation: Mapped[str] = mapped_column(String, nullable=False, default="")
    identity_anchor: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 自述锚

    # ---- OCEAN 人格（0-100，DESIGN §13）----
    ocean_openness: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    ocean_conscientiousness: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    ocean_extraversion: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    ocean_agreeableness: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    ocean_neuroticism: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # ---- PAD 情绪（-1..1，DESIGN §13）----
    pad_pleasure: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pad_arousal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pad_dominance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    emotion_updated_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ---- 集合型属性（JSON 文本，DESIGN §13）----
    needs: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # [{name,value,weight}]
    skills: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # {skill: level}
    goals: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # {short,long}
    inventory: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # knowledge_boundary：§7 语言判定用（识字率/行话/阶层用语）
    knowledge_boundary: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # ---- LOD 与游标（DESIGN §13 LOD：0/1/2）----
    lod: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_profiles_branch", "branch_id"),
        Index("idx_profiles_branch_lod", "branch_id", "lod"),
    )


class NpcHealth(TimestampMixin, Base):
    """NPC 健康档 — 疾病/旧伤/成瘾/残疾 + 创伤应激（DESIGN §13/§14，M2）。

    一行 = 一条健康属性。可为「隐藏」（自我未知）属性：
    - hidden=1 时默认不进任何 LLM/戏内输出面，仅情境触发命中才浮现；
    - descriptors 是直陈词面（泄漏扫描面），trigger_conditions 是情境触发关键词；
    字段与语义对齐 codex sim/npc/hidden.py HiddenAttribute + self-unknown.md §1/§6。
    category 取值：disease / old_injury / addiction / disability / trauma。
    """

    __tablename__ = "npc_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    npc_id: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # codex HiddenCategory
    label: Mapped[str] = mapped_column(String, nullable=False)  # 世界内指称
    severity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 0.0-1.0
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    descriptors: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # 直陈词面
    # trigger_conditions：情境触发关键词 JSON（浮现代码用）
    trigger_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_health_npc", "branch_id", "npc_id"),
        Index("idx_health_hidden", "branch_id", "hidden"),
        Index("idx_health_category", "branch_id", "category"),
    )


class MatterState(TimestampMixin, Base):
    """物质熵增状态 — 可损耗对象的完整性/质量/腐朽进度（DESIGN §11/§14，M2）。

    物质熵增是慢变量：结构/物品随 tick 自发衰减（integrity↓、decay↑），
    施工与破坏改变其数值；integrity 归零变 rubble 永不恢复（§14）。
    本表只持久化「当前物质熵状态」，每次变更仍由 events 流的 tile_changed /
    matter.* 事件驱动（§19 禁止直接赋值；§11 熵材料随事件落库）——迁移与
    事件模型说明见 docs/data/schema.md §12/§13。

    subject_kind：structure / item / terrain / natural（树/水土等慢变量 M5）。
    """

    __tablename__ = "matter_state"

    subject_id: Mapped[str] = mapped_column(String)  # 对象稳定 id（分支内唯一）
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    subject_kind: Mapped[str] = mapped_column(String, nullable=False, default="structure")
    material: Mapped[str] = mapped_column(String, nullable=False, default="")
    integrity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)  # 0.0-1.0
    quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)  # 手艺，影响衰减
    decay_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 每 tick 衰减
    load_bearing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # JSON 支撑结构 id 列表（承重依赖图，§14）
    supported_by: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_rubble: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_decay_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        PrimaryKeyConstraint("branch_id", "subject_id"),
        Index("idx_matter_branch", "branch_id"),
        Index("idx_matter_branch_kind", "branch_id", "subject_kind"),
    )


class Structure(TimestampMixin, Base):
    """结构拓扑投影（M4-D2，裁 14-2 ③④⑤）。

    事件流是熵态真相；本表只存当前拓扑与生命周期，不复制 integrity/quality/
    decay_rate/is_rubble。rubble 保留 tombstone 行（phase=rubble）。
    """

    __tablename__ = "structures"

    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    structure_id: Mapped[str] = mapped_column(String, nullable=False)
    tiles: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    material: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False, default="building")
    load_bearing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supported_by: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True)
    built_by: Mapped[str | None] = mapped_column(String, nullable=True)
    built_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("branch_id", "structure_id"),
        Index("idx_struct_branch", "branch_id"),
        Index("idx_struct_owner", "branch_id", "owner_id"),
        Index("idx_struct_phase", "branch_id", "phase"),
    )


class MaterialBalance(TimestampMixin, Base):
    """材料余额投影（M4-D2d）— MATERIAL_MOVED 的 from/to 双边消费。

    事件流是真相；本表只存每个 `(branch, ref, material)` 当前净余额。
    `world:*` 是外部供给基准，允许净负；`npc/structure` 不得为负。
    """

    __tablename__ = "material_balances"

    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    ref: Mapped[str] = mapped_column(String, nullable=False)
    material_id: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        PrimaryKeyConstraint("branch_id", "ref", "material_id"),
        Index("idx_material_branch_material", "branch_id", "material_id"),
    )
