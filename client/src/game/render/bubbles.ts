/** 头顶气泡的显示预算与简单避让；世界镜像保持原样。 */
export const MAX_VISIBLE_BUBBLES = 4;
const BUBBLE_GAP = 4;

export function selectBubbleNames(
  bubbles: ReadonlyMap<string, { readonly expiresAt: number }>,
  protagonistName: string | undefined,
): string[] {
  return [...bubbles]
    .sort(([a, left], [b, right]) => {
      if (a === protagonistName) return -1;
      if (b === protagonistName) return 1;
      return right.expiresAt - left.expiresAt || a.localeCompare(b);
    })
    .slice(0, MAX_VISIBLE_BUBBLES)
    .map(([name]) => name);
}

interface BubbleBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** x 居中、y 底对齐，与 Phaser Text 的 origin(0.5, 1) 一致。 */
export function placeBubble(
  box: BubbleBox,
  placed: readonly BubbleBox[],
  gap = BUBBLE_GAP,
): BubbleBox {
  const result = { ...box };
  while (true) {
    const overlaps = placed.filter(
      (other) =>
        Math.abs(result.x - other.x) < (result.width + other.width) / 2 + gap &&
        result.y > other.y - other.height - gap &&
        result.y - result.height < other.y + gap,
    );
    if (overlaps.length === 0) return result;
    result.y = Math.min(...overlaps.map((other) => other.y - other.height)) - gap;
  }
}
