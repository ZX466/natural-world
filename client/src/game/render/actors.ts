/**
 * client/src/game/render/actors.ts — R2：facing/anim 前端推断。
 *
 * sim 侧 Actor.facing/anim 现硬编码（ws.py "s"/"idle"，EntityState 只有 pos）——
 * 表现层推断是纯客户端职责；sim 真供数日，switch 到协议字段的缝已留
 * （MirrorActor 的 facing/anim 键直接读即可，本模块推断函数仍服务插值中间帧）。
 */
import type { MirrorActor } from '../world-mirror';

export type Facing = 'n' | 'e' | 's' | 'w';
export type Anim = 'idle' | 'walk';

/** 位移方向 → 朝向（对角取主导轴，|dy|≥|dx| 时 y 优先；零位移默认朝南）。 */
export function inferFacing(dx: number, dy: number): Facing {
  if (dx === 0 && dy === 0) return 's';
  if (Math.abs(dy) >= Math.abs(dx)) return dy > 0 ? 's' : 'n';
  return dx > 0 ? 'e' : 'w';
}

/** 前后两帧位置 → 动画态（变格=walk，原格=idle）。 */
export function inferAnim(prev: { x: number; y: number }, cur: { x: number; y: number }): Anim {
  return prev.x === cur.x && prev.y === cur.y ? 'idle' : 'walk';
}

/** facing → 图集行号（build_palette.py 布局实测：下/上/右/左 = 0/1/2/3）。 */
export function facingRow(facing: Facing): number {
  return { down: 0, up: 1, right: 2, left: 3 }[({ n: 'up', e: 'right', s: 'down', w: 'left' } as const)[facing]];
}

/** walk 循环帧号（3 帧布局：步-站-步，150ms/帧）。anim 传 idle 恒取站立帧 1。 */
export function walkFrame(row: number, animClockMs: number): number {
  if (animClockMs < 0) return row * 3 + 1; // 负钟=站立
  const phase = Math.floor(animClockMs / 150) % 3;
  return row * 3 + phase;
}

/** Actor 当前逻辑帧号（合成入口：朝向行 + 动画帧）。 */
export function frameOf(actor: MirrorActor, prev: { x: number; y: number }, animClockMs: number): number {
  const row = facingRow(inferFacing(actor.x - prev.x, actor.y - prev.y));
  const anim = inferAnim(prev, actor);
  return walkFrame(row, anim === 'idle' ? -1 : animClockMs);
}
