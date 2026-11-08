/** Observable locomotion facts and their renderer-independent presentation adapter. */
import type { JumpVisual } from '../net/protocol';
import type { MotionTarget } from './render/actor-motion';
import type { SampledPoint } from './render/motion-buffer';

const jumpKeys = [
  'rtoken',
  'start_x',
  'start_y',
  'goal_x',
  'goal_y',
  'start_height',
  'target_height',
  'progress',
  'active',
  'duration',
  'arc_height',
] as const;

export function validElevation(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 3;
}

export function copyJump(value: unknown): JumpVisual | null {
  if (!value || typeof value !== 'object') return null;
  const j = value as Partial<JumpVisual>;
  if (
    typeof j.rtoken !== 'string' ||
    !j.rtoken.length ||
    j.rtoken.length > 128 ||
    ![j.start_x, j.start_y, j.goal_x, j.goal_y].every(
      (v) => typeof v === 'number' && Number.isInteger(v) && v >= 0,
    ) ||
    !validElevation(j.start_height) ||
    !validElevation(j.target_height) ||
    typeof j.progress !== 'number' ||
    !Number.isFinite(j.progress) ||
    j.progress < 0 ||
    j.progress > 1 ||
    typeof j.active !== 'boolean' ||
    typeof j.duration !== 'number' ||
    !Number.isFinite(j.duration) ||
    j.duration <= 0 ||
    j.duration > 4 ||
    typeof j.arc_height !== 'number' ||
    !Number.isFinite(j.arc_height) ||
    j.arc_height <= 0 ||
    j.arc_height > 2
  )
    return null;
  return {
    rtoken: j.rtoken,
    start_x: j.start_x!,
    start_y: j.start_y!,
    goal_x: j.goal_x!,
    goal_y: j.goal_y!,
    start_height: j.start_height,
    target_height: j.target_height,
    progress: j.progress,
    active: j.active,
    duration: j.duration,
    arc_height: j.arc_height,
  };
}

export function sameJump(
  left: JumpVisual | null | undefined,
  right: JumpVisual | null | undefined,
): boolean {
  return left === right || (!!left && !!right && jumpKeys.every((key) => left[key] === right[key]));
}

export const gaitCadenceMs = (gait: 'walk' | 'run' | undefined): number =>
  gait === 'walk' ? 500 : 250;

export function flightTarget(
  jump: JumpVisual | null | undefined,
  project: (x: number, y: number, height: number) => SampledPoint,
): MotionTarget['flight'] {
  if (!jump) return undefined;
  const start = project(jump.start_x, jump.start_y, jump.start_height);
  const end = project(jump.goal_x, jump.goal_y, jump.target_height);
  const crest = project(jump.start_x, jump.start_y, jump.start_height + jump.arc_height);
  return {
    id: jump.rtoken,
    progress: jump.progress,
    active: jump.active,
    durationMs: jump.duration * 1000,
    start,
    end,
    arc: { x: crest.x - start.x, y: crest.y - start.y, z: crest.z - start.z },
  };
}
