import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
import { createHeightLookup, depthKey, isoProject, screenBounds } from '../render/iso';
import { actorDepth, labelY, aboveSurface } from '../render/presentation';
import { useUiStore } from '../../store/uiStore';

vi.mock('phaser', () => ({ default: { Scene: class {} } }));
import { WorldScene } from '../scenes/WorldScene';

class View {
  texture: { key: string };
  destroyed = false;
  setOrigin = vi.fn(() => this);
  setDepth = vi.fn(() => this);
  setFrame = vi.fn(() => this);
  setAlpha = vi.fn(() => this);
  setScale = vi.fn(() => this);
  setVisible = vi.fn(() => this);
  setPosition = vi.fn((x: number, y: number) => {
    this.x = x;
    this.y = y;
    return this;
  });
  destroy() {
    this.destroyed = true;
  }
  constructor(
    public x: number,
    public y: number,
    key = '',
    public width = 0,
    public height = 0,
  ) {
    this.texture = { key };
  }
}

type ActorView = {
  sprite: View;
  shadow: View;
  label: View;
  lastFacing: string;
  animClockMs: number;
};

function setup(mode: 'flat' | 'iso' = 'iso') {
  const mirror = new WorldMirror();
  mirror.setMap({ w: 4, h: 4, tileset: 'grid', collision: new Uint8Array(16).fill(1) });
  mirror.protagonist = 'hero';
  mirror.actors.set('hero', {
    rtoken: 'hero',
    x: 2,
    y: 1,
    facing: 's',
    sprite: 'protagonist',
    anim: 'idle',
    name: '陈默',
  });
  const heights = new Array<number>(16).fill(1);
  heights[6] = 3;
  const camera = {
    setBounds: vi.fn().mockReturnThis(),
    setZoom: vi.fn().mockReturnThis(),
    startFollow: vi.fn().mockReturnThis(),
    stopFollow: vi.fn(),
  };
  const marker = new View(0, 0);
  const emit = vi.fn((_name: string, _target: unknown, result?: (accepted: boolean) => void) => {
    const target = _target as { x: number; y: number };
    result?.(mirror.map?.collision[target.y * mirror.map.w + target.x] === 1);
  });
  const scene = new WorldScene(mirror, mode);
  Object.assign(scene, {
    heightAt: createHeightLookup({ w: 4, h: 4, h_values: heights }),
    textures: { exists: () => true },
    cameras: { main: camera },
    game: { events: { emit } },
    goalMarker: marker,
    add: {
      sprite: (x: number, y: number, key: string) => new View(x, y, key),
      ellipse: (x: number, y: number, w: number, h: number) => new View(x, y, '', w, h),
      text: (x: number, y: number) => new View(x, y),
    },
  });
  const internal = scene as unknown as {
    views: Map<string, ActorView>;
    syncActorViews(delta: number, time: number): void;
    syncCamera(): void;
    handlePointer(pointer: { worldX: number; worldY: number }): void;
  };
  return { scene, internal, mirror, camera, marker, emit };
}

beforeEach(() => useUiStore.setState({ speed: 1 }));

it('spawns billboard feet at the effective top with a shared depth and contact shadow', () => {
  const { internal } = setup();
  internal.syncActorViews(0, 0);
  const { sprite, shadow, label } = internal.views.get('hero')!;
  const top = isoProject(2, 1, 3, screenBounds(4, 4));
  expect({ x: sprite.x, y: sprite.y }).toEqual({ x: top.sx, y: top.sy });
  expect(sprite.setOrigin).toHaveBeenLastCalledWith(0.5, 1);
  expect(sprite.setDepth).toHaveBeenLastCalledWith(depthKey(2, 1) + 1);
  expect({ x: shadow.x, y: shadow.y, w: shadow.width, h: shadow.height }).toEqual({
    x: top.sx,
    y: top.sy,
    w: 16,
    h: 4,
  });
  expect(shadow.setDepth).toHaveBeenLastCalledWith(depthKey(2, 1) + 0.5);
  expect(label.setPosition).toHaveBeenLastCalledWith(top.sx, aboveSurface(top.sy, 32, 6, 3.5));
});

