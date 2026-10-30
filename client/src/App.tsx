/**
 * client/src/App.tsx — 壳布局：TopBar + CanvasHost + PanelHost + ImpulseBar。
 * Phaser 画 canvas 内世界，React 只画 canvas 外；不共享 DOM。
 */
import type { ReactElement } from 'react';
import { useCallback, useEffect, useState } from 'react';
import { CanvasHost } from './ui/CanvasHost';
import { ImpulseBar } from './ui/ImpulseBar';
import { PanelHost } from './ui/PanelHost';
import { SaveLoadPanel } from './ui/SaveLoadPanel';
import { SettingsPage } from './ui/SettingsPage';
import { TopBar, type SidePanel } from './ui/TopBar';

export default function App(): ReactElement {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activePanel, setActivePanel] = useState<SidePanel | null>(() =>
    globalThis.matchMedia?.('(min-width: 900px)').matches ? 'journal' : null,
  );

  const closePanel = useCallback(() => {
    const target = activePanel;
    setActivePanel(null);
    if (target) requestAnimationFrame(() => document.getElementById(`${target}-toggle`)?.focus());
  }, [activePanel]);
  const closeSettings = useCallback(() => {
    setSettingsOpen(false);
    requestAnimationFrame(() => document.getElementById('settings-toggle')?.focus());
  }, []);

  useEffect(() => {
    const compact = window.matchMedia('(max-width: 899px)');
    const onChange = () => {
      if (compact.matches) setActivePanel(null);
    };
    compact.addEventListener('change', onChange);
    return () => compact.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.isComposing && !settingsOpen) closePanel();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [closePanel, settingsOpen]);

  return (
    <div className="od-app">
      <TopBar
        activePanel={activePanel}
        onTogglePanel={(panel) => setActivePanel((current) => (current === panel ? null : panel))}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <div className="od-workspace">
        <main className="od-stage" aria-label="小镇">
          <div className="od-stage__world">
            <CanvasHost />
          </div>
          <ImpulseBar />
        </main>
        {activePanel !== null && (
          <button
            type="button"
            className="od-panel-backdrop"
            aria-label="关闭侧栏遮罩"
            tabIndex={-1}
            onClick={closePanel}
          />
        )}
        <aside
          id="side-panel"
          className="od-side-panel"
          aria-label="手札与存档"
          hidden={activePanel === null}
        >
          <div className="od-side-panel__head">
            <span className="od-side-panel__title">
              {activePanel === 'saves' ? '游历记档' : '随行手札'}
            </span>
            <button
              type="button"
              className="od-menu__btn"
              aria-label="收起侧栏"
              onClick={closePanel}
            >
              收起
            </button>
          </div>
          <div className="od-side-panel__content">
            {activePanel === 'journal' && <PanelHost />}
            {activePanel === 'saves' && <SaveLoadPanel />}
          </div>
        </aside>
      </div>
      {settingsOpen && <SettingsPage onClose={closeSettings} />}
    </div>
  );
}
