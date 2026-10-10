/**
 * client/src/game/clock.ts — 戏内时钟（R3：服务端权威帧 + 客户端平滑推进）。
 *
 * 权威帧（full_snapshot/state_delta/session_state 的 time 块）到达即整体重同步；
 * 两帧之间按 speed × 60 游戏秒/真实秒 本地推进（与 sim 60tps 对齐，DESIGN §10）。
 * 世界暂停/倍速/读档最坏漂移一帧间隔，任何帧到达即纠正。
 * phase 换算与 sim/core/calendar.py::phase_of_day 对齐（黎明 5-7/白天 7-17/黄昏 17-19/夜晚其余）。
 * 集市日 (day-1)%5==0 镜像 calendar.py MARKET_DAY_INTERVAL。
 */
import { useUiStore } from '../store/uiStore';
import type { components } from '@shared/protocol';

/** 戏内时间权威帧（协议 1.3 生成物，shared/protocol.ts components.schemas.TimeInfo）。 */
export type TimeInfo = components['schemas']['TimeInfo'];

const GAME_SECONDS_PER_REAL_SECOND = 60; // sim 1x = 60tps
const GAME_SECONDS_PER_DAY = 86_400;
const MARKET_DAY_INTERVAL = 5;

export interface WorldClock {
  /** 权威帧重同步（ws dispatch 三个带 time 的消息都调它）。 */
  apply: (t: TimeInfo) => void;
  start: () => void;
  stop: () => void;
}

export function createClock(): WorldClock {
  let gameSecondOfDay = 0; // 当日已过游戏秒（0..86399）
  let day = 1;
  let isMarketDay = true;
  let timer: ReturnType<typeof setInterval> | null = null;
  let lastTick: number | null = null;

  function publish(): void {
    const hour = Math.floor(gameSecondOfDay / 3600);
    const minute = Math.floor((gameSecondOfDay % 3600) / 60);
    const phase =
      hour < 5 ? 'night' : hour < 7 ? 'dawn' : hour < 17 ? 'day' : hour < 19 ? 'dusk' : 'night';
    useUiStore.getState().setGameClock({ day, hour, minute, phase, isMarketDay });
  }

  return {
    apply(t: TimeInfo): void {
      day = t.day;
      isMarketDay = t.is_market_day;
      gameSecondOfDay = t.hour * 3600 + t.minute * 60;
      publish();
    },
    start(): void {
      if (timer !== null) return;
      lastTick = Date.now();
      timer = setInterval(() => {
        const store = useUiStore.getState();
        if (store.paused) {
          lastTick = Date.now(); // 暂停期间不积欠时
          return;
        }
        const now = Date.now();
        const dt = (now - (lastTick ?? now)) / 1000;
        lastTick = now;
        gameSecondOfDay += dt * GAME_SECONDS_PER_REAL_SECOND * store.speed;
        while (gameSecondOfDay >= GAME_SECONDS_PER_DAY) {
          gameSecondOfDay -= GAME_SECONDS_PER_DAY;
          day += 1;
          isMarketDay = (day - 1) % MARKET_DAY_INTERVAL === 0;
        }
        publish();
      }, 250);
    },
    stop(): void {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    },
  };
}

/** 单例：ws dispatch 与 runtime 共用（一个世界一个钟）。 */
export const worldClock = createClock();
