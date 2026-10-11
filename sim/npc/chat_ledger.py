"""sim.npc.chat_ledger — 聊天驱动的关系/记忆进程内账本（批次 E2）。

**禁第二 SQL 驱动**（Global Constraints）：RelationshipStore 是 sync sqlite3，
与实况 aiosqlite 单写者共库=跨驱动锁风险（chenmo_memory docstring 同口径）。
关系/记忆是 runtime 内存态（needs/火场同口径）——**效应**经 npc.chat /
npc.monologue 事件表达，账本本身不进重放面（C4：世界真相仍是事件流）。

常量对齐 sim/npc/society.py（CHAT_AFFECTION_DELTA / RETELL_TRUST_DELTA）；
值域 [0,1] clamp 与 society/RelationshipStore 同约定。
"""

from __future__ import annotations

from sim.npc.society import CHAT_AFFECTION_DELTA, RETELL_TRUST_DELTA

#: 单人记忆环形缓冲上限（观测/检索面，非世界真相）。
_MEMORY_CAP = 20

#: 互动 kind → (字段, delta)——与 society._RULES 同源（DRY：改一处两处红测试）。
_RULES: dict[str, tuple[str, float]] = {
    "chat": ("affection", CHAT_AFFECTION_DELTA),
    "retell": ("trust", RETELL_TRUST_DELTA),
}

#: 观测面字段序（relations_of 输出稳定序，C5）。
_FIELDS = ("affection", "trust", "fear", "debt", "face")


class ChatLedger:
    """{owner: {other: {field: value}}} + {npc: [(tick, text)]} 环形缓冲。"""

    def __init__(self) -> None:
        self._relations: dict[str, dict[str, dict[str, float]]] = {}
        self._memories: dict[str, list[tuple[int, str]]] = {}

    def adjust(self, owner: str, other: str, *, kind: str) -> None:
        """一次互动的关系漂移（owner 对 other 的印象行；值域 clamp [0,1]）。"""
        if kind not in _RULES:
            raise ValueError(f"未知互动类型: {kind!r}")
        field, delta = _RULES[kind]
        row = self._relations.setdefault(owner, {}).setdefault(other, dict.fromkeys(_FIELDS, 0.0))
        row[field] = min(1.0, max(0.0, row[field] + delta))

    def remember(self, npc_id: str, content: str, *, tick: int) -> None:
        """记忆环形缓冲：追加 + 截断到上限（保留最新）。"""
        buf = self._memories.setdefault(npc_id, [])
        buf.append((tick, content))
        if len(buf) > _MEMORY_CAP:
            del buf[: len(buf) - _MEMORY_CAP]

    def memories_of(self, npc_id: str) -> list[tuple[int, str]]:
        """该 NPC 的记忆副本（调用方改不动内部缓冲）。"""
        return list(self._memories.get(npc_id, ()))

    def relations_of(self, owner: str) -> dict[str, dict[str, float]]:
        """owner 对他人的全部关系行副本（观测面）。"""
        return {o: dict(row) for o, row in self._relations.get(owner, {}).items()}

    def __len__(self) -> int:
        return len(self._relations)

    def reset(self) -> None:
        """清空关系与记忆（读档=分叉：账本是本分支投影，分叉即失效——review I2）。"""
        self._relations.clear()
        self._memories.clear()
