/**
 * client/src/store/uiStore.ts — 薄 Zustand 适配层（m0-client.md §5.3）。
 *
 * codex 意见 4：只暴露白名单低频字段（戏内时间/相位/连接态），字段清单
 * 对齐 m1-checklist W1；高频实体位置绝不进 React 树。
 * codex 意见 2：快照/世界真相数值禁入本 store（戏外调试层走 W2 独立通道，M0 不做）。
 */
import { create } from 'zustand';
import type {
  NpcView,
  NpcViewDelta,
  PlanDelta,
  SessionAnchor,
  VoxelRequestMessage,
  VoxelStateMessage,
} from '../net/protocol';
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
export type VoxelMaterial = NonNullable<VoxelRequestMessage['material']>;

/** 每个 upsert 都是该人物的完整叙事投影；空数组会撤下此前可见的文字。 */
function applyNpcViewDeltas(
  current: readonly NpcView[],
  changes: readonly NpcViewDelta[],
): NpcView[] {
  const rows = new Map(current.map((view) => [view.rtoken, view]));
  for (const view of changes) {
    if ('op' in view) {
      if (view.op === 'remove') rows.delete(view.rtoken);
    } else {
      rows.set(view.rtoken, {
        rtoken: view.rtoken,
        ...(view.name === undefined ? {} : { name: view.name }),
        health: [...new Set(view.health)],
        bond: view.bond,
        knows: [...new Set(view.knows)],
      });
    }
  }
  return [...rows.values()];
}

interface UiState {
  voxelMaterial: VoxelMaterial;
  setVoxelMaterial: (material: VoxelMaterial) => void;
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
  /** 服务端筛选过的低频人物叙事；没有健康/关系原始数值和实体位置。 */
  npcViews: NpcView[];
  /** state_delta.plan 数据面（整组替换）。计划看板 UI 已于 2026-10-26 退役，
   *  字段保留供其他消费者；不要再接回面板。 */
  plans: PlanDelta[];
  /** impulse 入站 error 帧玩家可见文案（仅 ref=player_impulse 置位） */
  impulseError: string | null;
  /** 读档失败文案（error 帧 ref=load_anchor）——存档面板内展示；
   *  读档请求发出时清空，避免旧失败文案赖在面板上。 */
  loadError: string | null;
  /** 读档在途（D3）。**由帧驱动**：`loadAnchor()` 置位，
   *  `full_snapshot`（世界已恢复）或 `error{ref:load_anchor}` 清除。
   *  面板的 `disabled` 必须用它，不能用同步 `try/finally` 的本地 busy——
   *  大库读档重放 20s+，本地 busy 会立刻清回，按钮等于从未禁用（可连点双 fork）。 */
  loadPending: boolean;
  /** 读档分叉告知（session_state.notice，D4）。服务端早已备好过闸的戏内口语行，
   *  修前 ws.ts 直接丢弃 ⇒ 玩家永远不知道世界换线了。 */
  forkNotice: string | null;
  /** 当前游标指针（session_state.anchor，D4）：只含 name + story_label（零原始数值）。 */
  sessionAnchor: SessionAnchor | null;
  /** `set_control` 被拒文案（error 帧 ref=set_control，D5）。 */
  controlError: string | null;
  setWsStatus: (s: WsStatus) => void;
  setGameClock: (t: InGameTime | null) => void;
  setSpeed: (s: Speed) => void;
  setPaused: (p: boolean) => void;
  setCombatActive: (active: boolean) => void;
  recordCombatEvent: () => void;
  setLastImpulseCue: (cue: string | null) => void;
  pushMonologue: (form: MonologueForm, content: string) => void;
  /** 整组替换（重连/读档快照的历史投影）。与 push 不同：快照带的是最近 N 条
   *  的**完整**投影，按增量追加会让同一句叠两遍（实机截图实证）。 */
  replaceMonologues: (entries: readonly MonologueEntry[]) => void;
  pushChatter: (name: string | null, content: string) => void;
  /** 同上，街谈巷议面。 */
  replaceChatter: (entries: readonly ChatterEntry[]) => void;
  replaceNpcViews: (entries: readonly NpcView[]) => void;
  mergeNpcViews: (entries: readonly NpcViewDelta[]) => void;
  setPlans: (plans: PlanDelta[]) => void;
  setImpulseError: (e: string | null) => void;
  setLoadError: (e: string | null) => void;
  setLoadPending: (p: boolean) => void;
  setForkNotice: (n: string | null) => void;
  setSessionAnchor: (a: SessionAnchor | null) => void;
  setControlError: (e: string | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  voxelInventory: null,
  voxelError: null,
  voxelMaterial: 'earth',
  setVoxelMaterial: (voxelMaterial) =>
    set((state) => ((state.voxelInventory?.[voxelMaterial] ?? 0) > 0 ? { voxelMaterial } : {})),
  setVoxelInventory: (voxelInventory) =>
    set((state) => ({
      voxelInventory,
      voxelMaterial:
        (voxelInventory?.[state.voxelMaterial] ?? 0) > 0 ? state.voxelMaterial : 'earth',
    })),
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
  npcViews: [],
  plans: [],
  impulseError: null,
  loadError: null,
  loadPending: false,
  forkNotice: null,
  sessionAnchor: null,
  controlError: null,
  setWsStatus: (wsStatus) => set({ wsStatus }),
  setGameClock: (gameClock) => set({ gameClock }),
  setSpeed: (speed) => set({ speed }),
  setPaused: (paused) => set({ paused }),
  setCombatActive: (combatActive) => set({ combatActive }),
  recordCombatEvent: () => set((s) => ({ combatEventCount: s.combatEventCount + 1 })),
  setLastImpulseCue: (lastImpulseCue) => set({ lastImpulseCue }),
  pushMonologue: (form, content) =>
    set((s) => ({ monologues: [...s.monologues, { form, content }].slice(-MONOLOGUE_CAP) })),
  replaceMonologues: (entries) => set(() => ({ monologues: [...entries].slice(-MONOLOGUE_CAP) })),
  pushChatter: (name, content) =>
    set((s) => ({ chatter: [...s.chatter, { name, content }].slice(-CHATTER_CAP) })),
  replaceChatter: (entries) => set(() => ({ chatter: [...entries].slice(-CHATTER_CAP) })),
  replaceNpcViews: (entries) => set({ npcViews: applyNpcViewDeltas([], entries) }),
  mergeNpcViews: (entries) =>
    set((state) => ({ npcViews: applyNpcViewDeltas(state.npcViews, entries) })),
  setPlans: (plans) => set({ plans }),
  setImpulseError: (impulseError) => set({ impulseError }),
  setLoadError: (loadError) => set({ loadError }),
  setLoadPending: (loadPending) => set({ loadPending }),
  setForkNotice: (forkNotice) => set({ forkNotice }),
  setSessionAnchor: (sessionAnchor) => set({ sessionAnchor }),
  setControlError: (controlError) => set({ controlError }),
}));
