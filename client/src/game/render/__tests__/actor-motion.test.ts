import { expect, it } from 'vitest';
import { CHENMO_SHEET, walkFrameFor } from '../actors';
import {
  advanceMotion,
  cameraFacing,
  replayDelayMs,
  TILE_CADENCE_MS_1X,
  type MotionTarget,
} from '../actor-motion';

const FRAME = 1000 / 60;
const NOMINAL_STEP = FRAME / TILE_CADENCE_MS_1X; // 每渲染帧应走的格数（1x）

it.each([4, 16])(
  'counts a whole displayed step after idle at %sx and sparse render frames',
  (speed) => {
    const target = { x: 0, y: 0, height: 1, cadenceMs: 500 };
    let state = advanceMotion(undefined, target, 0, 200, speed);
    state = advanceMotion(state, { ...target, x: 2 }, 1000, 200, speed);
    state = advanceMotion(state, { ...target, x: 2 }, 1200, 200, speed);
    expect(state.x).toBe(2);
    expect(state.animClock).toBeCloseTo(2 * TILE_CADENCE_MS_1X);
    state = advanceMotion(state, { ...target, x: 2 }, 1400, 200, speed);
    expect(state.animClock).toBe(-1);
    state = advanceMotion(state, { ...target, x: 3 }, 1600, 200, speed);
    state = advanceMotion(state, { ...target, x: 3 }, 1800, 200, speed);
    expect(state.x).toBe(3);
    expect(state.animClock).toBeCloseTo(TILE_CADENCE_MS_1X);
  },
);

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

it.each([
  [1, 500, 533],
  [4, 500, 158],
  [16, 500, 64.25],
  [1, 250, 283],
  [4, 250, 95.5],
  [16, 250, 48.625],
])('uses %ix speed and %ims cadence for a %ims replay delay', (speed, cadence, delay) => {
  expect(replayDelayMs(speed, cadence)).toBe(delay);
});

it('advances the leg clock by all displayed distance from the first walking frame', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 1);
  state = advanceMotion(state, { x: 1, y: 0, height: 1 }, 250, FRAME, 1);
  const firstStep = advanceMotion(state, { x: 1, y: 0, height: 1 }, 400, FRAME, 1);
  expect(firstStep.x).toBeGreaterThan(0);
  expect(firstStep.animClock).toBeCloseTo((firstStep.x - state.x) * 250);
  const nextStep = advanceMotion(firstStep, { x: 1, y: 0, height: 1 }, 500, 100, 1);
  expect(nextStep.animClock - firstStep.animClock).toBeCloseTo((nextStep.x - firstStep.x) * 250);
});

it('uses the supplied inverse-projection distance for stride and teleport classification', () => {
  const distanceInTiles: NonNullable<MotionTarget['distanceInTiles']> = (from, to) => {
    const dx = (to.x - from.x) / 16;
    const dy = (to.y - from.y + 12 * (to.z - from.z)) / 8;
    return Math.hypot((dx + dy) / 2, (dy - dx) / 2);
  };
  let state = advanceMotion(
    undefined,
    { x: 0, y: -12, height: 1, distanceInTiles },
    0,
    FRAME,
    1,
    16,
  );
  state = advanceMotion(state, { x: 0, y: -120, height: 10, distanceInTiles }, 250, FRAME, 1, 16);
  expect(state.samples).toHaveLength(2);
  state = advanceMotion(state, { x: 0, y: -120, height: 10, distanceInTiles }, 600, FRAME, 1, 16);
  expect(state.animClock).toBe(-1);
  state = advanceMotion(state, { x: 16, y: -112, height: 10, distanceInTiles }, 850, FRAME, 1, 16);
  const first = advanceMotion(
    state,
    { x: 16, y: -112, height: 10, distanceInTiles },
    950,
    FRAME,
    1,
    16,
  );
  const next = advanceMotion(
    first,
    { x: 16, y: -112, height: 10, distanceInTiles },
    1050,
    100,
    1,
    16,
  );
  expect(next.animClock - first.animClock).toBeCloseTo(((next.x - first.x) / 16) * 250);
});

