# Gameplay Closure Plan

## Scope

Close audit gaps against DESIGN.md §§7-17 while preserving C1-C6, event sourcing,
deterministic replay, and outbound zero-metadata rules. Existing batch-E wiring is
the base; new behavior must use existing event factories and runtime hooks.

## Work slices

1. Mixed entropy and chaos: add reasoned production injection API, adverse-chain
state, and wire combat critical outcomes, major NPC decisions, encounters, and
player adverse consequences. Add replay/determinism and no-outbound tests.
2. Dialogue and cognition: add Chen Mo provider path with template fallback,
wire language degradation and sunk-cost/trauma/intoxication scorers, and persist
memory through existing SQL memory store interfaces.
3. Errands and rendering: make 20 deterministic scripted errands executable,
complete request -> objective -> completion -> reward flow, and project npc.chat
events to client bubble frames with tests.
4. World and NPC content: wire support-graph cascades and matter decay, add L0
demography/LOD transitions with compression, animal profiles, and role-specific
NPC hooks using existing immutable/event boundaries.
5. Acceptance: unskip only deterministic T4/T5 contract tests; keep true-model
T4 behind its explicit three-lock gate. Run full pytest, ruff, pyright, protocol
generation, and client tests.

## Rules

- Tests first for each slice.
- No new dependencies.
- No direct state mutation or event bypass.
- LLM output never renders raw; validate and filter through existing gates.
- Entropy material stays internal and never enters prompt, perception, or WS.
