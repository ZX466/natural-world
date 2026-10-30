# Earth-bank visibility implementation plan

**Goal:** Show blocked height-1 earth banks distinctly before a player clicks, while preserving collision, heights, materials and protocol 1.14.
**Baseline:** `2ad6606` (assigned ff from `1895014`; README-only main update). Inbox backed up; SHA256 unchanged by ff; remains ignored/untracked.
**Execution:** Inline Codex execution with systematic debugging, writing-plans and TDD; main performs independent collection/review. Spec: current `.orca/talking.txt`, round eleven. No other agent messages or browser automation.

## Design and constraints

- A bank is an effective height-1 cell with collision 0. Use three short diagonal earth-toned strokes, each with opaque dark and light faces; this differs from the existing inset-diamond dig scar. Geometry stays inside the top face.
- Pool graphics by coordinate with retained-set cleanup. Compare the bank predicate in SurfaceCell so a collision-only update invalidates markers. Version-stable frames and changed-false syncs do no marker work; unrelated terrain edits reuse retained geometry.
- Only walkable dug height-1 cells get scars; banks and scars are mutually exclusive. Active structures retain the height-2 override; bank dig 1→0 removes its marker without changing physics. A collision 0→1 transition at height 1 also removes it.
- Derive one readonly VoxelEdits type from protocol VoxelEdit's `height`/`action`, and use it for both IsoTerrain and effectiveHeight. No parallel hand-written edit shapes.
- No changes to sim/**, map/height JSON, terrain_class.py, asset generators, shared protocol, dependencies, camera, movement or jumping. Run only asset `--check`, never regenerate them.
- Numeric and call-level headless checks only; no browser/human visual acceptance claim. At 3.5x zoom, the design targets 7px outer stroke thickness with a 3.5px light center and a strong two-tone luminance difference.

## Review focus

- Collision flips while height/color/action are unchanged must remove/add bank graphics.
- Height-zero edits, edit removal, active structures, map replacement and shutdown must clean stale markers.
- A blocked dug height-1 cell must use the bank glyph alone; a walkable dug cell must retain the existing scar.
- Retained markers must not rebuild on unrelated edits; no-work frames must not inspect collision or allocate graphics.
- Full real-map counts must come from actual data, including discrepancies in the assignment's neighborhood coordinates.

## 1. Regression contracts (in progress)

- [ ] Add RED tests for bank admission, shape/contrast/scale, walkability changes, scar exclusivity, edit-height changes and cleanup.
- [ ] Add a lightweight real-map scene adapter: 1568 bank markers, no markers on 3947 walkable cells; all adjacent 269 marked; both requested/current spawn neighborhoods covered; idle/changed-false frames do no work.
- [ ] Add compile-time tests for one protocol-derived readonly VoxelEdits contract. Run RED and commit checkpoint.

## 2. Implementation

- [ ] Converge types; cache bank predicate, add pooled syncBanks and cleanup, and make scar admission complementary.
- [ ] Run targeted tests, review new edge cases and run final client checks/build.

## 3. Evidence, gates and handoff

- [ ] Record whole-map/neighborhood counts, actual glyph luminance/geometry metrics and idle/retention evidence.
- [ ] Run full non-bench pytest via uv, Ruff check/format, Pyright, frontend checks/test/build, gen:protocol:check and both byte checks.
- [ ] Verify forbidden paths unchanged, commit implementation/evidence/own recovery section and write ignored talking receipt.

## Initial evidence

- Actual source-map read: banks=1568, cardinal-adjacent to walkable=269. Code's SPAWN_TILE=(100,53), with 135 banks in its inclusive 31×31 neighborhood. The assignment's (14,17) neighborhood contains 57, not 18. Both areas will be checked; no map/spawn edit is authorized or necessary.
- Semantic clarification: an original blocked height-1 bank digs to height 0 and stays blocked (round ten). Clearing a height-2 column to height 1 opens it. Tests will check both height-zero removal and a height-one collision transition without inventing new physics.
