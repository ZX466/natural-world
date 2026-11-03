"""每日健康演进：真实投影写路径、确定性与同步快照边界。"""

from __future__ import annotations

import inspect
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import delete, insert, select

from sim.core.calendar import TICKS_PER_GAME_DAY
from sim.core.clock import GameClock
from sim.core.events import EventKind, npc_death_event
from sim.core.persistence.models import NpcHealth, NpcProfile
from sim.core.persistence.npc_store import NpcStore, _project_health
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus
from sim.npc.hidden import HiddenCategory

if TYPE_CHECKING:
    from sim.content.health_evolve import HealthRow, HealthSnapshot


def _row(
    *,
    npc_id: str = "chenmo",
    code: str = "wrist",
    category: HiddenCategory = "old_injury",
    severity: float = 0.2,
    active: bool = True,
    hidden: bool = False,
    notes: str | None = None,
    created_at_tick: int = 0,
) -> HealthRow:
    from sim.content.health_evolve import HealthRow

    return HealthRow(npc_id, category, code, severity, active, hidden, notes, created_at_tick)


def _snapshot(
    rows: tuple[HealthRow, ...],
    *,
    branch_id: str = "main",
    profile_ids: frozenset[str] | None = None,
) -> HealthSnapshot:
    from sim.content.health_evolve import HealthSnapshot

    ids = frozenset(row.npc_id for row in rows) if profile_ids is None else profile_ids
    return HealthSnapshot(branch_id, rows, ids)


def _loop(*, day: int = 1, npc_ids: tuple[str, ...] = ("chenmo",)) -> TickLoop:
    tick = (day - 1) * TICKS_PER_GAME_DAY
    clock = GameClock()
    clock.restore_tick(tick)
    return TickLoop(
        clock=clock,
        bus=build_default_bus(),
        state=WorldState(
            world_seed=42,
            tick=tick,
            entities={npc_id: EntityState(entity_id=npc_id, pos=(1, 1)) for npc_id in npc_ids},
        ),
    )


def _set_day(loop: TickLoop, day: int) -> None:
    loop.state = loop.state.model_copy(update={"tick": (day - 1) * TICKS_PER_GAME_DAY})


async def _persist_rows(
    store,
    rows: tuple[HealthRow, ...],
    *,
    branch_id: str = "main",
    profile_ids: tuple[str, ...] | None = None,
    id_offset: int = 0,
) -> None:
    """仅在共享临时库中建夹具；固定全行初值供 A6 逐列对账。"""
    ids = tuple(sorted({row.npc_id for row in rows})) if profile_ids is None else profile_ids
    async with store.session_factory.begin() as db:
        db.add_all(
            NpcProfile(
                branch_id=branch_id,
                id=npc_id,
                name=npc_id,
                lod=2,
                created_at=100.25,
            )
            for npc_id in ids
        )
        db.add_all(
            NpcHealth(
                id=id_offset + index,
                branch_id=branch_id,
                npc_id=row.npc_id,
                category=row.category,
                code=row.code,
                label="伤处",
                severity=row.severity,
                active=row.active,
                hidden=row.hidden,
                descriptors='["伤处"]',
                trigger_conditions='["伤处疼"]',
                notes=row.notes,
                created_at_tick=row.created_at_tick,
                created_at=123.5,
            )
            for index, row in enumerate(rows, start=1)
        )


async def _health_rows(db, branch_id: str = "main") -> list[dict[str, Any]]:
    result = await db.execute(
        select(NpcHealth.__table__)
        .where(NpcHealth.branch_id == branch_id)
        .order_by(NpcHealth.npc_id, NpcHealth.code)
    )
    return [dict(row) for row in result.mappings()]


async def test_A1_enqueue_drain_flush_changes_persisted_health_without_changing_lod(store, session):
    from sim.content.health_evolve import DailyHealthEvolution, load_health_snapshot

    await _persist_rows(store, (_row(hidden=True, notes="seed:injury"),))
    loop = _loop()
    evolve = DailyHealthEvolution(
        loop, await load_health_snapshot(store.session_factory, branch_id="main")
    )
    _set_day(loop, 2)

    assert evolve(2) is None
    assert len(loop.pending_events) == 1
    assert (await session.scalar(select(NpcHealth))).severity == 0.2
    events = loop.drain_events()
    assert [event.event_type for event in events] == [EventKind.NPC_HEALTH_CHANGED]
    await NpcStore(store).flush_tick(events)
    session.expire_all()
    row = await session.scalar(select(NpcHealth))
    assert (row.severity, row.active, row.hidden, row.notes) == (0.15, True, True, "seed:injury")
    assert (row.created_at_tick, row.created_at, row.label) == (0, 123.5, "伤处")
    assert (await session.scalar(select(NpcProfile))).lod == 2


