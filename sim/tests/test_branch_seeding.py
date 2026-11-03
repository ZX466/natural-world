"""第二十轮 B：分支内补种，合法死亡不复活，祖先未来不越界。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import event, select, update

from sim.content.animals import seed_animals
from sim.content.protagonist import _profile_row as protagonist_row
from sim.content.protagonist import seed_protagonist
from sim.content.villagers import _profile_row as villager_row
from sim.content.villagers import build_roster, seed_villagers
from sim.core.events import npc_death_event, world_create_event
from sim.core.persistence.models import Branch, Event, NpcProfile
from sim.core.persistence.npc_store import NpcStore
from sim.npc.model import NpcProfileData


async def _insert_villagers(store, *, main_count: int, child_count: int) -> None:
    async with store.session_factory() as session:
        for branch_id, count in (("main", main_count), ("child", child_count)):
            for profile in build_roster()[:count]:
                row = villager_row(profile)
                row["branch_id"] = branch_id
                session.add(NpcProfile(**row))
        await session.commit()


async def _counts(store) -> tuple[int, int]:
    async with store.session_factory() as session:
        branches = (await session.scalars(select(NpcProfile.branch_id))).all()
    return branches.count("main"), branches.count("child")


async def _make_child(store, *, cutoff: int) -> None:
    async with store.session_factory() as session:
        session.add(Branch(id="child", forked_from_branch="main", forked_from_seq=cutoff))
        await session.commit()


@pytest.mark.parametrize(
    ("main_count", "child_count", "added", "expected"),
    [
        (0, 0, 50, (50, 0)),
        (0, 50, 50, (50, 50)),
        (0, 49, 50, (50, 49)),
        (50, 49, 0, (50, 49)),
        (50, 50, 0, (50, 50)),
    ],
    ids=["B1-empty", "B2-child-full", "B3-child-partial", "B4-main-full", "B5-both-full"],
)
async def test_default_main_uses_only_its_own_ids(store, main_count, child_count, added, expected):
    await _insert_villagers(store, main_count=main_count, child_count=child_count)

    actual_added = await seed_villagers(store.session_factory)
    actual_counts = await _counts(store)
    print(
        f"target=main before={(main_count, child_count)} added={actual_added} after={actual_counts}"
    )
    assert (actual_added, actual_counts) == (added, expected)
    assert await seed_villagers(store.session_factory) == 0
    assert await _counts(store) == expected


@pytest.mark.parametrize(
    ("main_count", "child_count", "added", "expected"),
    [
        (0, 0, 50, (0, 50)),
        (0, 50, 0, (0, 50)),
        (0, 49, 1, (0, 50)),
        (50, 49, 1, (50, 50)),
        (50, 50, 0, (50, 50)),
    ],
    ids=["B1-empty", "B2-child-full", "B3-child-partial", "B4-main-full", "B5-both-full"],
)
async def test_explicit_child_fills_only_child(store, main_count, child_count, added, expected):
    await _insert_villagers(store, main_count=main_count, child_count=child_count)

    actual_added = await seed_villagers(store.session_factory, branch_id="child")
    actual_counts = await _counts(store)
    print(
        f"target=child before={(main_count, child_count)} "
        f"added={actual_added} after={actual_counts}"
    )
    assert (actual_added, actual_counts) == (added, expected)
    assert await seed_villagers(store.session_factory, branch_id="child") == 0
    assert await _counts(store) == expected


@pytest.mark.parametrize(
    ("seed", "npc_id", "total"),
    [
        (seed_villagers, "villager_01", 50),
        (seed_protagonist, "chenmo", 1),
        (seed_animals, "cat_grey", 3),
    ],
    ids=["villagers", "protagonist", "animals"],
)
async def test_same_ids_can_exist_in_both_branches_and_each_seed_is_idempotent(
    store, seed, npc_id, total
):
    assert await seed(store.session_factory) == total
    assert await seed(store.session_factory, branch_id="child") == total
    assert await seed(store.session_factory) == 0
    assert await seed(store.session_factory, branch_id="child") == 0
    assert await _counts(store) == (total, total)
    async with store.session_factory() as session:
        branches = (
            await session.scalars(
                select(NpcProfile.branch_id)
                .where(NpcProfile.id == npc_id)
                .order_by(NpcProfile.branch_id)
            )
        ).all()
    assert branches == ["child", "main"]


@pytest.mark.parametrize("branch_id", ["main", "child"])
@pytest.mark.parametrize(
    ("seed", "npc_id", "remaining"),
    [
        (seed_villagers, "villager_01", 49),
        (seed_protagonist, "chenmo", 0),
        (seed_animals, "cat_grey", 2),
    ],
    ids=["villagers", "protagonist", "animals"],
)
async def test_standalone_seed_does_not_resurrect_local_death(
    store, seed, npc_id, remaining, branch_id
):
    await seed(store.session_factory)
    if branch_id == "child":
        async with store.session_factory() as session:
            await session.execute(update(NpcProfile).values(branch_id="child"))
            await session.commit()
    await NpcStore(store, branch_id=branch_id).flush_tick(
        [npc_death_event(1, entity_id=npc_id, branch_id=branch_id)]
    )
    kwargs = {} if branch_id == "main" else {"branch_id": "child"}
    expected_counts = (remaining, 0) if branch_id == "main" else (0, remaining)
    assert await _counts(store) == expected_counts

    assert await seed(store.session_factory, **kwargs) == 0
    assert await _counts(store) == expected_counts
    async with store.session_factory() as session:
        assert await session.get(NpcProfile, {"branch_id": branch_id, "id": npc_id}) is None


@pytest.mark.parametrize("precomputed", [False, True], ids=["standalone", "shared-history"])
@pytest.mark.parametrize(
    ("seed", "npc_id", "remaining"),
    [
        (seed_villagers, "villager_01", 49),
        (seed_protagonist, "chenmo", 0),
        (seed_animals, "cat_grey", 2),
    ],
    ids=["villagers", "protagonist", "animals"],
)
async def test_ancestor_death_before_cutoff_is_not_resurrected(
    store, seed, npc_id, remaining, precomputed
):
    await seed(store.session_factory)
    await NpcStore(store).flush_tick([npc_death_event(1, entity_id=npc_id)])
    assert await _counts(store) == (remaining, 0)
    await _make_child(store, cutoff=1)
    kwargs = {}
    if precomputed:
        from sim.content.seeding import death_ids_from_history

        kwargs["dead_ids"] = death_ids_from_history(await store.read_branch_history("child"))

    assert await seed(store.session_factory, branch_id="child", **kwargs) == remaining
    assert await seed(store.session_factory, branch_id="child", **kwargs) == 0
    assert await _counts(store) == (remaining, remaining)
    async with store.session_factory() as session:
        assert await session.get(NpcProfile, {"branch_id": "child", "id": npc_id}) is None


@pytest.mark.parametrize("precomputed", [False, True], ids=["standalone", "shared-history"])
@pytest.mark.parametrize(
    ("seed", "npc_id", "remaining", "total"),
    [
        (seed_villagers, "villager_01", 49, 50),
        (seed_protagonist, "chenmo", 0, 1),
        (seed_animals, "cat_grey", 2, 3),
    ],
    ids=["villagers", "protagonist", "animals"],
)
async def test_ancestor_death_after_cutoff_does_not_remove_old_child_life(
    store, seed, npc_id, remaining, total, precomputed
):
    await seed(store.session_factory)
    await store.append("main", [world_create_event(0, 42, (npc_id,)).to_store_dict()])
    # 同 tick 的 seq=2 死亡在 seq=1 锚点之后；只能按有界谱系而非 tick/父 head 读取。
    await NpcStore(store).flush_tick([npc_death_event(0, entity_id=npc_id)])
    assert await _counts(store) == (remaining, 0)
    await _make_child(store, cutoff=1)
    kwargs = {}
    if precomputed:
        from sim.content.seeding import death_ids_from_history

        kwargs["dead_ids"] = death_ids_from_history(await store.read_branch_history("child"))

    assert await seed(store.session_factory, branch_id="child", **kwargs) == total
    assert await _counts(store) == (remaining, total)
    async with store.session_factory() as session:
        row = await session.get(NpcProfile, {"branch_id": "child", "id": npc_id})
        assert row is not None
        assert row.branch_id == "child"


@pytest.mark.parametrize(
    ("dead_ids", "expected"),
    [
        (frozenset(), (50, 1, 3)),
        (frozenset({"villager_01", "chenmo", "cat_grey"}), (49, 0, 2)),
    ],
    ids=["explicit-empty", "explicit-deaths"],
)
async def test_explicit_death_set_is_reused_without_reading_history(
    store, engine, dead_ids, expected
):
    from sim.content.seeding import death_ids_from_history

    await store.append("main", [world_create_event(0, 42, ()).to_store_dict()])
    await NpcStore(store).flush_tick(
        [npc_death_event(1, entity_id=npc_id) for npc_id in sorted(dead_ids)]
    )
    shared = death_ids_from_history(await store.read_branch_history("main"))
    assert shared == dead_ids
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    event.listen(engine.sync_engine, "before_cursor_execute", record_sql)
    try:
        added = (
            await seed_villagers(store.session_factory, dead_ids=shared),
            await seed_protagonist(store.session_factory, dead_ids=shared),
            await seed_animals(store.session_factory, dead_ids=shared),
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_sql)

    assert added == expected
    assert not any("from events" in sql or "from branches" in sql for sql in statements)
    async with store.session_factory() as session:
        assert len((await session.scalars(select(Event))).all()) == 1 + len(dead_ids)


async def test_empty_database_still_seeds_main_without_opening_a_branch(store):
    assert await store.current_branch_id_or_none() is None
    with pytest.raises(ValueError, match="missing branch history"):
        await store.read_branch_history("main")

    assert await seed_villagers(store.session_factory) == 50
    assert await seed_protagonist(store.session_factory) == 1
    assert await seed_animals(store.session_factory) == 3
    assert await _counts(store) == (54, 0)
    assert await store.current_branch_id_or_none() is None
    async with store.session_factory() as session:
        assert (await session.scalars(select(Branch))).all() == []
        assert (await session.scalars(select(Event))).all() == []


@pytest.mark.parametrize(
    ("seed", "npc_id", "remaining"),
    [
        (seed_villagers, "villager_01", 49),
        (seed_protagonist, "chenmo", 0),
        (seed_animals, "cat_grey", 2),
    ],
    ids=["villagers", "protagonist", "animals"],
)
async def test_missing_current_flag_does_not_make_existing_main_deaths_empty(
    store, seed, npc_id, remaining
):
    await seed(store.session_factory)
    await NpcStore(store).flush_tick([npc_death_event(1, entity_id=npc_id)])
    async with store.session_factory() as session:
        await session.execute(update(Branch).values(is_current=False))
        await session.commit()
    assert await store.current_branch_id_or_none() is None

    assert await seed(store.session_factory) == 0
    assert await _counts(store) == (remaining, 0)
    assert await store.current_branch_id_or_none() is None
    from sim.content.seeding import read_branch_death_ids

    assert await read_branch_death_ids(store) == frozenset({npc_id})


@pytest.mark.parametrize(
    ("seed", "npc_id"),
    [
        (seed_villagers, "villager_01"),
        (seed_protagonist, "chenmo"),
        (seed_animals, "cat_grey"),
    ],
    ids=["villagers", "protagonist", "animals"],
)
async def test_orphaned_events_are_not_mistaken_for_an_empty_genesis(store, seed, npc_id):
    async with store.session_factory() as session:
        session.add(
            Event(
                branch_id="main",
                seq=1,
                tick=1,
                event_type="npc.death",
                actor_id="",
                payload=json.dumps({"entity_id": npc_id}),
            )
        )
        await session.commit()
    assert await store.current_branch_id_or_none() is None

    with pytest.raises(ValueError, match="missing branch history"):
        await seed(store.session_factory)
    assert await _counts(store) == (0, 0)


@pytest.mark.parametrize(
    ("parent", "cutoff", "error"),
    [
        ("missing", 1, "missing branch history"),
        ("main", None, "missing branch cutoff"),
        ("child", 1, "cyclic branch history"),
    ],
)
async def test_invalid_existing_lineage_fails_before_writing_profiles(store, parent, cutoff, error):
    async with store.session_factory() as session:
        session.add(Branch(id="child", forked_from_branch=parent, forked_from_seq=cutoff))
        await session.commit()

    with pytest.raises(ValueError, match=error):
        await seed_villagers(store.session_factory, branch_id="child")
    assert await _counts(store) == (0, 0)


def test_readonly_profile_rows_keep_positional_and_zero_argument_calls():
    protagonist = protagonist_row()
    villager = villager_row(NpcProfileData("scholar", "先生", class_register="士绅"))

    assert protagonist["branch_id"] == "main"
    assert json.loads(str(protagonist["knowledge_boundary"])) == {
        "literacy": 0.7,
        "jargon": ["漕运", "行会"],
        "class_register": "平民",
    }
    assert villager["branch_id"] == "main"
    assert json.loads(str(villager["knowledge_boundary"])) == {"class_register": "士绅"}


def test_profile_row_branch_keyword_changes_only_branch():
    profile = NpcProfileData("scholar", "先生", class_register="士绅")
    assert villager_row(profile, branch_id="child") == {
        **villager_row(profile),
        "branch_id": "child",
    }
    assert protagonist_row(branch_id="child") == {**protagonist_row(), "branch_id": "child"}


@pytest.mark.parametrize("branch_id", ["main", "child"])
async def test_animal_species_and_identity_are_kept_in_target_branch(store, branch_id):
    kwargs = {} if branch_id == "main" else {"branch_id": branch_id}
    assert await seed_animals(store.session_factory, **kwargs) == 3
    async with store.session_factory() as session:
        rows = (
            await session.scalars(
                select(NpcProfile).where(NpcProfile.branch_id == branch_id).order_by(NpcProfile.id)
            )
        ).all()
    assert [(row.id, row.species, row.identity_anchor) for row in rows] == [
        ("cat_grey", "cat", "我叫灰。"),
        ("dog_black", "dog", "我叫黑子。"),
        ("raven", "raven", "我叫鸦。"),
    ]
