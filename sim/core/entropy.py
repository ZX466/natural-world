"""混合熵注入 — C5（m0-core.md §3）。

熵源采集（os.urandom 等）只允许出现在本模块内部；
注入必须经 apply(EntropyEvent) 落事件日志，重放时逐位一致。
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict

from sim.core.events import WorldEvent, entropy_event
from sim.core.rng import RngRegistry


class EntropyMixer(BaseModel):
    """采集外部熵 → 混入目标流。frozen：mix 返回新实例。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    rng: RngRegistry

    def mix(self, stream: str, tick: int, nbytes: int = 16) -> tuple[EntropyMixer, WorldEvent]:
        """采集 os.urandom → reseed 目标流 → 返回（新 mixer，熵事件）。

        调用方必须把事件交给 EventBus.apply 落日志；
        重放路径用 event.payload 里的材料调 replay_mix 重建同样的注册表。
        """
        material = os.urandom(nbytes)
        return (
            EntropyMixer(rng=self.rng.reseed(stream, material)),
            entropy_event(tick=tick, stream=stream, payload_hex=material.hex()),
        )

    def replay_mix(self, stream: str, material_hex: str) -> EntropyMixer:
        """重放路径：用事件里记录的熵材料重建注册表（不采集新熵）。"""
        return EntropyMixer(rng=self.rng.reseed(stream, bytes.fromhex(material_hex)))
