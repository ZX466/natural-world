/**
 * client/src/ui/TopBar.tsx — 壳 UI：戏内时钟 + 倍速 + 连接状态（m0-client.md §5.1）。
 * 铁律（C3）：只显示戏内时间，绝不显示 tick/seed/内部 id。
 */
import type { ReactElement } from 'react';
import { runtime } from '../game/runtime';
import { useUiStore, type Speed } from '../store/uiStore';

const SPEEDS: readonly Speed[] = [1, 4, 16];

const STATUS_STYLE: Record<string, string> = {
  open: 'bg-emerald-500',
  connecting: 'bg-amber-400',
  reconnecting: 'bg-amber-500 animate-pulse',
  closed: 'bg-rose-500',
};

function phaseLabel(phase: string): string {
  return { dawn: '黎明', day: '白天', dusk: '黄昏', night: '夜晚' }[phase] ?? phase;
}

export function TopBar({ onOpenSettings }: { onOpenSettings: () => void }): ReactElement {
  const wsStatus = useUiStore((s) => s.wsStatus);
  const gameClock = useUiStore((s) => s.gameClock);
  const speed = useUiStore((s) => s.speed);
  const paused = useUiStore((s) => s.paused);

  const hh = String(gameClock?.hour ?? 0).padStart(2, '0');
  const mm = String(gameClock?.minute ?? 0).padStart(2, '0');

  return (
    <header className="flex items-center gap-4 border-b border-stone-700 bg-stone-900 px-4 py-2 text-stone-200">
      <span className="font-mono text-lg">
        第 {gameClock?.day ?? 1} 天 {hh}:{mm}
      </span>
      {gameClock !== null && (
        <span className="text-sm text-stone-400">
          {phaseLabel(gameClock.phase)}
          {gameClock.isMarketDay && <span className="ml-2 text-amber-300">集市日</span>}
        </span>
      )}
      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          onClick={onOpenSettings}
          className="rounded bg-stone-700 px-3 py-1 text-sm hover:bg-stone-600"
        >
          设置
        </button>
        <button
          type="button"
          onClick={() => runtime.sendControl(paused ? 'resume' : 'pause')}
          className="rounded bg-stone-700 px-3 py-1 text-sm hover:bg-stone-600"
        >
          {paused ? '继续' : '暂停'}
        </button>
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => runtime.sendControl('set_speed', s)}
            className={`rounded px-2 py-1 text-sm ${
              speed === s && !paused
                ? 'bg-amber-500 text-stone-900'
                : 'bg-stone-700 hover:bg-stone-600'
            }`}
          >
            {s}x
          </button>
        ))}
        <span
          className={`ml-3 h-2.5 w-2.5 rounded-full ${STATUS_STYLE[wsStatus] ?? 'bg-stone-500'}`}
        />
      </div>
    </header>
  );
}
