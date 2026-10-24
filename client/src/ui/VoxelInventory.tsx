import type { ReactElement } from 'react';
import { useUiStore } from '../store/uiStore';

/** HUD-only stock: never converted into an impulse, prompt, or world event. */
export function VoxelInventory(): ReactElement | null {
  const inventory = useUiStore((s) => s.voxelInventory);
  const error = useUiStore((s) => s.voxelError);
  if (inventory === null && error === null) return null;
  return (
    <div className="pointer-events-none absolute right-3 bottom-3 grid gap-1 text-right text-sm text-[#f0dfb5]">
      {error !== null && (
        <p role="alert" className="rounded bg-[#18140fe6] px-3 py-1">
          {error}
        </p>
      )}
      {inventory !== null && (
        <p
          role="status"
          aria-label="行囊"
          className="rounded border border-[#8c6d42] bg-[#18140fe6] px-3 py-1"
        >
          土 ×{inventory.earth}
        </p>
      )}
    </div>
  );
}
