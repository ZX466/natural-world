/**
 * Renderer-independent snapshot interpolation and camera-relative sheet facing.
 *
 * ## Why a replay buffer
 *
 * The server moves an actor one tile every `TILE_CADENCE_MS_1X` (60 tick/s ÷
 * 15 tick/tile). The renderer runs at 60 fps, so between two authoritative
 * samples it has ~15 frames to fill in. The previous implementation tried to
 * finish each tile inside a *shorter* window and restarted the tween from the
 * current visual position whenever a new sample arrived. Every tile therefore
 * ended with a stretch of frames where the actor did not move at all, and the
 * frames in between had to run faster than the authoritative speed to catch
 * up — the reported "jerky, one hitch per tile" motion. Measured over 12s of
 * continuous walking at 1x: 19.9% of frames frozen, peak step 1.25× nominal.
 *
 * The fix keeps a short history of `(arrival time, authoritative position)`
 * samples and draws the instant roughly one cadence in the past, interpolating
 * between the two samples that bracket it. Both sides of that instant are
 * already known, so the actor neither stalls nor overshoots. The price is a
 * constant visual delay of about one tile (250ms at 1x, 62ms at 4x, 16ms at
 * 16x), which shrinks automatically as the world speeds up.
 */
import { advanceAnimClock, inferFacing, type Facing } from './actors';
import { newestSample, pushSample, rampDelay, sampleAt, type TimedSample } from './motion-buffer';

/** Authoritative tile cadence at 1x (60 tick/s ÷ 15 tick/tile, `sim/core/tick.py`). */
export const TILE_CADENCE_MS_1X = 250;

/** How far the renderer trails the authoritative samples, in tile cadences. */
export const REPLAY_DELAY_CADENCES = 1;

/**
 * A jump longer than this is not walking: it is a reconnect, a load, or a
 * teleport. Replaying it would slide the actor across the map, so snap instead.
 */
export const TELEPORT_TILES = 3;

/** Extra lag on top of one cadence, so a late snapshot never leaves the drawn
 *  instant past the newest sample (two frames at 60fps). */
export const REPLAY_JITTER_SLACK_MS = 33;

/** Nominal delay between the newest observation and what the renderer shows. */
export const replayDelayMs = (speed: number): number =>
  (TILE_CADENCE_MS_1X * REPLAY_DELAY_CADENCES) / Math.max(1, speed) + REPLAY_JITTER_SLACK_MS;

export interface MotionTarget {
  readonly x: number;
  readonly y: number;
  readonly height: number;
  readonly facing?: Facing;
}

export interface ActorMotion extends MotionTarget {
  readonly facing: Facing;
  readonly animClock: number;
  /** Oldest first, always ending with the newest authoritative sample. */
  readonly samples: readonly TimedSample[];
  /** How far behind the newest sample the renderer currently draws, in ms.
   *  Ramps toward `replayDelayMs(speed)` so a speed change never moves the
   *  drawn instant backwards. */
  readonly delayMs: number;
}

/**
 * Advances one rendered frame.
 *
 * `now` is the render timestamp (ms), `delta` the frame's elapsed time and
 * `speed` the world's time scale (1/4/16). The returned `x`/`y`/`height` are
 * what the renderer should draw; `samples` carries the history forward.
 *
 * `unitsPerTile` is how many of the caller's units one world tile spans: 1 for
 * the three.js layer (which works in tiles), `TILE` for Phaser's pixel space.
 * It only scales the teleport threshold — the interpolation itself is unit
 * agnostic.
 */
export function advanceMotion(
  previous: ActorMotion | undefined,
  target: MotionTarget,
  now: number,
  delta: number,
  speed: number,
  unitsPerTile = 1,
): ActorMotion {
  // One cadence of lag is what keeps both sides of the drawn instant known.
  // `REPLAY_JITTER_SLACK_MS` on top covers network jitter: a snapshot that
  // arrives late would otherwise leave the drawn instant past the newest
  // sample, holding the actor for a frame. It is a constant rather than a
  // function of `delta` so a dropped frame does not inflate the lag.
  const nominalDelay = replayDelayMs(speed);
  const sample: TimedSample = { at: now, x: target.x, y: target.y, z: target.height };

  if (previous === undefined)
    return {
      x: target.x,
      y: target.y,
      height: target.height,
      facing: target.facing ?? 's',
      animClock: -1,
      samples: [sample],
      delayMs: nominalDelay,
    };

  const delay = rampDelay(previous.delayMs, nominalDelay, delta);
  const last = newestSample(previous.samples);
  const moved = last.x !== target.x || last.y !== target.y || last.z !== target.height;
  const jumpLimit = TELEPORT_TILES * unitsPerTile;
  const teleported = moved && Math.hypot(target.x - last.x, target.y - last.y) > jumpLimit;

  let samples: readonly TimedSample[] = previous.samples;
  if (moved) {
    // Anchor the segment one delay before the arrival. Without it the drawn
    // instant can fall inside a segment spanning an arbitrary gap — an actor
    // that stood still for seconds would have its whole move compressed into
    // the last frame or two and pop a full tile. Anchoring also covers a late
    // arrival, whose glide would otherwise be skipped entirely.
    if (last.at < now - delay) samples = [{ at: now - delay, x: last.x, y: last.y, z: last.z }];
    samples = pushSample(samples, sample, jumpLimit);
  } else if (teleported) {
    samples = [sample];
  }

  const shown = sampleAt(samples, now - delay);
  const walked =
    !teleported && (Math.abs(shown.x - previous.x) > 1e-9 || Math.abs(shown.y - previous.y) > 1e-9);
  // `target.facing` wins when the caller knows the walk direction. Phaser feeds
  // projected pixels, where a height change moves y far more than a tile moves
  // x — inferring facing from those deltas would turn a level walk uphill into
  // a "north" step. Callers working in tiles can let it infer instead.
  // A teleport is not a step: the delta points wherever the actor was
  // reloaded to, so keep the facing it already had rather than spinning to
  // face the jump.
  const facing =
    target.facing ??
    (moved && !teleported
      ? inferFacing(target.x - last.x, target.y - last.y, previous.facing)
      : previous.facing);
  return {
    x: shown.x,
    y: shown.y,
    height: shown.z,
    facing,
    animClock: advanceAnimClock(previous.animClock, walked, delta),
    samples,
    delayMs: delay,
  };
}

export function cameraFacing(facing: Facing, azimuth: number): Facing {
  const vector = { n: [0, -1], s: [0, 1], e: [1, 0], w: [-1, 0] }[facing]!;
  const yaw = (azimuth * Math.PI) / 180;
  const toward = vector[0]! * Math.sin(yaw) + vector[1]! * Math.cos(yaw);
  const right = vector[0]! * Math.cos(yaw) - vector[1]! * Math.sin(yaw);
  return Math.abs(toward) >= Math.abs(right) ? (toward >= 0 ? 's' : 'n') : right >= 0 ? 'e' : 'w';
}
