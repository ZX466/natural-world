import { beforeEach, expect, it, vi } from 'vitest';
import { WsClient } from '../ws';
import { WorldMirror } from '../../game/world-mirror';
import { useUiStore } from '../../store/uiStore';

beforeEach(() => {
  useUiStore.setState({ combatActive: false, combatEventCount: 0 });
});

it('dispatches combat frames into observable store state', () => {
  const client = new WsClient('ws://test', new WorldMirror(), {
    onStatus: vi.fn(),
    onSnapshot: vi.fn(),
    onDelta: vi.fn(),
  });
  const dispatch = (frame: Record<string, unknown>) =>
    (client as unknown as { dispatch(raw: string): void }).dispatch(
      JSON.stringify({ v: '1.10', ws_seq: 1, ...frame }),
    );

  dispatch({ type: 'timescale', channel: 'control', mode: 'combat', active: true });
  expect(useUiStore.getState().combatActive).toBe(true);
  dispatch({
    type: 'combat_event',
    channel: 'render',
    exchange: 0,
    rtoken: 'rt-test',
    posture_visual: 'attack',
    exchange_resolved: true,
  });
  expect(useUiStore.getState().combatEventCount).toBe(1);
  dispatch({ type: 'timescale', channel: 'control', mode: 'normal', active: false });
  expect(useUiStore.getState().combatActive).toBe(false);
});
