import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { WorldMirror, type MapStatic } from '../../world-mirror';
import fixture from './fixtures/initial-visibility.json';
import { VISION_RADIUS, lineBlocked, pointVisible, visibleActorTokens } from '../visibility';

function grid(w = 30, h = 30): MapStatic {
  return { w, h, tileset: 'grid', collision: new Uint8Array(w * h).fill(1) };
}

it('pins the visual radius to the server human profile', () => {
  const human = readFileSync(
    new URL('../../../../../sim/perception/profiles/human.py', import.meta.url),
    'utf8',
  );
  expect(VISION_RADIUS).toBe(Number(/vision_radius\s*=\s*([\d.]+)/.exec(human)![1]));
});

it('ports endpoint exclusion and the original directional Bresenham tie rule', () => {
  const map = grid(5, 5);
  map.collision[6] = 0;
  expect(lineBlocked(map, { x: 0, y: 0 }, { x: 2, y: 1 })).toBe(true);
  expect(lineBlocked(map, { x: 2, y: 1 }, { x: 0, y: 0 })).toBe(false);
  map.collision[18] = 0;
  expect(lineBlocked(map, { x: 1, y: 1 }, { x: 3, y: 3 })).toBe(false);
  expect(lineBlocked(map, { x: 1, y: 1 }, { x: 1, y: 1 })).toBe(false);
  map.collision[12] = 0;
  expect(lineBlocked(map, { x: 1, y: 1 }, { x: 3, y: 3 })).toBe(true);
  expect(lineBlocked(map, { x: NaN, y: 1 }, { x: 3, y: 3 })).toBe(true);
});

it('uses Euclidean range, includes the radius boundary and rejects unseen cells', () => {
  const map = grid();
  const hero = { x: 15, y: 15 };
  expect(pointVisible(map, hero, { x: 23, y: 23 })).toBe(true);
  expect(pointVisible(map, hero, { x: 27, y: 15 })).toBe(true);
  expect(pointVisible(map, hero, { x: 24, y: 24 })).toBe(false);
  map.collision[15 * 30 + 16] = 0;
  expect(pointVisible(map, hero, { x: 17, y: 15 })).toBe(false);
});

it('keeps the protagonist present while hiding everyone when their viewpoint is missing', () => {
  const mirror = new WorldMirror();
  mirror.setMap(grid());
  mirror.protagonist = 'hero';
  mirror.applySnapshot(
    [
      { rtoken: 'hero', x: 15, y: 15, facing: 's' as const, sprite: 'protagonist', anim: 'idle' },
      { rtoken: 'far', x: 0, y: 0, facing: 's' as const, sprite: 'villager', anim: 'idle' },
    ],
    [],
  );
  expect([...visibleActorTokens(mirror)]).toEqual(['hero']);
  mirror.protagonist = 'missing';
  expect(visibleActorTokens(mirror).size).toBe(0);
  expect(mirror.actors.size).toBe(2); // Rendering never removes authoritative actor data.
});

it('measures real-map walls/open street and the real 50-villager initial roster', () => {
  const town = JSON.parse(
    readFileSync(new URL('../../../../../sim/content/linhe-town.json', import.meta.url), 'utf8'),
  ) as { width: number; height: number; chunks: Record<string, { collision: boolean[] }> };
  const map = grid(town.width, town.height);
  map.collision.fill(0);
  for (const [key, chunk] of Object.entries(town.chunks)) {
    const [cx, cy] = key.split(',').map(Number);
    const side = Math.sqrt(chunk.collision.length);
    chunk.collision.forEach((walk, index) => {
      const x = cx! * side + (index % side),
        y = cy! * side + Math.floor(index / side);
      if (x < map.w && y < map.h) map.collision[y * map.w + x] = Number(walk);
    });
  }
  const hero = { x: 100, y: 53 };
  expect(pointVisible(map, hero, { x: 100, y: 52 })).toBe(true);
  expect(lineBlocked(map, hero, { x: 100, y: 41 })).toBe(true);
  expect(pointVisible(map, hero, { x: 100, y: 41 })).toBe(false);
  const mirror = new WorldMirror();
  mirror.setMap(map);
  mirror.protagonist = 'hero';
  mirror.applySnapshot(
    [
      { rtoken: 'hero', ...hero, facing: 's' as const, sprite: 'protagonist', anim: 'idle' },
      ...fixture.actors.map(([token, x, y]) => ({
        rtoken: String(token),
        x: Number(x),
        y: Number(y),
        facing: 's' as const,
        sprite: 'villager',
        anim: 'idle',
      })),
    ],
    [],
  );
  const visible = visibleActorTokens(mirror);
  expect([...visible].sort()).toEqual(['hero', ...fixture.expectedVisible].sort());
  expect(visible.size).toBe(10);
  console.log(
    `Real 140x100 map: ${visible.size}/${mirror.actors.size} actors visible; open street (100,52) yes, behind walls (100,41) no.`,
  );
});
