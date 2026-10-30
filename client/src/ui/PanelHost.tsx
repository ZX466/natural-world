/**
 * client/src/ui/PanelHost.tsx — 右侧竖栏面板（批次 A UI；D10 分流）。
 *
 * 两块面板：心之声（陈默独白流：thought/plan 入流，环形缓冲
 * 最近 MONOLOGUE_CAP 条）+ 街谈巷议（批次 D10：村民 bubble 公开嘟囔，
 * CHATTER_CAP 条）。
 *
 * 「计划看板」已退役（2026-10-26 用户裁定删废话面板）：state_delta.plan
 * 的条目全部来自 NPC 的 defers 决定（sim/npc/runtime.py），内容恒为
 * 「先去别处，等会儿再回来」——行为本身已可见，单独一块板纯属噪音，
 * 且塞进心之声会把它误挂成陈默的内心。协议与 store 数据面保留不动。
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

  return (
    <aside id="panel-host" className="od-panelhost">
      <section
        aria-label="心之声"
        className={`od-panel od-panel--voice${monologues.length === 0 ? ' is-empty' : ''}`}
      >
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
      <section
        aria-label="街谈巷议"
        className={`od-panel od-panel--chatter${chatter.length === 0 ? ' is-empty' : ''}`}
      >
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
    </aside>
  );
}