it('buffers legal four-tile sample batches at 16x while still snapping large resets', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 16);
  state = advanceMotion(state, { x: 4, y: 0, height: 1 }, 62.5, FRAME, 16);
  expect(state.samples).toHaveLength(2);
  expect(state.x).toBeLessThan(4);
  state = advanceMotion(state, { x: 4, y: 0, height: 1 }, 62.5 + FRAME, FRAME, 16);
  expect(state.x).toBeGreaterThan(0);
  expect(state.x).toBeLessThan(4);
  const reset = advanceMotion(state, { x: 1000, y: 0, height: 1 }, 125, FRAME, 16);
  expect(reset.samples).toHaveLength(1);
  expect(reset.x).toBe(1000);
  expect(reset.animClock).toBe(-1);
  const slow = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 1);
  expect(advanceMotion(slow, { x: 4, y: 0, height: 1 }, 250, FRAME, 1).x).toBe(4);
});

const jump: NonNullable<MotionTarget['flight']> = {
  id: 'jump-1',
  progress: 0,
  start: { x: 0, y: 0, z: 1 },
  end: { x: 2, y: 0, z: 3 },
  arc: { x: 0, y: 0, z: 1 },
  active: true,
  durationMs: 600,
};

it('replays a dense 600ms flight through the full 533ms walk delay with idle legs', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1, cadenceMs: 500 }, 0, 10, 1);
  for (let time = 10; time <= 2200; time += 10) {
    const elapsed = Math.max(0, Math.min(600, Math.floor((time - 1000) / 20) * 20));
    const progress = elapsed / 600;
    const flight = time >= 1000 ? { ...jump, progress, active: progress < 1 } : undefined;
    state = advanceMotion(
      state,
      {
        x: progress === 1 ? 2 : 0,
        y: 0,
        height: progress === 1 ? 3 : 1,
        cadenceMs: 500,
        ...(flight ? { flight } : {}),
      },
      time,
      10,
      1,
    );
    const shownProgress = Math.max(0, Math.min(1, (time - 533 - 1000) / 600));
    expect(state.x).toBeCloseTo(2 * shownProgress, 8);
    expect(state.height).toBeCloseTo(
      1 + 2 * shownProgress + 4 * shownProgress * (1 - shownProgress),
      8,
    );
    if (shownProgress > 0 && shownProgress < 1) expect(state.animClock).toBe(-1);
    expect(state.samples.length).toBeLessThanOrEqual(128);
    if (time === 1600) expect(state.samples.length).toBeGreaterThan(8);
  }
  expect(state.x).toBe(2);
  expect(state.height).toBe(3);
});

it('reconstructs an entirely completed fast flight once from its certified endpoints', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1, cadenceMs: 500 }, 0, FRAME, 16);
  const target = {
    x: 2,
    y: 0,
    height: 3,
    cadenceMs: 500,
    flight: { ...jump, active: false, progress: 1 },
  };
  state = advanceMotion(state, target, 100, FRAME, 16);
  expect(state.samples.some((sample) => sample.flight?.progress === 0 && sample.at === 62.5)).toBe(
    true,
  );
  state = advanceMotion(state, target, 150, 50, 16);
  expect(state.x).toBeCloseTo(1.24);
  expect(state.height).toBeCloseTo(3.1824);
  expect(state.animClock).toBe(-1);
  state = advanceMotion(state, target, 200, 50, 16);
  expect(state.x).toBe(2);
  expect(state.height).toBe(3);
});

