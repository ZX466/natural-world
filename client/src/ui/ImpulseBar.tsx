/**
 * client/src/ui/ImpulseBar.tsx — 念头注入条（批次 A UI）。
 *
 * 玩家唯一主动动作入口：往陈默心里放一个念头（player_impulse，≤64 字）。
 * 出戏纪律：占位/错误文案全戏内口语，零工程词。纸色输入条，cue 四态
 * 以 data-cue 边色一闪提示（样式见 ui.css）。
 */
import { useEffect, useState, type FormEvent, type ReactElement } from 'react';
import { runtime, IMPULSE_MAX_LEN } from '../game/runtime';
import { useUiStore } from '../store/uiStore';

type SubmissionState = Pick<
  ReturnType<typeof useUiStore.getState>,
  'wsStatus' | 'setLastImpulseCue' | 'setImpulseError'
>;

/** 清除上次反馈；断线不递出，已连上才交给既有 runtime。 */
export function submitImpulse(
  text: string,
  send: (t: string) => void,
  state?: SubmissionState,
): boolean {
  state?.setLastImpulseCue(null);
  const cleaned = text.trim();
  if (!cleaned) return false;
  if (state && state.wsStatus !== 'open') {
    state.setImpulseError('话递不过去，四下里静得很。');
    return false;
  }
  state?.setImpulseError(null);
  send(cleaned);
  return true;
}

export function ImpulseBar(): ReactElement {
  const [text, setText] = useState('');
  const lastImpulseCue = useUiStore((s) => s.lastImpulseCue);
  const impulseError = useUiStore((s) => s.impulseError);
  const wsStatus = useUiStore((s) => s.wsStatus);
  const setLastImpulseCue = useUiStore((s) => s.setLastImpulseCue);

  useEffect(() => {
    if (lastImpulseCue === null) return;
    const timer = setTimeout(() => setLastImpulseCue(null), 6000);
    return () => clearTimeout(timer);
  }, [lastImpulseCue, setLastImpulseCue]);

  return (
    <div className="od-impulse" data-cue={lastImpulseCue ?? undefined}>
      {lastImpulseCue !== null && wsStatus === 'open' && impulseError === null && (
        <p className="od-impulse__notice" role="status">
          这个念头，他听见了。
        </p>
      )}
      {impulseError !== null && (
        <p className="od-impulse__error" role="alert">
          {impulseError}
        </p>
      )}
      <form
        className="od-impulse__form"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (submitImpulse(text, (t) => runtime.sendImpulse(t), useUiStore.getState())) {
            setText('');
          }
        }}
      >
        <span className="od-impulse__thread" aria-hidden="true" />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={IMPULSE_MAX_LEN}
          placeholder="往陈默心里放一个念头…"
          className="od-impulse__input"
        />
        <span className="od-impulse__seal" aria-hidden="true" />
        <button type="submit" className="od-impulse__send">
          发送
        </button>
      </form>
    </div>
  );
}
