import type { ReactElement } from 'react';
import { useUiStore } from '../store/uiStore';

/** 只呈现服务端叙事；空白不推断健康状态，也不提示尚未得知的隐情。 */
export function NpcPanel(): ReactElement {
  const people = useUiStore((state) => state.npcViews);

  return (
    <section
      aria-label="人物"
      className={`od-panel od-panel--npc${people.length === 0 ? ' is-empty' : ''}`}
      style={{ ...(people.length > 0 ? { flex: 1 } : {}), overflowY: 'auto' }}
    >
      <span className="od-panel__pin" aria-hidden="true" />
      <h2 className="od-panel__title">人物</h2>
      {people.length === 0 ? (
        <p className="od-panel__empty">还没有可记下的近况。</p>
      ) : (
        <ul className="od-voice-list">
          {people.map((person) => (
            <li key={person.rtoken} className="od-voice">
              <h3 className="od-chatter__name" style={{ margin: 0, fontSize: 'inherit' }}>
                {person.name?.trim() || '一位相识'}
              </h3>
              {[...new Set([...person.health, person.bond, ...person.knows])]
                .filter(Boolean)
                .map((text) => (
                  <p key={text} style={{ margin: '0.25rem 0 0' }}>
                    {text}
                  </p>
                ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
