/** Phaser owns the AudioContext; this channel owns only its nodes and buffers. */
export type EffectId = 'step' | 'dig' | 'place' | 'combat' | 'collapse';
export interface AudioBackend {
  unlock(): Promise<boolean>;
  play(effect: EffectId, gain: number): void;
  setAmbience(effect: 'fire' | null, gain: number): void;
  setVolume(volume: number): void;
  stopAll(): void;
  dispose(): void;
}

interface AudioOutput {
  context: AudioContext;
  destination: AudioNode;
}
interface Voice {
  source: AudioBufferSourceNode;
  filter: BiquadFilterNode;
  gain: GainNode;
}
const SPECS = {
  step: { seconds: 0.055, frequency: 650, level: 0.18, seed: 17 },
  dig: { seconds: 0.15, frequency: 1100, level: 0.22, seed: 31 },
  place: { seconds: 0.09, frequency: 500, level: 0.23, seed: 47 },
  combat: { seconds: 0.16, frequency: 1800, level: 0.17, seed: 61 },
  collapse: { seconds: 0.45, frequency: 700, level: 0.24, seed: 79 },
  fire: { seconds: 2, frequency: 950, level: 0.08, seed: 97 },
} as const;

function bounded(value: number): number {
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
}

export function createNoise(length: number, seed: number): Float32Array {
  const values = new Float32Array(length);
  let state = seed >>> 0 || 1;
  for (let index = 0; index < values.length; index++) {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    values[index] = ((state >>> 0) / 0xffffffff) * 2 - 1;
  }
  return values;
}

export class WebAudioSynth implements AudioBackend {
  private output: AudioOutput | null = null;
  private master: GainNode | null = null;
  private ready = false;
  private disposed = false;
  private volume = 0;
  private voices = new Set<Voice>();
  private buffers = new Map<string, AudioBuffer>();
  private fire: Voice | null = null;

  constructor(private readonly outputOf: () => AudioOutput | null) {}

  async unlock(): Promise<boolean> {
    if (this.disposed) return false;
    try {
      const output = this.output ?? this.outputOf();
      if (!output || output.context.state === 'closed') return false;
      if (output.context.state !== 'running') await output.context.resume();
      if (this.disposed || output.context.state !== 'running') return false;
      this.output = output;
      if (!this.master) {
        this.master = output.context.createGain();
        this.master.connect(output.destination);
      }
      this.master.gain.setValueAtTime(this.volume, output.context.currentTime);
      this.ready = true;
      return true;
    } catch {
      return false;
    }
  }

  setVolume(volume: number): void {
    this.volume = bounded(volume);
    if (this.master && this.output)
      this.master.gain.setValueAtTime(this.volume, this.output.context.currentTime);
  }

  play(effect: EffectId, gain: number): void {
    this.voice(effect, gain, false);
  }

  setAmbience(effect: 'fire' | null, gain: number): void {
    if (effect === null || bounded(gain) === 0) {
      if (this.fire) this.release(this.fire);
      this.fire = null;
      return;
    }
    if (this.fire && this.output) {
      this.fire.gain.gain.setValueAtTime(
        SPECS.fire.level * bounded(gain),
        this.output.context.currentTime,
      );
    } else this.fire = this.voice('fire', gain, true);
  }

  private voice(effect: EffectId | 'fire', gain: number, loop: boolean): Voice | null {
    const output = this.output;
    if (
      !this.ready ||
      this.disposed ||
      !output ||
      !this.master ||
      output.context.state !== 'running' ||
      bounded(gain) === 0
    )
      return null;
    if (this.voices.size >= 8) {
      const oldest = this.voices.values().next().value;
      if (oldest) this.release(oldest);
    }
    const { context } = output;
    const spec = SPECS[effect];
    let buffer = this.buffers.get(effect);
    if (!buffer) {
      const length = Math.max(1, Math.round(spec.seconds * context.sampleRate));
      buffer = context.createBuffer(1, length, context.sampleRate);
      const noise = createNoise(length, spec.seed);
      for (let index = 0; index < length; index++) {
        const edge = Math.min(
          1,
          index / (context.sampleRate * 0.008),
          (length - 1 - index) / (context.sampleRate * 0.008),
        );
        noise[index] = (noise[index] ?? 0) * edge;
      }
      buffer.getChannelData(0).set(noise);
      this.buffers.set(effect, buffer);
    }
    const source = context.createBufferSource();
    const filter = context.createBiquadFilter();
    const envelope = context.createGain();
    source.buffer = buffer;
    source.loop = loop;
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(spec.frequency, context.currentTime);
    source.connect(filter);
    filter.connect(envelope);
    envelope.connect(this.master);
    const level = spec.level * bounded(gain);
    if (loop) envelope.gain.setValueAtTime(level, context.currentTime);
    else {
      envelope.gain.setValueAtTime(0.0001, context.currentTime);
      envelope.gain.linearRampToValueAtTime(level, context.currentTime + 0.008);
      envelope.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + spec.seconds);
    }
    const voice = { source, filter, gain: envelope };
    this.voices.add(voice);
    source.onended = () => this.release(voice);
    source.start();
    if (!loop) source.stop(context.currentTime + spec.seconds);
    return voice;
  }

  private release(voice: Voice): void {
    if (!this.voices.delete(voice)) return;
    if (this.fire === voice) this.fire = null;
    voice.source.onended = null;
    try {
      voice.source.stop();
    } catch {
      /* A naturally ended source needs only disconnection. */
    }
    voice.source.disconnect();
    voice.filter.disconnect();
    voice.gain.disconnect();
  }

  stopAll(): void {
    for (const voice of [...this.voices]) this.release(voice);
  }

  dispose(): void {
    this.disposed = true;
    this.ready = false;
    this.stopAll();
    this.master?.disconnect();
    this.master = null;
    this.output = null;
    this.buffers.clear();
  }
}
