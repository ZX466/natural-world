/**
 * client/src/game/main.ts — Phaser.Game 装配（m0-client.md §2）。
 * parent=CanvasHost div（唯一 DOM 交界）；WorldScene 拿 WorldMirror。
 */
import Phaser from 'phaser';
import type { WorldMirror } from './world-mirror';
import { WorldScene } from './scenes/WorldScene';

export function createGame(parent: HTMLElement, mirror: WorldMirror): Phaser.Game {
  return new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    width: 800,
    height: 600,
    pixelArt: true,
    backgroundColor: '#1a1f24',
    scene: [new WorldScene(mirror)],
  });
}
