"""Live-only async L2 producer; the synchronous NPC beat consumes finished decisions."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from sim.agent.npc_l2 import L2Decision, NpcL2Service
from sim.core.events import EventKind, WorldEvent
from sim.core.world import WorldState
from sim.llm.client import ProfileSnapshot
from sim.npc.contract import HiddenState
from sim.npc.runtime import NpcRuntime
from sim.npc.sim_exec import _nearest_other


@dataclass(frozen=True)
class _Ready:
    decision: L2Decision
    runtime: NpcRuntime
    revision: int
    generation: int
    lod_revision: int
    identity: str


class NpcL2Coordinator:
    def __init__(
        self,
        *,
        service: NpcL2Service,
        profile_provider: Callable[[], ProfileSnapshot | None],
        runtime: Callable[[], NpcRuntime],
        state: Callable[[], WorldState],
        revision: Callable[[], int],
        is_live: Callable[[], bool],
        context_of: Callable[[str], str],
        hidden_of: Callable[[str], HiddenState],
        memory_of: Callable[[str], tuple[str, ...]],
        names: Mapping[str, str],
        write_lock: asyncio.Lock,
        norms_of: Callable[[str], Awaitable[tuple[str, ...]]] | None = None,
    ) -> None:
        self.service = service
        self._provider = profile_provider
        self._runtime = runtime
        self._state = state
        self._revision = revision
        self._is_live = is_live
        self._context = context_of
        self._hidden = hidden_of
        self._memory = memory_of
        self._norms = norms_of
        self._names = names
        self._lock = write_lock
        self.available = False
        self._generation = 0
        self._pending: dict[str, _Ready] = {}
        self._picked: dict[str, int] = {}
        self._pick_count = 0
        self._conclusions: dict[str, deque[str]] = {}
        self._heard: dict[str, deque[str]] = {}

    def _active(self) -> bool:
        try:
            return self._provider() is not None
        except Exception:
            # Includes decrypt/profile-store failure. Never log the exception or key.
            return False

    def _eligible(self, npc_id: str) -> bool:
        state = self._state()
        actor = state.entities.get(npc_id)
        protagonist = state.entities.get("chenmo")
        profile = self._runtime().profiles.get(npc_id)
        return (
            actor is not None
            and protagonist is not None
            and actor.incapacitated_until is None
            and protagonist.incapacitated_until is None
            and profile is not None
            and profile.lod == 2
            and profile.species == "human"
            and abs(actor.pos[0] - protagonist.pos[0]) + abs(actor.pos[1] - protagonist.pos[1]) <= 3
        )

    def _current(self, npc_id: str, ready: _Ready) -> bool:
        runtime = self._runtime()
        profile = runtime.profiles.get(npc_id)
        return (
            self.available
            and self._is_live()
            and self._eligible(npc_id)
            and ready.runtime is runtime
            and ready.revision == self._revision()
            and ready.generation == self._generation
            and ready.lod_revision == runtime.lod_revisions.get(npc_id, 0)
            and profile is not None
            and ready.identity == profile.identity_anchor
        )

    async def step(self) -> None:
        """One fair candidate per poll. Network I/O never holds the simulation lock."""
        if not self._is_live():
            return
        self.available = self._active()
        if not self.available:
            self._pending.clear()
            return
        async with self._lock:
            runtime = self._runtime()
            candidates = sorted(
                (
                    nid
                    for nid in runtime.profiles
                    if nid not in self._pending and self._eligible(nid)
                ),
                key=lambda nid: (self._picked.get(nid, -1), nid),
            )
            if not candidates:
                return
            npc_id = candidates[0]
            self._picked[npc_id] = self._pick_count
            self._pick_count += 1
            state = self._state()
            profile = runtime.profiles[npc_id]
            listener = _nearest_other(state.entities[npc_id], state)
            revision, generation = self._revision(), self._generation
            lod_revision = runtime.lod_revisions.get(npc_id, 0)
            perception = self._context(npc_id)
            memories = tuple(dict.fromkeys((*self._memory(npc_id), *self._heard.get(npc_id, ()))))
            norms = await self._norms(npc_id) if self._norms is not None else ()
            hidden = self._hidden(npc_id)
        decision = await self.service.decide_once(
            profile,
            perception=perception,
            tick=state.tick,
            listener_id=listener,
            listener_name=self._names.get(listener or "", "眼前的人"),
            memory_entries=memories,
            norms_entries=norms,
            hidden=hidden,
            forbidden_ids=tuple(state.entities),
        )
        async with self._lock:
            self.available = self._active()
            if decision is None:
                return
            ready = _Ready(
                decision, runtime, revision, generation, lod_revision, profile.identity_anchor
            )
            if self._current(npc_id, ready):
                self._pending[npc_id] = ready

    def take_ready(self) -> dict[str, L2Decision]:
        """Validate current range, revision, recipient and hidden window before event assembly."""
        result = {}
        for npc_id, ready in self._pending.items():
            if not self._current(npc_id, ready):
                continue
            decision = ready.decision
            hidden = self._hidden(npc_id)
            if any(hidden.check_reason(text) for text in (decision.thought, decision.line) if text):
                continue
            if decision.action == "request_chat":
                state = self._state()
                if decision.listener_id != _nearest_other(state.entities[npc_id], state):
                    continue
            result[npc_id] = decision
        self._pending.clear()
        return result

    def record(self, ready: Mapping[str, L2Decision], events: Sequence[WorldEvent]) -> None:
        """Keep only actually emitted final conclusions for bounded downgrade writeback."""
        for event in events:
            npc_id = str(event.payload.get("npc_id", ""))
            decision = ready.get(npc_id)
            if decision is None:
                continue
            if event.event_type is EventKind.NPC_MONOLOGUE:
                text = event.payload.get("content")
            elif event.event_type is EventKind.NPC_CHAT:
                text = event.payload.get("line")
            else:
                continue
            if isinstance(text, str) and text and text in (decision.thought, decision.line):
                self._conclusions.setdefault(npc_id, deque(maxlen=6)).append(text)

    def observe(self, events: Sequence[WorldEvent]) -> None:
        """Remember committed direct speech for its recipient, never another NPC's thoughts."""
        for event in events:
            if event.event_type is not EventKind.NPC_CHAT:
                continue
            recipient = str(event.payload.get("to_id", ""))
            speaker = str(event.payload.get("npc_id", ""))
            self._runtime().note_dialogue(speaker, tick=event.tick)
            self._runtime().note_dialogue(recipient, tick=event.tick)
            if recipient not in self._runtime().profiles:
                continue
            line = event.payload.get("line")
            if isinstance(line, str) and line:
                name = self._names.get(speaker, "眼前的人")
                self._heard.setdefault(recipient, deque(maxlen=3)).append(f"{name}说：{line}")

    def take_summary(self, npc_id: str) -> str | None:
        """Rule compression reuses safe finished text; it never makes an extra model call."""
        parts = list(dict.fromkeys(self._conclusions.pop(npc_id, ())))[-3:]
        while parts and len("；".join(parts)) > 320:
            parts.pop(0)
        return "方才，" + "；".join(parts) if parts else None

    def reset(self) -> None:
        """Discard old-world work, but keep service budgets across player loads."""
        self._generation += 1
        self._pending.clear()
        self._conclusions.clear()
        self._heard.clear()
        self._picked.clear()
        self.available = False
