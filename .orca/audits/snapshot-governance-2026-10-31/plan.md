# Snapshot governance implementation plan

**Goal:** Keep per-flush crash checkpoints while bounding active hot snapshot rows and atomically marking abandoned parents cold.
**Spec:** Round thirteen in this worktree's talking.txt; baseline `c706b40` (already synchronized). Inbox backed up and unchanged by ff, ignored/untracked.
**Execution:** Inline Codex, TDD and transaction/recovery verification; main independently reviews/integrates. Only local commits; no browser, remote push or real-database maintenance.

**Synchronization note:** During the round, main synchronized its documentation-only correction `e5c54c4` (only .orca/memory.md) before the RED commit. It is the final common ancestor; the implementation/review range is **e5c54c4..codex**. The persistence code and AST baseline c706b40 are unchanged by that correction.

## Design

- A shared transaction-local policy module is used by both `flush_world` and `SqlEventStore.write_snapshot`. It flushes the just-added row, then deletes only active-branch hot rows outside the newest eight `(tick DESC, seq DESC)` and one first row per game day `(tick ASC, seq ASC)`.
- Snapshot primary key is `(branch_id, seq)`: several rows can share the earliest tick. Use deterministic SQL row ranking to select exactly one daily first, rather than protecting all rows at MIN(tick). Game day comes from the existing 86400-tick calendar constant.
- Daily-first and newest-eight keepers form a union: they can overlap, so the bound is **at most 8 + days**, not necessarily that exact sum for small histories. Cold rows are never deleted; known abandoned branches are never pruned, even if a legacy row is incorrectly hot.
- On the existing active-parent/head-fork abandonment transition, mark its snapshots cold in that same transaction. Preserve anchor-fork behavior, all events and all cold payloads. No new migration/API/protocol method is needed; existing write_snapshot protocol documentation is updated with its policy.
- Preserve latest_snapshot's tick/max_seq predicate and ordering verbatim. Test a historical cursor whose intermediate snapshot was pruned so restoration must replay from the retained first checkpoint, not just reload the unaffected newest snapshot.
- Update only the two implementation documents for actual flush cadence and retention; keep frozen DESIGN.md unchanged. Separate SQLite cold files and event-log archiving remain deferred.

## Review focus

- Same-tick snapshots need a seq tie-break, including day boundaries and overlapping keepers.
- Writes must be visible to the retention query even with autoflush disabled, while all deletion stays inside the caller transaction.
- Scoped active pruning must leave other branches/cold rows untouched; abandoned snapshots must keep byte-identical payloads and row counts.
- Failure after pruning or cold marking must roll back the checkpoint/events or entire fork respectively.
- Recovery JSON, branch-prefix order, cold reads and max_seq windows must survive removal of intermediate snapshots.

## Work

1. [x] RED: retention/day/tie/branch/cold/rollback/recovery tests in isolated SQLite; commit checkpoint.
2. [x] Implement shared policy and wire both snapshot writers plus the existing abandonment transition; align schema/event-sourcing docs.
3. [x] Measure same-day growth and three-day daily-first ticks, recovery JSON equality, and cold row preservation. Run full requested gates and asset byte checks; delivery includes own memory and talking receipt.

## Initial facts

- The actual store has two write paths: direct write_snapshot and flush_world's extra projection. fork.py abandons only active parents in head mode; historical anchor mode deliberately leaves parent status unchanged.
- Read-only query of **this worktree's** world.db: snapshots=0, events=10033, one active branch. This differs from the main tree's reported 3946 snapshots/36001 tick; the databases are separate. No real rows were changed. All new evidence uses isolated temporary databases.
- Existing snapshots are already gzip-compressed; cold marking changes only is_cold. Current implementation docs incorrectly describe active old rows as cold and promise physical export; both are corrected to this round's actual boundary.

## Evidence

