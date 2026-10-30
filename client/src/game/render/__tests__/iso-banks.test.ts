import type Phaser from 'phaser';
import { readFileSync } from 'node:fs';
import { afterEach, expect, expectTypeOf, it, vi } from 'vitest';
import { IsoTerrain } from '../iso-terrain';
import { createHeightLookup, depthKey, isoProject, screenBounds, type VoxelEdits } from '../iso';
import { WorldMirror, type MapStatic, type VoxelEdit } from '../../world-mirror';

type Point = { x: number; y: number };
type Face = { color: number; alpha: number; points: Point[] };

/** Lightweight draw-command adapter: no browser/canvas renderer or per-tile spies. */
class View {
  destroyed = false;
  alpha = 1;
  depth = 0;
  x = 0;
  y = 0;
  moves = 0;
  clears = 0;
  color = 0;
  fillAlpha = 1;
  faces: Face[] = [];
  setOrigin() { return this; }
  setTexture() { return this; }
  setDisplaySize() { return this; }
  setTint() { return this; }
  setDepth(depth: number) { this.depth = depth; return this; }
  setAlpha(alpha: number) { this.alpha = alpha; return this; }
  setPosition(x: number, y: number) { this.x = x; this.y = y; this.moves++; return this; }
  clear() { this.faces = []; this.clears++; return this; }
  fillStyle(color: number, alpha: number) { this.color = color; this.fillAlpha = alpha; return this; }
  fillPoints(points: Point[]) {
    this.faces.push({color: this.color, alpha: this.fillAlpha, points: points.map(p => ({...p}))});
    return this;
  }
  destroy() { this.destroyed = true; }
}

function setup(heights = [1, 1, 2, 0], w = 2, h = 2) {
  const graphics: View[] = [];
  const textures = new Set<string>();
  const noop = () => {};
  const context = { beginPath: noop, moveTo: noop, lineTo: noop, closePath: noop, fill: noop, clearRect: noop, save: noop, restore: noop, rect: noop, clip: noop, fillStyle: '' };
  vi.stubGlobal('document', { createElement: () => ({ width: 0, height: 0, getContext: () => context }) });
  const scene = {
    textures: {
      exists: (key: string) => textures.has(key),
      addCanvas: (key: string) => { textures.add(key); return { refresh: noop }; },
      remove: (key: string) => textures.delete(key),
    },
    add: {
      graphics: () => { const marker = new View(); graphics.push(marker); return marker; },
      image: () => new View(),
    },
  };
  const map: MapStatic = { w, h, tileset: 'grid', collision: new Uint8Array(w*h).fill(1), ground: new Uint16Array(w*h).fill(7) };
  map.collision[0] = 0;
  const structures = new Map<string, {tiles: [number, number][]; phase: string}>();
  const edits = new Map<string, VoxelEdit>();
  const terrain = new IsoTerrain(scene as unknown as Phaser.Scene, createHeightLookup({w,h,h_values:heights}));
  const markers = () => graphics.filter(marker => !marker.destroyed);
  return {terrain, map, structures, edits, graphics, markers};
}

const bankFaces = (marker: View) => marker.faces.filter(face => face.alpha === 1);
const luma = (color: number) => 0.2126*(color>>16) + 0.7152*((color>>8)&255) + 0.0722*(color&255);
afterEach(() => vi.unstubAllGlobals());

it('shares one protocol-derived readonly height/action type across geometry and terrain', () => {
  expectTypeOf<VoxelEdits>().toEqualTypeOf<ReadonlyMap<string, Pick<VoxelEdit, 'height' | 'action'>>>();
  expectTypeOf<NonNullable<Parameters<IsoTerrain['sync']>[2]>>().toEqualTypeOf<VoxelEdits>();
});

