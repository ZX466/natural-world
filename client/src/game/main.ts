/**
 * client/src/game/main.ts — Phaser.Game 装配（m0-client.md §2）。
 * parent=CanvasHost div（唯一 DOM 交界）；WorldScene 拿 WorldMirror。
 * 场景 → runtime 的出站桥：WorldScene emit 'client:move_request'（M0-C04 起），
 * 此处唯一监听并转 runtime.requestMove（M7 修复：emit 后无人监听的断链，
 * runtime.requestMove 自 C04 起零调用者）。
 */
import Phaser from 'phaser';
import type { WorldMirror } from './world-mirror';
import { WorldScene } from './scenes/WorldScene';
import { runtime } from './runtime';
import { terrainFromSearch } from './render/presentation';
import type { VoxelRequestMessage } from '../net/protocol';
import { createThreeWorld } from './render/three/three-world';
import type { WorldGame } from './world-game';

export function createGame(parent: HTMLElement, mirror: WorldMirror): WorldGame {
  // The three world owns its own canvas and is the default; `?terrain=phaser`
  // is the rollback switch back to the Phaser painter.
  const threeTerrain = terrainFromSearch(globalThis.location?.search ?? '') === 'three';
  if (threeTerrain) return createThreeWorld(parent, mirror, runtime);
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    width: 800,
    height: 600,
    pixelArt: true,
    transparent: false,
    backgroundColor: '#2a4032',
    scale: {
      mode: Phaser.Scale.RESIZE, // 批次 D8：画布随容器伸缩（截图里右侧全黑的根因：
      // 固定 800×600 在宽屏上居中，容器其余区域露出父 div 背景）
      width: 800,
      height: 600,
    },
    scene: [new WorldScene(mirror)],
  });
  game.events.on(
    'client:move_request',
    ({ x, y }: { x: number; y: number }, result?: (accepted: boolean) => void) => {
      const accepted = runtime.requestMove(x, y);
      result?.(accepted);
    },
  );
  game.events.on(
    'client:voxel_request',
    ({ action, x, y, material }: Pick<VoxelRequestMessage, 'action' | 'x' | 'y' | 'material'>) => {
      runtime.requestVoxel(action, x, y, material);
    },
  );
  return game;
}
