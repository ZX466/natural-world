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

1. [ ] RED: Browser regression for usable canvas width / hidden default save panel, plus SSR contracts for disclosure controls and the labeled impulse input.
2. [ ] Implement the responsive shell/sidebar and focused CSS cleanup. Verify sidebar toggles, dismissal/focus, save/settings access and long narrative content in the real browser.
3. [ ] Capture desktop and narrow after screenshots; run client tests/typecheck/lint/format/build and protocol drift check. Review scope, commit own recovery/handoff, and close only task-owned preview processes/browser contexts.

## Review focus

- Sidebar switches must not remount the canvas or add a second fixed column.
- Entering a narrow breakpoint must not leave an open desktop panel covering the scene.
- All toolbar/form controls must fit; settings may scroll vertically but must not overflow horizontally.
- Save operations and narrative content remain reachable; new UI controls must not send world commands.
- Phaser must resize its canvas after a sidebar change without requiring a window resize.
