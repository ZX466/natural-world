/** Audible presentation only: never consume monologues, thoughts, tasks or private state. */
import type { CombatEventMessage, StateDeltaMessage } from '../../net/protocol';
import type { WorldMirror } from '../world-mirror';
import type { AudioBackend, EffectId } from './synth';

export interface AudioPreferences {
  muted: boolean;
  volume: number;
}
export class WorldAudio {
  private backend: AudioBackend | null = null;
  private preferences: AudioPreferences = { muted: true, volume: 0.25 };
  private unlocked = false;
  private connected = false;
  private hasSnapshot = false;
  private mirror: WorldMirror | null = null;
  private positions = new Map<string, { x: number; y: number }>();
  private phases = new Map<string, string>();
  private played = new Map<EffectId, number>();
  private exchanges = new Set<string>();
  private generation = 0;

  constructor(private readonly now: () => number = () => performance.now()) {}

  attach(backend: AudioBackend): void {
    this.detach();
    this.backend = backend;
    this.backend.setVolume(this.preferences.muted ? 0 : this.preferences.volume);
  }

  detach(owner?: AudioBackend): void {
    if (owner && owner !== this.backend) return;
    this.backend?.dispose();
    this.backend = null;
    this.unlocked = false;
    this.generation++;
  }

  configure(preferences: AudioPreferences): void {
    this.preferences = {
      muted: preferences.muted,
      volume: Number.isFinite(preferences.volume)
        ? Math.max(0, Math.min(1, preferences.volume))
        : 0,
    };
    this.backend?.setVolume(this.preferences.muted ? 0 : this.preferences.volume);
    if (this.preferences.muted || this.preferences.volume === 0) this.suspend();
  }

  async unlock(): Promise<boolean> {
    const backend = this.backend;
    const generation = this.generation;
    if (!backend || this.preferences.muted || this.preferences.volume === 0) return false;
    const unlocked = await backend.unlock();
    if (
      this.backend !== backend ||
      generation !== this.generation ||
      this.preferences.muted ||
      this.preferences.volume === 0
    )
      return false;
    this.unlocked = unlocked;
    this.ambience();
    return unlocked;
  }

  suspend(): void {
    this.generation++;
    this.unlocked = false;
    this.backend?.stopAll();
  }

  status(status: string): void {
    this.connected = status === 'open';
    if (!this.connected) {
      this.hasSnapshot = false;
      this.suspend();
      this.positions.clear();
      this.exchanges.clear();
    }
  }

  snapshot(mirror: WorldMirror): void {
    this.mirror = mirror;
    this.hasSnapshot = true;
    this.positions = new Map(
      [...mirror.actors].map(([id, actor]) => [id, { x: actor.x, y: actor.y }]),
    );
    this.phases = new Map([...mirror.structures].map(([id, structure]) => [id, structure.phase]));
    this.played.clear();
    this.exchanges.clear();
    this.backend?.stopAll();
  }

  delta(message: StateDeltaMessage, mirror: WorldMirror): void {
    this.mirror = mirror;
    for (const edit of message.voxel_edits ?? []) {
      if (edit.action === 'dig' || edit.action === 'place')
        this.effect(edit.action, edit.x, edit.y);
    }
    for (const update of message.actors) {
      const previous = this.positions.get(update.rtoken);
      const current = mirror.actors.get(update.rtoken);
      if (previous && current && update.op !== 'add' && update.op !== 'remove') {
        const distance = Math.hypot(current.x - previous.x, current.y - previous.y);
        if (distance > 0 && distance <= 4) this.effect('step', current.x, current.y);
      }
      if (current) this.positions.set(update.rtoken, { x: current.x, y: current.y });
      else this.positions.delete(update.rtoken);
    }
    for (const update of message.structures ?? []) {
      const current = mirror.structures.get(update.rtoken);
      if (current?.phase === 'rubble' && this.phases.get(update.rtoken) !== 'rubble') {
        const tile = current.tiles[0];
        if (tile) this.effect('collapse', tile[0], tile[1]);
      }
      if (current) this.phases.set(update.rtoken, current.phase);
      else this.phases.delete(update.rtoken);
    }
    this.ambience();
  }

  combat(message: CombatEventMessage, mirror: WorldMirror): void {
    this.mirror = mirror;
    const key = `${message.rtoken}:${message.exchange}:${message.posture_visual}`;
    if (!message.exchange_resolved || this.exchanges.has(key)) return;
    if (this.exchanges.size >= 64) {
      const oldest = this.exchanges.values().next().value;
      if (oldest) this.exchanges.delete(oldest);
    }
    this.exchanges.add(key);
    const actor = mirror.actors.get(message.rtoken);
    if (actor) this.effect('combat', actor.x, actor.y);
  }

  private get audible(): boolean {
    return (
      this.connected &&
      this.hasSnapshot &&
      this.unlocked &&
      !this.preferences.muted &&
      this.preferences.volume > 0
    );
  }

  private gainAt(x: number, y: number): number {
    const listener = this.mirror?.actors.get(this.mirror.protagonist ?? '');
    if (!listener || !Number.isFinite(x) || !Number.isFinite(y)) return 0;
    const distance = Math.hypot(x - listener.x, y - listener.y);
    return distance <= 8 ? 1 / (1 + distance * 0.45) : 0;
  }

  private effect(effect: EffectId, x: number, y: number): void {
    if (!this.audible) return;
    const gain = this.gainAt(x, y),
      now = this.now();
    if (gain === 0 || now - (this.played.get(effect) ?? -Infinity) < 120) return;
    this.played.set(effect, now);
    this.backend?.play(effect, gain);
  }

  private ambience(): void {
    let gain = 0;
    if (this.audible)
      for (const light of this.mirror?.lights.values() ?? []) {
        if (light.kind === 'fire') gain = Math.max(gain, this.gainAt(light.x, light.y));
      }
    this.backend?.setAmbience(gain > 0 ? 'fire' : null, gain);
  }
}
