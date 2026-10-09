/**
 * client/src/ui/PanelHost.tsx — 右侧竖栏面板（批次 A UI；D10 分流）。
 *
 * 三块面板：心之声（陈默独白流：thought/plan 入流，环形缓冲
 * 最近 MONOLOGUE_CAP 条）+ 街谈巷议（批次 D10：村民 bubble 公开嘟囔，
 * CHATTER_CAP 条）+ 计划看板（state_delta.plan，有则展开无则收起）。
 * 出戏纪律：只渲染叙事文本，零数值零工程词。
 * 版式：宣纸竖栏，墨字 + 朱印（见 ui.css）。
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
    <aside id="panel-host" className="od-panelhost">
      <section aria-label="心之声" className="od-panel od-panel--voice">
        <span className="od-panel__pin" aria-hidden="true" />
        <h2 className="od-panel__title">心之声</h2>
        {monologues.length === 0 ? (
          <p className="od-panel__empty">陈默心里还很安静。</p>
        ) : (
          <ul className="od-voice-list">
            {monologues.map((m, i) => (
              <li key={`${i}-${m.content}`} className="od-voice">
                <span className="od-voice__tag">{FORM_LABEL[m.form]}</span>
                {m.content}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="街谈巷议" className="od-panel od-panel--chatter">
        <span className="od-panel__pin" aria-hidden="true" />
        <h2 className="od-panel__title">街谈巷议</h2>
        {chatter.length === 0 ? (
          <p className="od-panel__empty">镇上还很安静。</p>
        ) : (
          <ul className="od-chatter-list">
            {chatter.map((c, i) => (
              <li key={`${i}-${c.content}`} className="chatter-item od-chatter">
                {c.name !== null && <span className="od-chatter__name">{c.name}：</span>}
                {c.content}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="计划" className="od-panel od-panel--plan">
        <span className="od-panel__pin" aria-hidden="true" />
        <h2 className="od-panel__title">计划</h2>
        {plans.length === 0 ? (
          <p className="od-panel__empty">还没有什么打算。</p>
        ) : (
          <ul className="od-plan-list">
            {plans.map((p) => (
              <li key={p.rtoken} className="plan-item od-plan">
                {p.text}
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
