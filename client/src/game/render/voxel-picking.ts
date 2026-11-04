import { ISO, depthKey, isoProject, isoUnproject, screenBounds, type HeightLookup } from './iso';

/** 可走面的静态高度（与 `sim/content/terrain_class.py::HEIGHT_EARTH` 同值）。
 *  单向不变量 `walkable ⇒ h == EARTH` 保证所有可走格的顶面都在这一层。 */
const WALK_HEIGHT = 1;

/** The frozen dark slat quad is(-3,1),(-1,2),(3,-1),(1,-2), at offsets -7/0/7.
 * Its two pairs of edges are |x-2y|<=5 and |3x+4y|<=5; the light inset is inside it. */
function hitsBankGlyph(dx: number, dy: number): boolean {
  return [-7, 0, 7].some((offset) => {
    const x = dx - offset;
    return Math.abs(x - 2 * dy) <= 5 + 1e-6 && Math.abs(3 * x + 4 * dy) <= 5 + 1e-6;
  });
}

/** Editing follows high Images and bank-top glyph depth above the baked ground. */
export function pickVoxel(
  px: number,
  py: number,
  w: number,
  h: number,
  heightAt: HeightLookup,
  isBank?: (x: number, y: number) => boolean,
): { x: number; y: number } | null {
  if (!Number.isFinite(px) || !Number.isFinite(py)) return null;
  const bounds = screenBounds(w, h),
    ground = isoUnproject(px, py, bounds);
  const seen = new Set<string>();
  let best: { x: number; y: number } | null = null,
    bestRank = -Infinity;
  for (let lift = 0; lift <= 3; lift++)
    for (let dy = -1; dy <= 1; dy++)
      for (let dx = -1; dx <= 1; dx++) {
        const x = ground.x + lift + dx,
          y = ground.y + lift + dy,
          key = `${x},${y}`;
        if (x < 0 || y < 0 || x >= w || y >= h || seen.has(key)) continue;
        seen.add(key);
        const height = heightAt(x, y),
          top = isoProject(x, y, height, bounds),
          base = isoProject(x, y, 0, bounds);
        const distance = Math.abs(px - top.sx);
        if (distance > ISO.TW / 2) continue;
        const slope = (distance * ISO.TH) / ISO.TW;
        if (py < top.sy - ISO.TH / 2 + slope - 1e-6 || py > base.sy + ISO.TH / 2 - slope + 1e-6)
          continue;
        // Only painted bank strokes are at depthKey + .5. The empty parts of
        // its baked top/side stay below high Images, preserving house-side editing.
        const bankTop =
          height === 1 && isBank?.(x, y) === true && hitsBankGlyph(px - top.sx, py - top.sy);
        const rank = (height >= 2 || bankTop ? 1000000 : 0) + depthKey(x, y) + (bankTop ? 0.5 : 0);
        if (rank > bestRank) {
          bestRank = rank;
          best = { x, y };
        }
      }
  return best;
}

/**
 * Movement picks the **ground the player stands on**, not the visible column.
 *
 * 2026-10-29「人物无法移动」回归修：此前移动也走 `pickVoxel`，而它是为编辑设计的
 * （`h>=2` 优先）。等距画面里一个 h=3 的方块与它斜后方 4 格的 h=1 地面**顶面菱形
 * 完全重合**（高度差 2*ISO.HH = 32px = 4*(TH/2)），于是「点空地」被判成「点房子」。
 * 真实地图实测：3947 个可走格里 763 个（19.3%）如此；出生点 13×13 邻域 26 个
 * 可走格里 21 个如此 → `movementFailure` 全拒 → 一个移动帧都发不出去。
 *
 * 因此这里**不做遮挡判定**，只做可走面（h=1）的精确反投影：把屏幕 y 下移
 * `WALK_HEIGHT * ISO.HH` 再 `isoUnproject`，得到顶面覆盖该点的格。命中阻挡格
 * 或高度不是可走面则返回 null，由调用方转给编辑路径。
 */
export function pickGround(
  px: number,
  py: number,
  w: number,
  h: number,
  heightAt: HeightLookup,
  walkable: (x: number, y: number) => boolean,
): { x: number; y: number } | null {
  if (!Number.isFinite(px) || !Number.isFinite(py)) return null;
  const { x, y } = isoUnproject(px, py + WALK_HEIGHT * ISO.HH, screenBounds(w, h));
  if (x < 0 || y < 0 || x >= w || y >= h) return null;
  if (!walkable(x, y)) return null;
  // 防御：可走格若因资产漂移而非 EARTH 高度，宁可不动也不要把人送到错位格。
  return heightAt(x, y) === WALK_HEIGHT ? { x, y } : null;
}
