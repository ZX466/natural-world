/**
 * client/src/ui/CanvasHost.tsx — React 与 Phaser 唯一 DOM 交界（m0-client.md §1）。
 * 挂载时创建 Phaser.Game；卸载销毁。组件内部不渲染任何世界内容。
 */
import type { ReactElement } from 'react';
import { useEffect, useRef } from 'react';
import type Phaser from 'phaser';
import { createGame } from '../game/main';
import { worldMirror } from '../game/runtime';

export function CanvasHost(): ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  const gameRef = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    if (ref.current === null || gameRef.current !== null) return;
    gameRef.current = createGame(ref.current, worldMirror);
    return () => {
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, []);

  return <div ref={ref} className="h-full w-full" />;
}
