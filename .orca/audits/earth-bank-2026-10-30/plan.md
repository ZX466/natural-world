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

## 1. Regression contracts (complete)

- [x] Add RED tests for bank admission, shape/contrast/scale, walkability changes, scar exclusivity, edit-height changes and cleanup.
- [x] Add a lightweight real-map scene adapter: 1568 bank markers, no markers on 3947 walkable cells; all adjacent 269 marked; both requested/current spawn neighborhoods covered; idle/changed-false frames do no work.
- [x] Add compile-time tests for one protocol-derived readonly VoxelEdits contract. Run RED and commit checkpoint.

## 2. Implementation

- [x] Converge types; cache bank predicate, add pooled syncBanks and cleanup, and make scar admission complementary.
- [x] Run targeted tests, review new edge cases and run final client checks/build.

## 3. Evidence, gates and handoff

- [x] Record whole-map/neighborhood counts, actual glyph luminance/geometry metrics and idle/retention evidence.
- [x] Run full non-bench pytest via uv, Ruff check/format, Pyright, frontend checks/test/build, gen:protocol:check and both byte checks.
- [x] Verify forbidden paths unchanged; delivery includes implementation/evidence/own recovery section and an ignored talking receipt.

## Initial evidence

- Actual source-map read: banks=1568, cardinal-adjacent to walkable=269. Code's SPAWN_TILE=(100,53), with 135 banks in its inclusive 31×31 neighborhood. The assignment's (14,17) neighborhood contains 57, not 18. Both areas will be checked; no map/spawn edit is authorized or necessary.
- Semantic clarification: an original blocked height-1 bank digs to height 0 and stays blocked (round ten). Clearing a height-2 column to height 1 opens it. Tests will check both height-zero removal and a height-one collision transition without inventing new physics.

## Verification evidence

- RED **46ce58e**: seven behavior tests failed / one type-only test passed at runtime (`red.log`); TypeScript independently failed on both type equality assertions (`type-red.log`). The real-map failure began at a genuine bank (32,0), not a synthetic color mismatch.
- GREEN: all 55 focused tests passed (new bank tests plus all existing terrain/geometry tests). Final full client suite **318 passed / 43 files**, 2.23s (`client.log`). Typecheck, ESLint and Prettier also passed.
- Two production files changed. VoxelEdits is one protocol-derived readonly map of `height` and `action`; terrain consumes that exact alias. Scar eligibility is computed from the same cached surface as bank eligibility, eliminating the former divergent read paths. No mutation of map.collision, heights or edits occurs in the renderer.

### Real-map admission and lifecycle

The permanent regression reads the checked-in 140×100 map chunks and height JSON into a lightweight draw-command adapter, then executes the actual IsoTerrain methods. It asserts the glyph's presence at every projected height-1 cell, including absence on every walkable cell. The adapter records real fill/color/anchor/depth commands; it does not rasterize or open a browser.

| Population | Actual count | Covered |
|---|---:|---:|
| Blocked height-1 banks | 1568 | 1568 |
| Walkable cells | 3947 | 0 bank glyphs |
| Banks cardinal-adjacent to walking cells | 269 | 269 |
| Assignment center (14,17), inclusive 31×31 | 57 | 57 |
| Actual SPAWN_TILE (100,53), inclusive 31×31 | 135 | 135 |

The assignment's 18-cell count and (14,17) spawn label do not match these checked-in sources. Both regions are covered rather than changing source data to fit the task text. Asset hashes, the coordinate definition and counters are in `acceptance.json`.

- Three opaque dark/light slats are entirely inside the top diamond, anchored at its center with depthKey+0.5. The existing scar remains a single 0x3f3020 diamond at alpha 0.55. A cell cannot receive both glyphs.
- A collision-only 0→1 flip at unchanged height/color destroys the bank marker; a later 1→0 flip creates it again. Digging an original bank to height 0 removes the marker while collision stays 0. Empty edit snapshots restore it; active structures, map resizing/replacement, null maps and shutdown clean stale markers.
- Retained glyph geometry is drawn once per coordinate. An unrelated terrain edit reuses its object and geometry; a new version with identical surfaces does not even move it. In 120 version-stable frames the full real-map case records **zero collision reads, allocations, redraws or position updates**. No FPS/GPU performance claim is made.

### Contrast and zoom evidence

The actual draw commands choose dark **#2c1b10** and light **#f1d793**, with opacity 1. The recorded luminances using `Y = 0.2126R + 0.7152G + 0.0722B` (0..255) are **29.820** and **215.618**, a **185.798** difference. Every stroke is 2 world pixels thick with a 1-pixel light center; at the unchanged camera zoom 3.5 these become **7px / 3.5px**. This is analytic geometry at the configured zoom, not a screenshot observation.

The read-only PNG analysis samples each of the 1568 original bank tiles using the renderer's central 4×4 average (per-channel floor). Background Y ranges **51.400..190.7532**, mean **121.9507**. On every tile at least one opaque face differs from the background by **92.905** or more (mean **111.1801**), exceeding the requested 15 threshold; zero tiles fail. These are source-pixel statistics and paired-face contrast, not a whole-tile recolor or human visual acceptance. No assets were regenerated.

### Local review

- Collision enters only the bank/scar presentation predicates and marker invalidation; the existing ground paint, height projection, movement picking and camera behavior are preserved.
- Bank pooling and cleanup cover both true→false predicates and map-origin changes. Scars retain their original ink, opacity and geometry; all legacy tests pass.
- Shared/protocol, sim/**, terrain classification, map/height/PNG assets and dependencies remain unchanged. No network calls, secrets, browser, external agent messages or package/venv deletion occurred.
- Next handoff remains main's independent review and human gameplay appearance check.

## Final gates (executed locally)

| Gate | Result | Evidence |
|---|---|---|
| `uv run pytest -m "not bench" -q` | **2996 passed, 121 skipped, 72 deselected, 4 existing deprecation warnings; 366.30s; exit 0** | `pytest.log` |
| Ruff check / format check | Passed, 366 files already formatted | Tool output |
| Pyright | 0 errors / 0 warnings / 0 information | Tool output |
| Client typecheck / ESLint / Prettier | Passed | Tool output |
| Full client Vitest | **318 passed / 43 files**, 2.23s; all 29 legacy terrain tests pass | `client.log` |
| Client production build | Passed, 13.38s; existing >500kB chunk warning | `build.log` |
| `gen:protocol:check` | Passed; protocol 1.14 unchanged | `protocol.log` |
| Height-map `--check` | Byte-identical JSON/PNG; unchanged 1112/5515/4379/2994 counts | `height-check.log` |
| Block-atlas `--check` | Byte-identical PNG/JSON, 12 frames | `atlas-check.log` |
| Diff/scope | `git diff --check` clean; no sim/shared/assets/dependency/camera/input mutations | Local diff |

The permanent test is `client/src/game/render/__tests__/iso-banks.test.ts` (run from client via `npm run test -- src/game/render/__tests__/iso-banks.test.ts`). `acceptance.json` is committed alongside this plan; execution logs stay local. No browser, screenshot, GPU benchmark or human visual check was performed, as required by the workflow. Main should collect the complete `2ad6606..codex` range (RED `46ce58e` plus implementation), independently review the markers and perform human appearance acceptance.
