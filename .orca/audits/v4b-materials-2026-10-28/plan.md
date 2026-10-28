# V4b material classification implementation plan

> Execution: inline with superpowers:executing-plans and tdd-workflow. No extra agent/tree or browser automation. Local codex commits only.

Goal: dig yields and place consumes the material of the target's static height: 1=earth, 2=stone, 3=wood. Preserve one-unit quantities, material reasons, current visual heights and C3 HUD isolation.

Spec: `.orca/talking.txt`, seventh round V4b, delegated by the user's instruction to finish it.

Architecture: reuse VoxelRuntime's height callback; keep committed counts and pending reservations per material. Replay existing MATERIAL_MOVED events verbatim, preserving old earth-only history. Expand only VoxelEditedPayload's material literal in events.py. Publish all three stock counters, while schema/client allow absent stone/wood as zero. Protocol 1.13 is updated in both envelope constants and the OpenAPI source, then TypeScript is generated normally.

Scope: sim/agent/voxel_exec.py, sim/api/ws.py (and main.py only if existing wiring needs it), the one literal in sim/core/events.py, shared/openapi.json + generated protocol.ts, client net/ws.ts, world-mirror.ts, VoxelInventory.tsx, related tests and docs/api/versioning.md. No sim/world, sim/npc, sim/llm, migration, height table, atlas, material picker, or effectiveHeight edits.

## Tasks

- [x] 0. Backup talking.txt, fetch and fast-forward local main; verify inbox remains untracked. Baseline 13e2ca7, clean worktree.
- [x] 1. RED: cover height-based yields, symmetric spending, separate pending reservations, wrong-material rejection without persistence, replay/snapshot equality, old history, three-field validation and HUD rows. Record intended failures and commit the test checkpoint.
- [x] 2. GREEN: implement per-material state and reservations, literal expansion, protocol 1.13/OpenAPI generation, client validation and HUD. Run the same targets and commit the green checkpoint.
- [ ] 3. Run all assigned gates plus production build; review boundaries and read/load integration, record results, update Codex recovery and talking receipt.

## Review focus

1. Pending placement reservations cannot consume another material's stock or overspend before flush.
2. Replayed historical material IDs are not reclassified using today's height; foreign/unknown transfers do not affect the player's counts.
3. Empty/reset snapshots clear all counters and transient reservations; rejected inputs do not mutate stock or write events.
4. Missing optional stone/wood are zero; present negative/fractional/null/non-finite values are rejected before forwarding to HUD.
5. Inventory stays in voxel_state/HUD; world event payloads gain only the authorized material literal, and static rendering/collision rules stay unchanged.

## Ledger

- Task 0 complete: talking backup verified, git fetch succeeded, ff 16489c3..13e2ca7 succeeded, talking not tracked.
- Environment: pytest via uv; client npm/Vitest and existing server-rendered React tests. coverage/pytest-cov are not installed or configured; no test dependency will be added solely for a coverage number.
- Pre-flight: protocol schema generation is shared by runtime frame tests, client validation and HUD tests. Event factory accepts no material argument; preserve its metadata via a validated immutable payload replacement rather than changing its signature outside the permitted one-line events.py scope.
- Scope decision: use the already-loaded static height callback; no height sampling/statistics rerun and no extra asset.
- Task 1 complete: baseline Python 50 passed and client 12 passed. RED Python 43 failed/26 passed; RED client 6 failed/15 passed. Checkpoint 61570c2 is on codex. Logs in this audit directory.
- Generator ruling: JSON Schema `default: 0` makes the installed openapi-typescript emit required fields, breaking legacy earth-only frames (typecheck observed RED). Keep stone/wood outside required, document absent=0 in their descriptions, and implement zero fallback in HUD; do not alter the generator or hand-edit its output.
- Version integration: live FastAPI still had an independent 1.12 literal. New real app.openapi version test observed RED before updating only that literal to 1.13; WS constants and physical OpenAPI source are aligned.
- Task 2 GREEN: focused Python 70/70 and client 21/21 passed; gen:protocol:check and typecheck passed with generated stone?/wood?. Full client 259/259, ruff check/format (363 files), pyright and production build passed. Full Python suite is in progress; commit this implementation checkpoint without claiming final gate completion.
