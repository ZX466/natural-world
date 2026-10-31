# Snapshot governance implementation plan

**Goal:** Keep per-flush crash checkpoints while bounding active hot snapshot rows and atomically marking abandoned parents cold.
**Spec:** Round thirteen in this worktree's talking.txt; baseline `c706b40` (already synchronized). Inbox backed up and unchanged by ff, ignored/untracked.
**Execution:** Inline Codex, TDD and transaction/recovery verification; main independently reviews/integrates. Only local commits; no browser, remote push or real-database maintenance.

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

1. [ ] RED: retention/day/tie/branch/cold/rollback/recovery tests in isolated SQLite; commit checkpoint.
2. [ ] Implement shared policy and wire both snapshot writers plus the existing abandonment transition; align schema/event-sourcing docs.
3. [ ] Measure same-day growth and three-day daily-first ticks, recovery JSON equality, and cold row preservation. Run full requested gates and asset byte checks; commit own memory and write talking receipt.

## Initial facts

- The actual store has two write paths: direct write_snapshot and flush_world's extra projection. fork.py abandons only active parents in head mode; historical anchor mode deliberately leaves parent status unchanged.
- Read-only query of **this worktree's** world.db: snapshots=0, events=10033, one active branch. This differs from the main tree's reported 3946 snapshots/36001 tick; the databases are separate. No real rows were changed. All new evidence uses isolated temporary databases.
- Existing snapshots are already gzip-compressed; cold marking changes only is_cold. Current implementation docs incorrectly describe active old rows as cold and promise physical export; both are corrected to this round's actual boundary.
