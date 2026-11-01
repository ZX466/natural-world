import { describe, expect, it, vi } from 'vitest';
import { createNoise, WebAudioSynth } from '../synth';

function fakeContext() {
  const parameter = () => ({
    value: 0,
    setValueAtTime: vi.fn(),
    linearRampToValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn(),
  });
  const source = () => ({
    buffer: null,
    loop: false,
    connect: vi.fn(),
    disconnect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    onended: null,
  });
  return {
    state: 'suspended',
    sampleRate: 8000,
    currentTime: 0,
    destination: {},
    resume: vi.fn(async function (this: { state: string }) {
      this.state = 'running';
    }),
    createGain: vi.fn(() => ({ gain: parameter(), connect: vi.fn(), disconnect: vi.fn() })),
    createBiquadFilter: vi.fn(() => ({
      type: 'lowpass',
      frequency: parameter(),
      connect: vi.fn(),
      disconnect: vi.fn(),
    })),
    createBuffer: vi.fn((_channels: number, length: number) => ({
      getChannelData: () => new Float32Array(length),
    })),
    createBufferSource: vi.fn(source),
  };
}

describe('deterministic procedural WebAudio', () => {
  it('reproduces byte-identical bounded noise with no random source', () => {
    expect(createNoise(128, 42)).toEqual(createNoise(128, 42));
    expect(createNoise(128, 42)).not.toEqual(createNoise(128, 43));
    expect([...createNoise(128, 42)].every((value) => value >= -1 && value <= 1)).toBe(true);
  });

  it('creates no nodes or sound before unlock and tears down its sources without closing Phaser context', async () => {
    const context = fakeContext();
    const synth = new WebAudioSynth(() => ({
      context: context as unknown as AudioContext,
      destination: context.destination as AudioNode,
    }));
    synth.play('dig', 1);
    expect(context.createBufferSource).not.toHaveBeenCalled();
    expect(await synth.unlock()).toBe(true);
    synth.setVolume(0.25);
    synth.play('dig', 1);
    expect(context.createBufferSource).toHaveBeenCalledTimes(1);
    expect(context.createBufferSource.mock.results[0]?.value.start).toHaveBeenCalled();
    synth.stopAll();
    expect(context.createBufferSource.mock.results[0]?.value.stop).toHaveBeenCalled();
    synth.dispose();
    synth.play('place', 1);
    expect(context.createBufferSource).toHaveBeenCalledTimes(1);
  });

  it('degrades silently when WebAudio is unavailable', async () => {
    const synth = new WebAudioSynth(() => null);
    expect(await synth.unlock()).toBe(false);
    expect(() => synth.play('dig', 1)).not.toThrow();
  });

  it('bounds simultaneous voices and releases a fire loop immediately', async () => {
    const context = fakeContext();
    const synth = new WebAudioSynth(() => ({
      context: context as unknown as AudioContext,
      destination: context.destination as AudioNode,
    }));
    await synth.unlock();
    synth.setVolume(0.25);
    for (let index = 0; index < 12; index++) synth.play('step', 1);
    expect(
      context.createBufferSource.mock.results
        .slice(0, 4)
        .every((result) => result.value.disconnect.mock.calls.length > 0),
    ).toBe(true);
    synth.stopAll();
    synth.setAmbience('fire', 1);
    const fire = context.createBufferSource.mock.results.at(-1)?.value;
    expect(fire?.loop).toBe(true);
    synth.setAmbience(null, 0);
    expect(fire?.stop).toHaveBeenCalled();
    synth.dispose();
  });
});
