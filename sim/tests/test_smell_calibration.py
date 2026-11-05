"""B1 定标：人群密集可闻、独行不可闻（spec §4.1 的实测口径写成回归钉）。"""

from __future__ import annotations

import numpy as np

from sim.perception.profiles.base import PerceptionProfile
from sim.perception.smell_world import SMELL_SOURCE_STRENGTH, SmellWorld

TICKS = 200
WIND = (0.0, 0.0)  # 静风 = 最坏情形（不吹散）


def _settle(positions: dict[str, tuple[int, int]]) -> np.ndarray:
    world = SmellWorld(height=100, width=140)
    values = np.zeros(0)
    for _ in range(TICKS):
        samples = world.step(positions, wind=WIND)
        values = np.array(list(samples.values()), dtype=np.float64)
    return values


def _clustered(n: int, seed: int = 42) -> dict[str, tuple[int, int]]:
    rng = np.random.default_rng(seed)
    anchors = ((100, 52), (72, 52))
    return {
        f"npc_{i}": (
            anchors[i % 2][0] + int(rng.integers(-4, 5)),
            anchors[i % 2][1] + int(rng.integers(-4, 5)),
        )
        for i in range(n)
    }


def test_source_strength_is_calibrated_for_crowds() -> None:
    assert SMELL_SOURCE_STRENGTH == 0.04


def test_smell_floor_is_its_own_knob() -> None:
    profile = PerceptionProfile(species="human", vision_radius=12.0, hearing_radius=14.0)
    assert profile.smell_floor == 0.08
    assert profile.smell_floor != profile.hearing_floor


def test_a_lone_walker_never_smells_the_crowd() -> None:
    values = _settle({"walker": (100, 52)})
    assert float(values.max()) < 0.08, "独行者不该闻到味道（用户反馈的直接来源）"


def test_a_crowd_always_smells() -> None:
    values = _settle(_clustered(50))
    assert int((values >= 0.08).sum()) == 50


def test_the_floor_coincides_with_the_lowest_text_tier() -> None:
    """门槛必须与最低档重合，否则「过了门槛却落不进任何档」的死区（spec 陷阱 #7）。

    地板 0.08 之上，四档必须逐级可辨；地板本身落进最低档。
    """
    from sim.perception.narrate import narrate_smell

    texts = [narrate_smell(c) for c in (0.08, 0.18, 0.30, 0.55)]
    assert len(set(texts)) == 4, f"四档文案必须互不相同: {texts}"
    assert narrate_smell(0.08) == narrate_smell(0.17), "0.08 与 0.17 都应在最低档"