it('uses the same built/collapsing/rubble height changes for actor feet and camera', () => {
  const { internal, mirror, camera } = setup();
  mirror.applyStructures([{ rtoken: 'house', x: 2, y: 1, phase: 'built' }]);
  internal.syncActorViews(0, 1000);
  internal.syncCamera();
  const built = isoProject(2, 1, 2, screenBounds(4, 4));
  expect(internal.views.get('hero')!.sprite.y).toBe(built.sy);
  expect(camera.startFollow.mock.calls.at(-1)?.[0]).toMatchObject({ x: built.sx, y: built.sy });
  mirror.applyStructures([{ rtoken: 'house', x: 2, y: 1, phase: 'collapsing' }]);
  internal.syncActorViews(0, 1100);
  internal.syncCamera();
  expect(internal.views.get('hero')!.sprite.y).toBe(built.sy);
  mirror.applyStructures([{ rtoken: 'house', x: 2, y: 1, phase: 'rubble' }]);
  internal.syncActorViews(0, 1200);
  internal.syncCamera();
  expect(internal.views.get('hero')!.sprite.y).toBe(isoProject(2, 1, 3, screenBounds(4, 4)).sy);
  expect(camera.startFollow.mock.calls.at(-1)?.[0].y).toBe(internal.views.get('hero')!.sprite.y);
});

it('follows the logical top without crowd offsets and pads the diamond bounds by 64', () => {
  const { internal, mirror, camera } = setup();
  mirror.actors.set('a-neighbour', {
    rtoken: 'a-neighbour',
    x: 2,
    y: 1,
    facing: 's',
    sprite: 'villager',
    anim: 'idle',
  });
  internal.syncActorViews(0, 1000);
  internal.syncCamera();
  const top = isoProject(2, 1, 3, screenBounds(4, 4));
  const target = camera.startFollow.mock.calls.at(-1)?.[0];
  expect(target).toMatchObject({ x: top.sx, y: top.sy });
  expect(target).not.toBe(internal.views.get('hero')!.sprite);
  const bounds = screenBounds(4, 4);
  expect(camera.setBounds).toHaveBeenLastCalledWith(
    -64,
    -64,
    bounds.width + 128,
    bounds.height + 128,
  );
  internal.syncCamera();
  expect(camera.startFollow).toHaveBeenCalledTimes(1);
  mirror.actors.delete('hero');
  internal.syncCamera();
  expect(camera.stopFollow).toHaveBeenCalledTimes(1);
});

it('keeps the walk cycle running for the whole glide, not just the frame a cell changes', () => {
  const { internal, mirror } = setup();
  internal.syncActorViews(16, 0);
  const view = internal.views.get('hero')!;
  // 一格走 250ms；delta 只在换格那一帧到达，其余 14 帧都在插值途中。
  mirror.actors.get('hero')!.y = 2;
  internal.syncActorViews(16, 16); // 换格帧：开始滑行
  const atSnap = view.animClockMs;
  internal.syncActorViews(16, 48);
  internal.syncActorViews(16, 80);
  // 修前：moved 只看「本帧换格」，其余帧归 -1 → 站立帧滑行 = 飘。
  expect(view.animClockMs).toBeGreaterThan(atSnap);
  // 滑行途中必须是走环帧 0（row0south × 17 列），不是站立帧 1。
  expect(view.sprite.setFrame).toHaveBeenLastCalledWith(0);
});

it('returns to the standing frame once the glide lands', () => {
  const { internal, mirror } = setup();
  internal.syncActorViews(16, 0);
  const view = internal.views.get('hero')!;
  mirror.actors.get('hero')!.y = 2;
  internal.syncActorViews(16, 16);
  internal.syncActorViews(16, 300); // k 早已到 1
  expect(view.animClockMs).toBe(-1);
  expect(view.sprite.setFrame).toHaveBeenLastCalledWith(1);
});

