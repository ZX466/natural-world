"""陈默专用 needs 投影：沿用内容种子、村民速率和补救口径。"""

from __future__ import annotations

import pytest

from sim.agent.self_needs import ProtagonistNeeds
from sim.content import protagonist
from sim.npc.model import Need


def test_seed_builder_preserves_existing_profile_payload() -> None:
    assert protagonist.build_needs() == (
        Need("hunger", 0.3, 1.0),
        Need("energy", 0.2, 0.8),
        Need("social", 0.4, 0.6),
    )
    assert protagonist._profile_row()["needs"] == (
        '[{"name": "hunger", "value": 0.3, "weight": 1.0}, '
        '{"name": "energy", "value": 0.2, "weight": 0.8}, '
        '{"name": "social", "value": 0.4, "weight": 0.6}]'
    )


@pytest.mark.parametrize("initial_tick", (0, 450740))
def test_decay_uses_elapsed_ticks_not_absolute_tick(initial_tick: int) -> None:
    projection = ProtagonistNeeds(initial_tick)
    assert projection.hunger == 0.3

    projection.advance_to(initial_tick + 43200)

    assert tuple(n.value for n in projection.needs) == pytest.approx((0.8, 0.95, 0.65))
    assert projection.hunger == pytest.approx(0.8)


def test_chunked_advance_matches_a_single_elapsed_jump() -> None:
    chunked = ProtagonistNeeds(450740)
    single = ProtagonistNeeds(450740)

    for elapsed in (7200, 21600, 43200):
        chunked.advance_to(450740 + elapsed)
    single.advance_to(450740 + 43200)

    assert tuple(n.value for n in chunked.needs) == pytest.approx((0.8, 0.95, 0.65))
    assert tuple(n.value for n in single.needs) == pytest.approx((0.8, 0.95, 0.65))


def test_repeated_tick_does_not_repeat_decay() -> None:
    projection = ProtagonistNeeds(1000)
    projection.advance_to(1000)
    assert projection.hunger == 0.3
    projection.advance_to(4600)
    projection.apply("eat")
    settled = projection.needs

    projection.advance_to(4600)
    projection.advance_to(4600)

    assert projection.needs == settled


@pytest.mark.parametrize("older_tick", (0, 1000, 2000))
def test_older_tick_keeps_values_and_forward_watermark(older_tick: int) -> None:
    projection = ProtagonistNeeds(1000)
    projection.advance_to(4600)
    current = projection.needs

    projection.advance_to(older_tick)
    assert projection.needs == current
    projection.advance_to(8200)

    assert tuple(n.value for n in projection.needs) == pytest.approx(
        (0.3833333333333333, 0.325, 0.4416666666666667)
    )


@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("eat", (0.7, 0.45, 0.5)),
        ("rest", (0.7, 0.3, 0.8)),
        ("request_chat", (0.4, 0.6, 0.8)),
        ("work", (0.7, 0.6, 0.8)),
        ("unknown", (0.7, 0.6, 0.8)),
    ),
)
def test_apply_uses_existing_remedies_and_preserves_need_order(
    action: str, expected: tuple[float, ...]
) -> None:
    projection = ProtagonistNeeds(
        0,
        needs=(Need("social", 0.7, 0.6), Need("energy", 0.6, 0.8), Need("hunger", 0.8, 1.0)),
    )

    projection.apply(action)

    assert tuple(n.value for n in projection.needs) == pytest.approx(expected)
    assert tuple((n.name, n.weight) for n in projection.needs) == (
        ("social", 0.6),
        ("energy", 0.8),
        ("hunger", 1.0),
    )
    assert projection.hunger == pytest.approx(expected[2])


def test_decay_continues_from_the_same_frontier_after_remedy() -> None:
    projection = ProtagonistNeeds(1000)
    projection.advance_to(4600)
    projection.apply("eat")

    projection.advance_to(8200)

    assert tuple(n.value for n in projection.needs) == pytest.approx(
        (0.0833333333333333, 0.175, 0.4416666666666667)
    )


def test_long_elapsed_jump_clips_needs_at_one() -> None:
    projection = ProtagonistNeeds(0)

    projection.advance_to(864000)

    assert tuple(n.value for n in projection.needs) == (1.0, 1.0, 1.0)


@pytest.mark.parametrize(
    ("action", "expected"),
    (
        ("eat", (0.0, 0.0, 0.1)),
        ("rest", (0.1, 0.0, 0.1)),
        ("request_chat", (0.1, 0.1, 0.0)),
    ),
)
def test_remedy_clips_affected_needs_at_zero(action: str, expected: tuple[float, ...]) -> None:
    projection = ProtagonistNeeds(
        0,
        needs=(Need("hunger", 0.1, 1.0), Need("energy", 0.1, 0.8), Need("social", 0.1, 0.6)),
    )

    projection.apply(action)

    assert tuple(n.value for n in projection.needs) == expected


def test_updates_leave_content_seed_and_previous_snapshot_immutable() -> None:
    seed = protagonist.build_needs()
    projection = ProtagonistNeeds(0, needs=seed)
    snapshot = projection.needs

    projection.advance_to(43200)
    projection.apply("eat")

    assert tuple(n.value for n in projection.needs) == pytest.approx((0.5, 0.8, 0.65))
    original = (Need("hunger", 0.3, 1.0), Need("energy", 0.2, 0.8), Need("social", 0.4, 0.6))
    assert seed == original
    assert snapshot == original
    assert protagonist.build_needs() == original
    assert ProtagonistNeeds(43200).needs == original


@pytest.mark.parametrize("attribute", ("needs", "hunger"))
def test_projection_views_are_read_only(attribute: str) -> None:
    projection = ProtagonistNeeds(0)

    with pytest.raises(AttributeError):
        setattr(projection, attribute, ())


@pytest.mark.parametrize("seed", ((), (Need("curiosity", 0.5, 1.0),)))
def test_custom_needs_without_hunger_are_preserved(seed: tuple[Need, ...]) -> None:
    projection = ProtagonistNeeds(0, needs=seed)

    projection.advance_to(86400)
    projection.apply("eat")

    assert projection.needs == seed
    assert projection.hunger == 0.0