- RED **1fd362f**: 13 failed / 8 passed with the old implementation; expected failures cover both writers, disabled autoflush, same-tick ties, retention, cold flags, rollback wiring and removal of an intermediate historical checkpoint.
- GREEN focused integration: **56 passed** across new snapshot contracts, the entire old max_seq window file, world restart tests and fork clone tests. Historical anchor forks keep their active parent hot; sealed parent checkpoints remain readable after cold marking.
- All new persistence tests use isolated SQLite. Full-JSON recovery covers state/paths, nonempty RNG progress, combat flag and chaos chain. A checkpoint at tick 30 is present before growth, then actually pruned by tick 80; bounded ancestor restore selects retained tick 0 and reconstructs the exact earlier JSON. A separate no-qualified-snapshot case also reproduces the full JSON.
- Failure injection runs the actual prune/mark helper before throwing. The event/checkpoint/delete transaction or whole fork rolls back; direct write_snapshot's already-separate prior event commit keeps its historical contract.

### Measured row growth

`uv run python .orca/audits/snapshot-governance-2026-10-31/measure.py` runs the production flush/fork paths in owned temporary on-disk databases, using explicit deterministic checkpoint fixtures and no model/API/browser calls.

| Same-day writes | Hot rows | Total rows |
|---:|---:|---:|
| 1 | 1 | 1 |
| 8 | 8 | 8 |
| 9 | 9 | 9 |
| 10 | 9 | 9 |
| 100 | 9 | 9 |
| 250 | 9 | 9 |
| 1000 | 9 | 9 |

After 1100 writes over three game days, there are **11** hot rows: first ticks **1, 86400, 172800** and newest ticks **172842..172849**. The unit test's independent 100-write/three-day sequence starts at tick 0 and retains first ticks **0, 86400, 172800**, also 11 rows. First means the earliest available checkpoint in the day, not necessarily midnight.

Head-fork then marks **11/11** parent rows cold, with **11 before / 11 after**, identical `(seq,tick,gzip SHA256)` tuples, and **1101 before / 1101 after** byte-equivalent event rows. Cold marking is metadata only; no physical export or recompression is performed.

Growth is bounded per covered game day (`hot <= 8 + days`, with overlap), not a constant bound over infinitely many days or archived histories. No DB file shrink/2GB guarantee is claimed.

`acceptance.json` also records the full-JSON recovery assertions and matching AST SHA256 for `SqlEventStore.latest_snapshot` against c706b40. That method's predicates, ordering and behavior were not edited. Temporary directory ownership is verified before automatic cleanup; the real world.db is never opened for writes.

## Final gates (executed locally)

| Gate | Result | Evidence |
|---|---|---|
| `uv run pytest -m "not bench" -q` | **3012 passed, 121 skipped, 72 deselected, 4 existing deprecation warnings; 362.83s; exit 0** | `pytest.log` |
| Focused persistence integration | 56 passed, including full max_seq/restart/fork-clone coverage | `integration.log` |
| Ruff check / format check | Passed; 368 files already formatted | Tool output |
| Pyright | 0 errors / 0 warnings / 0 information | Tool output |
| Client typecheck / ESLint / Prettier | Passed | Tool output |
| Client full Vitest | 321 passed / 44 files, 2.49s | `client-tests.log` |
| `gen:protocol:check` | Passed; protocol unchanged at 1.14 | Tool output |
| Height-map `--check` | Byte-identical JSON/PNG | `height-check.log` |
| Block-atlas `--check` | Byte-identical PNG/JSON, 12 frames | `atlas-check.log` |
| Audit reproducer | Passed; explicit Ruff check/format also clean | `measure.log`, `acceptance.json` |
| Diff/scope | `git diff --check` clean; no sim/api/shared/client/assets/lockfile/DESIGN changes | Local diff |

Only existing snapshot columns and indexes are used; no schema migration or public EventStore method is added. Both declarations of the existing write_snapshot contract are documented. The two implementation docs explain cadence divergence from frozen DESIGN via 846a052 and distinguish hot deletion from cold marking. No on-disk file export, event deletion, compression optimization or old-store backfill was performed. Existing hot rows in an active branch become subject to retention on its next snapshot write.

Local correctness/security review checked branch-scoped parameterized SQL, tie determinism, pending-row visibility, caller-owned transactions, rollback, cold readability and untouched recovery/window code. No remaining critical/important issue was found in the assigned path. Next: main independently collects the full `e5c54c4..codex` range (RED 1fd362f plus implementation) and reruns the acceptance checks. Logs remain local; this plan, reproducer and acceptance JSON are committed.
