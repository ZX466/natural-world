/**
 * client/src/ui/save-names.ts — 存档默认名（主树 D6-②）。
 *
 * 旧实现按 `items.length + 1` 起名 ⇒ 删档后编号回退，会造出两个「游历 3」。
 * 正确契约：取现存默认名里的**最大编号 + 1**，与列表长度无关。
 * 只认 `游历 <正整数>` 形状；玩家自定义名（含「游历 外传」这类）不参与编号。
 */
const DEFAULT_NAME_PATTERN = /^游历\s+(\d+)$/;

export function nextSaveName(items: readonly { name: string }[]): string {
  let max = 0;
  for (const item of items) {
    const match = DEFAULT_NAME_PATTERN.exec(item.name);
    if (match === null) continue;
    const raw = match[1];
    if (raw === undefined) continue;
    const n = Number.parseInt(raw, 10);
    if (Number.isFinite(n) && n > max) max = n;
  }
  return `游历 ${max + 1}`;
}
