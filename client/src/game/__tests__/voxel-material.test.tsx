import { Children, isValidElement, type ReactElement, type ReactNode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useUiStore } from '../../store/uiStore';
import { VoxelInventory } from '../../ui/VoxelInventory';
import { WorldMirror, type VoxelEdit } from '../world-mirror';
import { createHeightLookup, isoProject, screenBounds } from '../render/iso';

vi.mock('phaser', () => ({ default: { Scene: class {} } }));
// Keep the real Zustand actions, only adapt the hook for non-DOM component traversal.
vi.mock('../../store/uiStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../store/uiStore')>();
  return {
    ...actual,
    useUiStore: Object.assign(
      <T,>(select: (state: ReturnType<typeof actual.useUiStore.getState>) => T) =>
        select(actual.useUiStore.getState()),
      actual.useUiStore,
    ),
  };
});
import { WorldScene } from '../scenes/WorldScene';

type Button = ReactElement<{
  children?: ReactNode;
  'aria-label': string;
  'aria-pressed': boolean;
  disabled: boolean;
  onClick(): void;
}>;

function buttons(node: ReactNode): Button[] {
  if (!isValidElement<{ children?: ReactNode }>(node)) return [];
  return [
    ...(node.type === 'button' ? [node as Button] : []),
    ...Children.toArray(node.props.children).flatMap(buttons),
  ];
}

beforeEach(() => {
  useUiStore.setState({ voxelMaterial: 'earth', voxelInventory: null, voxelError: null });
});

it('selects the HUD stone row and the actual scene right-click carries stone', () => {
  useUiStore.getState().setVoxelInventory({ earth: 1, stone: 1, wood: 0 });
  const stone = buttons(VoxelInventory()).find(
    (button) => button.props['aria-label'] === '选择石料',
  );
  expect(stone).toBeDefined();
  stone!.props.onClick();
  expect(useUiStore.getState().voxelMaterial).toBe('stone');
  const mirror = new WorldMirror();
  mirror.setMap({ w: 4, h: 4, tileset: 'grid', collision: new Uint8Array(16).fill(1) });
  mirror.protagonist = 'hero';
  const scene = new WorldScene(mirror, 'iso');
  const emit = vi.fn();
  Object.assign(scene, {
    game: { events: { emit } },
    heightAt: createHeightLookup({ w: 4, h: 4, h_values: new Array(16).fill(1) }),
    goalMarker: null,
  });
  const { sx, sy } = isoProject(0, 3, 1, screenBounds(4, 4));
  (scene as unknown as { handlePointerDown(p: unknown): void }).handlePointerDown({
    worldX: sx,
    worldY: sy,
    button: 2,
    id: 1,
  });
  expect(emit).toHaveBeenCalledWith('client:voxel_request', {
    action: 'place',
    x: 0,
    y: 3,
    material: 'stone',
  });
});

it('disables empty material rows and resets an exhausted or disconnected selection', () => {
  useUiStore.getState().setVoxelInventory({ earth: 1, stone: 2, wood: 0 });
  const wood = buttons(VoxelInventory()).find(
    (button) => button.props['aria-label'] === '选择木料',
  );
  expect(wood?.props.disabled).toBe(true);
  useUiStore.getState().setVoxelMaterial('wood');
  expect(useUiStore.getState().voxelMaterial).toBe('earth');
  useUiStore.getState().setVoxelMaterial('stone');
  useUiStore.getState().setVoxelInventory({ earth: 1, stone: 0 });
  expect(useUiStore.getState().voxelMaterial).toBe('earth');
  useUiStore.getState().setVoxelInventory({ earth: 0, stone: 1 });
  useUiStore.getState().setVoxelMaterial('stone');
  useUiStore.getState().setVoxelInventory(null);
  expect(useUiStore.getState().voxelMaterial).toBe('earth');
});

it('retains material across snapshot replacement and invalidates material-only changes', () => {
  const mirror = new WorldMirror();
  const row = {
    x: 1,
    y: 1,
    action: 'place' as const,
    gid: 0,
    height: 2,
    material: 'stone' as const,
  };
  mirror.applyVoxelEdits([row], true);
  expect(mirror.voxelEdits.get('1,1')?.material).toBe('stone');
  const before = mirror.terrainVersion;
  mirror.applyVoxelEdits([{ ...row, material: 'wood' }]);
  expect(mirror.terrainVersion).toBeGreaterThan(before);
  expect(mirror.voxelEdits.get('1,1')?.material).toBe('wood');
  mirror.applyVoxelEdits([{ ...row, material: 'iron' } as unknown as VoxelEdit]);
  expect(mirror.voxelEdits.get('1,1')?.material).toBe('wood');
  const { material: _material, ...legacy } = row;
  mirror.applyVoxelEdits([legacy], true);
  expect(mirror.voxelEdits.get('1,1')?.material).toBe('earth');
});

it('previews a stocked placement as blocking before any world edit is sent', () => {
  useUiStore.getState().setVoxelInventory({ earth: 1, stone: 1 });
  useUiStore.getState().setVoxelMaterial('stone');
  const mirror = new WorldMirror();
  mirror.setMap({ w: 4, h: 4, tileset: 'grid', collision: new Uint8Array(16).fill(1) });
  const scene = new WorldScene(mirror, 'iso');
  const graphics = {
    clear: vi.fn(),
    lineStyle: vi.fn(),
    strokePoints: vi.fn(),
    lineBetween: vi.fn(),
  };
  Object.assign(scene, {
    heightAt: createHeightLookup({ w: 4, h: 4, h_values: new Array(16).fill(1) }),
    voxelProgress: graphics,
  });
  const { sx, sy } = isoProject(0, 3, 1, screenBounds(4, 4));
  const input = scene as unknown as {
    handlePointerMove(p: unknown): void;
    syncVoxelPresentation(): void;
  };
  input.handlePointerMove({ worldX: sx, worldY: sy, button: 0, id: 1 });
  input.syncVoxelPresentation();
  expect(graphics.strokePoints).toHaveBeenCalledTimes(1);
  expect(graphics.lineBetween).toHaveBeenCalledTimes(2);
  expect(mirror.voxelEdits.size).toBe(0);
  useUiStore.getState().setVoxelInventory(null);
  graphics.strokePoints.mockClear();
  input.syncVoxelPresentation();
  expect(graphics.strokePoints).not.toHaveBeenCalled();
});
