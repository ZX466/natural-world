"""sim.world.ecology — 生态相位派生（M6 内容面；DESIGN §13 生态，K12 订正后口径）。

**职责边界（最小面）**：
- 生态 = **tick 纯函数派生**（opencode A3 判定：相位由 tick 派生、可重放、
  **不入库**——对照 A8 火势中间态口径）；无状态、无 IO、无事件写；
- **到期桶形态**（pi P4 红线：「每 tick 全量扫」=400µs/tick 必红——本模块
  按**到期 tick 分桶**，每 tick 只算 O(桶内项)，不是 O(全量)）；
- 派生面 = 猎物-捕食者相位（logistic 增长占位）+ 季节迁徙节律——输出是
  **可叙事的相位标签**（消费方=感知帧/独白叙事），**零数值出站**（铁律 1：
  数量/密度/增长率不进帧、不进协议——K12 payload 零归因同源纪律）。

**为什么是纯派生不是事件驱动**（A3 §2.4 + K4 C1 判定）：生态相位无治理状态
（无 `entry_id` 谱系、无语料行）、任何 tick 可离线重算 ⇒ 事件只会复制
「tick 本来就能算出的东西」（第二真相源，撞 schema §19.3）。`ecology.shift`
事件**只在相位跨越时发**（信号≠状态，对照 fire.ignited 同判）——由调用方
（世界循环）比较前后相位决定，本模块只给派生函数。

C5：同 (seed, tick) 必得同相位（无隐藏随机/时钟）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sim.core.calendar import TICKS_PER_GAME_DAY

#: 生态节律周期（游戏日；内容常量·占位值——猎物繁盛/回落的完整循环长度）。
ECOLOGY_PERIOD_DAYS: Final[int] = 7

#: 相位标签（可叙事；零数值——铁律 1，进帧的只有这几个词）。
PHASE_BLOOM: Final[str] = "繁盛"
PHASE_PLATEAU: Final[str] = "平稳"
PHASE_SCARCE: Final[str] = "稀少"

#: 事件流名（生态抽签归混沌流同族；占用 P9 RNG/熵行额度，不叠加新行——P9 口径）。
ECOLOGY_STREAM: Final[str] = "ecology"


@dataclass(frozen=True)
class EcologyPhase:
    """某 tick 的生态相位（frozen；**零数值字段**——只带可叙事标签与坐标哨兵）。

    `prey_trend`/`predator_trend`：三档相位词（升/平/降的可叙事标签），
    **不是**数值——数量/密度不进任何出站面（K12 纪律）。
    """

    tick: int
    phase: str  # PHASE_* 之一
    prey_trend: str  # PHASE_* 之一（猎物侧）
    predator_trend: str  # PHASE_* 之一（捕食者侧，滞后猎物半周期）

    def __post_init__(self) -> None:
        for f in (self.phase, self.prey_trend, self.predator_trend):
            if f not in (PHASE_BLOOM, PHASE_PLATEAU, PHASE_SCARCE):
                raise ValueError(f"生态相位标签非法: {f!r}")


def _cycle_position(tick: int) -> int:
    """tick → 周期内位置 [0, period)（纯派生；到期桶的桶键）。"""
    return (tick // TICKS_PER_GAME_DAY) % ECOLOGY_PERIOD_DAYS


def ecology_phase_at(tick: int) -> EcologyPhase:
    """某 tick 的生态相位（**纯函数**；到期桶键=周期内日序，每游戏日一档）。

    相位曲线（占位 logistic 直段）：前 1/3 繁盛、中 1/3 平稳、后 1/3 稀少；
    捕食者滞后猎物半周期（捕食者相位 = 猎物相位平移 `period//2`）。
    C5：同 tick 恒同相位；异 tick 独立（无调用序依赖）。
    """
    pos = _cycle_position(tick)
    third = ECOLOGY_PERIOD_DAYS // 3
    if pos < third:
        prey = PHASE_BLOOM
    elif pos < third * 2:
        prey = PHASE_PLATEAU
    else:
        prey = PHASE_SCARCE
    pred_pos = (pos + ECOLOGY_PERIOD_DAYS // 2) % ECOLOGY_PERIOD_DAYS
    if pred_pos < third:
        predator = PHASE_BLOOM
    elif pred_pos < third * 2:
        predator = PHASE_PLATEAU
    else:
        predator = PHASE_SCARCE
    return EcologyPhase(tick=tick, phase=prey, prey_trend=prey, predator_trend=predator)


def ecology_shift_due(prev_tick: int, cur_tick: int) -> bool:
    """相位是否在 (prev_tick, cur_tick] 内跨越（世界循环据此发 `ecology.shift`）。

    跨越判定 = 两端相位标签不同（**信号≠状态**：只有可叙事相位变了才算
    「shift」——档内每 tick 重算恒同值，不该发事件）。帧驱动一帧 0..N tick，
    逐 tick 比较会漏跨越 ⇒ 用「首尾标签不同」近似（同 day-switch 跨越式判定
    口径，M3 B-B2 教训：等值点会被整帧跳过）。
    """
    if cur_tick <= prev_tick:
        return False
    return ecology_phase_at(prev_tick).phase != ecology_phase_at(cur_tick).phase