it('moves the iso camera with the glide instead of snapping a cell ahead', () => {
  const { internal, mirror, camera } = setup();
  internal.syncActorViews(16, 0);
  internal.syncCamera();
  const target = camera.startFollow.mock.calls.at(-1)?.[0] as { x: number; y: number };
  const before = { x: target.x, y: target.y };
  mirror.actors.get('hero')!.y = 2;
  internal.syncActorViews(16, 48); // 换格帧：滑行开始
  internal.syncActorViews(16, 96); // 滑行到 ~19%
  internal.syncCamera();
  const dest = isoProject(2, 2, 1, screenBounds(4, 4));
  expect(target.y).toBeGreaterThan(before.y);
  expect(target.y).toBeLessThan(dest.sy); // 跟着人物滑，不提前跳到新格
});

it('cleans reset views and recreates them directly at the projected surface', () => {
  const { internal, mirror } = setup();
  internal.syncActorViews(0, 0);
  const previous = internal.views.get('hero')!.sprite;
  mirror.reset();
  mirror.protagonist = 'hero';
  mirror.actors.set('hero', {
    rtoken: 'hero',
    x: 0,
    y: 0,
    facing: 's',
    sprite: 'protagonist',
    anim: 'idle',
  });
  internal.syncActorViews(0, 0);
  expect(previous.destroyed).toBe(true);
  const next = internal.views.get('hero')!.sprite;
  const top = isoProject(0, 0, 1, screenBounds(4, 4));
  expect({ x: next.x, y: next.y }).toEqual({ x: top.sx, y: top.sy });
});

