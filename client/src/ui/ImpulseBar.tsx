/**
 * client/src/ui/ImpulseBar.tsx — 念头注入条（批次 A UI）。
 *
 * 玩家唯一主动动作入口：往陈默心里放一个念头（player_impulse，≤64 字）。
 * 出戏纪律：占位/错误文案全戏内口语，零工程词。样式对齐 TopBar 石色系，
 * cue 四态边色一闪提示。
 */
import { useState, type FormEvent, type ReactElement } from 'react';
import { runtime, IMPULSE_MAX_LEN } from '../game/runtime';
import { useUiStore } from '../store/uiStore';

/** cue → 输入条边色（视觉反馈；resistance 最刺眼） */
const CUE_STYLE: Record<string, string> = {
  accepted: 'border-emerald-500',
  hesitation: 'border-amber-400',
  complaint: 'border-orange-400',
  resistance: 'border-rose-500',
};

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
    <div data-cue={lastImpulseCue ?? undefined}>
      {impulseError !== null && (
        <p className="px-4 pt-1 text-xs text-rose-300" role="alert">
          {impulseError}
        </p>
      )}
      <form
        className={`flex items-center gap-2 border-t-2 bg-stone-900/95 px-4 py-2 ${
          CUE_STYLE[lastImpulseCue ?? ''] ?? 'border-stone-700'
        }`}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          submitImpulse(text, (t) => runtime.sendImpulse(t));
          setText('');
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={IMPULSE_MAX_LEN}
          placeholder="往陈默心里放一个念头…"
          className="min-w-0 flex-1 rounded bg-stone-800 px-3 py-1.5 text-sm text-stone-200 placeholder-stone-500 focus:outline-none focus:ring-1 focus:ring-amber-400/60"
        />
        <button
          type="submit"
          className="rounded bg-amber-500 px-4 py-1.5 text-sm font-medium text-stone-900 hover:bg-amber-400"
        >
          发送
        </button>
      </form>
    </div>
  );
}
