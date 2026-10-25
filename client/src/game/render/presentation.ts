/**
 * client/src/game/render/presentation.ts — A 档画面降噪（2026-10-20）。
 *
 * 用户反馈「人物都聚集在一起，给人的感觉就是很混乱」。根因里属于表现层的部分：
 * 1. 所有角色 depth=10 固定 → 上下相邻的人互相压盖，没有前后关系；
 * 2. 50 个村民名字标签常显 → 小片区内文字互相覆盖；
 * 3. 人站同一格时精灵完全重合；
 * 4. 脚下没有接触阴影，重叠时看不出各自站位。
 *
 * 本模块只做纯计算，便于单测；Phaser 对象操作留在 WorldScene。
 */
const TILE = 16;

export function rendererFromSearch(search: string): 'flat' | 'iso' {
  return new URLSearchParams(search).get('renderer') === 'flat' ? 'flat' : 'iso';
}

/**
 * 深度分层带（2026-10-20 A 档修正：此前 actorDepth=100+footY 越过夜幕层，
 * 角色不再被夜色压暗）。
 *
 *   地面/结构  0 .. 14
 *   精灵      10 .. 70   （脚底 y 线性映射，靠下者压靠上者）
 *   名字      71 .. 80   （所有名字在所有精灵之上）
 *   气泡      81 .. 89   （气泡压名字）
 *   雨        99
 *   夜幕     100
 */
export const ACTOR_DEPTH_BASE = 10;
const ACTOR_DEPTH_TOP = 70;
const LABEL_DEPTH_BASE = 71;
const LABEL_DEPTH_TOP = 80;
const BUBBLE_DEPTH_BASE = 81;
const BUBBLE_DEPTH_TOP = 89;
/** 世界高度（100 格 @16px）——深度归一化用的最大脚底像素。 */
const MAP_MAX_FOOT_Y = 100 * TILE;
/** 雨层深度（WorldScene 同源）。 */
export const RAIN_LAYER_DEPTH = 99;
/** 夜幕遮罩深度（WorldScene 同源）。 */
export const NIGHT_OVERLAY_DEPTH = 100;

/** Town world depthKey tops out below 250k. Iso labels/bubbles have separate
 * bands; rain and night cover the entire world and its text. Flat bands above stay intact.
 */
export const ISO_DEPTH = { LABEL: 300000, BUBBLE: 310000, RAIN: 400000, NIGHT: 400001 } as const;
export const ISO_LABEL_GAP_PX = 6;
export const ISO_BUBBLE_GAP_PX = 20;

/** Sprite height is in world pixels; the gap stays fixed in screen pixels. */
export function aboveSurface(
  footY: number,
  spriteHeight: number,
  gapPx: number,
  zoom: number,
): number {
  return footY - spriteHeight - gapPx / zoom;
}

/** 名字标签显示半径（逻辑格，曼哈顿距离；主角自身恒显示）。 */
export const NAME_LABEL_RADIUS = 8;

/** 同格多人视觉偏移池：分布在一个格内四角/中心之间，最大 ±5px（格 16px）。 */
export const STACK_OFFSETS: readonly { readonly dx: number; readonly dy: number }[] = [
  { dx: 0, dy: 0 },
  { dx: -4, dy: -2 },
  { dx: 4, dy: -2 },
  { dx: -4, dy: 3 },
  { dx: 4, dy: 3 },
];

/** 脚底 y（世界像素）→ 归一化 0..1（越界钳制）。 */
function normalizeFootY(footY: number): number {
  const t = footY / MAP_MAX_FOOT_Y;
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

/** 角色精灵深度：按脚底 y 排序，落在 [10,70]；同格同深度。 */
export function actorDepth(footY: number): number {
  return (
    ACTOR_DEPTH_BASE + Math.round(normalizeFootY(footY) * (ACTOR_DEPTH_TOP - ACTOR_DEPTH_BASE))
  );
}

/** 名字深度：所有名字都在所有精灵之上（[71,80]）。 */
export function labelDepth(footY: number, renderer: 'flat' | 'iso' = 'flat'): number {
  return (
    (renderer === 'iso' ? ISO_DEPTH.LABEL : LABEL_DEPTH_BASE) +
    Math.round(normalizeFootY(footY) * (LABEL_DEPTH_TOP - LABEL_DEPTH_BASE))
  );
}

/** 气泡深度：压过名字层（[81,89]），仍在雨/夜幕之下。 */
export function bubbleDepth(footY: number, renderer: 'flat' | 'iso' = 'flat'): number {
  return (
    (renderer === 'iso' ? ISO_DEPTH.BUBBLE : BUBBLE_DEPTH_BASE) +
    Math.round(normalizeFootY(footY) * (BUBBLE_DEPTH_TOP - BUBBLE_DEPTH_BASE))
  );
}

/** 是否显示名字标签（主角邻近才显示，消 50 个常显标签的噪声）。 */
export function shouldShowNameLabel(distance: number, radius: number = NAME_LABEL_RADIUS): boolean {
  return distance <= radius;
}

/** 逻辑格曼哈顿距离。 */
export function manhattan(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

/** 角色帧高（GOD/村民素材 16×32，脚底对齐 origin(0.5,1)）。 */
export const ACTOR_FRAME_HEIGHT = 32;
/** 名字基线离头顶的间隙（世界像素）。 */
export const LABEL_GAP = 2;
/** 气泡底边离头顶的间隙（留出名字高度，避免气泡压字）。 */
export const BUBBLE_GAP = 14;

/** 名字头顶锚点 y（脚底 y − 帧高 − 间隙）。 */
export function labelY(footY: number): number {
  return footY - ACTOR_FRAME_HEIGHT - LABEL_GAP;
}

/** 气泡底边锚点 y（比名字再高 BUBBLE_GAP − LABEL_GAP）。 */
export function bubbleY(footY: number): number {
  return footY - ACTOR_FRAME_HEIGHT - BUBBLE_GAP;
}

export interface StackCandidate {
  rtoken: string;
  x: number;
  y: number;
}

/**
 * 同格多人 → 稳定视觉偏移。
 *
 * 按格分组后，组内按 rtoken 字典序排序（与快照到达顺序无关，C5 确定性），
 * 依序取 STACK_OFFSETS，超出容量循环复用。独占一格恒 (0,0)。
 */
export function assignStackOffsets(
  actors: Iterable<StackCandidate>,
): Map<string, { dx: number; dy: number }> {
  const byCell = new Map<string, StackCandidate[]>();
  for (const a of actors) {
    const key = `${a.x},${a.y}`;
    const bucket = byCell.get(key);
    if (bucket) bucket.push(a);
    else byCell.set(key, [a]);
  }
  const out = new Map<string, { dx: number; dy: number }>();
  for (const bucket of byCell.values()) {
    bucket.sort((a, b) => (a.rtoken < b.rtoken ? -1 : a.rtoken > b.rtoken ? 1 : 0));
    for (let i = 0; i < bucket.length; i += 1) {
      const offset = STACK_OFFSETS[i % STACK_OFFSETS.length]!;
      out.set(bucket[i]!.rtoken, { dx: offset.dx, dy: offset.dy });
    }
  }
  return out;
}
