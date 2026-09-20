"""sim.perception — 感知层（DESIGN §7，C06-③）。

M1 落地：传播三要素（propagation）+ 感知帧（frame）+ 显著性（salience）
+ 叙事化（narrate）+ 引擎（senses）+ human profile（profiles.human）。
嗅觉/语言判定 M2（language.py 届时落地）。
"""

from sim.perception.frame import Channel, Observation, PerceptionFrame
from sim.perception.profiles.base import PerceptionProfile
from sim.perception.profiles.human import HUMAN
from sim.perception.senses import PerceptionEngine, rtoken_of

__all__ = [
    "HUMAN",
    "Channel",
    "Observation",
    "PerceptionEngine",
    "PerceptionFrame",
    "PerceptionProfile",
    "rtoken_of",
]
