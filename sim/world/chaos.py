"""混沌流 — DESIGN §11「确定性 ≠ 预定」（M5 批次 A 架构件，裁 30-F 我域）。

两件分离（C5 守卫的核心）：
- **确定性混沌 `chaotic(stream)`**：日常演化抽签（寻路扰动/对话微变/价格微调/
  情绪回落）。**纯函数形态**：由流材料指纹派生独立 Generator 抽 uniform(0,1)，
  **不推进注册表抽签状态、不落事件**（opencode 预研 §a 结论——抽样落事件会让
  R2 重放在父前缀与子事件各采一次，制造对账歧义）。同一 (world_seed, materials)
  下任意 tick 可独立重算、调用顺序不影响结果 ⇒ T2 回放逐位一致天然成立。
- **真随机注入**：走既有 `EntropyMixer.mix`（os.urandom 采集+reseed+entropy.inject
  事件落流）。本模块只提供「该不该注入」的判据面（`should_inject`），接线归
  世界循环单。

注入点判据（DESIGN §11 原文）：「这个结果会不会成为一段可以讲述的故事？会，就
注入」——事件驱动非 per-tick（opencode 预研 §a：20-150 条/游戏日，<0.01% 事件
密度）。判据输入 = 事件类型白名单（NPC 重大决策/致命一击/偶遇/每日天气/玩家
行为意外后果），由调用方在事件产生点判定，本模块不扫事件流。

出戏边界（裁 14-5 延续）：熵值/seed/luck 不进 prompt、不进感知帧、不进协议
三面——本模块返回值只被内核消费（TT 系统内部），T1 钉在 test_t1_m5_history_
preserved 体系内复核。
"""

from __future__ import annotations

import hashlib
from typing import Final

import numpy as np

from sim.core.rng import RngRegistry

#: 混沌流名（DESIGN §11「确定性混沌」的注册流）。
CHAOS_STREAM: Final = "chaos"

#: 确定性抽样的缓存键前缀（与 RngRegistry.generator 的抽签缓存隔离——
#: chaotic 不推进抽签进度，缓存生命周期=单次调用即可，无跨 tick 状态）。


def chaotic(stream: str, rng: RngRegistry) -> float:
    """确定性混沌抽签：uniform(0,1)，纯函数可重放。

    与 `RngRegistry.generator()` 的区别：generator 的 cache **保存抽签进度**
    （同 key 连续调用推进流）；chaotic 每次由材料指纹**重建** Generator，
    同材料恒同值（无进度、无调用序依赖）。流的材料被 `inject` 重播种后，
    chaotic 序列整体切换（DESIGN §11：注入后「重新播种」的语义）。
    """
    material = rng._material(stream)
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    gen = np.random.Generator(np.random.PCG64(seed))
    return float(gen.random())


def chaotic_at(stream: str, rng: RngRegistry, tick: int) -> float:
    """带 tick 变度的确定性抽签：同流同刻恒同值，异刻独立均匀样本。

    「日常演化每 tick 有微小不同」的语义载体——把 tick 揉进派生材料而非推进
    抽签进度，保持纯函数性（任意 tick 可独立重算）。tick=0 退化为 `chaotic`。
    """
    if tick == 0:
        return chaotic(stream, rng)
    material = rng._material(stream) + tick.to_bytes(8, "big")
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    gen = np.random.Generator(np.random.PCG64(seed))
    return float(gen.random())
