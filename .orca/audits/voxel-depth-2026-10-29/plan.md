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

## 1. Regression contracts (complete)

- [x] Add RED tests for sequential digs, zero floor, earth placement, commit boundaries, height restoration, strict payload height, legacy replay and protocol 1.14.
- [x] Add RED client tests for authoritative height, height-only invalidation, invalid rows, and mouse/cardinal-keyboard/collision agreement.
- [x] Observe expected failures, record evidence and commit the checkpoint.

## 2. Server, protocol and client implementation

- [x] Extend payload/factory, runtime current height and commit/replay folding. Use new height to derive gid and current height to derive yield.
- [x] Carry height through the voxel view and cold-start/branch restore; normalize height-less legacy voxel collision without rewriting event rows.
- [x] Add required height to live OpenAPI. Project that schema into the existing physical snapshot with a script; the current `gen:protocol` only generates TypeScript, so run it for `shared/protocol.ts` (never hand-edit generated types).
- [x] Bump all version pins to 1.14 and update the two API docs plus existing architecture height rule.
- [x] Render committed result height, validate it at the client boundary, invalidate height-only changes, use result height for block color and scars. Adapt legacy tests to valid terrain/height fixtures.

## 3. Evidence, gates and handoff

- [x] Real 140×100 map probe: 0/1/2/3 dig attempts on every cell, runtime→events→view→client; assert walkable implies height 1, mouse and cardinal keyboard match collision, earth banks still yield earth.
- [x] Persisted nested-branch history replay matches online heights/collision/inventory per cell. Delete the disposable `.orca/tmp` probes after execution; retain their output in this audit directory.
- [x] Run full non-bench pytest, Ruff check/format, Pyright, client typecheck/lint/format/test/build, protocol check and both asset byte checks.
- [x] Review diff for correctness/security/scope; delivery commit and local talking.txt receipt are the final handoff (never stage inbox).

## Evidence

- Baseline fast-forward `04e2175..9b375bd` completed; talking SHA256 unchanged, ignored and untracked; tree clean.
- RED checkpoint `7b1d559`: Python 9 failed / 13 passed, client 15 failed / 0 passed. Failures pin missing committed heights, invalid client rows, first-dig collision and legacy map replay, plus the version registration.
- Secondary RED for material appearance: two terrain tests rejected the old sampled/earth tint for a resulting stone layer; the edited surface now selects earth/stone/wood appearance by committed height. Scars exist only on dug height 1, never on a high layer or at zero.
- Integration: 88 Python tests passed, including real lifespan flush/cold restart/historical fork/nested fork; client 310 passed / 42 files. The branch assertions compare all 14,000 heights and collision cells, result-height rows and inventory. Material balances are independently folded from bounded ancestor prefixes; the older branch-local replay helper is not used as a false oracle for a child baseline.

### Real-map acceptance

The disposable Python probe loaded the checked-in 140×100 map and height JSON, proposed legal requests through the real VoxelRuntime, observed only committed batches, and carried them through the real voxel view. Targets are isolated reachable cells, with no dynamic structures/NPC occupancy. Each round attempts every cell; already open and zero-height cells reject. This is deterministic headless reconciliation, not browser or human visual acceptance.

| Dig attempts per cell | Accepted edits this round | Walkable cells | Height 0 / 1 / 2 / 3 | Blocked height-1 banks | Invariant violations |
|---|---:|---:|---|---:|---:|
| 0 | 0 | 3947 | 1112 / 5515 / 4379 / 2994 | 1568 | 0 |
| 1 | 8941 | 8326 | 2680 / 8326 / 2994 / 0 | 0 | 0 |
| 2 | 2994 | 11320 | 2680 / 11320 / 0 / 0 | 0 | 0 |
| 3 | 0 | 11320 | 2680 / 11320 / 0 / 0 | 0 | 0 |

- Total yield: earth 1568, stone 7373, wood 2994; replayed events 35805; zero height/view replay mismatches. Asset hashes and counts: `realmap-python.json`.
- The temporary Vitest probe consumed actual Python projection rows into WorldMirror, both incrementally and before asynchronous map arrival as a full snapshot. For each of the 56,000 state-cells it checked effectiveHeight, collision, `pickGround` at the height-1 plane and cardinal `canStep`; every mismatch count is zero (`realmap-client.json`). Existing diagonal/corner movement tests remain green.
- Height 1 is necessary for walkability, not sufficient: all 1568 original earth banks remain blocked until dug, and their resulting height 0 remains blocked. No reverse implication was introduced.
- Probe sources/config/input were deleted from `.orca/tmp` after success, as assigned. No browser, renderer automation, model or external network was launched.

### Review and retained behavior

- New `voxel.edited.height` is a strict integer 0..3. It is optional only for reading old event rows; every runtime-completed edit supplies it. The render contract requires height, and rejects malformed/missing heights. Height-only updates invalidate the terrain cache even if action/gid are unchanged.
- Depth/inventory change only after successful flush observation; pending reservations still prevent overspend. Old material transfers remain verbatim and are never reclassified by new heights. No database migration is needed.
- Placement still requires a walkable target and increases height by one; its material comes from the current target height, so valid height-1 walking surfaces consume earth. Stone/wood remain separate collected stock. No new stacking/jumping or material-selection UI is added.
- Active structures keep their existing height-2 render override and protection; movement/edit picking stay separate (`pickGround`/`pickVoxel`). Camera/interpolation, movement timing, build algorithms and asset/dependency files are untouched.
- Local self-review found no remaining critical/important issue in the assigned path. Main's independent review and human visual acceptance remain the integration step; no rendering/coverage-percentage claim is made.
- First full Python run: 2995 passed, 1 failed, 121 skipped, 72 deselected (381.06s). The sole failure caught the README version badge at 1.13; updated to 1.14 and its 7 checks passed. That run's subprocess decoding warnings came from UTF-8 stdout with the Windows GBK default; the final run uses `PYTHONUTF8=1` consistently, without changing project code.

### Final gates (executed locally)

| Gate | Result | Evidence |
|---|---|---|
| `uv run pytest -m "not bench" -q` | **2996 passed, 121 skipped, 72 deselected, 4 existing deprecation warnings; 377.83s; exit 0** | `pytest-final.log` |
| `uv run ruff check .` / `uv run ruff format --check .` | Passed; 366 files already formatted | Tool output |
| `uv run pyright` | 0 errors, 0 warnings | Tool output |
| client typecheck / lint / format:check | Passed | Tool output; build also runs TypeScript |
| client full Vitest | **310 passed / 42 files**, 2.20s | `client-integration-green.log` |
| `npm run build` | Passed, 13.05s; existing >500kB chunk warning | `build.log` |
| `npm run gen:protocol:check` | Passed; generated TypeScript matches the 1.14 snapshot | `protocol-check.log` |
| height-map builder `--check` | Byte-identical JSON/PNG, counts unchanged | `height-asset.log` |
| block-atlas builder `--check` | Byte-identical PNG/JSON, 12 frames | `atlas-asset.log` |
| `git diff --check` and scope | Passed; assets/dependencies/movement picker/camera/interpolation unchanged | Local diff |

Both real-map JSON reports are committed with this plan. Execution logs remain local. The retained four real persistence tests exercise flush, cold restart, bounded historical load and nested branch load; they can be rerun with `uv run pytest sim/tests/test_voxel_persistence.py -q`. No browser/visual acceptance was performed. Next: main independently reviews/collects the full `9b375bd..codex` range, then human verification of the dig/walk appearance.
