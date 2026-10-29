# Voxel depth and grounded movement implementation plan

> Execution: superpowers:executing-plans, inline in the existing Codex worktree. The user requested execution of the complete talking.txt assignment; main owns independent review/integration.

**Goal:** Record committed voxel result heights and keep every walkable edited cell at height 1.
**Architecture:** `voxel.edited.height` is authoritative for new events. The runtime folds committed heights; the render projection sends required `VoxelEdit.height`. Legacy height-less events fold one layer per action against static height, without changing their recorded materials or rewriting history. Rebuilt server collision and client collision enforce height 1, while structure tile overrides retain their existing meaning.
**Stack:** Python/uv/FastAPI/event store; TypeScript/Phaser/Vitest; OpenAPI code generation.
**Spec:** Current `.orca/talking.txt`, tenth round, baseline `9b375bd` (includes ground-picking P0 `b0d4341`).

## Constraints and review focus

- Protocol 1.14 at server/client/test/HTTP snapshot; required result height 0..3 on render rows; old event payloads remain readable.
- Dig 3→2 yields wood and stays blocked; 2→1 yields stone and opens; blocked earth bank 1→0 yields earth and stays blocked; zero cannot be dug.
- Keep existing dig/place admission (dig blocked, place walkable), ownership, reach, commit-only inventory/depth, reservations and structure protection. Placement consumes the current target layer's material and raises one layer.
- Preserve the one-way invariant: blocked height-1 earth banks must remain. Mouse/keyboard agree with collision; height 1 alone is not sufficient for admission.
- No jumping, browser automation, new dependencies, package/venv deletion, remote push or main-tree edits.
- Review risks: repeated same-action height changes with unchanged gid; legacy replay and branch-prefix order; structure overrides over an edited cell; malformed height/positive gid at nonwalking height; uncommitted depth or stock leaking into later edits.

## 1. Regression contracts (in progress)

- [ ] Add RED tests for sequential digs, zero floor, earth placement, commit boundaries, height restoration, strict payload height, legacy replay and protocol 1.14.
- [ ] Add RED client tests for authoritative height, height-only invalidation, invalid rows, and mouse/cardinal-keyboard/collision agreement.
- [ ] Observe expected failures, record evidence and commit the checkpoint.

## 2. Server, protocol and client implementation

- [ ] Extend payload/factory, runtime current height and commit/replay folding. Use new height to derive gid and current height to derive yield.
- [ ] Carry height through the voxel view and cold-start/branch restore; normalize height-less legacy voxel collision without rewriting event rows.
- [ ] Add required height to live OpenAPI. Project that schema into the existing physical snapshot with a script; the current `gen:protocol` only generates TypeScript, so run it for `shared/protocol.ts` (never hand-edit generated types).
- [ ] Bump all version pins to 1.14 and update the two API docs plus existing architecture height rule.
- [ ] Render committed result height, validate it at the client boundary, invalidate height-only changes, use result height for block color and scars. Adapt legacy tests to valid terrain/height fixtures.

## 3. Evidence, gates and handoff

- [ ] Real 140×100 map probe: 0/1/2/3 dig attempts on every cell, runtime→events→view→client; assert walkable implies height 1, mouse and cardinal keyboard match collision, earth banks still yield earth.
- [ ] Persisted nested-branch history replay matches online heights/collision/inventory per cell. Delete the disposable `.orca/tmp` probes after execution; retain their output in this audit directory.
- [ ] Run full non-bench pytest, Ruff check/format, Pyright, client typecheck/lint/format/test/build, protocol check and both asset byte checks.
- [ ] Review diff for correctness/security/scope, commit code and own memory snapshot, write local talking.txt receipt (never stage inbox).

## Evidence

- Baseline fast-forward `04e2175..9b375bd` completed; talking SHA256 unchanged, ignored and untracked; tree clean.
