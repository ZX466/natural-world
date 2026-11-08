import { expect, it } from 'vitest';
import { CHENMO_SHEET, walkFrameFor } from '../actors';
import { advanceMotion, cameraFacing, replayDelayMs, TILE_CADENCE_MS_1X } from '../actor-motion';

const FRAME = 1000 / 60;
const NOMINAL_STEP = FRAME / TILE_CADENCE_MS_1X; // 每渲染帧应走的格数（1x）

/**
 * Feeds the authoritative target the way the server does: one tile every
 * `TILE_CADENCE_MS_1X` (60 tick/s ÷ 15 tick/tile at 1x). Returns the rendered
 * position, walk clock and sheet frame of every frame.
 */
function walkRun({ frames = 600, speed = 1, jitterMs = 0 } = {}) {
  const cadence = TILE_CADENCE_MS_1X / speed;
  let seed = 12345;
  const jitter = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return (seed / 0x7fffffff - 0.5) * 2 * jitterMs;
  };
  const arrivals: number[] = [];
  for (let t = cadence; arrivals.length < frames; t += cadence)
    arrivals.push(Math.max(0, Math.round(t + jitter())));
  let target = 0;
  let nextArrival = 0;
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, speed);
  const rows = [{ x: state.x, clock: state.animClock }];
  for (let i = 1; i <= frames; i++) {
    const now = i * FRAME;
    while (nextArrival < arrivals.length && arrivals[nextArrival]! <= now) {
      nextArrival += 1;
      target = nextArrival;
    }
    state = advanceMotion(state, { x: target, y: 0, height: 1 }, now, FRAME, speed);
    rows.push({ x: state.x, clock: state.animClock });
  }
  return { rows, cadence };
}

/** Frames after the replay delay has filled; before that the renderer is
 *  legitimately still showing the spawn position. */
const warmup = (speed = 1) => Math.ceil(replayDelayMs(speed) / FRAME) + 2;

it('draws the replay delay behind the authoritative position', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 1);
  expect(state.x).toBe(0);
  // The authoritative move to x=1 arrives at t=250. The renderer shows an
  // instant `replayDelayMs(1)` in the past, so nothing has moved yet.
  state = advanceMotion(state, { x: 1, y: 0, height: 1 }, 250, FRAME, 1);
  expect(state.x).toBe(0);
  // It glides across the tile rather than jumping, and is part-way at the
  // halfway point of the delay.
  const halfAt = 250 + replayDelayMs(1) / 2;
  state = advanceMotion(state, { x: 1, y: 0, height: 1 }, halfAt, FRAME, 1);
  expect(state.x).toBeGreaterThan(0);
  expect(state.x).toBeLessThan(1);
  expect(state.facing).toBe('e');
  // And the step is complete once the delay has elapsed.
  state = advanceMotion(state, { x: 1, y: 0, height: 1 }, 250 + replayDelayMs(1), FRAME, 1);
  expect(state.x).toBe(1);
  expect(state.facing).toBe('e');
});

it('never freezes and never overspeeds while an actor walks continuously', () => {
  const { rows } = walkRun();
  const warm = warmup();
  const steps = rows.slice(1).map((row, i) => row.x - rows[i]!.x);
  const settled = steps.slice(warm);
  const frozen = settled.filter((step) => Math.abs(step) < 1e-9).length;
  expect(frozen).toBe(0);
  const peak = Math.max(...settled.map(Math.abs));
  expect(peak).toBeLessThanOrEqual(NOMINAL_STEP * 1.05);
  const travelled = rows[rows.length - 1]!.x - rows[warm]!.x;
  const elapsed = (rows.length - 1 - warm) * FRAME;
  expect(travelled / elapsed).toBeCloseTo(1 / TILE_CADENCE_MS_1X, 3);
});

it('keeps the walk cycle running instead of restarting it at every tile', () => {
  const { rows } = walkRun();
  const settled = rows.slice(warmup(), -1);
  // No frame falls back to the stand frame while the actor keeps walking.
  expect(settled.filter((row) => row.clock < 0)).toHaveLength(0);
  // And the cycle actually reaches every frame of the row, not just two.
  const frames = new Set(settled.map((row) => walkFrameFor(CHENMO_SHEET, 2, row.clock)));
  expect(frames.size).toBe(CHENMO_SHEET.framesPerRow);
});

it('keeps walking smooth when samples arrive with jitter', () => {
  const { rows } = walkRun({ jitterMs: 16 });
  const settled = rows.slice(warmup());
  const steps = settled.slice(1).map((row, i) => row.x - settled[i]!.x);
  expect(steps.filter((step) => Math.abs(step) < 1e-9)).toHaveLength(0);
  expect(Math.max(...steps.map(Math.abs))).toBeLessThanOrEqual(NOMINAL_STEP * 1.1);
});

