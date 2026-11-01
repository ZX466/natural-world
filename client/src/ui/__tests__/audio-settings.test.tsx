import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, expect, it } from 'vitest';
import { SettingsPage } from '../SettingsPage';
import { useAudioStore } from '../../store/audioStore';

beforeEach(() => useAudioStore.setState({ muted: true, volume: 0.25 }));

it('offers local opt-in audio with a named volume slider and a quiet default', () => {
  const html = renderToStaticMarkup(createElement(SettingsPage, { onClose: () => {} }));
  expect(html).toContain('世界音效');
  expect(html).toContain('开启音效');
  expect(html).toContain('aria-label="音效音量"');
  expect(html).toContain('value="25"');
  expect(useAudioStore.getState().muted).toBe(true);
});

it('clamps local volume without touching server model settings', () => {
  useAudioStore.getState().setVolume(2);
  expect(useAudioStore.getState().volume).toBe(1);
  useAudioStore.getState().setVolume(Number.NaN);
  expect(useAudioStore.getState().volume).toBe(0);
  useAudioStore.getState().setMuted(false);
  expect(useAudioStore.getState().muted).toBe(false);
});
