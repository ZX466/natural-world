import type { ReactElement } from 'react';
import { useUiStore } from '../store/uiStore';

/** HUD-only stock: never converted into an impulse, prompt, or world event. */
export function VoxelInventory(): ReactElement | null {
  const inventory = useUiStore((s) => s.voxelInventory);
  const error = useUiStore((s) => s.voxelError);
  const selected = useUiStore((s) => s.voxelMaterial);
  const rows =
    inventory === null
      ? []
      : [
          { id: 'earth' as const, label: '土', name: '土', count: inventory.earth },
          { id: 'stone' as const, label: '石', name: '石料', count: inventory.stone ?? 0 },
          { id: 'wood' as const, label: '木', name: '木料', count: inventory.wood ?? 0 },
        ];
  const hasStock = rows.some(({ count }) => count > 0);
  if (!hasStock && error === null) return null;
  return (
    <div className="pointer-events-none absolute right-3 bottom-3 grid gap-1 text-right text-sm text-[#f0dfb5]">
      {error !== null && (
        <p role="alert" className="rounded bg-[#18140fe6] px-3 py-1">
          {error}
        </p>
      )}
      {hasStock && (
        <div
          role="status"
          aria-label="行囊"
          className="rounded border border-[#8c6d42] bg-[#18140fe6] px-3 py-1"
        >
          {rows.map(({ id, label, name, count }) => (
            <button
              key={id}
              type="button"
              aria-label={`选择${name}`}
              aria-pressed={selected === id}
              disabled={count === 0}
              onClick={() => useUiStore.getState().setVoxelMaterial(id)}
              className="pointer-events-auto block w-full rounded px-2 text-right aria-pressed:bg-[#755a35] disabled:opacity-40"
            >
              {label} ×{count}
            </button>
          ))}
          <p className="text-xs opacity-70">右键放置，放后挡路</p>
        </div>
      )}
    </div>
  );
}
