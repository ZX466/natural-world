# Voxel height and incremental terrain implementation plan

> Execution: superpowers:executing-plans, inline. TDD for behavior and rendering work.

Goal: implement talking.txt fifth-round A/B without changing sim, protocol 1.12, dependencies, or flat-renderer behavior.

Spec: this worktree's `.orca/talking.txt` (fifth round A/B); direct user instruction to finish the task overrides the previous patch-command stop.

Architecture: WorldMirror increments a presentation version at terrain mutation boundaries. WorldScene supplies it to IsoTerrain so unchanged frames return in O(1). On changed frames, compare cached cell surfaces once; repaint the union of changed low-cell footprints using a clip and the original diagonal order, including every intersecting neighbor. Retain the canvas texture and existing high-block pool.

Global constraints: client only; no new npm dependencies; height is visual, collision/gid stay authoritative; local codex commits only; no browser automation; configuration-directory policy follows the direct user message.

## Tasks

- [x] 0. Import only client diff 621fd38..7b9c7b3 using a binary-safe file patch; baseline `npm test`: 225/225.
- [x] 1. A: update voxel/iso/terrain assertions first, observe RED; implement dig=max(0,h-1), place=min(3,h+1), structure precedence, no scar at zero; focused tests GREEN.
- [x] 2. B: test idle sync performs no ground/structure traversal with an unchanged version; test mutation version propagation, phase-only changes, local painting bounds/counts, retained textures and neighbor ordering. Observe RED, implement, GREEN.
- [x] 3. Update existing execution-spec height decision and dev-workflow browser instructions; run all specified Python/client gates plus production client build.
- [x] 4. Review complete diff, fix material findings with regression tests, commit with the implementation and recovery memory; write the resulting commit to the local talking receipt.

## Review focus

1. Low/high transitions at height 1/2; both old and new footprints must be cleared.
2. Empty/reset snapshots and structure removal must invalidate despite in-place ground arrays.
3. Clipped repaint must include background/foreground neighbors in identical diagonal order.
4. Phase-only built/collapsing changes must preserve ongoing fades and avoid canvas uploads.
5. Scene creation/map replacement must seed the same presentation version used by later frame syncs.

## Ledger

- Pre-flight: A changes shared effectiveHeight used by terrain, actor feet, camera and picking. B caches must use the same rule, and preserve flat drawing.
- Ruling: use `--binary --output` plus `git apply FILE` after the user's continue instruction; same client changes, no hand-edited patch, no protocol/sim changes.
- Ruling: preserve user-mandated local Git tracking for agent configuration directories; the contrary talking.txt documentation subtask is superseded by the direct instruction.
- Task 0 complete: binary patch applied; baseline client 39 files / 225 tests passed.
- Task 1 complete: 10 expected failures observed in a-red.log, then focused 40/40 and full client 234/234 passed.
- Task 2 in progress: version/texture/clip tests observed RED. First implementation: 120 idle frames made zero ground/collection traversals; pixel-center differential test matches full bake through six edge/height-transition snapshots. Single-cell edit uses 67 fills vs 4800 full-map fills.
- Ruling: use a <100 draw-call budget for the 40x40 single-cell fixture (over 98% reduction); the initial guessed 60-call ceiling excluded the one-pixel padding's legitimate neighbor coverage. Correctness/padding retained; risk is a modest overdraw budget, not missing faces.
- Task 2 verification: pixel test now checks actual RGB colors and compares six edit snapshots plus seven versioned mirror mutations to fresh full bakes. WorldScene version plumbing covered in renderer tests; typecheck passed after test-context types were corrected.
- Known limit: changed frames still compare all cached cell surfaces once; normal idle frames use the version fast path. Phaser CanvasTexture.refresh uploads the canvas through its existing API; the measured savings concern CPU draw calls and texture-object reuse, not an FPS or partial GPU-upload claim.
- Review process: honor the user's two-tree/talking-only workflow; perform local review and leave a concrete review receipt for Claude's integration review rather than creating another agent/tree.
- Review fix: structure snapshots originally depended on the voxel snapshot's version bump. Added a failing independent empty-structure-snapshot test, then made `applyStructures(list, replace=false)` own clearing/invalidation; websocket snapshots and reset now use that boundary. No schema/protocol change.
- Task 2 complete: final client 39 files / 246 tests passed, including 1x4, 4x1 and 3x2 edge maps. Independent empty-structure-snapshot regression observed RED (size 1, expected 0), then GREEN in the full suite. Final client typecheck, lint and format checks pass.

## Local review

- Height boundaries: literal tests cover dig/place at static heights 0..3 and built/collapsing precedence; low/high transition and zero-height scar removal pass.
- Invalidation: setMap, changed edit/structure batches, snapshot replacement and reset bump the presentation version. Identical/invalid rows, actor updates and dig progress do not. Websocket structure replacement now uses the owned invalidation boundary.
- Painting: old/new low footprints include one-pixel padding; clipped repaint enumerates inverse-bounded diagonals in the original order. RGB pixel-center comparisons match full bakes across edits, structures, resets, edges and thin maps. Atlas face geometry uses the same bounds; no browser/GPU validation was requested or performed.
- Lifecycle: canvas texture is reused for local edits; high-only/phase-only updates do not refresh ground. Shared height textures remain bounded to h=2/3 and all generated textures/images/markers are released on destroy.
- Scope: `git diff --name-only -- sim shared client/package.json client/package-lock.json` is empty. Imported old-asset deletions match the authorized main client baseline. No critical or important findings remain in local review; Claude still performs independent integration review per the two-tree workflow.
- Accepted limits: protocol 1.12 carries the last edit action only, so place followed by dig may move two visual levels. CPU paint-call evidence is not a browser FPS result; WebGL refresh can still upload the complete canvas.

## Final verification

| Check | Fresh result |
|---|---|
| `uv run pytest -m "not bench"` | 2945 passed, 121 skipped, 72 deselected, 4 warnings; 334.89s |
| `uv run ruff check .` / `ruff format --check .` | Passed; 365 files already formatted |
| `uv run pyright` | 0 errors, 0 warnings |
| client typecheck / lint / format:check | Passed after the final snapshot-boundary change |
| client `npm test` | 246 passed / 39 files; 2.32s |
| client `npm run build` | Passed; 11.76s; existing large-chunk warning |
| Idle/draw-count evidence | 120 frames: zero terrain/collection traversal; full 4800 fills versus dirty 67 |
| Scope / whitespace | sim, shared protocol, package.json and package-lock diff empty; git diff --check passed |

Local review completed; no deferred minor findings. Integration remains with Claude on the main tree. Branch/worktree kept; no merge, remote push or browser automation.
