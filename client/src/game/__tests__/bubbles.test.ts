import { expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
import { MAX_VISIBLE_BUBBLES } from '../render/bubbles';

vi.mock('phaser', () => ({ default: { Scene: class {} } }));

import { WorldScene } from '../scenes/WorldScene';

class Text {
  x = 0;
  y = 0;
  width = 140;
  height = 24;
  destroyed = false;
  constructor(public text: string) {}
  setOrigin() {
    return this;
  }
  setDepth() {
    return this;
  }
  setScale() {
    return this;
  }
  setPosition(x: number, y: number) {
    this.x = x;
    this.y = y;
    return this;
  }
  setText(text: string) {
    this.text = text;
    return this;
  }
  destroy() {
    this.destroyed = true;
  }
}

function crowdedScene() {
  const mirror = new WorldMirror();
  const scene = Object.create(WorldScene.prototype) as {
    mirror: WorldMirror;
    views: Map<string, { sprite: { x: number; y: number } }>;
    bubbleTexts: Map<string, Text>;
    add: { text(x: number, y: number, content: string): Text };
    syncBubbles(now: number): void;
  };
  Object.assign(scene, {
    mirror,
    views: new Map(),
    bubbleTexts: new Map(),
    add: { text: (_x: number, _y: number, content: string) => new Text(content) },
  });
  for (let i = 0; i < 10; i++) {
    const name = `npc${i}`;
    mirror.actors.set(name, {
      rtoken: name,
      name,
      x: 0,
      y: 0,
      facing: 'S',
      sprite: 'villager',
      anim: 'idle',
    });
    mirror.setBubble(name, `line${i}`, 100 + i, 0);
    scene.views.set(name, { sprite: { x: 100, y: 100 } });
  }
  return scene;
}

it('caps the actual Text pool and drops bubbles closest to expiry', () => {
  const scene = crowdedScene();
  scene.syncBubbles(1);
  expect(MAX_VISIBLE_BUBBLES).toBe(4);
  expect(scene.bubbleTexts.size).toBeLessThanOrEqual(MAX_VISIBLE_BUBBLES);
  expect([...scene.bubbleTexts.keys()].sort()).toEqual(['npc6', 'npc7', 'npc8', 'npc9']);
});

it('retains the protagonist even when their bubble expires first', () => {
  const scene = crowdedScene();
  scene.mirror.protagonist = 'npc0';
  scene.syncBubbles(1);
  expect([...scene.bubbleTexts.keys()].sort()).toEqual(['npc0', 'npc7', 'npc8', 'npc9']);
});

it('stacks overlapping bubbles and destroys texts that leave the retained set', () => {
  const scene = crowdedScene();
  scene.syncBubbles(1);
  const texts = [...scene.bubbleTexts.values()];
  expect(new Set(texts.map((text) => text.y)).size).toBe(texts.length);
  for (let i = 1; i < texts.length; i++) {
    expect(Math.abs(texts[i]!.y - texts[i - 1]!.y)).toBeGreaterThanOrEqual(24);
  }
  scene.mirror.bubbles.clear();
  scene.syncBubbles(1);
  expect(scene.bubbleTexts.size).toBe(0);
  expect(texts.every((text) => text.destroyed)).toBe(true);
});

// 复用此文件已有的 Scene 加载适配；执行真实 syncStructures，钉实际绘图调用。
function structureScene() {
  const mirror = new WorldMirror();
  const graphics = { clear: vi.fn(), fillStyle: vi.fn(), fillRect: vi.fn() };
  const scene = Object.create(WorldScene.prototype) as {
    syncStructures(): void;
  };
  Object.assign(scene, { mirror, structureLayer: graphics });
  mirror.applyStructures([{ rtoken: 'st-s1', x: 3, y: 4, phase: 'built' }]);
  scene.syncStructures();
  expect(graphics.fillStyle).toHaveBeenLastCalledWith(0x6b4f2a, 0.92);
  return { mirror, graphics, scene };
}

it('redraws a same-count structure phase change with rubble opacity', () => {
  const { mirror, graphics, scene } = structureScene();
  scene.syncStructures();
  expect(graphics.clear).toHaveBeenCalledTimes(1);
  mirror.applyStructures([{ rtoken: 'st-s1', x: 3, y: 4, phase: 'rubble' }]);
  scene.syncStructures();
  expect(graphics.clear).toHaveBeenCalledTimes(2);
  expect(graphics.fillStyle).toHaveBeenLastCalledWith(0x6b4f2a, 0.5);
});

it('redraws replaced tiles and clears the layer on an empty snapshot', () => {
  const { mirror, graphics, scene } = structureScene();
  mirror.structures.set('st-s1', { tiles: [[8, 9]], phase: 'built' });
  scene.syncStructures();
  expect(graphics.clear).toHaveBeenCalledTimes(2);
  expect(graphics.fillRect).toHaveBeenLastCalledWith(8 * 16, 9 * 16, 15, 15);
  mirror.structures.clear();
  scene.syncStructures();
  expect(graphics.clear).toHaveBeenCalledTimes(3);
});
