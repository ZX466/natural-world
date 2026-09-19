/**
 * client/src/App.tsx — 壳布局：TopBar + CanvasHost + PanelHost 占位（m0-client.md §1）。
 * Phaser 画 canvas 内世界，React 只画 canvas 外；不共享 DOM。
 */
import type { ReactElement } from 'react';
import { CanvasHost } from './ui/CanvasHost';
import { TopBar } from './ui/TopBar';

export default function App(): ReactElement {
  return (
    <div className="flex h-screen w-screen flex-col bg-stone-950">
      <TopBar />
      <div className="min-h-0 flex-1">
        <CanvasHost />
      </div>
      {/* PanelHost 占位：M1 思维面板 / M4 计划看板挂载点（布局骨架 M0 定型） */}
      <aside id="panel-host" className="hidden" />
    </div>
  );
}
