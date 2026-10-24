/**
 * client/src/store/uiStore.ts — 薄 Zustand 适配层（m0-client.md §5.3）。
 *
 * codex 意见 4：只暴露白名单低频字段（戏内时间/相位/连接态），字段清单
 * 对齐 m1-checklist W1；高频实体位置绝不进 React 树。
 * codex 意见 2：快照/世界真相数值禁入本 store（戏外调试层走 W2 独立通道，M0 不做）。
 */
import { create } from 'zustand';
import type { PlanDelta, VoxelStateMessage } from '../net/protocol';
import type { WsStatus } from '../net/ws';

/** 独白环形缓冲上限（超过丢最旧；M4 叙事面） */
export const MONOLOGUE_CAP = 20;

/** 街谈巷议环形缓冲上限（批次 D10：村民 bubble 与陈默心声分流；超过丢最旧） */
export const CHATTER_CAP = 8; // D20：嘟囔池收紧——12 条已足以把心之声挤出首屏

export type MonologueForm = 'bubble' | 'thought' | 'plan';

/** 独白条目（monologue 帧 / impulse reaction_monologue 的消费端形态） */
export interface MonologueEntry {
  form: MonologueForm;
  content: string;
}

/** 街谈巷议条目（批次 D12：bubble 署名——「谁在说」可读；无名退化为匿名） */
export interface ChatterEntry {
  name: string | null;
  content: string;
}

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
  voxelInventory: VoxelStateMessage['inventory'] | null;
  voxelError: string | null;
  setVoxelInventory: (inventory: VoxelStateMessage['inventory'] | null) => void;
  setVoxelError: (message: string | null) => void;
  wsStatus: WsStatus;
  gameClock: InGameTime | null;
  speed: Speed;
  paused: boolean;
  combatActive: boolean;
  /** 已消费的战斗表现帧数；仅用于观测接线，不显示在戏内。 */
  combatEventCount: number;
  /** impulse 反馈 cue（批次 A 起接真实数据源） */
  lastImpulseCue: string | null;
  /** 独白流（环形缓冲，上限 MONOLOGUE_CAP；只进面板文本，高频位置数据不在此） */
  monologues: MonologueEntry[];
  /** 街谈巷议（批次 D10：村民公开自语 bubble 专属环形缓冲——村民的嘟囔
   *  是镇上的公开声音，不是陈默的内心活动；与 monologues 分流防刷屏。
   *  D12：条目带署名） */
  chatter: ChatterEntry[];
  /** 计划看板（state_delta.plan 整组替换；空 = 收起） */
  plans: PlanDelta[];
  /** impulse 入站 error 帧玩家可见文案（仅 ref=player_impulse 置位） */
  impulseError: string | null;
  setWsStatus: (s: WsStatus) => void;
  setGameClock: (t: InGameTime | null) => void;
  setSpeed: (s: Speed) => void;
  setPaused: (p: boolean) => void;
  setCombatActive: (active: boolean) => void;
  recordCombatEvent: () => void;
  setLastImpulseCue: (cue: string | null) => void;
  pushMonologue: (form: MonologueForm, content: string) => void;
  pushChatter: (name: string | null, content: string) => void;
  setPlans: (plans: PlanDelta[]) => void;
  setImpulseError: (e: string | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  voxelInventory: null,
  voxelError: null,
  setVoxelInventory: (voxelInventory) => set({ voxelInventory }),
  setVoxelError: (voxelError) => set({ voxelError }),
  wsStatus: 'connecting',
  gameClock: null,
  speed: 1,
  paused: false,
  combatActive: false,
  combatEventCount: 0,
  lastImpulseCue: null,
  monologues: [],
  chatter: [],
  plans: [],
  impulseError: null,
  setWsStatus: (wsStatus) => set({ wsStatus }),
  setGameClock: (gameClock) => set({ gameClock }),
  setSpeed: (speed) => set({ speed }),
  setPaused: (paused) => set({ paused }),
  setCombatActive: (combatActive) => set({ combatActive }),
  recordCombatEvent: () => set((s) => ({ combatEventCount: s.combatEventCount + 1 })),
  setLastImpulseCue: (lastImpulseCue) => set({ lastImpulseCue }),
  pushMonologue: (form, content) =>
    set((s) => ({ monologues: [...s.monologues, { form, content }].slice(-MONOLOGUE_CAP) })),
  pushChatter: (name, content) =>
    set((s) => ({ chatter: [...s.chatter, { name, content }].slice(-CHATTER_CAP) })),
  setPlans: (plans) => set({ plans }),
  setImpulseError: (impulseError) => set({ impulseError }),
}));
