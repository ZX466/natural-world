import type { ReactElement } from 'react';
import { useUiStore } from '../store/uiStore';

/** HUD-only stock: never converted into an impulse, prompt, or world event. */
export function VoxelInventory(): ReactElement | null {
  const inventory = useUiStore((s) => s.voxelInventory);
  const error = useUiStore((s) => s.voxelError);
  const rows =
    inventory === null
      ? []
      : [
          { id: 'earth', label: '土', count: inventory.earth },
          { id: 'stone', label: '石', count: inventory.stone ?? 0 },
          { id: 'wood', label: '木', count: inventory.wood ?? 0 },
        ].filter(({ count }) => count > 0);
  if (rows.length === 0 && error === null) return null;
  return (
    <div className="pointer-events-none absolute right-3 bottom-3 grid gap-1 text-right text-sm text-[#f0dfb5]">
      {error !== null && (
        <p role="alert" className="rounded bg-[#18140fe6] px-3 py-1">
          {error}
        </p>
      )}
      {rows.length > 0 && (
        <div
          role="status"
          aria-label="行囊"
          className="rounded border border-[#8c6d42] bg-[#18140fe6] px-3 py-1"
        >
          {rows.map(({ id, label, count }) => (
            <p key={id}>
              {label} ×{count}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
