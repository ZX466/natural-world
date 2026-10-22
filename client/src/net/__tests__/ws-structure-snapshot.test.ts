import { expect, it, vi } from 'vitest';
import { WsClient } from '../ws';
import { WorldMirror } from '../../game/world-mirror';

function connection() {
  const mirror = new WorldMirror();
  const client = new WsClient('ws://test', mirror, {
    onStatus: vi.fn(),
    onSnapshot: vi.fn(),
    onDelta: vi.fn(),
  });
  const dispatch = (frame: Record<string, unknown>) =>
    (client as unknown as { dispatch(raw: string): void }).dispatch(
      JSON.stringify({ v: '1.11', ws_seq: 1, channel: 'render', actors: [], lights: [], ...frame }),
    );
  mirror.applyStructures([
    { rtoken: 'st-s1', x: 3, y: 3, phase: 'built' },
    { rtoken: 'st-s2', x: 4, y: 3, phase: 'built' },
  ]);
  return { mirror, dispatch };
}

it('replaces structures on full_snapshot, including tiles of retained tokens', () => {
  const { mirror, dispatch } = connection();
  dispatch({
    type: 'full_snapshot',
    structures: [{ rtoken: 'st-s1', x: 9, y: 9, phase: 'rubble' }],
  });
  expect([...mirror.structures]).toEqual([['st-s1', { tiles: [[9, 9]], phase: 'rubble' }]]);
});

it.each([[], undefined])(
  'clears structures on an empty or omitted snapshot array (%s)',
  (structures) => {
    const { mirror, dispatch } = connection();
    dispatch({ type: 'full_snapshot', structures });
    expect(mirror.structures.size).toBe(0);
  },
);

it('keeps state_delta incremental and consumes server remove rows', () => {
  const { mirror, dispatch } = connection();
  dispatch({ type: 'state_delta', structures: [{ rtoken: 'st-s1', x: 3, y: 3, phase: 'rubble' }] });
  expect(mirror.structures.get('st-s1')?.phase).toBe('rubble');
  expect(mirror.structures.has('st-s2')).toBe(true);
  dispatch({ type: 'state_delta', structures: [{ op: 'remove', rtoken: 'st-s2' }] });
  expect(mirror.structures.has('st-s2')).toBe(false);
});