@pytest.mark.parametrize(
    ("category", "severity", "expected"),
    [
        ("old_injury", 0.2, 0.15),
        ("disease", 0.95, 1.0),
        ("addiction", 0.2, 0.22),
        ("disability", 0.4, None),
        ("trauma", 0.2, 0.18),
    ],
)
def test_A2_A3_five_categories_follow_daily_rates(category, severity, expected):
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=2)
    evolve = DailyHealthEvolution(
        loop, _snapshot((_row(category=category, severity=severity),)), baseline_day=1
    )
    evolve(2)
    if expected is None:
        assert loop.pending_events == []
    else:
        assert len(loop.pending_events) == 1
        assert loop.pending_events[0].payload["severity"] == expected
        assert loop.pending_events[0].payload["active"] is True


@pytest.mark.parametrize(("category", "days"), [("old_injury", 4), ("trauma", 10)])
def test_A2_healing_reaches_exact_zero_once_and_never_reactivates(category, days):
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=days + 2)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(category=category),)), baseline_day=1)
    evolve(days + 1)
    events = loop.drain_events()
    assert len(events) == days
    assert events[-1].payload["severity"] == 0.0
    assert events[-1].payload["active"] is False
    assert sum(event.payload["active"] is False for event in events) == 1
    evolve(days + 1)
    evolve(days + 2)
    assert loop.pending_events == []


@pytest.mark.parametrize("category", ["old_injury", "trauma"])
def test_A2_active_zero_healing_row_deactivates_once(category):
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=3)
    evolve = DailyHealthEvolution(
        loop, _snapshot((_row(category=category, severity=0.0),)), baseline_day=1
    )
    evolve(3)
    assert len(loop.pending_events) == 1
    assert loop.pending_events[0].payload["active"] is False


@pytest.mark.parametrize("category", ["disease", "addiction"])
def test_A3_worsening_saturates_without_repeated_events_or_incapacitation(category):
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=5)
    evolve = DailyHealthEvolution(
        loop, _snapshot((_row(category=category, severity=0.99),)), baseline_day=1
    )
    evolve(5)
    assert len(loop.pending_events) == 1
    assert loop.pending_events[0].payload["severity"] == 1.0
    assert loop.pending_events[0].payload["active"] is True
    assert loop.pending_events[0].event_type is EventKind.NPC_HEALTH_CHANGED
    assert loop.state.entities["chenmo"].incapacitated_until is None


def test_A2_inactive_rows_stay_inactive_even_when_severity_is_positive():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=4)
    evolve = DailyHealthEvolution(
        loop, _snapshot((_row(category="disease", severity=0.5, active=False),)), baseline_day=1
    )
    evolve(4)
    assert loop.pending_events == []
    assert evolve.last_day == 4


def test_A9_unflushed_days_use_the_previous_days_new_severity():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=4)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(),)), baseline_day=1)
    for day in (2, 3, 4, 4, 2):
        evolve(day)
    assert [event.payload["severity"] for event in loop.pending_events] == [0.15, 0.1, 0.05]
    assert all(event.tick == 3 * TICKS_PER_GAME_DAY for event in loop.pending_events)
    assert evolve.last_day == 4


def test_A9_skipped_callback_days_are_evolved_in_order():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=4)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(),)), baseline_day=1)
    evolve(4)
    assert [event.payload["severity"] for event in loop.pending_events] == [0.15, 0.1, 0.05]


@pytest.mark.parametrize(
    ("created_at_tick", "expected"),
    [
        (TICKS_PER_GAME_DAY, [0.15, 0.1, 0.05]),
        (TICKS_PER_GAME_DAY + 1, [0.15, 0.1]),
        (2 * TICKS_PER_GAME_DAY + 1, [0.15]),
        (3 * TICKS_PER_GAME_DAY + 1, []),
    ],
)
def test_A9_new_injury_is_never_evolved_before_its_creation_boundary(created_at_tick, expected):
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=4)
    evolve = DailyHealthEvolution(
        loop, _snapshot((_row(created_at_tick=created_at_tick),)), baseline_day=1
    )
    evolve(4)
    assert [event.payload["severity"] for event in loop.pending_events] == expected


def test_A10_default_baseline_does_not_catch_up_old_days():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=4)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(),)))
    evolve(4)
    assert loop.pending_events == []
    assert evolve.last_day == 4
    _set_day(loop, 5)
    evolve(5)
    assert loop.pending_events[0].payload["severity"] == 0.15


def test_A10_refresh_replaces_values_without_consuming_the_pending_day():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=2)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(),)), baseline_day=1)
    evolve.refresh(_snapshot((_row(severity=0.7, hidden=True, notes="collapse_injury"),)))
    assert evolve.last_day == 1
    evolve(2)
    assert loop.pending_events[0].payload == {
        "npc_id": "chenmo",
        "category": "old_injury",
        "code": "wrist",
        "severity": 0.65,
        "active": True,
        "hidden": True,
        "notes": "collapse_injury",
    }