it('marks only blocked height-one surfaces, with three contrasting slats inside the top face', () => {
  const {terrain,map,structures,markers} = setup();
  map.collision[2] = map.collision[3] = 0;
  const collision = map.collision.slice();
  terrain.redraw(map, structures);
  expect(map.collision).toEqual(collision);
  expect(markers()).toHaveLength(1);
  const marker = markers()[0]!;
  const top = isoProject(0,0,1,screenBounds(2,2));
  expect(marker).toMatchObject({x:top.sx,y:top.sy,depth:depthKey(0,0)+0.5});
  expect(bankFaces(marker)).toHaveLength(6); // Three dark slats, each with a light center.
  const colors = new Set(marker.faces.map(face=>face.color));
  expect(colors.size).toBe(2);
  expect(colors.has(0x3f3020)).toBe(false); // Existing inset-diamond scar ink.
  const luminances = [...colors].map(luma);
  expect(Math.abs(luminances[0]!-luminances[1]!)).toBeGreaterThan(150);
  for (const face of marker.faces) for (const point of face.points)
    expect(Math.abs(point.x)/16+Math.abs(point.y)/8).toBeLessThan(1);
  const [a,b] = marker.faces[0]!.points;
  expect(Math.hypot(a!.x-b!.x,a!.y-b!.y)*3.5).toBeGreaterThan(7);
});

it('removes and recreates banks when collision alone changes at the same height and color', () => {
  const {terrain,map,structures,markers} = setup();
  terrain.redraw(map, structures, undefined, 1);
  const bank = markers()[0];
  expect(bank).toBeDefined();
  map.collision[0] = 1;
  terrain.sync(map, structures, undefined, 2);
  expect(bank!.destroyed).toBe(true);
  expect(markers()).toHaveLength(0);
  map.collision[0] = 0;
  terrain.sync(map, structures, undefined, 3);
  expect(markers()).toHaveLength(1);
  expect(markers()[0]).not.toBe(bank);
});

it('uses either a bank or a scar on a dug height-one cell, retaining scar appearance after it opens', () => {
  const {terrain,map,structures,edits,markers} = setup();
  edits.set('0,0', {x:0,y:0,action:'dig',gid:0,height:1});
  terrain.redraw(map, structures, edits, 1);
  expect(markers()).toHaveLength(1);
  expect(bankFaces(markers()[0]!)).toHaveLength(6);
  map.collision[0] = 1;
  edits.set('0,0', {x:0,y:0,action:'dig',gid:7,height:1});
  terrain.sync(map, structures, edits, 2);
  expect(markers()).toHaveLength(1);
  expect(markers()[0]!.faces).toMatchObject([{color:0x3f3020,alpha:0.55}]);
});

it('removes a bank when digging reaches zero and restores it with an empty snapshot', () => {
  const {terrain,map,structures,markers} = setup();
  const mirror = new WorldMirror();
  mirror.setMap(map);
  terrain.redraw(map, structures, mirror.voxelEdits, mirror.terrainVersion);
  const bank = markers()[0];
  expect(bank).toBeDefined();
  mirror.applyVoxelEdits([{x:0,y:0,action:'dig',gid:0,height:0}]);
  terrain.sync(map, structures, mirror.voxelEdits, mirror.terrainVersion);
  expect(markers()).toHaveLength(0);
  expect(map.collision[0]).toBe(0); // Visual fix never opens a dug-out bank.
  mirror.applyVoxelEdits([], true);
  terrain.sync(map, structures, mirror.voxelEdits, mirror.terrainVersion);
  expect(markers()).toHaveLength(1);
});

it('cleans bank overlays for active structures, map replacement and shutdown', () => {
  const {terrain,map,structures,markers} = setup();
  terrain.redraw(map, structures);
  expect(markers()).toHaveLength(1);
  structures.set('house', {tiles:[[0,0]],phase:'built'});
  terrain.sync(map, structures);
  expect(markers()).toHaveLength(0);
  structures.clear();
  terrain.sync(map, structures);
  expect(markers()).toHaveLength(1);
  const replacement = {...map,w:1,h:4};
  terrain.sync(replacement, structures);
  const top = isoProject(0,0,1,screenBounds(1,4));
  expect(markers()[0]).toMatchObject({x:top.sx,y:top.sy});
  terrain.sync(null, structures);
  expect(markers()).toHaveLength(0);
  terrain.redraw(map, structures);
  expect(markers()).toHaveLength(1);
  terrain.destroy();
  expect(markers()).toHaveLength(0);
});

