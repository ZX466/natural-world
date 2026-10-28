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
- [x] 3. Run all assigned gates plus production build; review boundaries and read/load integration, record results, update Codex recovery and talking receipt with the final commit.

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
- GREEN checkpoint: 93b9e29, reachable after the RED checkpoint 61570c2 on codex.
- Review finding and narrow scope extension: the existing live OpenAPI extension still published the closed earth-only VoxelInventory. A new real app.openapi-vs-snapshot test observed RED. Synchronize just that declaration in sim/api/openapi_ext.py; otherwise endpoint schema rejects/omits the new protocol fields. No new API, shared-schema loader, reason enum or world module changes.
- First full Python run: 2959 passed / 9 failed / 121 skipped / 72 deselected (337.09s). All failures traced to old-version pins, README's protocol badge, earth-only inventory expectations or the real-map dig helper incorrectly assuming every obstruction yielded earth.
- Integration fixes: real lifespan/flush/restart/historical-fork tests now use an independent literal height/material oracle for their actual selected cell and assert the corresponding persisted balance. The four lifecycle tests and live websocket test pass (13/13 with status-tool tests). No production lifecycle/fork code changed.
- Scope extension for the version gate: README's single protocol badge updated to 1.13. Existing auth and structure tests retain their behavior assertions with the new envelope/inventory expectations. No implementation-status tool edits.
- Review GREEN: all 110 targeted runtime/gateway/protocol/auth/persistence/status tests passed (17.23s), including actual lifespan cold restart, historical fork and nested fork. Full Python was rerun after the live schema fix; frontend source remains unchanged since the passing 259-test/full-static/build run.

## TDD evidence and review

| Guarantee | Tests / evidence |
|---|---|
| h=1/2/3 yields earth/stone/wood; quantity stays one | test_voxel_runtime.py literal three-cell fixture, same ground gid for all cells; RED then GREEN |
| Place consumes the target material and reserves each material independently | three parameterized round trips, pending-placement and restore-reservation tests; RED then GREEN |
| Wrong material writes no world event or database balance | test_voxel_gateway.py real NpcStore history/balance comparison across a rejected stone placement; RED then GREEN |
| Replay equals persisted stock and old earth events keep their recorded material | three-material NpcStore snapshot/replay equality, legacy earth-on-height-3, empty-history reset; RED then GREEN |
| Actual restart/fork restoration retains committed material and drops future edits | test_voxel_persistence.py real lifespan/flush/cold start/historical fork/nested fork targets; old earth-only oracle observed RED then corrected to the explicit material spec |
| Protocol remains closed and old earth-only frames stay valid | physical and live VoxelInventory schema equality; generated optional stone?/wood?; client malformed-count cases and authenticated live WS tests |
| HUD has only nonzero soil/stone/wood rows; absent optional counts are zero | VoxelInventory server-rendered React tests, mirror and WS callback tests; RED then GREEN |
| C3 and narrow event change preserved | no inventory in real persisted event payloads; events.py changes exactly the material literal; no sim/world, sim/npc, sim/llm or renderer/asset/dependency/migration changes |

Local review checked reservation release uses the material reserved for that pending cell; invalid fractional/negative stock is rejected before mutating a count. Snapshot inventory is copied, and replay resets every count/reservation. Stone/wood rejection text remains in the existing closed outbound literal set. No critical/important findings remain after the live-schema fix.

Coverage tooling is not installed/configured; no coverage percentage is claimed. No browser automation or rendered FPS/visual acceptance was requested or run. Independent integration review remains with Claude via talking.txt.

## Final verification

| Gate | Fresh result |
|---|---|
| `uv run pytest -m "not bench"` | 2969 passed, 121 skipped, 72 deselected, 5 warnings; 337.00s; exit 0 |
| Related runtime/gateway/lifecycle/protocol/auth/status targets | 110 passed; 17.23s |
| `uv run ruff check .` / `ruff format --check .` | Passed; 363 files already formatted |
| `uv run pyright` | 0 errors, 0 warnings |
| `npm run gen:protocol:check` | Passed after the final live-schema correction; generated types unchanged |
| client typecheck / lint / format:check | Passed |
| client Vitest | 259 passed / 39 files; 1.92s |
| client production build | Passed; 11.26s; existing >500kB chunk-size warning |
| Scope and whitespace | Forbidden production directories, renderer/assets/dependencies/migrations unchanged; events.py has only the approved literal expansion; git diff --check passed |

Warnings: final pytest includes dependency deprecations plus one aiosqlite worker `Event loop is closed` thread-cleanup warning reported under `test_m4c_llm_driver.py::TestProtagonistProfile::test_seed_inserts_profile_and_idempotent`. No test failed; this warning is recorded rather than described as resolved or silently discarded. No LLM/driver production changes were made for it.
The named test was repeated alone: 1 passed in 0.81s, warning not reproduced. This diagnostic does not claim the suite-level cleanup warning is fixed.

All V4b decisions are implemented. Known visual place-then-dig depth approximation is unchanged. No remote push, no migration, no browser run; local review complete, integration review remains with the main tree.
