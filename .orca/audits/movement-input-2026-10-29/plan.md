# Movement input implementation plan

> Inline execution with TDD; keep the existing Codex worktree and talking-only handoff. No browser automation or new dependency.

Goal: remove the walkable long-press dead zone; add throttled drag movement and eight-direction WASD/arrows; clear goal markers on arrival/replacement/cancel; show local diegetic feedback for blocked, disconnected or unreachable targets.

Spec: `.orca/talking.txt`, ninth-round movement-input assignment. Baseline safely fast-forwarded to 0aa5d00 after backing up the inbox; client baseline 259/259 passed.

Architecture: runtime owns a local collision BFS (same eight-neighbor/no-corner-cut topology as sim), connection guard and existing HUD feedback slot. The existing scene-to-runtime move event gains a local result callback so a rejected request cannot create a false goal marker. Wire format and protocol 1.13 stay unchanged. Scene pointer input reuses visible-cell picking for both movement and editing, avoiding different targets for a short/long press at the same screen point; projection and height helpers remain untouched.

Input decisions: walkable pointerdown issues its move immediately; blocked cells retain the 150ms dig hold and right-click place. Drag keeps the latest target, at least 100ms between updates, and waits for position progress before replacing an active route (otherwise the server's start-inclusive path is repeatedly reset). Final release may flush one last target. Keyboard uses logical-grid eight directions, deduplicates unchanged origin/direction, and on key release/Escape/blur sends a normal move_request to the current tile to cancel a pending path. Text-entry focus never captures movement keys.

Global constraints: sim/** zero changes; no protocol edits; INTERP_MS=200, camera, effectiveHeight, NPC movement, tick/clock/path semantics and terrain assets unchanged. Test evidence is headless/fake-clock client timing plus the real deterministic server movement loop; no browser/network latency is claimed.

## Tasks

- [x] 0. Backup talking, fetch/ff main, check inbox untracked; baseline client green.
- [x] 1. RED: runtime honesty/reachability/no-corner, local result bridge, pointer long press/drag, keyboard focus/release/diagonal, goal cleanup.
- [x] 2. GREEN: minimal client reachability helper, runtime/bridge, scene movement lifecycle and input handlers; preserve dig/place tests.
- [x] 3. Measure first-step/click latency and drag sends/sec; run all assigned gates plus client build and asset byte checks.
- [x] 4. Review scope/lifecycle edge cases, commit with the implementation/recovery record, write the resulting commit in the local talking receipt.

## Review focus

1. Opposite keys, repeats, focus entering a text box, blur and shutdown cannot leave held input running.
2. Diagonal keyboard input checks both orthogonal cells before any move request.
3. Same-array collision edits / map replacement cannot leave a stale reachability result.
4. Drag retargets do not continuously reset the server's path before its first moving step.
5. Reset/reconnect/branch changes drop local gesture/marker state; no stale input targets the new world.

## Ledger

- Baseline 0aa5d00 (contains 37e6a51 terrain changes), clean branch; talking preserved and not tracked.
- Existing contract verified: Pathfinder.find(start,start) returns (start,), issue_move replaces the path, so existing move_request cancels without a new message. _apply_move retains the path's first point; headless latency measurements must count its consumption, not only the 0..14 phase offset.
- Pointer targeting intentionally shares the visible-cell picker already used for dig/place; no render/picking algorithm or geometry constant is changed. Tests using a ground-plane click will be expressed at the intended visible surface when necessary.
- Existing voxelError HUD slot is reused for local movement feedback; no new prompt/impulse or UI panel/state slot.
- RED checkpoint f74f4af: 15 intended failures / 8 passes in the input/runtime/bridge targets.
- Focus/release, snapshot-dig suppression, placement cancellation and offline-drag cleanup each observed their own failing regression before fixes. Existing presentation mocks were completed with the new event bridge and game lifecycle; no rendering behavior was changed to accommodate mocks.
- Client full suite was GREEN at 284 tests before the timing/offline-regression additions; final counts will be recorded after rerunning it. Typecheck/lint/format checks already passed on the implementation.

## Measurement evidence

- Client fake-clock probe: keydown and walkable pointerdown dispatch in the same handler (0ms virtual delay). 124 pointermove events over 1000ms with a 4Hz authoritative-position fixture admit 4 movement requests, plus one final release request; no progress admits only the initial request until release.
- Real server probe server_timing.py: all 15 starting tick phases, 60tps, zero transport/browser delay. Chenmo phase=4; first changed position after 16..30 ticks = 266.667..500.000ms for both a fresh keyboard neighbor and a fresh click request. This includes consumption of the path's starting cell, which the task's phase-only 0..14-tick estimate omitted. Full path motion after startup remains 4 tiles/s; no phase, path or clock semantics were changed.
- Existing move_request to the current position was exercised before the first step and prevented later displacement. Real network RTT and an already-arriving server step are not included; this is not a browser latency claim.
- Review verified the installed Phaser KeyboardManager synchronously emits MANAGER_PROCESS from its native DOM listener, so preventDefault in the keyboard plugin callback is timely; no global capture is added that would swallow text-field arrow keys.
- An additional native probe of successive neighbor commands measures 2 tiles/s after startup, versus 4 tiles/s for an already-issued long straight route. Each new neighbor request retains its starting point and consumes another movement phase. This is explicitly reported; improving it by altering server path/phase semantics is outside this client-only assignment.

## Final review and verification

Focus entering text fields on keyup, snapshot replacement during a dig, offline drag reconnection, first-frame gesture retention, and unrelated terrain invalidation of an active keyboard goal all have regression tests observed RED before fixes. Blur/shutdown are tested through actual event emitters, including listener/timer cleanup. BFS reads the current collision data each request, and diagonal keyboard preflight forbids detours through a blocked corner. Local bridge callbacks report admission only, not a server acknowledgement.

| Gate | Fresh result |
|---|---|
| Full `uv run pytest -m "not bench"` | 2985 passed, 121 skipped, 72 deselected, 4 deprecation warnings; 371.81s |
| Ruff check / format | Passed; 365 files formatted |
| Pyright | 0 errors, 0 warnings |
| Height-map / block-atlas --check | Both byte-identical JSON/PNG |
| gen:protocol:check | EXIT 0; protocol remains 1.13 |
| Client typecheck / lint / format | Passed on final input implementation |
| Client tests | 290 passed / 40 files; 1.84s |
| Client production build | Passed; 11.56s; existing >500kB chunk warning |
| Protected scope | sim/**, shared/**, renderer/**, terrain assets and npm dependencies unchanged; camera body byte-identical and INTERP_MS=200 |

No browser/network latency, physical input-to-render latency or coverage percentage is claimed. A transport-delayed step already committed by the server cannot be undone by the client. Existing visual interpolation, step cadence and server silence for unreachable paths remain unchanged.

Local review complete with no remaining critical/important findings. Keep the codex worktree and local commits; independent integration review/manual input feel acceptance belong to the main tree. No remote push or direct agent messaging.
