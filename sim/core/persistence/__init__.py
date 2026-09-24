"""sim.core.persistence — 事件存储与持久化层（M0/M1）

导出：ORM 模型、EventStore、crypto（api_key 加密）、vector（sqlite-vec 脚手架）。
"""

from sim.core.persistence.knowledge_store import (
    KnowledgeStore,
    KnowledgeStoreError,
    KnowledgeWriteResult,
)
from sim.core.persistence.memory_store import SqlMemoryStore
from sim.core.persistence.models import (
    Base,
    Branch,
    EntropyLog,
    Event,
    Knowledge,
    LLMProfile,
    NpcMemory,
    PlayerAnchor,
    Relationship,
    Snapshot,
)
from sim.core.persistence.store import EventStore

__all__ = [
    "Base",
    "Branch",
    "EntropyLog",
    "Event",
    "EventStore",
    "Knowledge",
    "KnowledgeStore",
    "KnowledgeStoreError",
    "KnowledgeWriteResult",
    "LLMProfile",
    "NpcMemory",
    "PlayerAnchor",
    "Relationship",
    "Snapshot",
    "SqlMemoryStore",
]
