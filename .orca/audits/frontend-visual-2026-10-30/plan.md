# Frontend visual review and layout repair

**Authorization:** User directly requested “检查前端画面，优化一下” after round eleven. Work remains in Codex from `6aa0528`; no main-tree changes or remote push.
**Goal:** Give the game more usable space and keep it visible at narrow widths, preserving the current wood/paper theme and existing simulation/rendering behavior.

## Observed baseline (real browser)

- Approved Chromium executable: `C:/Users/zx198/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe`. Reused linked playwright-core 1.64.1, no dependency installation.
- Isolated backend uses its own `.orca/tmp/frontend-visual-2026-10-30/world.db` and a static real-world preview with the model driver disabled. Only local preview processes/browser contexts are owned by this task.
- 1440×900: canvas 872px wide; 1280×720: 712px; 1024×768: 456px; 390×844: **0px**. Two permanently visible fixed-width sidebars occupy 568px. Screenshot evidence: before-1440.png / before-1280.png / before-1024.png / before-390.png.
- Empty save list takes a whole column. Empty narrative panels stretch into large blank sheets. The impulse bar contains a narrow decorative seal that resembles a broken control.
- Settings has a fixed secondary form column; check and repair its narrow-screen layout too. No credential fields are filled or submitted during inspection.

## Chosen small design

- One 288px sidebar for either journal or saves, selected from clearly labeled toolbar buttons. Journal starts open on desktop (>=900px); compact windows start with the world unobstructed. The sidebar can be collapsed for full-width play.
- Below 900px the open sidebar overlays the world rather than squeezing it; a close button, Escape and outside click dismiss it. Return focus to the toolbar control. Returning from settings also restores its control focus.
- Header controls wrap cleanly. Use dynamic viewport height; keep the world and impulse input within the available area. Remove the decorative input seal, add a meaningful input label and clear keyboard focus indicators.
- Empty journal cards become compact; populated cards retain independent scrolling. Save controls/list are preserved. Settings uses a bounded centered grid and stacks on small screens.
- Keep existing colors, pixel assets, projection, camera, zoom, collision, movement, protocol and all server code unchanged. No new dependencies or model/network calls.

## Work

1. [x] RED: Browser regression for usable canvas width / hidden default save panel, plus SSR contracts for disclosure controls and the labeled impulse input.
2. [x] Implement the responsive shell/sidebar and focused CSS cleanup. Verify sidebar toggles, dismissal/focus, save/settings access and long narrative content in the real browser.
3. [x] Capture desktop and narrow after screenshots; run client tests/typecheck/lint/format/build and protocol drift check. Review scope and close only task-owned preview processes/browser contexts; delivery includes own recovery/handoff.

## Review focus

- Sidebar switches must not remount the canvas or add a second fixed column.
- Entering a narrow breakpoint must not leave an open desktop panel covering the scene.
- All toolbar/form controls must fit; settings may scroll vertically but must not overflow horizontally.
- Save operations and narrative content remain reachable; new UI controls must not send world commands.
- Phaser must resize its canvas after a sidebar change without requiring a window resize.

## Results and evidence

RED checkpoint **bc6739c**: three SSR contracts failed; the actual browser found squeezed game width at all three sizes, a permanent empty save column, missing disclosure controls, and duplicate zero-width mobile canvases. The mobile render produced three `Framebuffer status: Incomplete Attachment` page errors. Baseline metrics are retained in `red-layout.json`.

| Viewport | Before canvas width | After canvas size | Width gain |
|---|---:|---|---:|
| 1440×900 | 872 | 1152×791 | 32.11% |
| 1024×768 | 456 | 736×659 | 61.40% |
| 390×844 | 0 | 390×688 | World visible again |

The browser checks also collapse the desktop sidebar to obtain the full 1440px world width. Switching between journal and saves retains one sidebar and does not add another column. Entering compact mode closes the desktop panel; opening saves on mobile overlays the scene while the canvas stays 390px wide. Long narrative entries scroll independently, with no horizontal overflow. Empty and configured settings layouts fit the mobile viewport; the configured case uses a local response fixture, never real credentials or a model call.

### Canvas resize follow-up

Actual after screenshots exposed a second defect: after header font/wrapping layout settled, the compact canvas remained 390×642 while its parent was 390×688. A dedicated browser assertion reproduced that mismatch (`resize-red.log`). CanvasHost now observes its parent, waits for the game `ready` event, and calls **scale.setParentSize** with nonzero integer dimensions. In Phaser RESIZE mode, `scale.resize` followed by refresh can derive the canvas from an old parentSize and undo the requested size; this was verified against the installed ScaleManager source and the actual game instance. Cleanup disconnects the observer/listener and guards disposed instances. Final canvas/container differences are below one CSS pixel, with exactly one canvas at all tested sizes.

### Verification

- Real approved Chromium: layout checks, panel switching, full-width collapse, Escape/focus return, long narrative scroll, breakpoint collapse, mobile overlay/outside dismissal, and both empty/configured settings passed. Final **page errors 0**; an independent fresh compact reload also recorded **console errors 0**.
- Client full Vitest: **321 passed / 44 files**, final run 1.92s. Existing TopBar status tests keep their original assertions with the new required props supplied.
- TypeScript, ESLint, Prettier and `gen:protocol:check` passed; protocol remains **1.14**.
- Final production build passed in **11.26s**, retaining the existing >500kB bundle warning.
- No changes to sim/**, client/src/game/**, protocol/shared, map/render assets or dependencies. The backend/full asset suites were not repeated for this UI-only change; their source and data remain byte-unchanged from the just-validated baseline.
- Local self-review checked responsive min sizes, selection/focus lifecycle, canvas cleanup, data/credential boundaries, and unchanged save/settings request contracts.

### Artifacts and cleanup

- `acceptance.json`: before/after dimensions, checks, browser path and cleanup record.
- Committed comparison screenshots: `before-1440.png`, `after-1440.png`, `before-390.png`, `after-390.png`.
- Additional local screenshots cover populated journal, mobile save drawer and empty/configured settings; execution logs remain local.
- The helper `verify-layout.cjs` reuses the existing linked Playwright library and the approved Chromium executable. It expects an isolated preview on 5173/8000; no installation is performed.
- All task-owned browser contexts and preview services were closed. Backend/frontend process ownership was checked against the exact workspace/script command lines before stopping them. The temporary world.db stays under this tree's ignored preview directory. User browsers, saves and service processes were untouched.

Final keyboard review added a real browser regression for a composing Escape key on the impulse input. It first reproduced sidebar dismissal/focus loss (`ime-red.log`); the shell now ignores Escape while `isComposing` is true. The final browser run passes that check as well, and the client gates were rerun after this one-line fix. Settings keeps its existing Return action rather than binding Escape to discard a form. README now describes the sidebar controls.

Next: main independently collects the full `6aa0528..codex` UI range and reviews the screenshots. Round eleven's `2ad6606..6aa0528` handoff remains separately documented if it has not yet been collected.
