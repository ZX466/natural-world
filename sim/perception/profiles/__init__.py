"""感知层 profiles — 物种级（不是角色级）感知参数（DESIGN §7）。"""

from sim.perception.profiles.base import PerceptionProfile
from sim.perception.profiles.human import HUMAN

__all__ = ["HUMAN", "PerceptionProfile"]
