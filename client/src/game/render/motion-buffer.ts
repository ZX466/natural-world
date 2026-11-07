/**
 * Shared replay buffer for actor motion — the one implementation behind both
 * the Phaser and the three.js renderers.
 *
 * The world advances an actor one tile every `TILE_CADENCE_MS_1X` while the
 * renderer draws 60 frames in that time. Filling those frames by interpolating
 * *between two authoritative samples* is what keeps motion continuous; the
 * alternative — a fixed window that restarts from the current visual position
 * on every sample — leaves a frozen stretch at the end of each tile and makes
 * the remaining frames run fast to catch up. That was the reported hitch.
 *
 * Samples are kept oldest-first and always end with the newest observation.
 * Callers pick the units: tiles for the three.js layer, screen pixels for
 * Phaser, so the same buffer serves both projections.
 */

/** Samples kept beyond the newest two. Two suffice to bracket the replay
 *  instant; the slack absorbs samples arriving faster than rendered frames. */
export const HISTORY_SAMPLES = 8;

export interface TimedSample {
  /** Render-clock instant the observation arrived at. */
  readonly at: number;
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

export interface SampledPoint {
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

export const newestSample = (samples: readonly TimedSample[]): TimedSample =>
  samples[samples.length - 1]!;

/**
 * Appends an observation, or resets the history when the jump is too large to
 * be walking (a reconnect, a load, a teleport).
 *
 * `jumpLimit` is in the caller's units, so a screen-space buffer passes pixels
 * and a tile-space buffer passes tiles.
 */
export function pushSample(
  samples: readonly TimedSample[],
  next: TimedSample,
  jumpLimit: number,
  keep = HISTORY_SAMPLES,
): readonly TimedSample[] {
  const last = samples.length === 0 ? undefined : newestSample(samples);
  const teleported = last !== undefined && Math.hypot(next.x - last.x, next.y - last.y) > jumpLimit;
  const base = teleported ? [] : [...samples];
  base.push(next);
  // Only the samples around the replay instant matter; at 16x the server emits
  // ~64 samples a second, which would otherwise grow every actor's queue and
  // copy it all on each frame.
  while (base.length > keep) base.shift();
  return base;
}

/**
 * The position at `instant`, interpolating between the two samples that
 * bracket it in time.
 *
 * Bracketing by time — rather than by sample index — is what keeps motion
 * continuous. Indexing by sample order ("interpolate the newest pair, progress
 * by their own interval") restarts progress at zero every time a sample
 * arrives, which drops a frame: the first frame of each pair renders the
 * position the previous frame already showed. Measured at 4x: 47 frozen
 * frames in 12s. Time bracketing carries the progress across the sample
 * boundary, so there is no such frame.
 *
 * Before the first sample the first is held; after the last, the last is held
 * (the actor has stopped, or the newest data is late).
 */
export function sampleAt(samples: readonly TimedSample[], instant: number): SampledPoint {
  const first = samples[0]!;
  const last = newestSample(samples);
  if (instant <= first.at) return { x: first.x, y: first.y, z: first.z };
  if (instant >= last.at) return { x: last.x, y: last.y, z: last.z };
  let index = 0;
  while (index + 1 < samples.length && samples[index + 1]!.at <= instant) index += 1;
  const before = samples[index]!;
  const after = samples[index + 1]!;
  const gap = after.at - before.at;
  // Duplicate timestamps resolve to the later sample.
  if (gap <= 0) return { x: after.x, y: after.y, z: after.z };
  const k = (instant - before.at) / gap;
  return {
    x: before.x + (after.x - before.x) * k,
    y: before.y + (after.y - before.y) * k,
    z: before.z + (after.z - before.z) * k,
  };
}

/**
 * Moves the replay delay toward its nominal value, at a bounded rate.
 *
 * The delay has to follow the world's speed: one cadence of lag is what keeps
 * both sides of the replay instant known, and the cadence shrinks as the world
 * speeds up. But the *instant* drawn is `now - delay`, so changing the delay
 * instantly would move the instant instantly — a 16x→1x switch would jump it
 * 234ms into the past and yank the actor back two tiles in one frame.
 *
 * Ramping the delay keeps the instant monotone as long as it grows no faster
 * than real time. `RAMP_RATE` stays below 1 so the instant always advances:
 * slowing the world reads as the actor easing to the new speed over a few
 * hundred milliseconds, speeding it up as a brief burst of acceleration. No
 * frame ever shows the actor going backwards, and once the ramp lands the lag
 * is exactly one cadence again.
 */
export const RAMP_RATE = 0.6;

export function rampDelay(current: number, nominal: number, delta: number): number {
  if (delta <= 0) return current;
  const step = delta * RAMP_RATE;
  const gap = nominal - current;
  if (Math.abs(gap) <= step) return nominal;
  return current + Math.sign(gap) * step;
}
