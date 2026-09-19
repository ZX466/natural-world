/**
 * client/src/store/uiStore.ts — 薄 Zustand 适配层（m0-client.md §5.3）。
 *
 * codex 意见 4：只暴露白名单低频字段（戏内时间/相位/连接态），字段清单
 * 对齐 m1-checklist W1；高频实体位置绝不进 React 树。
 * codex 意见 2：快照/世界真相数值禁入本 store（戏外调试层走 W2 独立通道，M0 不做）。
 */
import { create } from 'zustand';
import type { WsStatus } from '../net/ws';

/** 戏内时间白名单——本 store 允许暴露的全部世界派生字段。 */
export interface InGameTime {
  day: number;
  hour: number;
  minute: number;
  phase: 'dawn' | 'day' | 'dusk' | 'night';
  isMarketDay: boolean;
}

export type Speed = 1 | 4 | 16;

interface UiState {
  wsStatus: WsStatus;
  gameClock: InGameTime | null;
  speed: Speed;
  paused: boolean;
  /** impulse 反馈 cue（M4 起有真实数据；M0 供占位 UI） */
  lastImpulseCue: string | null;
  setWsStatus: (s: WsStatus) => void;
  setGameClock: (t: InGameTime | null) => void;
  setSpeed: (s: Speed) => void;
  setPaused: (p: boolean) => void;
  setLastImpulseCue: (cue: string | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  wsStatus: 'connecting',
  gameClock: null,
  speed: 1,
  paused: false,
  lastImpulseCue: null,
  setWsStatus: (wsStatus) => set({ wsStatus }),
  setGameClock: (gameClock) => set({ gameClock }),
  setSpeed: (speed) => set({ speed }),
  setPaused: (paused) => set({ paused }),
  setLastImpulseCue: (lastImpulseCue) => set({ lastImpulseCue }),
}));
