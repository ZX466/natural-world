import { expect, it } from 'vitest';
import { avatars3dFromSearch, rendererFromSearch, terrainFromSearch } from '../presentation';

it('rendererFromSearch keeps its two modes and ignores terrain', () => {
  // The actor/label renderer is unchanged: three.js is a terrain backend, not
  // a third presentation mode. Everything above the ground stays Phaser.
  expect(rendererFromSearch('')).toBe('iso');
  expect(rendererFromSearch('?renderer=iso')).toBe('iso');
  expect(rendererFromSearch('?renderer=flat')).toBe('flat');
  expect(rendererFromSearch('?terrain=three')).toBe('iso');
  expect(rendererFromSearch('?renderer=flat&terrain=three')).toBe('flat');
});

it('terrainFromSearch defaults to the three world', () => {
  // The user accepted the perspective world on 2026-11-07, so it is now what
  // the game boots into; the Phaser painter is the rollback path, not the
  // default. `?renderer=` must not move this switch.
  expect(terrainFromSearch('')).toBe('three');
  expect(terrainFromSearch('?renderer=flat')).toBe('three');
  expect(terrainFromSearch('?renderer=iso')).toBe('three');
  expect(terrainFromSearch('?terrain=banana')).toBe('three');
});

it('terrainFromSearch falls back to Phaser only on the exact word', () => {
  expect(terrainFromSearch('?terrain=phaser')).toBe('phaser');
  expect(terrainFromSearch('?renderer=iso&terrain=phaser')).toBe('phaser');
  expect(terrainFromSearch('?renderer=flat&terrain=phaser')).toBe('phaser');
  expect(terrainFromSearch('?terrain=Phaser')).toBe('three');
});

it('terrainFromSearch accepts the explicit three word too', () => {
  expect(terrainFromSearch('?terrain=three')).toBe('three');
  expect(terrainFromSearch('?renderer=iso&terrain=three')).toBe('three');
});

it('avatars3dFromSearch is off unless the flag is exactly "1"', () => {
  // The 3D avatars are opt-in so the shipped 2D sheets stay the default until
  // the user accepts the look. Only the exact value "1" turns them on.
  expect(avatars3dFromSearch('')).toBe(false);
  expect(avatars3dFromSearch('?avatar3d=0')).toBe(false);
  expect(avatars3dFromSearch('?avatar3d=true')).toBe(false);
  expect(avatars3dFromSearch('?avatar3d=1')).toBe(true);
  expect(avatars3dFromSearch('?avatar3d=1&terrain=phaser')).toBe(true);
});

it('the avatar switch is independent of the terrain and renderer switches', () => {
  // `?avatar3d=1` only affects the three path; the parser itself does not care
  // which terrain is selected, so the two stay separable in tests and in URLs.
  const combos = [
    ['', 'iso', 'three', false],
    ['?avatar3d=1', 'iso', 'three', true],
    ['?renderer=flat&terrain=phaser', 'flat', 'phaser', false],
    ['?renderer=flat&terrain=phaser&avatar3d=1', 'flat', 'phaser', true],
  ] as const;
  for (const [search, renderer, terrain, avatars3d] of combos) {
    expect(rendererFromSearch(search)).toBe(renderer);
    expect(terrainFromSearch(search)).toBe(terrain);
    expect(avatars3dFromSearch(search)).toBe(avatars3d);
  }
});

it('the two switches are independent', () => {
  const combos = [
    ['?renderer=flat&terrain=three', 'flat', 'three'],
    ['?renderer=flat&terrain=phaser', 'flat', 'phaser'],
    ['?renderer=iso&terrain=three', 'iso', 'three'],
    ['?renderer=iso&terrain=phaser', 'iso', 'phaser'],
  ] as const;
  for (const [search, renderer, terrain] of combos) {
    expect(rendererFromSearch(search)).toBe(renderer);
    expect(terrainFromSearch(search)).toBe(terrain);
  }
});
