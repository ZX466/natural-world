/**
 * client/src/ui/CanvasHost.tsx — React 与 Phaser 唯一 DOM 交界（m0-client.md §1）。
 * 挂载时创建 Phaser.Game；卸载销毁。组件内部不渲染任何世界内容。
 */
import type { ReactElement } from 'react';
import { useEffect, useRef } from 'react';
import type Phaser from 'phaser';
import { createGame } from '../game/main';
import { worldMirror } from '../game/runtime';
import { VoxelInventory } from './VoxelInventory';

export function CanvasHost(): ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  const gameRef = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    const parent = ref.current;
    if (parent === null || gameRef.current !== null) return;
    const game = createGame(parent, worldMirror);
    gameRef.current = game;
    let disposed = false;
    const resize = () => {
      if (disposed || !game.isBooted) return;
      const width = parent.clientWidth;
      const height = parent.clientHeight;
      if (width > 0 && height > 0 && (game.scale.width !== width || game.scale.height !== height)) {
        // RESIZE mode derives the canvas from parentSize during refresh.
        game.scale.setParentSize(width, height);
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    game.events.once('ready', resize);
    resize();
    return () => {
      disposed = true;
      observer.disconnect();
      game.events.off('ready', resize);
      game.destroy(true);
      if (gameRef.current === game) gameRef.current = null;
    };
  }, []);

  return (
    <div className="relative h-full w-full">
      <div ref={ref} className="h-full w-full" />
      <VoxelInventory />
    </div>
  );
}