it('keeps the sample history bounded even at 16x', () => {
  // 16x 下服务端每秒发 ~64 个样本。按固定 3 秒保留会让每个 actor 的队列涨到
  // ~190 项，而每帧都要整体复制（×51 人）。回放时刻只落后一个延迟，更老的
  // 样本永远不可能夹住它，所以只留几格即可。
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 0 }, 0, FRAME, 16);
  for (let i = 1; i < 2000; i++) {
    const now = i * FRAME;
    state = advanceMotion(state, { x: i * 0.26, y: 0, height: 0 }, now, FRAME, 16);
  }
  expect(state.samples.length).toBeLessThanOrEqual(8);
});

it('scales the teleport threshold by the caller units so pixel steps stay ordinary moves', () => {
  // Phaser feeds screen pixels: one tile is 16px, so a 16px step must not be
  // mistaken for a teleport (which would freeze the sprite on every tile).
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 1, 16);
  state = advanceMotion(state, { x: 16, y: 0, height: 1 }, 250, FRAME, 1, 16);
  expect(state.samples).toHaveLength(2);
  expect(state.x).toBe(0);
  const halfAt = 250 + replayDelayMs(1) / 2;
  const half = advanceMotion(state, { x: 16, y: 0, height: 1 }, halfAt, FRAME, 1, 16);
  expect(half.x).toBeGreaterThan(0);
  expect(half.x).toBeLessThan(16);
  // A 12-tile jump is still a teleport even in pixel units.
  const jumped = advanceMotion(state, { x: 16 * 13, y: 0, height: 1 }, 500, FRAME, 1, 16);
  expect(jumped.samples).toHaveLength(1);
  expect(jumped.x).toBe(208);
});

it('snaps on a teleport and drops the stale history', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 1);
  state = advanceMotion(state, { x: 1, y: 0, height: 1 }, 100, FRAME, 1);
  const jumped = advanceMotion(state, { x: 12, y: 0, height: 1 }, 200, FRAME, 1);
  expect(jumped.x).toBe(12);
  expect(jumped.samples).toHaveLength(1);
  expect(jumped.animClock).toBe(-1);
});

it('keeps the actor standing still when the authoritative target stops moving', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 1);
  for (let i = 1; i <= 60; i++)
    state = advanceMotion(state, { x: 0, y: 0, height: 1 }, i * FRAME, FRAME, 1);
  expect(state.x).toBe(0);
  expect(state.animClock).toBe(-1);
});

it('does not pop when an actor resumes after standing still', () => {
  // 子代理在旧实现上抓到的缺陷：停顿 10 秒后第一步会把整格压缩进一两帧。
  // 现在到达前会补一个锚点样本，段长恒为一个延迟。
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 1);
  const xs: number[] = [];
  const cadence = TILE_CADENCE_MS_1X;
  for (let i = 1; i < 900; i++) {
    const now = i * FRAME;
    const target = now < 10000 ? 0 : Math.floor((now - 10000) / cadence) + 1;
    state = advanceMotion(state, { x: target, y: 0, height: 1 }, now, FRAME, 1);
    xs.push(state.x);
  }
  const steps = xs.slice(1).map((x, i) => x - xs[i]!);
  expect(Math.max(...steps.map(Math.abs))).toBeLessThanOrEqual(NOMINAL_STEP * 1.05);
});

it('never moves the actor backwards when the world slows down', () => {
  // 旧实现（按时间回放）在 16x→1x 时会把人物往回拽两格：250ms 在 16x 是十六格，
  // 在 1x 只有一格。延迟现在平滑爬升，绘制的时刻只会前进。
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 0 }, 0, FRAME, 16);
  let target = 0;
  let next = TILE_CADENCE_MS_1X / 16;
  const xs: number[] = [];
  for (let i = 1; i < 1200; i++) {
    const now = i * FRAME;
    const speed = now > 5000 ? 1 : 16;
    const cadence = TILE_CADENCE_MS_1X / speed;
    while (now >= next) {
      target += 1;
      next += cadence;
    }
    state = advanceMotion(state, { x: target, y: 0, height: 0 }, now, FRAME, speed);
    xs.push(state.x);
  }
  const steps = xs.slice(1).map((x, i) => x - xs[i]!);
  expect(Math.min(...steps)).toBeGreaterThanOrEqual(0);
  // And it still ends up where the server says it is.
  expect(xs[xs.length - 1]!).toBeCloseTo(target, 0);
});

it.each([
  ['s', 0, 's'],
  ['n', 0, 'n'],
  ['e', 0, 'e'],
  ['s', 180, 'n'],
  ['n', 180, 's'],
  ['e', 90, 's'],
] as const)('selects the camera-relative %s frame at yaw %i', (facing, yaw, expected) => {
  expect(cameraFacing(facing, yaw)).toBe(expected);
});
