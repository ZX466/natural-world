/**
 * client/src/ui/PanelHost.tsx — 右侧竖栏面板（批次 A UI；D10 分流）。
 *
 * 三块面板：心之声（陈默独白流：thought/plan 入流，环形缓冲
 * 最近 MONOLOGUE_CAP 条）+ 街谈巷议（批次 D10：村民 bubble 公开嘟囔，
 * CHATTER_CAP 条）+ 计划看板（state_delta.plan，有则展开无则收起）。
 * 出戏纪律：只渲染叙事文本，零数值零工程词。
 */
import type { ReactElement } from 'react';
import { useUiStore, type MonologueEntry } from '../store/uiStore';

const FORM_LABEL: Record<MonologueEntry['form'], string> = {
  thought: '心想',
  bubble: '自语',
  plan: '打算',
};

export function PanelHost(): ReactElement {
  const monologues = useUiStore((s) => s.monologues);
  const chatter = useUiStore((s) => s.chatter);
  const plans = useUiStore((s) => s.plans);

  return (
    <aside
      id="panel-host"
      className="flex w-64 shrink-0 flex-col gap-3 overflow-y-auto border-l border-stone-700 bg-stone-900/95 p-3"
    >
      <section aria-label="心之声" className="min-h-0">
        <h2 className="mb-2 text-xs font-semibold tracking-widest text-stone-400">心之声</h2>
        {monologues.length === 0 ? (
          <p className="text-xs leading-relaxed text-stone-500">
            陈默心里还很安静。
          </p>
        ) : (
          <ul className="space-y-2">
            {monologues.map((m, i) => (
              <li
                key={`${i}-${m.content}`}
                className="rounded bg-stone-800/70 px-2.5 py-1.5 text-xs leading-relaxed text-stone-200"
              >
                <span className="mr-1 text-[10px] text-amber-300/80">{FORM_LABEL[m.form]}</span>
                {m.content}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="街谈巷议" className="min-h-0">
        <h2 className="mb-2 text-xs font-semibold tracking-widest text-stone-400">街谈巷议</h2>
        {chatter.length === 0 ? (
          <p className="text-xs leading-relaxed text-stone-500">镇上还很安静。</p>
        ) : (
          <ul className="space-y-2">
            {chatter.map((c, i) => (
              <li
                key={`${i}-${c}`}
                className="chatter-item rounded bg-stone-800/40 px-2.5 py-1.5 text-xs leading-relaxed text-stone-400"
              >
                {c}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="计划" className="min-h-0">
        <h2 className="mb-2 text-xs font-semibold tracking-widest text-stone-400">计划</h2>
        {plans.length === 0 ? (
          <p className="text-xs text-stone-500">还没有什么打算。</p>
        ) : (
          <ul className="space-y-2">
            {plans.map((p) => (
              <li
                key={p.rtoken}
                className="plan-item rounded bg-stone-800/70 px-2.5 py-1.5 text-xs leading-relaxed text-stone-300"
              >
                {p.text}
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