describe.each(['flat', 'iso'] as const)('%s interaction and movement', (mode) => {
  it.each([
    ['hero', 'protagonist', 1, 34],
    ['god', 'god_villager_taocunzhang', 1, 6],
    ['villager', 'villager', 0, 8],
    ['animal', 'fauna_deer', 0, 0],
  ] as const)(
    'preserves visible standing and walking frames for %s',
    (token, sprite, standCol, eastStart) => {
      const { internal, mirror } = setup(mode);
      const actor = { rtoken: token, x: 0, y: 1, facing: 's', sprite, anim: 'idle' };
      mirror.actors.set(token, actor);
      for (const pose of ['idle', 'work', 'eat', 'rest', 'chat', 'unknown']) {
        actor.anim = pose;
        internal.syncActorViews(16, 0);
        const view = internal.views.get(token)!;
        expect(view.sprite.setFrame).toHaveBeenLastCalledWith(standCol);
        expect(view.sprite.setAlpha).toHaveBeenLastCalledWith(
          token === 'animal' && pose === 'rest' ? 0.5 : 1,
        );
      }
      actor.x = 1;
      internal.syncActorViews(150, 150);
      const view = internal.views.get(token)!;
      expect(view.sprite.setFrame).toHaveBeenLastCalledWith(eastStart);
      actor.x = 2;
      internal.syncActorViews(150, 300);
      expect(view.sprite.setFrame).toHaveBeenLastCalledWith(token === 'animal' ? 0 : eastStart + 1);
      internal.syncActorViews(16, 316);
      expect(view.lastFacing).toBe('e');
      // 仍在滑行（k<1）→ 必须继续播走环，不许落回站立帧（站着滑 = 飘）。
      expect(view.animClockMs).toBeGreaterThanOrEqual(0);
      // 滑行到点后回到站立帧。
      internal.syncActorViews(16, 700);
      expect(view.animClockMs).toBe(-1);
      expect(view.sprite.setFrame).toHaveBeenLastCalledWith(eastStart + standCol);
    },
  );

  it('routes visible move intents to preflight and marks only accepted targets on their surface', () => {
    const { internal, mirror, marker, emit } = setup(mode);
    mirror.actors.get('hero')!.x = 0;
    mirror.actors.get('hero')!.y = 0;
    // 目标格必须是生产形状的可走格：不变量 `walkable ⇒ h == 1`（夹具里 (2,1) 是
    // 可走却 h=3 的违规格，只用于高度/镜头用例，不能当移动目标）。
    const goal = { x: 1, y: 1 };
    const hit =
      mode === 'iso' ? isoProject(goal.x, goal.y, 1, screenBounds(4, 4)) : { sx: 16, sy: 16 };
    internal.handlePointer({ worldX: hit.sx, worldY: hit.sy });
    expect(emit).toHaveBeenLastCalledWith('client:move_request', goal, expect.any(Function));
    const markerPos =
      mode === 'iso'
        ? isoProject(goal.x, goal.y, 1, screenBounds(4, 4))
        : { sx: goal.x * 16 + 8, sy: goal.y * 16 + 8 };
    expect(marker.setPosition).toHaveBeenLastCalledWith(markerPos.sx, markerPos.sy);
    if (mode === 'iso') {
      expect(marker.setDepth).toHaveBeenLastCalledWith(depthKey(goal.x, goal.y) + 1.5);
    } else {
      expect(marker.setDepth).not.toHaveBeenCalled(); // flat keeps the depth created at create().
    }
    emit.mockClear();
    marker.setVisible.mockClear();
    // 本地预检拒绝：可走性判在拾取阶段（`groundTarget` 只返回可走格），
    // 阻挡格与界外都不发网络帧——世界真相仍只由 sim 决定。
    mirror.map!.collision[goal.y * 4 + goal.x] = 0;
    internal.handlePointer({ worldX: hit.sx, worldY: hit.sy });
    internal.handlePointer({ worldX: -10000, worldY: -10000 });
    expect(emit).not.toHaveBeenCalled();
    expect(marker.setVisible).not.toHaveBeenCalledWith(true);
  });

  it('preserves four-way facing, the existing walk clock, and animation frames', () => {
    const { internal, mirror } = setup(mode);
    internal.syncActorViews(0, 0);
    mirror.actors.get('hero')!.x = 3;
    internal.syncActorViews(16, 100);
    internal.syncActorViews(0, 350);
    const view = internal.views.get('hero')!;
    expect(view.lastFacing).toBe('e');
    expect(view.sprite.setFrame).toHaveBeenCalledWith(34); // 陈默朝东走环首帧：row2 × 17列。
    const target = mode === 'iso' ? isoProject(3, 1, 1, screenBounds(4, 4)) : { sx: 56, sy: 24 };
    expect({ x: view.sprite.x, y: view.sprite.y }).toEqual({ x: target.sx, y: target.sy });
  });
});

it('preserves flat sprite, shadow, and camera formulas', () => {
  const { internal, camera } = setup('flat');
  internal.syncActorViews(0, 1000);
  internal.syncCamera();
  const { sprite, shadow } = internal.views.get('hero')!;
  expect({ x: sprite.x, y: sprite.y }).toEqual({ x: 40, y: 24 });
  expect(sprite.setDepth).toHaveBeenLastCalledWith(actorDepth(24));
  expect({ x: shadow.x, y: shadow.y, w: shadow.width, h: shadow.height }).toEqual({
    x: 40,
    y: 23,
    w: 10,
    h: 4,
  });
  expect(camera.startFollow).toHaveBeenLastCalledWith(sprite, true, 0.12, 0.12);
  expect(camera.setBounds).toHaveBeenLastCalledWith(0, 0, 64, 64);
  expect(camera.setZoom).toHaveBeenLastCalledWith(3.5);
  expect(internal.views.get('hero')!.label.setPosition).toHaveBeenLastCalledWith(
    sprite.x,
    labelY(sprite.y),
  );
});
