import { useAudioStore } from '../../store/audioStore';
import { WorldAudio } from './world-audio';

export const worldAudio = new WorldAudio();
worldAudio.configure(useAudioStore.getState());
useAudioStore.subscribe((settings) => worldAudio.configure(settings));