def test_A10_refresh_rejects_another_branch_without_changing_the_current_snapshot():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=2)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(),)), baseline_day=1)
    with pytest.raises(ValueError):
        evolve.refresh(_snapshot((_row(severity=0.9),), branch_id="child"))
    evolve(2)
    assert evolve.branch_id == "main"
    assert loop.pending_events[0].payload["severity"] == 0.15


def test_A10_reset_can_move_to_an_earlier_day_and_another_branch():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=4)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(),)))
    evolve.reset(_snapshot((_row(severity=0.6),), branch_id="child"), baseline_day=1)
    _set_day(loop, 2)
    evolve(2)
    assert (evolve.branch_id, evolve.last_day) == ("child", 2)
    assert loop.pending_events[0].branch_id == "child"
    assert loop.pending_events[0].payload["severity"] == 0.55


def test_A10_future_day_is_rejected_before_any_event_is_queued():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=2)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(),)), baseline_day=1)
    with pytest.raises(ValueError):
        evolve(3)
    assert loop.pending_events == []
    assert evolve.last_day == 1


@pytest.mark.parametrize(
    ("has_profile", "has_entity"), [(False, True), (True, False), (False, False)]
)
def test_A4_both_profile_and_live_entity_are_required(has_profile, has_entity):
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=2, npc_ids=("chenmo",) if has_entity else ())
    snapshot = _snapshot(
        (_row(),), profile_ids=frozenset({"chenmo"}) if has_profile else frozenset()
    )
    DailyHealthEvolution(loop, snapshot, baseline_day=1)(2)
    assert loop.pending_events == []


def test_A4_profile_without_health_rows_never_creates_a_health_record():
    from sim.content.health_evolve import DailyHealthEvolution

    loop = _loop(day=2)
    snapshot = _snapshot((), profile_ids=frozenset({"chenmo"}))
    DailyHealthEvolution(loop, snapshot, baseline_day=1)(2)
    assert loop.pending_events == []


async def test_A4_loader_excludes_orphans_and_other_branch_profiles_but_keeps_inactive_rows(store):
    from sim.content.health_evolve import load_health_snapshot

    await _persist_rows(
        store,
        (
            _row(npc_id="visible", hidden=False),
            _row(npc_id="quiet", active=False),
            _row(npc_id="ghost"),
        ),
        profile_ids=("visible", "quiet", "without_health"),
    )
    await _persist_rows(
        store, (_row(npc_id="ghost", severity=0.8),), branch_id="child", id_offset=100
    )
    main = await load_health_snapshot(store.session_factory, branch_id="main")
    child = await load_health_snapshot(store.session_factory, branch_id="child")
    assert main.branch_id == "main"
    assert main.profile_ids == frozenset({"visible", "quiet", "without_health"})
    assert [(row.npc_id, row.active, row.hidden) for row in main.rows] == [
        ("quiet", False, False),
        ("visible", True, False),
    ]
    assert [(row.npc_id, row.severity) for row in child.rows] == [("ghost", 0.8)]
    assert all(type(row).__name__ == "HealthRow" for row in (*main.rows, *child.rows))


async def test_A4_pending_death_does_not_receive_health_after_death_and_flush_succeeds(
    store, session
):
    from sim.content.health_evolve import DailyHealthEvolution, load_health_snapshot

    await _persist_rows(store, (_row(),))
    loop = _loop(day=2)
    evolve = DailyHealthEvolution(
        loop,
        await load_health_snapshot(store.session_factory, branch_id="main"),
        baseline_day=1,
    )
    loop.enqueue(npc_death_event(loop.state.tick, entity_id="chenmo"))
    evolve(2)
    events = loop.drain_events()
    assert [event.event_type for event in events] == [EventKind.NPC_DEATH]
    await NpcStore(store).flush_tick(events)
    assert (await session.scalars(select(NpcProfile))).all() == []
    assert (await session.scalars(select(NpcHealth))).all() == []


async def test_A4_projected_death_is_filtered_even_if_world_entities_are_stale(store):
    from sim.content.health_evolve import DailyHealthEvolution, load_health_snapshot

    await _persist_rows(store, (_row(),))
    await NpcStore(store).flush_tick([npc_death_event(1, entity_id="chenmo")])
    snapshot = await load_health_snapshot(store.session_factory, branch_id="main")
    assert snapshot.rows == ()
    assert snapshot.profile_ids == frozenset()
    loop = _loop(day=2)
    DailyHealthEvolution(loop, snapshot, baseline_day=1)(2)
    assert loop.pending_events == []


