/**
 * client/src/App.tsx — 壳布局：TopBar + CanvasHost + PanelHost + ImpulseBar。
 * Phaser 画 canvas 内世界，React 只画 canvas 外；不共享 DOM。
 */
import type { ReactElement } from 'react';
import { useState } from 'react';
import { CanvasHost } from './ui/CanvasHost';
import { ImpulseBar } from './ui/ImpulseBar';
import { PanelHost } from './ui/PanelHost';
import { SaveLoadPanel } from './ui/SaveLoadPanel';
import { SettingsPage } from './ui/SettingsPage';
import { TopBar } from './ui/TopBar';

export default function App(): ReactElement {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="od-app flex h-screen w-screen flex-col">
      <TopBar onOpenSettings={() => setSettingsOpen(true)} />
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1">
            <CanvasHost />
          </div>
          <ImpulseBar />
        </div>
        <PanelHost />
        <SaveLoadPanel />
      </div>
      {settingsOpen && <SettingsPage onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
