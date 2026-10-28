import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
const data = vi.hoisted(() => ({
  inventory: null as { earth: number; stone?: number; wood?: number } | null,
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

it('shows the three nonzero materials as separate ordered rows', () => {
  data.inventory = { earth: 2, stone: 3, wood: 4 };
  data.error = null;
  const html = renderToStaticMarkup(<VoxelInventory />);
  expect(html).toContain('土 ×2');
  expect(html).toContain('石 ×3');
  expect(html).toContain('木 ×4');
  expect(html.indexOf('土 ×2')).toBeLessThan(html.indexOf('石 ×3'));
  expect(html.indexOf('石 ×3')).toBeLessThan(html.indexOf('木 ×4'));
  expect(html.match(/<p/g)).toHaveLength(3);
});

it('hides zero rows while keeping nonzero optional stock visible', () => {
  data.inventory = { earth: 0, stone: 2, wood: 0 };
  data.error = null;
  const html = renderToStaticMarkup(<VoxelInventory />);
  expect(html).toContain('石 ×2');
  expect(html).not.toContain('土 ×');
  expect(html).not.toContain('木 ×');
});

it('treats absent optional materials as zero and hides a fully empty bag', () => {
  data.error = null;
  data.inventory = { earth: 0 };
  expect(renderToStaticMarkup(<VoxelInventory />)).toBe('');
  data.inventory = { earth: 0, stone: 0, wood: 0 };
  expect(renderToStaticMarkup(<VoxelInventory />)).toBe('');
});