it('reuses bank geometry through changed-false frames and unrelated terrain edits', () => {
  const {terrain,map,structures,edits,markers,graphics} = setup();
  terrain.redraw(map, structures, edits, 1);
  const bank = markers()[0];
  expect(bank).toBeDefined();
  const clears = bank!.clears, moves = bank!.moves;
  terrain.sync(map, structures, edits, 2); // New version, identical surface.
  expect(bank!.clears).toBe(clears);
  expect(bank!.moves).toBe(moves);
  edits.set('0,1', {x:0,y:1,action:'place',gid:0,height:3});
  terrain.sync(map, structures, edits, 3);
  expect(markers()[0]).toBe(bank);
  expect(bank!.clears).toBe(clears);
  expect(graphics).toHaveLength(1);
});

it('marks every real-map bank, covers both neighborhoods, and does no collision work for 120 idle frames', () => {
  const root = new URL('../../../../../', import.meta.url);
  const source = JSON.parse(readFileSync(new URL('sim/content/linhe-town.json',root),'utf8')) as {
    width:number; height:number; chunks:Record<string,{ground:number[];collision:boolean[]}>;
  };
  const heights = JSON.parse(readFileSync(new URL('client/public/assets/tilesets/linhe-height.json',root),'utf8')) as {h_values:number[]};
  const {terrain,map,structures,markers,graphics} = setup(heights.h_values,source.width,source.height);
  for (const [key,chunk] of Object.entries(source.chunks)) {
    const [cx,cy] = key.split(',').map(Number);
    const side = Math.sqrt(chunk.collision.length);
    expect(side).toBe(16);
    for (let i=0;i<chunk.collision.length;i++) {
      const x=cx!*side+i%side, y=cy!*side+Math.floor(i/side);
      if(x>=map.w||y>=map.h) continue;
      map.collision[y*map.w+x] = Number(chunk.collision[i]);
      map.ground![y*map.w+x] = chunk.ground[i]!;
    }
  }
  const original = map.collision.slice();
  terrain.redraw(map, structures, undefined, 1);
  const byPosition = new Map(markers().map(marker=>[`${marker.x},${marker.y}`,marker]));
  let banks=0,walkable=0,adjacent=0,requestedArea=0,currentArea=0;
  for(let y=0;y<map.h;y++) for(let x=0;x<map.w;x++) {
    const i=y*map.w+x;
    const top=isoProject(x,y,1,screenBounds(map.w,map.h));
    const marked=byPosition.has(`${top.sx},${top.sy}`);
    const expected=heights.h_values[i]===1&&map.collision[i]===0;
    expect(marked,`${x},${y}`).toBe(expected);
    if(map.collision[i]===1)walkable++;
    if(!expected)continue;
    banks++;
    if(Math.abs(x-14)<=15&&Math.abs(y-17)<=15)requestedArea++;
    if(Math.abs(x-100)<=15&&Math.abs(y-53)<=15)currentArea++;
    if([[1,0],[-1,0],[0,1],[0,-1]].some(([dx,dy])=>x+dx!>=0&&y+dy!>=0&&x+dx!<map.w&&y+dy!<map.h&&map.collision[(y+dy!)*map.w+x+dx!]===1))adjacent++;
  }
  expect({banks,walkable,adjacent,requestedArea,currentArea}).toEqual({banks:1568,walkable:3947,adjacent:269,requestedArea:57,currentArea:135});
  expect(markers()).toHaveLength(banks);
  expect(map.collision).toEqual(original);
  let reads=0;
  map.collision = new Proxy(map.collision,{get(target,key){if(typeof key==='string'&&/^\d+$/.test(key))reads++;return Reflect.get(target,key,target);}});
  const drawCalls=markers().reduce((n,marker)=>n+marker.clears,0);
  const moves=markers().reduce((n,marker)=>n+marker.moves,0);
  for(let frame=0;frame<120;frame++)terrain.sync(map,structures,undefined,1);
  expect(reads).toBe(0);
  expect(graphics).toHaveLength(banks);
  expect(markers().reduce((n,marker)=>n+marker.clears,0)).toBe(drawCalls);
  expect(markers().reduce((n,marker)=>n+marker.moves,0)).toBe(moves);
  terrain.sync(map,structures,undefined,2);
  expect(markers().reduce((n,marker)=>n+marker.clears,0)).toBe(drawCalls);
  expect(markers().reduce((n,marker)=>n+marker.moves,0)).toBe(moves);
  console.info(JSON.stringify({banks,walkable,adjacent,requestedArea,currentArea,idle_frames:120,idle_collision_reads:0,idle_marker_creations:0,idle_marker_redraws:0,changed_false_marker_updates:0}));
});
