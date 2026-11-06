/** Renderer-independent snapshot interpolation and camera-relative sheet facing. */
import { advanceAnimClock, inferFacing, type Facing } from './actors';

export interface MotionTarget {
  readonly x: number;
  readonly y: number;
  readonly height: number;
  readonly facing?: Facing;
}
export interface ActorMotion extends MotionTarget {
  readonly targetX: number;
  readonly targetY: number;
  readonly targetHeight: number;
  readonly fromX: number;
  readonly fromY: number;
  readonly fromHeight: number;
  readonly changedAt: number;
  readonly facing: Facing;
  readonly animClock: number;
}

export function advanceMotion(
  previous: ActorMotion | undefined,
  target: MotionTarget,
  now: number,
  delta: number,
  speed: number,
): ActorMotion {
  if (!previous)
    return {
      ...target,
      targetX: target.x,
      targetY: target.y,
      targetHeight: target.height,
      fromX: target.x,
      fromY: target.y,
      fromHeight: target.height,
      changedAt: now,
      facing: target.facing ?? 's',
      animClock: -1,
    };
  const changed =
    previous.targetX !== target.x ||
    previous.targetY !== target.y ||
    previous.targetHeight !== target.height;
  const fromX = changed ? previous.x : previous.fromX;
  const fromY = changed ? previous.y : previous.fromY;
  const fromHeight = changed ? previous.height : previous.fromHeight;
  const changedAt = changed ? now : previous.changedAt;
  const duration = Math.max(1000 / 60, 200 / Math.max(1, speed));
  const k = Math.min(1, Math.max(0, (now - changedAt) / duration));
  return {
    x: fromX + (target.x - fromX) * k,
    y: fromY + (target.y - fromY) * k,
    height: fromHeight + (target.height - fromHeight) * k,
    targetX: target.x,
    targetY: target.y,
    targetHeight: target.height,
    fromX,
    fromY,
    fromHeight,
    changedAt,
    facing: changed
      ? inferFacing(target.x - previous.targetX, target.y - previous.targetY, previous.facing)
      : previous.facing,
    animClock: advanceAnimClock(previous.animClock, changed || k < 1, delta),
  };
}

export function cameraFacing(facing: Facing, azimuth: number): Facing {
  const vector = { n: [0, -1], s: [0, 1], e: [1, 0], w: [-1, 0] }[facing]!;
  const yaw = (azimuth * Math.PI) / 180;
  const toward = vector[0]! * Math.sin(yaw) + vector[1]! * Math.cos(yaw);
  const right = vector[0]! * Math.cos(yaw) - vector[1]! * Math.sin(yaw);
  return Math.abs(toward) >= Math.abs(right) ? (toward >= 0 ? 's' : 'n') : right >= 0 ? 'e' : 'w';
}
