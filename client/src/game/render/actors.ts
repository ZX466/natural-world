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
  return { down: 0, up: 1, right: 2, left: 3 }[
    ({ n: 'up', e: 'right', s: 'down', w: 'left' } as const)[facing]
  ];
}

/** C-2：chenmo.png 272×256 = **17 列**×16 行 @16px——Phaser spritesheet 线性帧号
 *  f = col + row*COLS。此前按 3 列算（row*3）→ 帧号全落表第 0 行，朝北 idle
 *  命中全透明帧（主角消失）。COLS 与 png 实宽绑定，换素材必同改。
 *  D10：具体数值搬进 CHENMO_SHEET（几何单源）。 */

/** 帧表几何（D10 抽象：chenmo 17 列 3 帧 vs villager 4 列 4 帧共用一套换算）。 */
export interface SheetGeometry {
  /** 图集列数（png 宽 ÷ 16px；Phaser 线性帧号的行进因子） */
  cols: number;
  /** 行内参与 walk 环的帧数 */
  framesPerRow: number;
  /** 站立帧所在列（chenmo=1 中帧；villager=0） */
  standCol?: number;
}

/** chenmo 几何（17 列 × 步-站-步） */
export const CHENMO_SHEET: SheetGeometry = { cols: 17, framesPerRow: 3, standCol: 1 };
/** villager 几何（NPC_test.png 64×128；帧 16×32——2026-10-12「有头没身」修正：
 *  此前按 16px 帧算 4×8 行是错的，实为 **4 列 × 4 行 @16×32**。每行 4 帧全参与
 *  行走环，行序 下/上/右/左（R0-R3）。16×32 素材无独立劳作姿势行（D14 的
 *  R4-7 姿势行在 32px 帧几何下不存在——静止姿势退化为朝向站立帧）。 */
export const VILLAGER_SHEET: SheetGeometry = { cols: 4, framesPerRow: 4, standCol: 0 };

/** GOD 古风外观池几何（build_god_characters.py 产物 48×128 = 3 列 × 4 行 @16×32；
 *  源 96×128@32×32 缩半+行序重排为 下/上/右/左——与 facingRow 直接对齐）。
 *  2026-10-12 D1-D5 裁决接入：D4 只摘平民，军事/名人不入池。 */
export const GOD_SHEET: SheetGeometry = { cols: 3, framesPerRow: 3, standCol: 1 };

/** GOD 池 texture key（与后端 villagers.GOD_SPRITE_POOL 同名——
 *  sprite_for_entity 单一真相源，两端清单漂移 = 兜底 villager 皮）。 */
export const GOD_SPRITE_KEYS: readonly string[] = [
  'god_villager_taocunzhang',
  'god_villager_acheng',
  'god_villager_ali',
  'god_villager_xiaolan',
  'god_villager_zhouyue',
  'god_villager_mengjiaoshou',
  'god_villager_xuning',
  'god_villager_taobo',
  'god_villager_axiu',
  'god_villager_ayuan',
  'god_villager_linkai',
  'god_villager_ada',
  'god_villager_zhibufu',
  'god_villager_liangcangguanshi',
  'god_villager_chuanlingbing',
  'god_villager_laojunhou',
  'god_villager_zuheshishen',
];

/** GOD 皮帧号合成：3 列几何（col1 站立 + 行内 3 帧走环）。
 *  劳作姿势与 villager 同口径——16×32 帧无独立姿势行，静止退朝向站立帧。 */
export function godVillagerFrame(
  sheet: SheetGeometry,
  anim: string,
  facing: Facing,
  animClockMs: number,
): number {
  return villagerFrame(sheet, anim, facing, animClockMs);
}

/** D14：劳作姿势 → 素材行号。16×32 帧几何下 villager 无独立姿势行（原 R4-R7
 *  是 16px 帧误算的产物，实为 R0-R3 的下半身）——work/eat/rest/chat 静止统一
 *  退朝向站立帧（与 walk/idle 同帧；姿势差异化待换带姿势行的素材再启用）。 */
const POSE_ROW: Record<string, number> = {};

/** villager 帧号合成：行走中（animClock≥0）→ facing 走环；静止 → 劳作姿势行
 *  站立帧（work/eat/rest/chat），walk/idle 姿势 = facing 走环站立帧。 */
export function villagerFrame(
  sheet: SheetGeometry,
  anim: string,
  facing: Facing,
  animClockMs: number,
): number {
  if (animClockMs >= 0) {
    return walkFrameFor(sheet, facingRow(facing), animClockMs); // 行走环
  }
  const poseRow = POSE_ROW[anim];
  if (poseRow !== undefined) return poseRow * sheet.cols + (sheet.standCol ?? 0);
  return walkFrameFor(sheet, facingRow(facing), -1); // walk/idle/未知 → 站立帧
}

/** 通用线性帧号：站立帧 row*cols+standCol；walk 环行内 framesPerRow 帧循环。
 *  D10：walkFrame 的一般化（单入口防两套换算漂移——C-2 教训）。 */
export function walkFrameFor(sheet: SheetGeometry, row: number, animClockMs: number): number {
  const standCol = sheet.standCol ?? 0;
  if (animClockMs < 0) return row * sheet.cols + standCol;
  const phase = Math.floor(animClockMs / 150) % sheet.framesPerRow;
  return row * sheet.cols + phase;
}

/** walk 循环帧号（线性 f = row*COLS + phase）。animClock<0 = 站立帧（col 1）。 */
export function walkFrame(row: number, animClockMs: number): number {
  return walkFrameFor(CHENMO_SHEET, row, animClockMs);
}

/** Actor 当前逻辑帧号（合成入口：朝向行 + 动画帧）。 */
export function frameOf(
  actor: MirrorActor,
  prev: { x: number; y: number },
  animClockMs: number,
): number {
  const row = facingRow(inferFacing(actor.x - prev.x, actor.y - prev.y));
  const anim = inferAnim(prev, actor);
  return walkFrame(row, anim === 'idle' ? -1 : animClockMs);
}
