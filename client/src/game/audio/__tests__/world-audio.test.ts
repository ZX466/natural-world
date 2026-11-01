import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StateDeltaMessage } from '../../../net/protocol';
import { WorldMirror } from '../../world-mirror';
import type { EffectId } from '../synth';
import { WorldAudio } from '../world-audio';

function delta(extra: Partial<StateDeltaMessage> = {}): StateDeltaMessage {
  return {
    type: 'state_delta',
    channel: 'render',
    v: '1.14',
    ws_seq: 1,
    actors: [],
    time: { day: 1, hour: 12, minute: 0, phase: 'day', is_market_day: false },
    ...extra,
  };
}

describe('world audio presentation', () => {
  let mirror: WorldMirror;
  let audio: WorldAudio;
  let backend: {
    unlock: ReturnType<typeof vi.fn<() => Promise<boolean>>>;
    play: ReturnType<typeof vi.fn<(effect: EffectId, gain: number) => void>>;
    setVolume: ReturnType<typeof vi.fn<(volume: number) => void>>;
    setAmbience: ReturnType<typeof vi.fn<(effect: 'fire' | null, gain: number) => void>>;
    stopAll: ReturnType<typeof vi.fn<() => void>>;
    dispose: ReturnType<typeof vi.fn<() => void>>;
  };
  let now: number;

  beforeEach(() => {
    now = 1000;
    mirror = new WorldMirror();
    mirror.applySnapshot(
      [{ rtoken: 'hero', x: 10, y: 10, facing: 's', sprite: 'chenmo', anim: 'idle' }],
      [],
    );
    mirror.protagonist = 'hero';
    backend = {
      unlock: vi.fn(async () => true),
      play: vi.fn(),
      setVolume: vi.fn(),
      setAmbience: vi.fn(),
      stopAll: vi.fn(),
      dispose: vi.fn(),
    };
    audio = new WorldAudio(() => now);
    audio.attach(backend);
    audio.status('open');
    audio.snapshot(mirror);
  });

  async function enable() {
    audio.configure({ muted: false, volume: 0.25 });
    await audio.unlock();
  }

  it('starts muted, ignores snapshots and does not resume a context before a gesture', async () => {
    audio.delta(
      delta({ voxel_edits: [{ action: 'dig', x: 10, y: 10, height: 0, gid: 0 }] }),
      mirror,
    );
    await audio.unlock();
    expect(backend.unlock).not.toHaveBeenCalled();
    expect(backend.play).not.toHaveBeenCalled();
    audio.configure({ muted: false, volume: 0.25 });
    audio.snapshot(mirror);
    expect(backend.play).not.toHaveBeenCalled();
  });

  it('maps actual voxel edits to dig/place without replaying snapshot history', async () => {
    await enable();
    audio.delta(
      delta({ voxel_edits: [{ action: 'dig', x: 10, y: 10, height: 2, gid: 0 }] }),
      mirror,
    );
    now += 200;
    audio.delta(
      delta({ voxel_edits: [{ action: 'place', x: 11, y: 10, height: 3, gid: 0 }] }),
      mirror,
    );
    expect(backend.play.mock.calls.map((call) => call[0])).toEqual(['dig', 'place']);
    audio.snapshot(mirror);
    expect(backend.play).toHaveBeenCalledTimes(2);
  });

  it('hears nearby actual movement, with no spawn, stationary or teleport footsteps', async () => {
    await enable();
    const movement = delta({ actors: [{ rtoken: 'hero', x: 11, y: 10 }] });
    mirror.applyActorDeltas(movement.actors);
    audio.delta(movement, mirror);
    expect(backend.play).toHaveBeenCalledWith('step', expect.any(Number));
    now += 200;
    audio.delta(movement, mirror);
    const teleport = delta({ actors: [{ rtoken: 'hero', x: 80, y: 80 }] });
    mirror.applyActorDeltas(teleport.actors);
    audio.delta(teleport, mirror);
    expect(backend.play).toHaveBeenCalledTimes(1);
  });

  it('derives combat sound from visible combat_event and deduplicates exchange presentation', async () => {
    await enable();
    const event = {
      type: 'combat_event' as const,
      channel: 'render' as const,
      v: '1.14',
      ws_seq: 2,
      exchange: 1,
      exchange_resolved: true,
      posture_visual: '进攻',
      rtoken: 'hero',
    };
    audio.combat(event, mirror);
    now += 200;
    audio.combat(event, mirror);
    expect(backend.play.mock.calls.map((call) => call[0])).toEqual(['combat']);
  });

  it('maps an observable fire light to fire ambience; existing production has no such producer', async () => {
    mirror.lights.set('flame', {
      rtoken: 'flame',
      x: 11,
      y: 10,
      kind: 'fire',
      radius: 3,
      flicker: 1,
    });
    await enable();
    expect(backend.setAmbience).toHaveBeenCalledWith('fire', expect.any(Number));
    mirror.lights.clear();
    audio.delta(delta(), mirror);
    expect(backend.setAmbience).toHaveBeenLastCalledWith(null, 0);
  });

  it('mute stops all sound and later enabling does not play queued events', async () => {
    await enable();
    audio.configure({ muted: true, volume: 0.25 });
    expect(backend.stopAll).toHaveBeenCalled();
    audio.delta(
      delta({ voxel_edits: [{ action: 'dig', x: 10, y: 10, height: 0, gid: 0 }] }),
      mirror,
    );
    audio.configure({ muted: false, volume: 0.25 });
    expect(backend.play).not.toHaveBeenCalled();
    await audio.unlock();
    expect(backend.play).not.toHaveBeenCalled();
  });

  it('drops distant, disconnected and repeated high-frequency effects', async () => {
    await enable();
    const near = delta({ voxel_edits: [{ action: 'dig', x: 10, y: 10, height: 0, gid: 0 }] });
    audio.delta(
      delta({ voxel_edits: [{ action: 'dig', x: 100, y: 100, height: 0, gid: 0 }] }),
      mirror,
    );
    audio.delta(near, mirror);
    audio.delta(near, mirror);
    expect(backend.play).toHaveBeenCalledTimes(1);
    audio.status('closed');
    now += 200;
    audio.delta(near, mirror);
    expect(backend.play).toHaveBeenCalledTimes(1);
    expect(backend.stopAll).toHaveBeenCalled();
  });

  it('a late unlock cannot restart a detached backend', async () => {
    let finish: (value: boolean) => void = () => {};
    backend.unlock.mockImplementation(
      () =>
        new Promise<boolean>((resolve) => {
          finish = resolve;
        }),
    );
    audio.configure({ muted: false, volume: 0.25 });
    const pending = audio.unlock();
    audio.detach();
    finish(true);
    expect(await pending).toBe(false);
    expect(backend.dispose).toHaveBeenCalled();
    expect(backend.play).not.toHaveBeenCalled();
  });

  it('a late unlock cannot restart sound after the game loses focus', async () => {
    let finish: (value: boolean) => void = () => {};
    backend.unlock.mockImplementation(
      () =>
        new Promise<boolean>((resolve) => {
          finish = resolve;
        }),
    );
    audio.configure({ muted: false, volume: 0.25 });
    const pending = audio.unlock();
    audio.suspend();
    finish(true);
    expect(await pending).toBe(false);
  });
});
