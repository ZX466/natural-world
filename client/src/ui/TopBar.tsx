/**
 * client/src/ui/TopBar.tsx — 戏内时钟 + 倍速 + 连接状态（m0-client.md §5.1）。
 * 铁律（C3）：只显示戏内时间，绝不显示 tick/seed/内部 id。
 * 版式：宣纸顶栏 + 木刻墨字（见 ui.css）。
 */
import type { ReactElement } from 'react';
import { runtime } from '../game/runtime';
import { useUiStore, type Speed } from '../store/uiStore';
import { storyLabel } from './labels';

const SPEEDS: readonly Speed[] = [1, 4, 16];
const CONNECTION_LABELS = {
  open: null,
  connecting: '连接中…',
  reconnecting: '正在重连…',
  closed: '已断开，正在重试',
};

const STATUS_CLASS: Record<string, string> = {
  open: 'od-status--open',
  connecting: 'od-status--connecting',
  reconnecting: 'od-status--reconnecting',
  closed: 'od-status--closed',
};

function phaseLabel(phase: string): string {
  return { dawn: '黎明', day: '白天', dusk: '黄昏', night: '夜晚' }[phase] ?? phase;
}

export type SidePanel = 'journal' | 'saves';

export function TopBar({
  onOpenSettings,
  onTogglePanel,
  activePanel,
}: {
  onOpenSettings: () => void;
  onTogglePanel: (panel: SidePanel) => void;
  activePanel: SidePanel | null;
}): ReactElement {
  const wsStatus = useUiStore((s) => s.wsStatus);
  const gameClock = useUiStore((s) => s.gameClock);
  const speed = useUiStore((s) => s.speed);
  const paused = useUiStore((s) => s.paused);
  const combatActive = useUiStore((s) => s.combatActive);
  const sessionAnchor = useUiStore((s) => s.sessionAnchor);
  const controlError = useUiStore((s) => s.controlError);
  const connectionLabel = CONNECTION_LABELS[wsStatus];

  const hh = String(gameClock?.hour ?? 0).padStart(2, '0');
  const mm = String(gameClock?.minute ?? 0).padStart(2, '0');

  return (
    <header className="od-topbar">
      <span className="od-topbar__rivets" aria-hidden="true" />
      <div className="od-topbar__time">
        <span className="od-clock">
          第 {gameClock?.day ?? 1} 天 {hh}:{mm}
        </span>
        {gameClock !== null && (
          <span className="od-clock-phase">
            {phaseLabel(gameClock.phase)}
            {gameClock.isMarketDay && <span className="od-market">集市日</span>}
          </span>
        )}
      </div>
      <div className="od-topbar__right">
        {connectionLabel && (
          <span className="od-clock-phase" role="status" data-connection-status={wsStatus}>
            {connectionLabel}
          </span>
        )}
        {combatActive && <span role="status">刀光剑影</span>}
        {/* D4：游标指针（session_state.anchor，只有 name + story_label）。
            重连/读档后玩家能看见「世界此刻停在哪个档」。 */}
        {sessionAnchor !== null && (
          <span
            className="od-clock-phase od-clock-phase--anchor"
            role="status"
            // 空串是 calendar 未就绪的合法形状（anchors-api.md §1.1）⇒ 按契约
            // 显「未标注」。`title=""` 会挂一个永远弹不出内容的提示，比没有更糟。
            title={storyLabel(sessionAnchor.story_label)}
          >
            {sessionAnchor.name}
          </span>
        )}
        {/* D5：set_control 被拒的提示位（此前 6 条戏内文案无任何落点）。 */}
        {controlError !== null && (
          <span className="od-clock-phase od-clock-phase--alert" role="alert">
            {controlError}
          </span>
        )}
        <button
          type="button"
          id="journal-toggle"
          aria-controls="side-panel"
          aria-expanded={activePanel === 'journal'}
          onClick={() => onTogglePanel('journal')}
          className={`od-tb-btn${activePanel === 'journal' ? ' is-on' : ''}`}
        >
          手札
        </button>
        <button
          type="button"
          id="saves-toggle"
          aria-controls="side-panel"
          aria-expanded={activePanel === 'saves'}
          onClick={() => onTogglePanel('saves')}
          className={`od-tb-btn${activePanel === 'saves' ? ' is-on' : ''}`}
        >
          存档
        </button>
        <button type="button" id="settings-toggle" onClick={onOpenSettings} className="od-tb-btn">
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
        <span
          className={`od-status ${STATUS_CLASS[wsStatus] ?? 'od-status--closed'}`}
          role="status"
          aria-label={connectionLabel ?? '连接正常'}
          title={connectionLabel ?? '连接正常'}
        />
      </div>
    </header>
  );
}
