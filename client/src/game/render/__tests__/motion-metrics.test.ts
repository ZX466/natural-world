import { expect, it } from 'vitest';
import { CHENMO_SHEET, walkFrameFor } from '../actors';
import {
  advanceMotion,
  replayDelayMs,
  TILE_CADENCE_MS_1X,
  type ActorMotion,
} from '../actor-motion';

const FRAME = 1000 / 60;

/**
 * 复现真实链路：服务端每 250ms（1x）推进一格，渲染 60fps。
 * 返回每帧的渲染位置、动画钟与图集帧号，供下面的指标断言使用。
 */
function simulate(speed: number, seconds = 12) {
  const cadence = TILE_CADENCE_MS_1X / speed;
  const frames = Math.floor((seconds * 1000) / FRAME);
  let target = 0;
  let nextArrival = cadence;
  let state: ActorMotion | undefined;
  const rows: { x: number; clock: number; frame: number }[] = [];
  for (let i = 0; i < frames; i++) {
    const now = i * FRAME;
    while (now >= nextArrival) {
      target += 1;
      nextArrival += cadence;
    }
    state = advanceMotion(state, { x: target, y: 0, height: 0 }, now, FRAME, speed, 1);
    rows.push({
      x: state.x,
      clock: state.animClock,
      frame: walkFrameFor(CHENMO_SHEET, 2, state.animClock),
    });
  }
  return { rows, cadence };
}

/** 指标口径：整段统计，不排除零位移帧（排除会掩盖空等）。 */
function metrics(speed: number) {
  const { rows, cadence } = simulate(speed);
  // Skip the replay-delay warm-up: before the buffer has filled the renderer
  // legitimately still shows the spawn position.
  const settled = rows.slice(Math.ceil(replayDelayMs(speed) / FRAME) + 2, -1);
  const steps = settled.slice(1).map((row, i) => row.x - settled[i]!.x);
  const nominal = FRAME / (TILE_CADENCE_MS_1X / speed);
  return {
    frozen: steps.filter((step) => Math.abs(step) < 1e-9).length,
    frames: steps.length,
    peakRatio: Math.max(...steps.map(Math.abs)) / nominal,
    rate:
      (settled[settled.length - 1]!.x - settled[0]!.x) / (((settled.length - 1) * FRAME) / 1000),
    idealRate: 1000 / cadence,
    clockResets: settled.filter((row) => row.clock < 0).length,
    framesSeen: new Set(settled.map((row) => row.frame)).size,
  };
}

it.each([1, 4, 16])('keeps %ix motion continuous, correctly paced and fully animated', (speed) => {
  const m = metrics(speed);
  expect(m.frozen).toBe(0);
  // 16x 下每渲染帧要跨 1.07 格，量化误差让 60fps 采样天然差 0.1% 左右；
  // 1x/4x 每帧只走 0.27/1.07 格，可要求更紧。
  expect(Math.abs(m.rate - m.idealRate)).toBeLessThan(speed === 16 ? 0.2 : 0.05);
  expect(m.peakRatio).toBeLessThanOrEqual(2);
  // 整段行走里动画钟不回站立帧，且走环用满 3 帧。
  expect(m.clockResets).toBe(0);
  expect(m.framesSeen).toBe(CHENMO_SHEET.framesPerRow);
});