def test_A5_event_sequence_is_ordered_deterministic_and_contains_only_health_fields():
    from sim.content.health_evolve import DailyHealthEvolution

    rows = (_row(npc_id="z", code="alpha"), _row(npc_id="a", code="beta"), _row(npc_id="a"))
    results = []
    for order in (rows, tuple(reversed(rows))):
        loop = _loop(day=3, npc_ids=("z", "a"))
        DailyHealthEvolution(loop, _snapshot(order), baseline_day=1)(3)
        results.append(loop.drain_events())
    assert results[0] == results[1]
    assert [(event.payload["npc_id"], event.payload["code"]) for event in results[0]] == [
        ("a", "beta"),
        ("a", "wrist"),
        ("z", "alpha"),
        ("a", "beta"),
        ("a", "wrist"),
        ("z", "alpha"),
    ]
    assert all(event.tick == 2 * TICKS_PER_GAME_DAY for event in results[0])
    assert all(
        set(event.payload)
        == {"npc_id", "category", "code", "severity", "active", "hidden", "notes"}
        for event in results[0]
    )


async def test_A6_normal_projection_and_direct_replay_match_every_persisted_column(store):
    from sim.content.health_evolve import DailyHealthEvolution, load_health_snapshot

    await _persist_rows(
        store,
        (_row(hidden=True, notes="seed:old"), _row(code="fever", category="disease", severity=0.8)),
    )
    async with store.session_factory() as db:
        initial = await _health_rows(db)
    loop = _loop(day=3)
    DailyHealthEvolution(
        loop,
        await load_health_snapshot(store.session_factory, branch_id="main"),
        baseline_day=1,
    )(3)
    events = loop.drain_events()
    await NpcStore(store).flush_tick(events)
    async with store.session_factory() as db:
        projected = await _health_rows(db)
    # 重建同一份完整初值，包括 id/created_at；共享临时库足够，无需另声明 engine。
    async with store.session_factory.begin() as db:
        await db.execute(delete(NpcHealth))
        await db.execute(insert(NpcHealth), initial)
        for event in events:
            await _project_health(db, "main", event)
        replayed = await _health_rows(db)
    assert projected == replayed
    assert [row["severity"] for row in replayed] == [1.0, 0.1]
    assert all(row["created_at"] == 123.5 for row in replayed)


@pytest.mark.parametrize(
    "bad_fields",
    [
        {"code": None},
        {"code": 123},
        {"category": "unknown"},
        {"severity": float("nan")},
        {"severity": float("inf")},
        {"severity": -0.1},
        {"severity": 1.1},
        {"severity": "broken"},
        {"active": "true"},
        {"hidden": "false"},
        {"notes": "不能把隐藏叙事写回事件"},
        {"created_at_tick": True},
        {"created_at_tick": -1},
        {"created_at_tick": "broken"},
    ],
)
def test_A10_bad_npc_data_is_isolated_without_blocking_other_npcs(bad_fields):
    from sim.content.health_evolve import DailyHealthEvolution

    rows = (
        replace(_row(npc_id="bad", code="a"), **bad_fields),
        _row(npc_id="bad", code="z"),
        _row(npc_id="good"),
    )
    loop = _loop(day=2, npc_ids=("bad", "good"))
    evolve = DailyHealthEvolution(loop, _snapshot(rows), baseline_day=1)
    evolve(2)
    assert [
        (event.payload["npc_id"], event.payload["severity"]) for event in loop.pending_events
    ] == [("good", 0.15)]
    assert evolve.last_day == 2


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, TypeError])
def test_A10_enqueue_failures_propagate_instead_of_being_treated_as_bad_npc_data(
    monkeypatch, error_type
):
    from sim.content.health_evolve import DailyHealthEvolution

    def broken_enqueue(_event):
        raise error_type("queue unavailable")

    loop = _loop(day=2)
    evolve = DailyHealthEvolution(loop, _snapshot((_row(),)), baseline_day=1)
    monkeypatch.setattr(loop, "enqueue", broken_enqueue)
    with pytest.raises(error_type, match="queue unavailable"):
        evolve(2)
    assert evolve.last_day == 1


def test_A10_callback_is_synchronous_without_loading_or_sampling_wall_time(monkeypatch):
    from sim.content import health_evolve

    def forbidden(*_args, **_kwargs):
        raise AssertionError("synchronous day callback attempted I/O or wall time")

    loop = _loop(day=2)
    evolve = health_evolve.DailyHealthEvolution(loop, _snapshot((_row(),)), baseline_day=1)
    monkeypatch.setattr(health_evolve, "load_health_snapshot", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    assert not inspect.iscoroutinefunction(evolve.__call__)
    result = evolve(2)
    assert result is None
    assert not inspect.isawaitable(result)
    assert loop.pending_events[0].payload["severity"] == 0.15
