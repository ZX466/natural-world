import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
const data = vi.hoisted(() => ({
  inventory: null as { earth: number } | null,
  error: null as string | null,
}));
vi.mock('../../store/uiStore', () => ({
  useUiStore: (select: (state: unknown) => unknown) =>
    select({
      voxelInventory: data.inventory,
      voxelError: data.error,
    }),
}));
import { VoxelInventory } from '../VoxelInventory';

it('hides unknown inventory and displays only the received earth count', () => {
  data.inventory = null;
  data.error = null;
  expect(renderToStaticMarkup(<VoxelInventory />)).toBe('');
  data.inventory = { earth: 3 };
  const html = renderToStaticMarkup(<VoxelInventory />);
  expect(html).toContain('土 ×3');
  expect(html).toContain('行囊');
});

it('presents the server diegetic rejection alongside inventory', () => {
  data.inventory = { earth: 0 };
  data.error = '离得太远，够不着那里。';
  const html = renderToStaticMarkup(<VoxelInventory />);
  expect(html).toContain('role="alert"');
  expect(html).toContain(data.error);
});