it.each([4, 16])(
  'replays a %ix flight that only delivered its launch and landing samples',
  (speed) => {
    let state = advanceMotion(
      undefined,
      { x: 0, y: 0, height: 1, cadenceMs: 500 },
      0,
      FRAME,
      speed,
    );
    state = advanceMotion(
      state,
      { x: 0, y: 0, height: 1, cadenceMs: 500, flight: jump },
      1000,
      FRAME,
      speed,
    );
    const duration = 600 / speed;
    const target = {
      x: 2,
      y: 0,
      height: 3,
      cadenceMs: 500,
      flight: { ...jump, progress: 1, active: false },
    };
    state = advanceMotion(state, target, 1000 + duration, FRAME, speed);
    const middle = 1000 + replayDelayMs(speed, 500) + duration / 2;
    state = advanceMotion(state, target, middle, FRAME, speed);
    expect(state.x).toBeCloseTo(1);
    expect(state.height).toBeCloseTo(3);
    expect(state.airborne).toBe(true);
    expect(state.animClock).toBe(-1);
    state = advanceMotion(state, target, middle + duration, FRAME, speed);
    expect(state.x).toBe(2);
    expect(state.height).toBe(3);
    expect(state.airborne).toBe(false);
  },
);

it('keeps the displayed path monotone while switching walk/run cadences and world speeds', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1, cadenceMs: 500 }, 0, FRAME, 1);
  let distance = 0;
  for (let frame = 1; frame <= 600; frame++) {
    const now = frame * FRAME;
    const speed = now < 3000 ? 1 : now < 5000 ? 16 : now < 7000 ? 4 : 1;
    const cadenceMs = now < 3000 || (now >= 5000 && now < 7000) ? 500 : 250;
    distance += (FRAME * speed) / cadenceMs;
    const next = advanceMotion(
      state,
      { x: Math.floor(distance), y: 0, height: 1, cadenceMs },
      now,
      FRAME,
      speed,
    );
    expect(next.x).toBeGreaterThanOrEqual(state.x);
    state = next;
  }
});

it('initializes a fresh view at its current pose without replaying persisted completed metadata', () => {
  const state = advanceMotion(
    undefined,
    { x: 10, y: 4, height: 1, flight: { ...jump, active: false, progress: 1 } },
    10000,
    FRAME,
    1,
  );
  expect({ x: state.x, y: state.y, height: state.height }).toEqual({ x: 10, y: 4, height: 1 });
  expect(state.samples).toEqual([{ at: 10000, x: 10, y: 4, z: 1 }]);
});

it('does not clamp later walking to the endpoint of persisted completed flight metadata', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1, cadenceMs: 500 }, 0, FRAME, 1);
  const completed = { ...jump, active: false, progress: 1 };
  state = advanceMotion(
    state,
    { x: 2, y: 0, height: 3, cadenceMs: 500, flight: completed },
    600,
    FRAME,
    1,
  );
  for (let time = 620; time <= 2200; time += 20)
    state = advanceMotion(
      state,
      { x: time < 1500 ? 2 : 3, y: 0, height: 3, cadenceMs: 500, flight: completed },
      time,
      20,
      1,
    );
  expect(state.x).toBe(3);
  expect(state.height).toBe(3);
  expect(state.samples.at(-1)?.flight).toBeUndefined();
});

it('holds paused flight progress indefinitely and only advances after a newer received phase', () => {
  let state = advanceMotion(undefined, { x: 0, y: 0, height: 1 }, 0, FRAME, 1);
  const paused = { x: 0, y: 0, height: 1, flight: { ...jump, progress: 0.5 } };
  state = advanceMotion(state, paused, 300, FRAME, 1);
  state = advanceMotion(state, paused, 2000, FRAME, 0);
  expect({ x: state.x, y: state.y, height: state.height }).toEqual({ x: 1, y: 0, height: 3 });
  expect(state.animClock).toBe(-1);
  const resumed = { ...paused, flight: { ...jump, progress: 0.75 } };
  state = advanceMotion(state, resumed, 2300, FRAME, 1);
  state = advanceMotion(state, resumed, 5000, FRAME, 0);
  expect(state.x).toBe(1.5);
  expect(state.height).toBe(3.25);
  expect(state.animClock).toBe(-1);
});
