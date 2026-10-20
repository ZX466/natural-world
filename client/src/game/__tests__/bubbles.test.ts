import { expect, it, vi } from 'vitest';
import { WorldMirror } from '../world-mirror';
import { MAX_VISIBLE_BUBBLES } from '../presentation';

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
