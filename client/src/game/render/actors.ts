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

/** 位移方向 → 朝向（对角取主导轴，|dy|≥|dx| 时 y 优先；零位移**沿用原朝向**——
 *  H-3：停下不许转身，调用方传 lastFacing 缓存）。 */
export function inferFacing(dx: number, dy: number, lastFacing: Facing = 's'): Facing {
  if (dx === 0 && dy === 0) return lastFacing;
  if (Math.abs(dy) >= Math.abs(dx)) return dy > 0 ? 's' : 'n';
  return dx > 0 ? 'e' : 'w';
}

/** 前后两帧位置 → 动画态（变格=walk，原格=idle）。 */
export function inferAnim(prev: { x: number; y: number }, cur: { x: number; y: number }): Anim {
  return prev.x === cur.x && prev.y === cur.y ? 'idle' : 'walk';
}

/** H-2：walk 动画钟推进——moved 时从站立帧起步并累加 delta，静止归 -1（站立帧）。
 *  修前的实现恰好写反（moved 恒归 0 → 循环死在第 0 帧）。 */
export function advanceAnimClock(current: number, moved: boolean, deltaMs: number): number {
  if (!moved) return -1;
  return current < 0 ? 0 : current + deltaMs;
}

/** facing → 图集行号（build_palette.py 布局实测：下/上/右/左 = 0/1/2/3）。 */
export function facingRow(facing: Facing): number {
  return { down: 0, up: 1, right: 2, left: 3 }[({ n: 'up', e: 'right', s: 'down', w: 'left' } as const)[facing]];
}

/** C-2：chenmo.png 272×256 = **17 列**×16 行 @16px——Phaser spritesheet 线性帧号
 *  f = col + row*COLS。此前按 3 列算（row*3）→ 帧号全落表第 0 行，朝北 idle
 *  命中全透明帧（主角消失）。COLS 与 png 实宽绑定，换素材必同改。 */
const CHENMO_COLS = 17;
const FRAMES_PER_ROW = 3; // 步-站-步

/** walk 循环帧号（线性 f = row*COLS + phase）。animClock<0 = 站立帧（col 1）。 */
export function walkFrame(row: number, animClockMs: number): number {
  if (animClockMs < 0) return row * CHENMO_COLS + 1;
  const phase = Math.floor(animClockMs / 150) % FRAMES_PER_ROW;
  return row * CHENMO_COLS + phase;
}

/** Actor 当前逻辑帧号（合成入口：朝向行 + 动画帧）。 */
export function frameOf(actor: MirrorActor, prev: { x: number; y: number }, animClockMs: number): number {
  const row = facingRow(inferFacing(actor.x - prev.x, actor.y - prev.y));
  const anim = inferAnim(prev, actor);
  return walkFrame(row, anim === 'idle' ? -1 : animClockMs);
}
