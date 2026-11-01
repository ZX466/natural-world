import { create } from 'zustand';

interface AudioSettings {
  muted: boolean;
  volume: number;
  setMuted(muted: boolean): void;
  setVolume(volume: number): void;
}

/** Explicit opt-in each page load; audio preference never changes world state. */
export const useAudioStore = create<AudioSettings>((set) => ({
  muted: true,
  volume: 0.25,
  setMuted: (muted) => set({ muted }),
  setVolume: (volume) =>
    set({ volume: Number.isFinite(volume) ? Math.max(0, Math.min(1, volume)) : 0 }),
}));
