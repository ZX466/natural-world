# Movement input implementation plan

> Inline execution with TDD; keep the existing Codex worktree and talking-only handoff. No browser automation or new dependency.

Goal: remove the walkable long-press dead zone; add throttled drag movement and eight-direction WASD/arrows; clear goal markers on arrival/replacement/cancel; show local diegetic feedback for blocked, disconnected or unreachable targets.

Spec: `.orca/talking.txt`, ninth-round movement-input assignment. Baseline safely fast-forwarded to 0aa5d00 after backing up the inbox; client baseline 259/259 passed.

Architecture: runtime owns a local collision BFS (same eight-neighbor/no-corner-cut topology as sim), connection guard and existing HUD feedback slot. The existing scene-to-runtime move event gains a local result callback so a rejected request cannot create a false goal marker. Wire format and protocol 1.13 stay unchanged. Scene pointer input reuses visible-cell picking for both movement and editing, avoiding different targets for a short/long press at the same screen point; projection and height helpers remain untouched.

Input decisions: walkable pointerdown issues its move immediately; blocked cells retain the 150ms dig hold and right-click place. Drag keeps the latest target, at least 100ms between updates, and waits for position progress before replacing an active route (otherwise the server's start-inclusive path is repeatedly reset). Final release may flush one last target. Keyboard uses logical-grid eight directions, deduplicates unchanged origin/direction, and on key release/Escape/blur sends a normal move_request to the current tile to cancel a pending path. Text-entry focus never captures movement keys.

Global constraints: sim/** zero changes; no protocol edits; INTERP_MS=200, camera, effectiveHeight, NPC movement, tick/clock/path semantics and terrain assets unchanged. Test evidence is headless/fake-clock client timing plus the real deterministic server movement loop; no browser/network latency is claimed.

## Tasks

- [x] 0. Backup talking, fetch/ff main, check inbox untracked; baseline client green.
- [ ] 1. RED: runtime honesty/reachability/no-corner, local result bridge, pointer long press/drag, keyboard focus/release/diagonal, goal cleanup.
- [ ] 2. GREEN: minimal client reachability helper, runtime/bridge, scene movement lifecycle and input handlers; preserve dig/place tests.
- [ ] 3. Measure first-step/click latency and drag sends/sec; run all assigned gates plus client build and asset byte checks.
- [ ] 4. Review scope/lifecycle edge cases, local commits, update own memory section and talking receipt.

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
