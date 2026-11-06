import { expect, it } from 'vitest';
import { rendererFromSearch, terrainFromSearch } from '../presentation';

it('rendererFromSearch keeps its two modes and ignores terrain', () => {
  // The actor/label renderer is unchanged: three.js is a terrain backend, not
  // a third presentation mode. Everything above the ground stays Phaser.
  expect(rendererFromSearch('')).toBe('iso');
  expect(rendererFromSearch('?renderer=iso')).toBe('iso');
  expect(rendererFromSearch('?renderer=flat')).toBe('flat');
  expect(rendererFromSearch('?terrain=three')).toBe('iso');
  expect(rendererFromSearch('?renderer=flat&terrain=three')).toBe('flat');
});

it('terrainFromSearch defaults to the Phaser painter', () => {
  // Default must stay the shipped path: the flat/iso renderers are rollback
  // insurance and must not change because three.js exists.
  expect(terrainFromSearch('')).toBe('phaser');
  expect(terrainFromSearch('?terrain=phaser')).toBe('phaser');
  expect(terrainFromSearch('?terrain=banana')).toBe('phaser');
  expect(terrainFromSearch('?renderer=flat')).toBe('phaser');
});

it('terrainFromSearch opts into three only on the exact word', () => {
  expect(terrainFromSearch('?terrain=three')).toBe('three');
  expect(terrainFromSearch('?renderer=iso&terrain=three')).toBe('three');
  expect(terrainFromSearch('?terrain=Three')).toBe('phaser');
  expect(terrainFromSearch('?terrain=three.js')).toBe('phaser');
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
