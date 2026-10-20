/**
 * client/src/ui/TopBar.tsx — 戏内时钟 + 倍速 + 连接状态（m0-client.md §5.1）。
 * 铁律（C3）：只显示戏内时间，绝不显示 tick/seed/内部 id。
 * 版式：宣纸顶栏 + 木刻墨字（见 ui.css）。
 */
import type { ReactElement } from 'react';
import { runtime } from '../game/runtime';
import { useUiStore, type Speed } from '../store/uiStore';

const SPEEDS: readonly Speed[] = [1, 4, 16];

const STATUS_CLASS: Record<string, string> = {
  open: 'od-status--open',
  connecting: 'od-status--connecting',
  reconnecting: 'od-status--reconnecting',
  closed: 'od-status--closed',
};

function phaseLabel(phase: string): string {
  return { dawn: '黎明', day: '白天', dusk: '黄昏', night: '夜晚' }[phase] ?? phase;
}

export function TopBar({ onOpenSettings }: { onOpenSettings: () => void }): ReactElement {
  const wsStatus = useUiStore((s) => s.wsStatus);
  const gameClock = useUiStore((s) => s.gameClock);
  const speed = useUiStore((s) => s.speed);
  const paused = useUiStore((s) => s.paused);
  const combatActive = useUiStore((s) => s.combatActive);

  const hh = String(gameClock?.hour ?? 0).padStart(2, '0');
  const mm = String(gameClock?.minute ?? 0).padStart(2, '0');

  return (
    <header className="od-topbar">
      <span className="od-topbar__rivets" aria-hidden="true" />
      <span className="od-clock">
        第 {gameClock?.day ?? 1} 天 {hh}:{mm}
      </span>
      {gameClock !== null && (
        <span className="od-clock-phase">
          {phaseLabel(gameClock.phase)}
          {gameClock.isMarketDay && <span className="od-market">集市日</span>}
        </span>
      )}
      <div className="od-topbar__right">
        {combatActive && <span role="status">刀光剑影</span>}
        <button type="button" onClick={onOpenSettings} className="od-tb-btn">
          设置
        </button>
        <button
          type="button"
          onClick={() => runtime.sendControl(paused ? 'resume' : 'pause')}
          className="od-tb-btn"
        >
          {paused ? '继续' : '暂停'}
        </button>
        <div className="od-speed">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => runtime.sendControl('set_speed', s)}
              className={`od-speed__btn${speed === s && !paused ? ' is-on' : ''}`}
            >
              {s}x
            </button>
          ))}
        </div>
        <span className={`od-status ${STATUS_CLASS[wsStatus] ?? 'od-status--closed'}`} />
      </div>
    </header>
  );
}
