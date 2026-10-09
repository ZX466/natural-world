/**
 * client/src/ui/ImpulseBar.tsx — 念头注入条（批次 A UI）。
 *
 * 玩家唯一主动动作入口：往陈默心里放一个念头（player_impulse，≤64 字）。
 * 出戏纪律：占位/错误文案全戏内口语，零工程词。纸色输入条，cue 四态
 * 以 data-cue 边色一闪提示（样式见 ui.css）。
 */
import { useState, type FormEvent, type ReactElement } from 'react';
import { runtime, IMPULSE_MAX_LEN } from '../game/runtime';
import { useUiStore } from '../store/uiStore';

/** 提交逻辑导出供单测钉（trim 空白即拒发；非空 trim 后交 runtime）。 */
export function submitImpulse(text: string, send: (t: string) => void): void {
  const cleaned = text.trim();
  if (!cleaned) return;
  send(cleaned);
}

export function ImpulseBar(): ReactElement {
  const [text, setText] = useState('');
  const lastImpulseCue = useUiStore((s) => s.lastImpulseCue);
  const impulseError = useUiStore((s) => s.impulseError);

  return (
    <div className="od-impulse" data-cue={lastImpulseCue ?? undefined}>
      {impulseError !== null && (
        <p className="od-impulse__error" role="alert">
          {impulseError}
        </p>
      )}
      <form
        className="od-impulse__form"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          submitImpulse(text, (t) => runtime.sendImpulse(t));
          setText('');
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
