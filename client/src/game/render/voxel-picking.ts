import { ISO, depthKey, isoProject, isoUnproject, screenBounds, type HeightLookup } from './iso';

/** Editing picks the visible block column. Short-click movement keeps the
 * existing ground-plane picker, so its established semantics do not change.
 */
export function pickVoxel(
  px: number,
  py: number,
  w: number,
  h: number,
  heightAt: HeightLookup,
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
        // High Images are above the baked low canvas; within each pool use its draw order.
        const rank = (height >= 2 ? 1000000 : 0) + depthKey(x, y);
        if (rank > bestRank) {
          bestRank = rank;
          best = { x, y };
        }
      }
  return best;
}
